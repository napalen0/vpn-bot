from __future__ import annotations

import asyncio
import json
import logging
import re
import shlex
from pathlib import Path

import asyncssh

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Server, VpnKey
from app.services.ssh_secret import decrypt_ssh_password

log = logging.getLogger(__name__)

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)


def _deploy_dir() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parents[i] for i in range(2, 6)]:
        d = parent / "deploy"
        if (d / "install_xray_vpnbot.sh").is_file():
            return d
    cwd = Path.cwd() / "deploy"
    if (cwd / "install_xray_vpnbot.sh").is_file():
        return cwd
    raise FileNotFoundError("deploy/install_xray_vpnbot.sh not found (expected vpn-bot/deploy/)")


def _resolved_ssh_password(server: Server | None, password_override: str | None) -> str:
    po = (password_override or "").strip()
    if po:
        return po
    if server is not None and (server.ssh_password_encrypted or "").strip():
        d = decrypt_ssh_password(server.ssh_password_encrypted)
        if d:
            return d.strip()
    return ""


def _connect_kwargs_install(
    *,
    host: str,
    ssh_port: int,
    ssh_user: str,
    password: str | None,
) -> dict:
    """Initial Xray install (no Server row with password in DB yet)."""
    kw: dict = {
        "host": host,
        "port": ssh_port,
        "username": ssh_user,
        "known_hosts": None,
    }
    settings = get_settings()
    key_path = (settings.xray_sync_ssh_private_key_path or "").strip()
    p = (password or "").strip() or settings.xray_sync_ssh_password.strip()
    if p:
        kw["password"] = p
    elif key_path:
        kw["client_keys"] = [key_path]
    else:
        raise ValueError(
            "SSH password required in form, or set XRAY_SYNC_SSH_PRIVATE_KEY_PATH / XRAY_SYNC_SSH_PASSWORD in .env"
        )
    return kw


def _connect_kwargs_server(server: Server, password_override: str | None = None) -> dict:
    if not (server.ssh_user or "").strip():
        raise ValueError("Server has no ssh_user configured")
    kw: dict = {
        "host": server.host,
        "port": int(server.ssh_port or 22),
        "username": server.ssh_user.strip(),
        "known_hosts": None,
    }
    settings = get_settings()
    key_path = (settings.xray_sync_ssh_private_key_path or "").strip()
    p = _resolved_ssh_password(server, password_override)
    if p:
        kw["password"] = p
    elif key_path:
        kw["client_keys"] = [key_path]
    else:
        raise ValueError(
            "Server SSH password required in DB (SSH card) or set XRAY_SYNC_SSH_PRIVATE_KEY_PATH in .env"
        )
    return kw


def can_ssh_to_server(server: Server, password_override: str | None = None) -> bool:
    if _resolved_ssh_password(server, password_override):
        return True
    return bool((get_settings().xray_sync_ssh_private_key_path or "").strip())


async def _run_as_root(
    conn: asyncssh.SSHClientConnection,
    shell_command: str,
    sudo_password: str | None,
) -> asyncssh.SSHCompletedProcess:
    """Run command as root: already root via SSH, sudo -S (form password), or sudo -n."""
    id_r = await conn.run("id -u", check=False)
    uid = (id_r.stdout or "").strip()
    if uid == "0":
        return await conn.run(shell_command, check=False)

    pwd = (sudo_password or "").strip()
    if pwd:
        wrapped = "sudo -S sh -c " + shlex.quote(shell_command)
        return await conn.run(wrapped, check=False, input=pwd + "\n")

    wrapped = "sudo -n sh -c " + shlex.quote(shell_command)
    r = await conn.run(wrapped, check=False)
    if r.exit_status != 0:
        err = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
        raise RuntimeError(
            "Not root: provide SSH password in provisioning form (for sudo -S), "
            "or configure NOPASSWD in /etc/sudoers, or SSH as root.\n"
            + err[-1500:]
        )
    return r


def _parse_vpnbot_json(stdout: str) -> dict:
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("VPNBOT_JSON:"):
            return json.loads(line[len("VPNBOT_JSON:") :].strip())
    raise ValueError("VPNBOT_JSON not found in output — installation did not complete normally.")


async def provision_xray_via_ssh(
    *,
    host: str,
    ssh_port: int = 22,
    ssh_user: str,
    ssh_password: str | None,
    sudo_password: str | None = None,
    reality_sni: str = "www.microsoft.com",  # default project masking domain
    reality_dest: str = "www.microsoft.com:443",
    vless_port: int = 8443,
) -> dict:
    """Upload script via SFTP and run as root (sudo -S with form password or already root)."""
    d = _deploy_dir()
    install = d / "install_xray_vpnbot.sh"
    script = install.read_text(encoding="utf-8")

    env_assign = " ".join(
        [
            f"REALITY_SNI={shlex.quote(reality_sni)}",
            f"REALITY_DEST={shlex.quote(reality_dest)}",
            f"VLESS_PORT={shlex.quote(str(vless_port))}",
        ]
    )
    remote_sh = "/tmp/vpnbot_install_xray.sh"
    inner = f"env {env_assign} bash {remote_sh}"

    settings = get_settings()
    sudo_actual = (sudo_password or ssh_password or "").strip() or None
    if not sudo_actual and (settings.xray_sync_ssh_password or "").strip():
        sudo_actual = settings.xray_sync_ssh_password.strip()

    async with asyncssh.connect(
        **_connect_kwargs_install(host=host, ssh_port=ssh_port, ssh_user=ssh_user, password=ssh_password)
    ) as conn:
        async with conn.start_sftp_client() as sftp:
            async with sftp.open(remote_sh, "w") as f:
                # asyncssh encodes str internally; passing bytes is not supported
                await f.write(script)
        chmod = await conn.run(f"chmod +x {remote_sh}", check=False)
        if chmod.exit_status != 0:
            raise RuntimeError(chmod.stderr or chmod.stdout or "chmod failed")
        run = await _run_as_root(conn, inner, sudo_actual)
        out = (run.stdout or "") + "\n" + (run.stderr or "")
        if run.exit_status != 0:
            log.error("xray install remote log:\n%s", out)
            raise RuntimeError(f"Server installation exited with code {run.exit_status}. Log: {out[-2000:]}")
        return _parse_vpnbot_json(out)


async def push_vless_client_uuid(
    *,
    server: Server,
    uuid: str,
    ssh_password: str | None = None,
) -> None:
    if not _UUID_RE.match(uuid):
        raise ValueError("Invalid UUID")
    if not server.ssh_user:
        raise ValueError("Server has no ssh_user configured (set during provisioning or in DB)")

    d = _deploy_dir()
    add_script = (d / "remote_add_vless_client.sh").read_text(encoding="utf-8")
    remote_sh = "/tmp/vpnbot_add_client.sh"
    tag = shlex.quote(server.inbound_tag or "vless-reality")

    settings = get_settings()
    sudo_pwd = _resolved_ssh_password(server, ssh_password) or None

    async with asyncssh.connect(**_connect_kwargs_server(server, ssh_password)) as conn:
        async with conn.start_sftp_client() as sftp:
            async with sftp.open(remote_sh, "w") as f:
                await f.write(add_script)
        uq = shlex.quote(uuid)
        cfg = shlex.quote("/usr/local/etc/xray/config.json")
        chmod_r = await conn.run(f"chmod +x {remote_sh}", check=False)
        if chmod_r.exit_status != 0:
            raise RuntimeError(chmod_r.stderr or chmod_r.stdout or "chmod failed")
        inner = f"bash {remote_sh} {uq} {cfg} {tag}"
        run = await _run_as_root(conn, inner, sudo_pwd)
        out = (run.stdout or "") + (run.stderr or "")
        if run.exit_status != 0:
            raise RuntimeError(out[-1500:] or f"push client {uuid} failed")
        if "OK:" not in out:
            log.warning("xray ssh: client %s added, but script did not return OK (ignoring)", uuid)

async def rebuild_reality_mask_on_server(
    *,
    server: Server,
    ssh_password: str | None = None,
    reality_sni: str = "www.microsoft.com",
    reality_dest: str = "www.microsoft.com:443",
) -> None:
    """Only dest/serverNames in Reality inbound; privateKey, shortIds and clients unchanged."""
    if not server.ssh_user:
        raise ValueError("Server has no ssh_user configured")

    d = _deploy_dir()
    path_script = d / "remote_set_reality_dest.sh"
    if not path_script.is_file():
        raise FileNotFoundError(str(path_script))
    script = path_script.read_text(encoding="utf-8")
    remote_sh = "/tmp/vpnbot_set_reality.sh"
    tag = shlex.quote(server.inbound_tag or "vless-reality")
    cfg = shlex.quote("/usr/local/etc/xray/config.json")
    sn = shlex.quote((reality_sni or "").strip() or "www.microsoft.com")
    de = shlex.quote((reality_dest or "").strip() or "www.microsoft.com:443")

    sudo_pwd = _resolved_ssh_password(server, ssh_password) or None

    async with asyncssh.connect(**_connect_kwargs_server(server, ssh_password)) as conn:
        async with conn.start_sftp_client() as sftp:
            async with sftp.open(remote_sh, "w") as f:
                await f.write(script)
        chmod_r = await conn.run(f"chmod +x {remote_sh}", check=False)
        if chmod_r.exit_status != 0:
            raise RuntimeError(chmod_r.stderr or chmod_r.stdout or "chmod failed")
        inner = f"bash {remote_sh} {sn} {de} {cfg} {tag}"
        run = await _run_as_root(conn, inner, sudo_pwd)
        out = (run.stdout or "") + "\n" + (run.stderr or "")
        if run.exit_status != 0:
            raise RuntimeError(out[-2000:] or "command failed")
        if "OK:" not in out:
            log.warning("xray ssh: command executed, but no OK (ignoring)")


async def apply_inbound_port_via_ssh(
    *,
    server: Server,
    port: int,
    ssh_password: str | None = None,
) -> None:
    """Inbound port in config.json + chmod + ufw/firewalld + restart xray."""
    if not server.ssh_user:
        raise ValueError("Server has no ssh_user configured")

    d = _deploy_dir()
    path_script = d / "remote_apply_inbound_port.sh"
    if not path_script.is_file():
        raise FileNotFoundError(str(path_script))
    script = path_script.read_text(encoding="utf-8")
    remote_sh = "/tmp/vpnbot_apply_port.sh"
    tag = shlex.quote(server.inbound_tag or "vless-reality")
    cfg = shlex.quote("/usr/local/etc/xray/config.json")
    p = shlex.quote(str(int(port)))

    sudo_pwd = _resolved_ssh_password(server, ssh_password) or None

    async with asyncssh.connect(**_connect_kwargs_server(server, ssh_password)) as conn:
        async with conn.start_sftp_client() as sftp:
            async with sftp.open(remote_sh, "w") as f:
                await f.write(script)
        chmod_r = await conn.run(f"chmod +x {remote_sh}", check=False)
        if chmod_r.exit_status != 0:
            raise RuntimeError(chmod_r.stderr or chmod_r.stdout or "chmod failed")
        inner = f"bash {remote_sh} {p} {cfg} {tag}"
        run = await _run_as_root(conn, inner, sudo_pwd)
        out = (run.stdout or "") + "\n" + (run.stderr or "")
        if run.exit_status != 0:
            raise RuntimeError(out[-2000:] or "command failed")
        if "OK:" not in out:
            log.warning("xray ssh: command executed, but no OK (ignoring)")


async def push_all_vless_uuids_to_server(
    *,
    server: Server,
    uuids: list[str],
    ssh_password: str | None = None,
) -> None:
    """Add all given UUIDs to the inbound (deduplicated), single xray restart."""
    if not server.ssh_user:
        raise ValueError("Server has no ssh_user configured")

    clean: list[str] = []
    for u in uuids:
        u = (u or "").strip()
        if _UUID_RE.match(u):
            clean.append(u)
    if not clean:
        raise ValueError("No valid UUIDs to push to Xray")

    d = _deploy_dir()
    path_script = d / "remote_bulk_add_vless_clients.sh"
    if not path_script.is_file():
        raise FileNotFoundError(str(path_script))
    script = path_script.read_text(encoding="utf-8")
    remote_sh = "/tmp/vpnbot_bulk_clients.sh"
    cfg = shlex.quote("/usr/local/etc/xray/config.json")
    tag = shlex.quote(server.inbound_tag or "vless-reality")
    uq = " ".join(shlex.quote(u) for u in clean)

    sudo_pwd = _resolved_ssh_password(server, ssh_password) or None

    async with asyncssh.connect(**_connect_kwargs_server(server, ssh_password)) as conn:
        async with conn.start_sftp_client() as sftp:
            async with sftp.open(remote_sh, "w") as f:
                await f.write(script)
        chmod_r = await conn.run(f"chmod +x {remote_sh}", check=False)
        if chmod_r.exit_status != 0:
            raise RuntimeError(chmod_r.stderr or chmod_r.stdout or "chmod failed")
        inner = f"bash {remote_sh} {cfg} {tag} {uq}"
        run = await _run_as_root(conn, inner, sudo_pwd)
        out = (run.stdout or "") + "\n" + (run.stderr or "")
        if run.exit_status != 0 or "OK:bulk_added" not in out:
            raise RuntimeError(out[-2000:] or "bulk push clients failed")


async def remove_xray_vpnbot_via_ssh(
    *,
    server: Server,
    ssh_password: str | None = None,
) -> None:
    """Stop xray, disable unit, remove config.json on the node."""
    if not server.ssh_user:
        raise ValueError("Server has no ssh_user configured")

    d = _deploy_dir()
    path_script = d / "remote_remove_xray_vpnbot.sh"
    if not path_script.is_file():
        raise FileNotFoundError(str(path_script))
    script = path_script.read_text(encoding="utf-8")
    remote_sh = "/tmp/vpnbot_remove_xray.sh"
    cfg = shlex.quote("/usr/local/etc/xray/config.json")

    sudo_pwd = _resolved_ssh_password(server, ssh_password) or None

    async with asyncssh.connect(**_connect_kwargs_server(server, ssh_password)) as conn:
        async with conn.start_sftp_client() as sftp:
            async with sftp.open(remote_sh, "w") as f:
                await f.write(script)
        chmod_r = await conn.run(f"chmod +x {remote_sh}", check=False)
        if chmod_r.exit_status != 0:
            raise RuntimeError(chmod_r.stderr or chmod_r.stdout or "chmod failed")
        inner = f"bash {remote_sh} {cfg}"
        run = await _run_as_root(conn, inner, sudo_pwd)
        out = (run.stdout or "") + "\n" + (run.stderr or "")
        if run.exit_status != 0 or "OK:removed" not in out:
            raise RuntimeError(out[-2000:] or "remove xray on server failed")


async def remove_vless_client_uuid(
    *,
    server: Server,
    uuid: str,
    ssh_password: str | None = None,
) -> None:
    if not _UUID_RE.match(uuid):
        raise ValueError("Invalid UUID")
    if not server.ssh_user:
        raise ValueError("Server has no ssh_user configured (set during provisioning or in DB)")

    d = _deploy_dir()
    rm_script = (d / "remote_remove_vless_client.sh").read_text(encoding="utf-8")
    remote_sh = "/tmp/vpnbot_remove_client.sh"
    tag = shlex.quote(server.inbound_tag or "vless-reality")
    sudo_pwd = _resolved_ssh_password(server, ssh_password) or None

    async with asyncssh.connect(**_connect_kwargs_server(server, ssh_password)) as conn:
        async with conn.start_sftp_client() as sftp:
            async with sftp.open(remote_sh, "w") as f:
                await f.write(rm_script)
        uq = shlex.quote(uuid)
        cfg = shlex.quote("/usr/local/etc/xray/config.json")
        chmod_r = await conn.run(f"chmod +x {remote_sh}", check=False)
        if chmod_r.exit_status != 0:
            raise RuntimeError(chmod_r.stderr or chmod_r.stdout or "chmod failed")
        inner = f"bash {remote_sh} {uq} {cfg} {tag}"
        run = await _run_as_root(conn, inner, sudo_pwd)
        out = (run.stdout or "") + (run.stderr or "")
        if run.exit_status != 0:
            raise RuntimeError(out[-1500:] or f"remove client {uuid} failed")
        if "OK:" not in out:
            log.warning("xray ssh: command executed, but no OK (ignoring)")


async def try_remove_vless_client_from_xray(server: Server, uuid: str) -> None:
    """Remove UUID from Xray; silently skip if no ssh_user or SSH creds (like try_push)."""
    if not server.ssh_user:
        return
    if not can_ssh_to_server(server, None):
        log.warning(
            "xray ssh: no SSH credentials to remove client from %s (password in DB or XRAY_SYNC_SSH_PRIVATE_KEY_PATH)",
            server.host,
        )
        return
    try:
        await remove_vless_client_uuid(server=server, uuid=uuid.strip(), ssh_password=None)
        log.info("xray ssh: removed client %s from %s", uuid, server.host)
    except Exception as e:
        log.warning("xray ssh: failed to remove UUID from %s: %s", server.host, e)


async def try_remove_vless_clients_for_keys(session: AsyncSession, keys: list[VpnKey]) -> None:
    """One SSH call per (server_id, uuid) pair; pool uses one UUID across multiple servers."""
    seen: set[tuple[int, str]] = set()
    for k in keys:
        uid = (k.uuid or "").strip()
        if not uid or not _UUID_RE.match(uid):
            continue
        norm = uid.lower()
        sk = (k.server_id, norm)
        if sk in seen:
            continue
        seen.add(sk)
        srv = await session.get(Server, k.server_id)
        if not srv:
            continue
        await try_remove_vless_client_from_xray(srv, uid)


async def try_push_vless_client_after_key(server: Server, uuid: str) -> None:
    """After key issuance, add UUID to Xray (password from DB, .env, or key file)."""
    if not server.ssh_user:
        return
    if not can_ssh_to_server(server, None):
        log.warning(
            "xray ssh: no SSH credentials for %s (password in DB or XRAY_SYNC_SSH_PRIVATE_KEY_PATH)",
            server.host,
        )
        return
    try:
        await asyncio.wait_for(
            push_vless_client_uuid(server=server, uuid=uuid, ssh_password=None),
            timeout=15,
        )
        log.info("xray ssh: pushed client %s to %s", uuid, server.host)
    except asyncio.TimeoutError:
        log.warning("xray ssh: timeout pushing UUID to %s", server.host)
    except Exception as e:
        log.warning("xray ssh: failed to push UUID to %s: %s", server.host, e)

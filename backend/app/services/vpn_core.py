from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Server, User, UserStatus, VpnKey, VpnKeyStatus
from app.services import settings_store
from app.services.xray_ssh import try_push_vless_client_after_key, try_remove_vless_clients_for_keys

# Default Reality masking domain (dest/serverNames on Xray and SNI in vless://).
DEFAULT_REALITY_MASK_SNI = "www.microsoft.com"


def effective_reality_sni(server: Server) -> str:
    """Client SNI: from DB or default Microsoft masking domain."""
    s = (server.sni or "").strip()
    return s or DEFAULT_REALITY_MASK_SNI


def country_flag_emoji(country_field: str | None) -> str:
    """Country flag from ISO2 code (DE, US) or globe emoji."""
    s = (country_field or "").strip().upper()
    if len(s) >= 2 and s[0].isalpha() and s[1].isalpha():
        a, b = s[0], s[1]
        return chr(0x1F1E6 + ord(a) - ord("A")) + chr(0x1F1E6 + ord(b) - ord("A"))
    return "🌐"


def export_fragment_for_server(server: Server, line_idx: int = 0) -> str:
    """Label in vless://...# fragment (flag + city)."""
    flag = country_flag_emoji(server.country)
    nm = (server.name or "node").strip()[:20] or "node"
    return f"{flag} {nm}"


def server_list_caption(server: Server) -> str:
    """Node list caption in bot: flag + city + latency."""
    flag = country_flag_emoji(server.country)
    nm = (server.name or "node").strip()[:20] or "node"
    lat = server.last_latency_ms
    lat_s = f" · {lat:.0f} ms" if lat is not None else ""
    return f"{flag} {nm}{lat_s}"


def build_vless_reality_uri(
    *,
    uuid: str,
    host: str,
    port: int,
    public_key: str,
    short_id: str,
    sni: str = "",
    fingerprint: str = "chrome",
    flow: str = "xtls-rprx-vision",
    name: str = "VPN",
    transport: str = "tcp",
    grpc_service_name: str = "grpc",
) -> str:
    fp = (fingerprint or "chrome").strip() or "chrome"
    if transport == "grpc":
        params = (
            "encryption=none&security=reality&type=grpc"
            f"&serviceName={quote(grpc_service_name, safe='')}"
            f"&fp={quote(fp, safe='')}"
            f"&pbk={quote(public_key.strip(), safe='')}"
        )
    else:
        fl = (flow or "xtls-rprx-vision").strip() or "xtls-rprx-vision"
        params = (
            "encryption=none&security=reality&type=tcp&headerType=none"
            f"&flow={quote(fl, safe='')}"
            f"&fp={quote(fp, safe='')}"
            f"&pbk={quote(public_key.strip(), safe='')}"
        )
    sn = (sni or "").strip()
    if sn:
        params += f"&sni={quote(sn, safe='')}"
    sid = (short_id or "").strip()
    if sid:
        params += f"&sid={quote(sid, safe='')}"
    frag = quote(name, safe="")
    return f"vless://{uuid}@{host.strip()}:{int(port)}?{params}#{frag}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime | None) -> datetime | None:
    """SQLite often returns naive datetimes; treat them as UTC for comparison with _now()."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def _pool_slots_cap(session: AsyncSession) -> int:
    return max(1, int(await settings_store.get_setting(session, "pool_slots_per_server") or "100"))


async def _distinct_live_users_on_server(session: AsyncSession, server_id: int) -> int:
    now = _now()
    n = await session.scalar(
        select(func.count(distinct(VpnKey.user_id))).where(
            VpnKey.server_id == server_id,
            VpnKey.status == VpnKeyStatus.active.value,
            VpnKey.expires_at.isnot(None),
            VpnKey.expires_at > now,
        )
    )
    return int(n or 0)


async def pick_server_with_capacity(session: AsyncSession) -> Server | None:
    cap = await _pool_slots_cap(session)
    q = await session.scalars(
        select(Server).where(Server.is_active.is_(True)).order_by(Server.country.asc(), Server.id.asc())
    )
    for srv in q:
        if await _distinct_live_users_on_server(session, srv.id) < cap:
            return srv
    return None


async def _user_pool_uuid(session: AsyncSession, user_id: int) -> str:
    k = await session.scalar(
        select(VpnKey)
        .where(VpnKey.user_id == user_id, VpnKey.status != VpnKeyStatus.revoked.value)
        .order_by(VpnKey.id.asc())
    )
    return k.uuid if k else str(uuid_lib.uuid4())


def _uri_for_server(server: Server, uid: str, user: User, *, label_idx: int = 0) -> str:
    label = export_fragment_for_server(server, label_idx)
    return build_vless_reality_uri(
        uuid=uid,
        host=server.host,
        port=server.port,
        public_key=server.public_key,
        short_id=server.short_id,
        sni=effective_reality_sni(server),
        fingerprint=server.fingerprint,
        flow=server.flow,
        name=label,
    )


def _grpc_uri_for_server(server: Server, uid: str, *, label_idx: int = 0) -> str | None:
    if not server.grpc_port:
        return None
    label = export_fragment_for_server(server, label_idx) + " gRPC"
    return build_vless_reality_uri(
        uuid=uid,
        host=server.host,
        port=server.grpc_port,
        public_key=server.public_key,
        short_id=server.short_id,
        sni=effective_reality_sni(server),
        fingerprint=server.fingerprint,
        name=label,
        transport="grpc",
    )


async def rewrite_vless_uris_for_server(session: AsyncSession, srv: Server) -> None:
    """Rebuild vless_uri for all keys on this server (port, SNI, pbk etc. taken from Server)."""
    keys = list(
        (
            await session.scalars(
                select(VpnKey).where(VpnKey.server_id == srv.id).order_by(VpnKey.id.asc())
            )
        ).all()
    )
    sni_eff = effective_reality_sni(srv)
    for idx, k in enumerate(keys):
        frag = export_fragment_for_server(srv, idx)
        k.vless_uri = build_vless_reality_uri(
            uuid=k.uuid.strip(),
            host=srv.host,
            port=int(srv.port),
            public_key=srv.public_key,
            short_id=srv.short_id or "",
            sni=sni_eff,
            fingerprint=srv.fingerprint or "chrome",
            flow=srv.flow or "xtls-rprx-vision",
            name=frag,
        )


async def ensure_user_pool_keys(
    session: AsyncSession, user: User, expires_at: datetime, traffic_bytes: int
) -> list[VpnKey]:
    """One UUID per user; one active key per pool server (if a slot is available)."""
    max_slots = await _pool_slots_cap(session)
    pool_uuid = await _user_pool_uuid(session, user.id)

    servers = list(
        (
            await session.scalars(
                select(Server).where(Server.is_active.is_(True)).order_by(Server.country.asc(), Server.id.asc())
            )
        ).all()
    )
    out: list[VpnKey] = []
    now_ = _now()

    for idx, server in enumerate(servers):
        existing = await session.scalar(
            select(VpnKey)
            .where(VpnKey.user_id == user.id, VpnKey.server_id == server.id)
            .order_by(VpnKey.id.desc())
        )

        if existing:
            ea = _as_utc(existing.expires_at)
            is_live = (
                existing.status == VpnKeyStatus.active.value and ea is not None and ea > now_
            )
            uid = pool_uuid
            uri = _uri_for_server(server, uid, user, label_idx=idx)
            existing.uuid = uid
            existing.vless_uri = uri
            existing.expires_at = expires_at
            existing.traffic_limit_bytes = traffic_bytes
            existing.status = VpnKeyStatus.active.value
            out.append(existing)
            continue

        live_here = await _distinct_live_users_on_server(session, server.id)
        if live_here >= max_slots:
            continue

        uid = pool_uuid
        uri = _uri_for_server(server, uid, user, label_idx=idx)
        nk = VpnKey(
            user_id=user.id,
            server_id=server.id,
            uuid=uid,
            vless_uri=uri,
            expires_at=expires_at,
            traffic_limit_bytes=traffic_bytes,
            status=VpnKeyStatus.active.value,
        )
        session.add(nk)
        out.append(nk)

    await session.commit()
    for k in out:
        await session.refresh(k)
        srv = await session.get(Server, k.server_id)
        if srv:
            await try_push_vless_client_after_key(srv, k.uuid)
    return out


async def create_trial_for_user(session: AsyncSession, user: User) -> VpnKey | None:
    if user.trial_used:
        return None
    traffic_gb = float(await settings_store.get_setting(session, "traffic_limit_trial_gb") or "10")
    traffic_bytes = int(traffic_gb * 1024**3)
    try:
        trial_days = max(1, min(365, int(await settings_store.get_setting(session, "trial_days") or "1")))
    except ValueError:
        trial_days = 1

    server = await pick_server_with_capacity(session)
    if not server:
        return None

    uid = str(uuid_lib.uuid4())
    uri = _uri_for_server(server, uid, user, label_idx=0)
    # Trial: duration from app_settings.trial_days; single config on one server (not pool).
    end = _now() + timedelta(days=trial_days)

    key = VpnKey(
        user_id=user.id,
        server_id=server.id,
        uuid=uid,
        vless_uri=uri,
        expires_at=end,
        traffic_limit_bytes=traffic_bytes,
        status=VpnKeyStatus.active.value,
    )
    user.trial_used = True
    user.subscription_end = end
    user.status = UserStatus.trial.value
    user.traffic_limit_bytes = traffic_bytes
    session.add(key)
    await session.commit()
    await session.refresh(key)
    srv = await session.get(Server, key.server_id)
    if srv:
        await try_push_vless_client_after_key(srv, key.uuid)
    return key


async def create_paid_key(
    session: AsyncSession, user: User, days: int, extend_from: datetime | None = None
) -> VpnKey | None:
    traffic_gb = float(await settings_store.get_setting(session, "traffic_limit_paid_gb") or "100")
    traffic_bytes = int(traffic_gb * 1024**3)

    base = _as_utc(extend_from) if extend_from else _now()
    # Upgrade from trial: paid days count from payment time, not from trial end.
    if user.status != UserStatus.trial.value:
        se = _as_utc(user.subscription_end)
        if se and se > base:
            base = se

        keys = (await session.scalars(select(VpnKey).where(VpnKey.user_id == user.id))).all()
        for k in keys:
            if k.status != VpnKeyStatus.active.value:
                continue
            ea = _as_utc(k.expires_at)
            if ea and ea > base:
                base = ea

    new_end = base + timedelta(days=days)
    user.subscription_end = new_end
    user.status = UserStatus.paid.value
    user.traffic_limit_bytes = traffic_bytes
    user.notify_sub_3d_before_sent = False
    user.notify_sub_expired_sent = False

    pool = await ensure_user_pool_keys(session, user, new_end, traffic_bytes)
    return pool[0] if pool else None


async def extend_subscription(session: AsyncSession, user: User, days: int) -> VpnKey | None:
    user.notify_sub_3d_before_sent = False
    user.notify_sub_expired_sent = False
    was_trial = user.status == UserStatus.trial.value
    base = _now()
    if not was_trial:
        se = _as_utc(user.subscription_end)
        if se and se > base:
            base = se
        keys_for_base = (
            await session.scalars(select(VpnKey).where(VpnKey.user_id == user.id))
        ).all()
        for k in keys_for_base:
            if k.status != VpnKeyStatus.active.value:
                continue
            ea = _as_utc(k.expires_at)
            if ea and ea > base:
                base = ea
    new_end = base + timedelta(days=days)

    keys = (await session.scalars(select(VpnKey).where(VpnKey.user_id == user.id))).all()

    for k in keys:
        if k.status == VpnKeyStatus.revoked.value:
            continue
        k.expires_at = new_end
        k.status = VpnKeyStatus.active.value

    user.subscription_end = new_end
    if user.status != UserStatus.blocked.value:
        user.status = UserStatus.paid.value
    if was_trial:
        paid_gb = float(await settings_store.get_setting(session, "traffic_limit_paid_gb") or "100")
        user.traffic_limit_bytes = int(paid_gb * 1024**3)
    await session.commit()
    if user.status == UserStatus.paid.value:
        await ensure_user_pool_keys(session, user, new_end, user.traffic_limit_bytes)
    last = await session.scalar(
        select(VpnKey).where(VpnKey.user_id == user.id).order_by(VpnKey.id.desc())
    )
    return last


async def delete_user_keys(session: AsyncSession, user_id: int) -> None:
    keys = (await session.scalars(select(VpnKey).where(VpnKey.user_id == user_id))).all()
    to_scrub = [k for k in keys if k.status != VpnKeyStatus.revoked.value]
    for k in keys:
        k.status = VpnKeyStatus.revoked.value
    await session.commit()
    await try_remove_vless_clients_for_keys(session, to_scrub)


async def refresh_user_status(session: AsyncSession, user: User) -> None:
    if user.status == UserStatus.blocked.value:
        return
    end = _as_utc(user.subscription_end)
    if not end:
        if user.trial_used and user.status == UserStatus.trial.value:
            user.status = UserStatus.expired.value
            await session.commit()
        return
    if end < _now():
        user.status = UserStatus.expired.value
        act = (
            await session.scalars(
                select(VpnKey).where(
                    VpnKey.user_id == user.id, VpnKey.status == VpnKeyStatus.active.value
                )
            )
        ).all()
        scrub = list(act)
        for key in act:
            key.status = VpnKeyStatus.expired.value
        await session.commit()
        await try_remove_vless_clients_for_keys(session, scrub)
        return
    await session.commit()

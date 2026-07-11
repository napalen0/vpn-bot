from __future__ import annotations

import pathlib
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, unquote
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.config import get_settings
from app.database import get_db
from app.models import Payment, PaymentStatus, Referral, Server, User, UserStatus, VpnKey, VpnKeyStatus
from app.services import settings_store
from app.services.payment_processor import manual_confirm_payment, sync_pending_from_cryptobot
from app.services.server_health import check_all_servers, check_server
from app.services.vpn_core import (
    build_vless_reality_uri,
    create_paid_key,
    create_trial_for_user,
    delete_user_keys,
    effective_reality_sni,
    export_fragment_for_server,
    extend_subscription,
    rewrite_vless_uris_for_server,
)
from app.services.ssh_secret import encrypt_ssh_password
from app.services.xray_ssh import (
    apply_inbound_port_via_ssh,
    can_ssh_to_server,
    provision_xray_via_ssh,
    rebuild_reality_mask_on_server,
    remove_xray_vpnbot_via_ssh,
    try_remove_vless_clients_for_keys,
)

templates = Jinja2Templates(directory=str(pathlib.Path(__file__).resolve().parent / "templates"))

router = APIRouter(prefix="/admin", tags=["admin"])


def require_admin(request: Request) -> None:
    if not request.session.get("admin"):
        raise HTTPException(status_code=303, headers={"Location": "/admin/login"})


@router.get("/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    return templates.TemplateResponse("admin/login.html", {"request": request, "error": None})


@router.post("/login", response_class=HTMLResponse)
async def admin_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    s = get_settings()
    u = (username or "").strip()
    p = (password or "").strip()
    if u == (s.admin_username or "").strip() and p == (s.admin_password or "").strip():
        request.session["admin"] = True
        return RedirectResponse("/admin/dashboard", status_code=303)
    # Don't return 401: browser shows "HTTP ERROR 401" instead of the form page
    return templates.TemplateResponse(
        "admin/login.html",
        {"request": request, "error": "Invalid username or password"},
        status_code=200,
    )


@router.get("/logout")
async def admin_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    _auth: None = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    today_start = now_utc().replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = today_start.replace(day=1)

    total_users = await session.scalar(select(func.count()).select_from(User)) or 0
    active_subs = await session.scalar(
        select(func.count())
        .select_from(User)
        .where(
            User.subscription_end.isnot(None),
            User.subscription_end > now_utc(),
            User.status != UserStatus.blocked.value,
        )
    ) or 0

    new_today = await session.scalar(
        select(func.count()).select_from(User).where(User.created_at >= today_start)
    ) or 0

    paid_today = (
        await session.scalars(
            select(Payment).where(
                Payment.status == PaymentStatus.paid.value,
                Payment.paid_at.isnot(None),
                Payment.paid_at >= today_start,
            )
        )
    ).all()
    paid_month = (
        await session.scalars(
            select(Payment).where(
                Payment.status == PaymentStatus.paid.value,
                Payment.paid_at.isnot(None),
                Payment.paid_at >= month_start,
            )
        )
    ).all()

    def sum_usdt(rows: list[Payment]) -> Decimal:
        t = Decimal(0)
        for p in rows:
            try:
                t += Decimal(str(p.amount))
            except Exception:
                pass
        return t

    servers = list((await session.scalars(select(Server).order_by(Server.id.asc()))).all())
    await check_all_servers(session, notify_on_failure=False)

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "total_users": total_users,
            "active_subs": active_subs,
            "new_today": new_today,
            "revenue_today": sum_usdt(list(paid_today)),
            "revenue_month": sum_usdt(list(paid_month)),
            "servers": servers,
        },
    )


@router.get("/users", response_class=HTMLResponse)
async def admin_users(
    request: Request,
    _auth: None = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    rows = (
        await session.scalars(
            select(User).options(selectinload(User.referrer)).order_by(User.id.desc()).limit(500)
        )
    ).all()
    invited_counts: dict[int, int] = {}
    for u in rows:
        c = await session.scalar(select(func.count()).select_from(User).where(User.referrer_id == u.id))
        invited_counts[u.id] = int(c or 0)
    return templates.TemplateResponse(
        "admin/users.html",
        {"request": request, "users": rows, "invited_counts": invited_counts},
    )


@router.post("/users/{user_id}/extend")
async def admin_user_extend(
    request: Request,
    user_id: int,
    days: int = Form(30),
    _auth: None = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    u = await session.get(User, user_id)
    if not u:
        raise HTTPException(404)
    await extend_subscription(session, u, days)
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/block")
async def admin_user_block(
    request: Request,
    user_id: int,
    _auth: None = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    u = await session.get(User, user_id)
    if u:
        active = list(
            (
                await session.scalars(
                    select(VpnKey).where(
                        VpnKey.user_id == u.id,
                        VpnKey.status == VpnKeyStatus.active.value,
                    )
                )
            ).all()
        )
        u.status = UserStatus.blocked.value
        for k in active:
            k.status = VpnKeyStatus.revoked.value
        await session.commit()
        await try_remove_vless_clients_for_keys(session, active)
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/unblock")
async def admin_user_unblock(
    request: Request,
    user_id: int,
    _auth: None = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    u = await session.get(User, user_id)
    if u:
        u.status = UserStatus.expired.value
        await session.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/delete")
async def admin_user_delete(
    request: Request,
    user_id: int,
    _auth: None = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    keys_before = list(
        (await session.scalars(select(VpnKey).where(VpnKey.user_id == user_id))).all()
    )
    await try_remove_vless_clients_for_keys(session, keys_before)
    await session.execute(delete(VpnKey).where(VpnKey.user_id == user_id))
    await session.execute(delete(Payment).where(Payment.user_id == user_id))
    await session.execute(delete(Referral).where(Referral.referrer_user_id == user_id))
    await session.execute(delete(Referral).where(Referral.referred_user_id == user_id))
    await session.execute(delete(User).where(User.id == user_id))
    await session.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/trial")
async def admin_user_trial(
    request: Request,
    user_id: int,
    _auth: None = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    u = await session.get(User, user_id)
    if u:
        u.trial_used = False
        u.notify_trial_ended_sent = False
        await session.commit()
        await create_trial_for_user(session, u)
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/manual_key")
async def admin_manual_key(
    request: Request,
    user_id: int,
    days: int = Form(30),
    _auth: None = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    u = await session.get(User, user_id)
    if u:
        await create_paid_key(session, u, days)
    return RedirectResponse("/admin/keys", status_code=303)


@router.get("/keys", response_class=HTMLResponse)
async def admin_keys(
    request: Request,
    _auth: None = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    keys = (
        await session.scalars(
            select(VpnKey).options(joinedload(VpnKey.user), joinedload(VpnKey.server)).order_by(VpnKey.id.desc()).limit(500)
        )
    ).all()
    srv_list = list((await session.scalars(select(Server).order_by(Server.id.asc()))).all())
    return templates.TemplateResponse(
        "admin/keys.html",
        {
            "request": request,
            "keys": keys,
            "servers": srv_list,
        },
    )


@router.post("/keys/{key_id}/delete")
async def admin_key_delete(
    request: Request,
    key_id: int,
    _auth: None = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    k = await session.get(VpnKey, key_id)
    if k:
        scrub = [k]
        k.status = VpnKeyStatus.revoked.value
        await session.commit()
        await try_remove_vless_clients_for_keys(session, scrub)
    return RedirectResponse("/admin/keys", status_code=303)


@router.post("/keys/{key_id}/extend")
async def admin_key_extend(
    request: Request,
    key_id: int,
    days: int = Form(30),
    _auth: None = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    k = await session.get(VpnKey, key_id)
    if k:
        u = await session.get(User, k.user_id)
        if u:
            await extend_subscription(session, u, days)
    return RedirectResponse("/admin/keys", status_code=303)


@router.post("/keys/{key_id}/server")
async def admin_key_server(
    request: Request,
    key_id: int,
    server_id: int = Form(...),
    _auth: None = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    k = await session.get(VpnKey, key_id)
    srv = await session.get(Server, server_id)
    if k and srv:
        k.server_id = srv.id
        k.vless_uri = build_vless_reality_uri(
            uuid=k.uuid,
            host=srv.host,
            port=srv.port,
            public_key=srv.public_key,
            short_id=srv.short_id,
            sni=effective_reality_sni(srv),
            fingerprint=srv.fingerprint,
            flow=srv.flow,
            name=export_fragment_for_server(srv, 0),
        )
        await session.commit()
    return RedirectResponse("/admin/keys", status_code=303)


@router.get("/payments", response_class=HTMLResponse)
async def admin_payments(
    request: Request,
    _auth: None = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    rows = (
        await session.scalars(
            select(Payment).options(joinedload(Payment.user)).order_by(Payment.id.desc()).limit(500)
        )
    ).all()
    return templates.TemplateResponse("admin/payments.html", {"request": request, "payments": rows})


@router.post("/payments/sync")
async def admin_payments_sync(
    request: Request,
    _auth: None = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    await sync_pending_from_cryptobot(session)
    return RedirectResponse("/admin/payments", status_code=303)


@router.post("/payments/{payment_id}/confirm")
async def admin_payment_confirm(
    request: Request,
    payment_id: int,
    _auth: None = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    await manual_confirm_payment(session, payment_id)
    return RedirectResponse("/admin/payments", status_code=303)


@router.get("/referrals", response_class=HTMLResponse)
async def admin_refs(
    request: Request,
    _auth: None = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    rows = (
        await session.scalars(select(Referral).order_by(Referral.id.desc()).limit(500))
    ).all()
    top = (
        await session.execute(
            select(Referral.referrer_user_id, func.count())
            .group_by(Referral.referrer_user_id)
            .order_by(func.count().desc())
            .limit(20)
        )
    ).all()
    return templates.TemplateResponse(
        "admin/referrals.html", {"request": request, "referrals": rows, "top": top}
    )


@router.post("/referrals/bonus")
async def admin_ref_bonus(
    request: Request,
    referrer_user_id: int = Form(...),
    days: int = Form(3),
    _auth: None = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    u = await session.get(User, referrer_user_id)
    if u:
        await extend_subscription(session, u, days)
    return RedirectResponse("/admin/referrals", status_code=303)


@router.get("/servers", response_class=HTMLResponse)
async def admin_servers(
    request: Request,
    _auth: None = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    rows = list((await session.scalars(select(Server).order_by(Server.id.asc()))).all())
    flash = request.query_params.get("provision")
    err = request.query_params.get("err")
    return templates.TemplateResponse(
        "admin/servers.html",
        {
            "request": request,
            "servers": rows,
            "provision_ok": flash == "ok",
            "provision_reality_ok": flash == "reality_ok",
            "provision_port_ok": flash == "port_ok",
            "provision_server_deleted": flash == "deleted",
            "provision_ssh_saved": flash == "ssh_saved",
            "provision_error": unquote(err) if err else None,
        },
    )


@router.post("/servers/add")
async def admin_server_add(
    request: Request,
    name: str = Form(...),
    country: str = Form(""),
    host: str = Form(...),
    port: int = Form(8443),
    public_key: str = Form(...),
    short_id: str = Form(...),
    sni: str = Form(...),
    health_check_url: str = Form(""),
    ssh_user: str = Form(""),
    ssh_port_in: str = Form(""),
    ssh_password: str = Form(""),
    _auth: None = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    su = ssh_user.strip() or None
    if su and not (ssh_password or "").strip():
        return RedirectResponse(
            f"/admin/servers?err={quote('SSH user specified but no password provided — it will be stored encrypted in DB')}",
            status_code=303,
        )
    sp = None
    if (ssh_port_in or "").strip().isdigit():
        sp = int(ssh_port_in.strip())
    enc = encrypt_ssh_password(ssh_password) if (ssh_password or "").strip() else None
    session.add(
        Server(
            name=name,
            country=country,
            host=host,
            port=port,
            public_key=public_key,
            short_id=short_id,
            sni=sni,
            health_check_url=health_check_url or None,
            is_active=True,
            ssh_user=su,
            ssh_port=sp,
            ssh_password_encrypted=enc,
        )
    )
    await session.commit()
    return RedirectResponse("/admin/servers", status_code=303)


@router.post("/servers/provision_ssh")
async def admin_server_provision_ssh(
    request: Request,
    name: str = Form(...),
    country: str = Form(""),
    host: str = Form(...),
    ssh_port: int = Form(22),
    ssh_user: str = Form(...),
    ssh_password: str = Form(""),
    sudo_password: str = Form(""),
    vless_port: int = Form(8443),
    reality_sni: str = Form("www.microsoft.com"),
    reality_dest: str = Form("www.microsoft.com:443"),
    _auth: None = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    cfg = get_settings()
    ssh_p = ssh_password.strip() or None
    sudo_p = sudo_password.strip() or None
    if not ssh_p and not (cfg.xray_sync_ssh_private_key_path or "").strip() and not (
        cfg.xray_sync_ssh_password or ""
    ).strip():
        return RedirectResponse(
            f"/admin/servers?err={quote('Provide SSH password in form, or set XRAY_SYNC_SSH_PRIVATE_KEY_PATH / XRAY_SYNC_SSH_PASSWORD in .env; password will be stored encrypted in DB')}",
            status_code=303,
        )
    try:
        meta = await provision_xray_via_ssh(
            host=host.strip(),
            ssh_port=ssh_port,
            ssh_user=ssh_user.strip(),
            ssh_password=ssh_p,
            sudo_password=sudo_p,
            reality_sni=reality_sni.strip() or "www.microsoft.com",
            reality_dest=reality_dest.strip() or "www.microsoft.com:443",
            vless_port=vless_port,
        )
    except Exception as e:
        return RedirectResponse(f"/admin/servers?err={quote(str(e)[:500])}", status_code=303)

    srv = Server(
        name=name.strip(),
        country=country.strip(),
        host=host.strip(),
        port=int(meta.get("vless_port", vless_port)),
        public_key=meta["public_key"],
        short_id=meta["short_id"],
        sni=meta["sni"],
        health_check_url=None,
        is_active=True,
        ssh_user=ssh_user.strip(),
        ssh_port=ssh_port,
    )
    if meta.get("inbound_tag"):
        srv.inbound_tag = str(meta["inbound_tag"])
    if meta.get("grpc_port"):
        srv.grpc_port = int(meta["grpc_port"])
    srv.ssh_password_encrypted = encrypt_ssh_password(ssh_p) if ssh_p else None
    session.add(srv)
    await session.commit()
    return RedirectResponse("/admin/servers?provision=ok", status_code=303)


@router.post("/servers/{server_id}/toggle")
async def admin_server_toggle(
    request: Request,
    server_id: int,
    _auth: None = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    srv = await session.get(Server, server_id)
    if srv:
        srv.is_active = not srv.is_active
        await session.commit()
    return RedirectResponse("/admin/servers", status_code=303)


@router.post("/servers/{server_id}/check")
async def admin_server_check(
    request: Request,
    server_id: int,
    _auth: None = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    srv = await session.get(Server, server_id)
    if srv:
        await check_server(session, srv)
    return RedirectResponse("/admin/servers", status_code=303)


@router.post("/servers/{server_id}/reality_microsoft")
async def admin_server_reality_microsoft(
    request: Request,
    server_id: int,
    _auth: None = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Patch Reality on node (Microsoft) + update SNI in DB + rebuild vless_uri for all server keys."""
    srv = await session.get(Server, server_id)
    if not srv:
        return RedirectResponse("/admin/servers", status_code=303)

    if not (srv.ssh_user or "").strip():
        return RedirectResponse(
            f"/admin/servers?err={quote('Server has no ssh_user configured')}",
            status_code=303,
        )
    if not can_ssh_to_server(srv, None):
        return RedirectResponse(
            f"/admin/servers?err={quote('No SSH credentials: set password in DB (SSH card) or XRAY_SYNC_SSH_PRIVATE_KEY_PATH')}",
            status_code=303,
        )
    try:
        await rebuild_reality_mask_on_server(server=srv, ssh_password=None)
    except Exception as e:
        return RedirectResponse(f"/admin/servers?err={quote(str(e)[:800])}", status_code=303)

    srv.sni = "www.microsoft.com"
    await rewrite_vless_uris_for_server(session, srv)
    await session.commit()
    return RedirectResponse("/admin/servers?provision=reality_ok", status_code=303)


@router.post("/servers/{server_id}/apply_port")
async def admin_server_apply_port(
    request: Request,
    server_id: int,
    port: int = Form(...),
    _auth: None = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Update port in DB + rebuild vless_uri; if ssh_user set, also update Xray on VPS + ufw + perms."""
    srv = await session.get(Server, server_id)
    if not srv:
        return RedirectResponse("/admin/servers", status_code=303)

    p = max(1, min(65535, int(port)))

    if srv.ssh_user:
        if not can_ssh_to_server(srv, None):
            return RedirectResponse(
                f"/admin/servers?err={quote('To change port on VPS: set password in DB or XRAY_SYNC_SSH_PRIVATE_KEY_PATH')}",
                status_code=303,
            )
        try:
            await apply_inbound_port_via_ssh(server=srv, port=p, ssh_password=None)
        except Exception as e:
            return RedirectResponse(f"/admin/servers?err={quote(str(e)[:800])}", status_code=303)

    srv.port = p
    await rewrite_vless_uris_for_server(session, srv)
    await session.commit()
    return RedirectResponse("/admin/servers?provision=port_ok", status_code=303)


@router.post("/servers/{server_id}/delete")
async def admin_server_delete(
    request: Request,
    server_id: int,
    confirm: str = Form(""),
    remove_remote: str = Form(""),
    _auth: None = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Delete server from DB and all vpn_keys on it; optionally remove Xray from VPS via SSH."""
    if confirm.strip() != "DELETE":
        return RedirectResponse(
            f"/admin/servers?err={quote('Type DELETE in the confirmation field to proceed')}",
            status_code=303,
        )

    srv = await session.get(Server, server_id)
    if not srv:
        return RedirectResponse("/admin/servers", status_code=303)

    do_remote = remove_remote == "on" and bool(srv.ssh_user)

    if do_remote:
        if not can_ssh_to_server(srv, None):
            return RedirectResponse(
                f"/admin/servers?err={quote('To remove from VPS: set password in DB or XRAY_SYNC_SSH_PRIVATE_KEY_PATH')}",
                status_code=303,
            )
        try:
            await remove_xray_vpnbot_via_ssh(server=srv, ssh_password=None)
        except Exception as e:
            return RedirectResponse(f"/admin/servers?err={quote(str(e)[:800])}", status_code=303)

    await session.execute(delete(VpnKey).where(VpnKey.server_id == server_id))
    await session.delete(srv)
    await session.commit()
    return RedirectResponse("/admin/servers?provision=deleted", status_code=303)


@router.post("/servers/{server_id}/ssh_credentials")
async def admin_server_ssh_credentials(
    request: Request,
    server_id: int,
    ssh_user: str = Form(""),
    ssh_port_in: str = Form(""),
    ssh_password: str = Form(""),
    clear_ssh_password: str = Form(""),
    _auth: None = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Save server SSH password in DB (Fernet), optionally update ssh_user / ssh_port."""
    srv = await session.get(Server, server_id)
    if not srv:
        return RedirectResponse("/admin/servers", status_code=303)
    if clear_ssh_password == "on":
        srv.ssh_password_encrypted = None
    elif (ssh_password or "").strip():
        srv.ssh_password_encrypted = encrypt_ssh_password(ssh_password)
    su = ssh_user.strip()
    if su:
        srv.ssh_user = su
    if (ssh_port_in or "").strip().isdigit():
        srv.ssh_port = int(ssh_port_in.strip())
    await session.commit()
    return RedirectResponse("/admin/servers?provision=ssh_saved", status_code=303)


@router.get("/settings", response_class=HTMLResponse)
async def admin_settings_page(
    request: Request,
    _auth: None = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    data = await settings_store.all_settings(session)
    return templates.TemplateResponse("admin/settings.html", {"request": request, "s": data})


@router.post("/settings")
async def admin_settings_save(
    request: Request,
    trial_days: str = Form(...),
    referral_bonus_days: str = Form(...),
    referral_min_plan_days: str = Form(...),
    traffic_limit_trial_gb: str = Form(...),
    traffic_limit_paid_gb: str = Form(...),
    pool_slots_per_server: str = Form(...),
    price_7_usdt: str = Form(...),
    price_30_usdt: str = Form(...),
    price_90_usdt: str = Form(...),
    bot_username: str = Form(""),
    _auth: None = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    pairs = {
        "trial_days": trial_days,
        "referral_bonus_days": referral_bonus_days,
        "referral_min_plan_days": referral_min_plan_days,
        "traffic_limit_trial_gb": traffic_limit_trial_gb,
        "traffic_limit_paid_gb": traffic_limit_paid_gb,
        "pool_slots_per_server": pool_slots_per_server,
        "price_7_usdt": price_7_usdt,
        "price_30_usdt": price_30_usdt,
        "price_90_usdt": price_90_usdt,
        "bot_username": bot_username,
    }
    for k, v in pairs.items():
        await settings_store.set_setting(session, k, v)
    return RedirectResponse("/admin/settings", status_code=303)


@router.get("", response_class=HTMLResponse)
async def admin_root(request: Request):
    if request.session.get("admin"):
        return RedirectResponse("/admin/dashboard")
    return RedirectResponse("/admin/login")

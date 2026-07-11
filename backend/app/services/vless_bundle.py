"""Export vless:// URIs for a user's active keys (available nodes only)."""

from __future__ import annotations

import base64

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Server, User, UserStatus, VpnKey, VpnKeyStatus
from app.services.vpn_core import (
    _as_utc,
    _grpc_uri_for_server,
    _now,
    build_vless_reality_uri,
    effective_reality_sni,
    ensure_user_pool_keys,
    export_fragment_for_server,
    refresh_user_status,
    server_list_caption,
)


def _server_is_available_for_export(srv: Server) -> bool:
    """Skip nodes disabled in panel or explicitly offline at last check."""
    if not srv.is_active:
        return False
    if srv.last_online is False:
        return False
    return True


async def build_vless_export_blocks(session: AsyncSession, user: User) -> list[dict[str, str]]:
    """List of {caption, vless_uri}, one per available server."""
    await refresh_user_status(session, user)
    await session.refresh(user)

    if user.status == UserStatus.blocked.value:
        return []

    end = _as_utc(user.subscription_end)
    now = _now()
    if not end or end <= now:
        return []
    if user.status == UserStatus.expired.value:
        return []

    if user.status == UserStatus.paid.value:
        await ensure_user_pool_keys(session, user, end, user.traffic_limit_bytes)
        await session.refresh(user)

    rows = list(
        (
            await session.scalars(
                select(VpnKey)
                .join(Server, VpnKey.server_id == Server.id)
                .options(selectinload(VpnKey.server))
                .where(
                    VpnKey.user_id == user.id,
                    VpnKey.status == VpnKeyStatus.active.value,
                    VpnKey.expires_at.isnot(None),
                    VpnKey.expires_at > now,
                )
                .order_by(Server.country.asc(), Server.name.asc(), VpnKey.id.asc())
            )
        ).all()
    )

    is_trial = user.status == UserStatus.trial.value

    seen_server: set[int] = set()
    blocks: list[dict[str, str]] = []
    idx = 0
    for k in rows:
        if k.server_id in seen_server:
            continue
        seen_server.add(k.server_id)
        srv = k.server
        if not srv or not _server_is_available_for_export(srv):
            continue
        if is_trial and idx >= 1:
            break
        frag = export_fragment_for_server(srv, idx)
        idx += 1
        uri = build_vless_reality_uri(
            uuid=k.uuid.strip(),
            host=srv.host,
            port=int(srv.port),
            public_key=srv.public_key,
            short_id=srv.short_id or "",
            sni=effective_reality_sni(srv),
            fingerprint=srv.fingerprint or "chrome",
            flow=srv.flow or "xtls-rprx-vision",
            name=frag,
        )
        blocks.append({"caption": server_list_caption(srv), "vless_uri": uri})
        grpc_uri = _grpc_uri_for_server(srv, k.uuid.strip(), label_idx=idx - 1)
        if grpc_uri:
            blocks.append({"caption": server_list_caption(srv) + " gRPC", "vless_uri": grpc_uri})

    return blocks


async def get_unified_vless_export_for_user(session: AsyncSession, user: User) -> str:
    """Backward-compatible: vless URIs joined by newline."""
    blocks = await build_vless_export_blocks(session, user)
    if not blocks:
        return ""
    return "\n".join(b["vless_uri"] for b in blocks) + "\n"


async def build_subscription_base64(session: AsyncSession, user: User) -> str:
    blocks = await build_vless_export_blocks(session, user)
    if not blocks:
        return ""
    raw = "\n".join(b["vless_uri"] for b in blocks)
    return base64.b64encode(raw.encode()).decode()

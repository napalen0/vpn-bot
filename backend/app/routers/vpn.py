from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.deps import require_api_key
from app.models import Server, User, UserStatus, VpnKey
from app.schemas import VpnDeleteIn, VpnExtendIn, VpnKeyOut, VpnPaidIn, VpnTrialIn
from app.services.vless_bundle import build_subscription_base64, build_vless_export_blocks
from app.services.vpn_core import (
    _as_utc,
    _now,
    create_paid_key,
    create_trial_for_user,
    delete_user_keys,
    ensure_user_pool_keys,
    extend_subscription,
    refresh_user_status,
)

router = APIRouter(prefix="/vpn", tags=["vpn"])


@router.post("/vless_export", dependencies=[Depends(require_api_key)])
async def vpn_vless_export(body: VpnTrialIn, session: AsyncSession = Depends(get_db)) -> dict:
    user = await session.get(User, body.user_id)
    if not user:
        raise HTTPException(404, "User not found")
    blocks = await build_vless_export_blocks(session, user)
    if not blocks:
        raise HTTPException(400, "No active VPN configuration or all nodes are offline")
    vless_text = "\n\n".join(b["vless_uri"] for b in blocks)
    return {"blocks": blocks, "vless_text": vless_text}


def _vpn_key_out(k: VpnKey) -> VpnKeyOut:
    out = VpnKeyOut.model_validate(k)
    srv = k.server if hasattr(k, "server") and k.server is not None else None
    if srv:
        return out.model_copy(
            update={
                "server_id": k.server_id,
                "server_country": srv.country or "",
                "server_name": srv.name,
            }
        )
    return out


async def _load_key_with_server(session: AsyncSession, key_id: int) -> VpnKey | None:
    return await session.scalar(
        select(VpnKey).options(selectinload(VpnKey.server)).where(VpnKey.id == key_id)
    )


@router.post("/create_trial", dependencies=[Depends(require_api_key)])
async def vpn_create_trial(body: VpnTrialIn, session: AsyncSession = Depends(get_db)) -> VpnKeyOut:
    user = await session.get(User, body.user_id)
    if not user:
        raise HTTPException(404, "User not found")
    key = await create_trial_for_user(session, user)
    if not key:
        raise HTTPException(400, "Trial already used or no active server")
    k = await _load_key_with_server(session, key.id)
    assert k
    return _vpn_key_out(k)


@router.post("/create_paid", dependencies=[Depends(require_api_key)])
async def vpn_create_paid(body: VpnPaidIn, session: AsyncSession = Depends(get_db)) -> VpnKeyOut:
    user = await session.get(User, body.user_id)
    if not user:
        raise HTTPException(404, "User not found")
    key = await create_paid_key(session, user, body.days)
    if not key:
        raise HTTPException(400, "No active server or pool is full")
    k = await _load_key_with_server(session, key.id)
    assert k
    return _vpn_key_out(k)


@router.post("/extend", dependencies=[Depends(require_api_key)])
async def vpn_extend(body: VpnExtendIn, session: AsyncSession = Depends(get_db)) -> dict:
    user = await session.get(User, body.user_id)
    if not user:
        raise HTTPException(404, "User not found")
    key = await extend_subscription(session, user, body.days)
    return {"ok": True, "key_id": key.id if key else None}


@router.post("/delete", dependencies=[Depends(require_api_key)])
async def vpn_delete(body: VpnDeleteIn, session: AsyncSession = Depends(get_db)) -> dict:
    user = await session.get(User, body.user_id)
    if not user:
        raise HTTPException(404, "User not found")
    await delete_user_keys(session, body.user_id)
    return {"ok": True}


@router.get("/keys/{user_id}", dependencies=[Depends(require_api_key)])
async def vpn_keys_user(user_id: int, session: AsyncSession = Depends(get_db)) -> list[VpnKeyOut]:
    keys = list(
        (
            await session.scalars(
                select(VpnKey)
                .join(Server, VpnKey.server_id == Server.id)
                .options(selectinload(VpnKey.server))
                .where(VpnKey.user_id == user_id)
                .order_by(Server.country.asc(), Server.name.asc(), VpnKey.id.asc())
            )
        ).all()
    )
    return [_vpn_key_out(k) for k in keys]


@router.post("/sync_pool", dependencies=[Depends(require_api_key)])
async def vpn_sync_pool(body: VpnTrialIn, session: AsyncSession = Depends(get_db)) -> list[VpnKeyOut]:
    user = await session.get(User, body.user_id)
    if not user:
        raise HTTPException(404, "User not found")
    await refresh_user_status(session, user)
    await session.refresh(user)
    if user.status != UserStatus.paid.value:
        raise HTTPException(400, "Available for paid subscriptions only")
    end = _as_utc(user.subscription_end)
    if not end or end <= _now():
        raise HTTPException(400, "No active subscription")
    await ensure_user_pool_keys(session, user, end, user.traffic_limit_bytes)
    keys = list(
        (
            await session.scalars(
                select(VpnKey)
                .join(Server, VpnKey.server_id == Server.id)
                .options(selectinload(VpnKey.server))
                .where(VpnKey.user_id == user.id)
                .order_by(Server.country.asc(), Server.name.asc(), VpnKey.id.asc())
            )
        ).all()
    )
    return [_vpn_key_out(k) for k in keys]


@router.get("/sub/{token}")
async def subscription_by_token(token: str, session: AsyncSession = Depends(get_db)):
    user = await session.scalar(select(User).where(User.sub_token == token))
    if not user:
        raise HTTPException(404, "Not found")
    content = await build_subscription_base64(session, user)
    if not content:
        return PlainTextResponse("", status_code=204)
    sub_end = _as_utc(user.subscription_end)
    expire_ts = int(sub_end.timestamp()) if sub_end else 0
    return PlainTextResponse(
        content,
        headers={
            "Content-Type": "text/plain; charset=utf-8",
            "Profile-Update-Interval": "12",
            "Subscription-Userinfo": (
                f"upload=0; download={user.traffic_used_bytes}; "
                f"total={user.traffic_limit_bytes}; expire={expire_ts}"
            ),
        },
    )

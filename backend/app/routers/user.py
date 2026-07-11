from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import uuid as uuid_lib

from app.database import get_db
from app.deps import require_api_key
from app.models import User
from app.schemas import UserCreateIn, UserOut

class SetLanguageIn(BaseModel):
    telegram_id: int
    language: str
from app.services.notifier import notify_admins
from app.services.referral_service import apply_referral_by_telegram
from app.services.vpn_core import refresh_user_status

router = APIRouter(prefix="/user", tags=["user"])


async def _ensure_sub_token(session: AsyncSession, user: User) -> None:
    if not user.sub_token:
        user.sub_token = str(uuid_lib.uuid4())
        await session.commit()
        await session.refresh(user)


@router.post("/create", dependencies=[Depends(require_api_key)])
async def user_create(body: UserCreateIn, session: AsyncSession = Depends(get_db)) -> UserOut:
    existing = await session.scalar(select(User).where(User.telegram_id == body.telegram_id))
    if existing:
        if body.referrer_telegram_id and not existing.referrer_id:
            await apply_referral_by_telegram(session, existing, body.referrer_telegram_id)
            await session.refresh(existing)
        await refresh_user_status(session, existing)
        await _ensure_sub_token(session, existing)
        return UserOut.model_validate(existing)

    u = User(
        telegram_id=body.telegram_id,
        username=body.username,
        first_name=body.first_name,
        language=body.language or "ru",
        sub_token=str(uuid_lib.uuid4()),
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)

    if body.referrer_telegram_id:
        await apply_referral_by_telegram(session, u, body.referrer_telegram_id)

    await notify_admins(
        f"\U0001f195 New user\n"
        f"tg: {u.telegram_id} @{u.username or '—'} · id: {u.id}"
    )
    return UserOut.model_validate(u)


@router.get("/telegram/{telegram_id}", dependencies=[Depends(require_api_key)])
async def user_by_telegram(telegram_id: int, session: AsyncSession = Depends(get_db)) -> UserOut:
    u = await session.scalar(select(User).where(User.telegram_id == telegram_id))
    if not u:
        raise HTTPException(404, "User not found")
    await refresh_user_status(session, u)
    return UserOut.model_validate(u)


@router.get("/{user_id}", dependencies=[Depends(require_api_key)])
async def user_get(user_id: int, session: AsyncSession = Depends(get_db)) -> UserOut:
    u = await session.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    await refresh_user_status(session, u)
    return UserOut.model_validate(u)


@router.post("/set_language", dependencies=[Depends(require_api_key)])
async def set_language(body: SetLanguageIn, session: AsyncSession = Depends(get_db)) -> UserOut:
    u = await session.scalar(select(User).where(User.telegram_id == body.telegram_id))
    if not u:
        raise HTTPException(404, "User not found")
    u.language = body.language
    await session.commit()
    await session.refresh(u)
    return UserOut.model_validate(u)

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Referral, User, UserStatus
from app.services import settings_store
from app.services.vpn_core import extend_subscription


async def apply_referral_by_telegram(
    session: AsyncSession, new_user: User, referrer_telegram_id: int
) -> bool:
    if new_user.referrer_id:
        return False
    ref_user = await session.scalar(select(User).where(User.telegram_id == referrer_telegram_id))
    if not ref_user or ref_user.id == new_user.id:
        return False
    new_user.referrer_id = ref_user.id
    existing = await session.scalar(select(Referral).where(Referral.referred_user_id == new_user.id))
    if not existing:
        session.add(
            Referral(
                referrer_user_id=ref_user.id,
                referred_user_id=new_user.id,
                referred_paid=False,
                bonus_days_granted=0,
            )
        )
    await session.commit()
    return True


async def reward_referrer_on_paid_plan(
    session: AsyncSession, referred_user: User, plan_days: int
) -> None:
    min_days = int(await settings_store.get_setting(session, "referral_min_plan_days") or "30")
    bonus = int(await settings_store.get_setting(session, "referral_bonus_days") or "3")
    if plan_days < min_days:
        return

    ref_row = await session.scalar(select(Referral).where(Referral.referred_user_id == referred_user.id))
    if not ref_row or ref_row.bonus_days_granted > 0:
        return

    referrer = await session.get(User, ref_row.referrer_user_id)
    if not referrer or referrer.status == UserStatus.blocked.value:
        return

    await extend_subscription(session, referrer, bonus)
    ref_row.referred_paid = True
    ref_row.bonus_days_granted = bonus
    await session.commit()

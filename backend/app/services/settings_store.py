from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AppSetting

DEFAULTS: dict[str, str] = {
    "pool_slots_per_server": "100",
    "trial_days": "1",
    "referral_bonus_days": "3",
    "referral_min_plan_days": "30",
    "traffic_limit_trial_gb": "10",
    "traffic_limit_paid_gb": "100",
    "price_7_usdt": "3",
    "price_30_usdt": "10",
    "price_90_usdt": "25",
    "bot_username": "",
}


async def get_setting(session: AsyncSession, key: str) -> str:
    row = await session.scalar(select(AppSetting).where(AppSetting.key == key))
    if row:
        return row.value
    return DEFAULTS.get(key, "")


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    row = await session.scalar(select(AppSetting).where(AppSetting.key == key))
    if row:
        row.value = value
    else:
        session.add(AppSetting(key=key, value=value))
    await session.commit()


async def ensure_defaults(session: AsyncSession) -> None:
    for k, v in DEFAULTS.items():
        existing = await session.scalar(select(AppSetting).where(AppSetting.key == k))
        if not existing:
            session.add(AppSetting(key=k, value=v))
    await session.commit()


async def all_settings(session: AsyncSession) -> dict[str, str]:
    rows = (await session.scalars(select(AppSetting))).all()
    out = dict(DEFAULTS)
    for r in rows:
        out[r.key] = r.value
    return out

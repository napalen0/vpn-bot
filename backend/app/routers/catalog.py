from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import require_api_key
from app.services import settings_store

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("", dependencies=[Depends(require_api_key)])
async def catalog(session: AsyncSession = Depends(get_db)) -> dict:
    s = await settings_store.all_settings(session)
    try:
        trial_days = max(1, min(365, int(s.get("trial_days", "1") or "1")))
    except ValueError:
        trial_days = 1
    return {
        "trial_days": trial_days,
        "bot_username": s.get("bot_username", ""),
        "prices": {
            "7": s.get("price_7_usdt", "3"),
            "30": s.get("price_30_usdt", "10"),
            "90": s.get("price_90_usdt", "25"),
        },
        "referral_min_plan_days": int(s.get("referral_min_plan_days", "30")),
        "referral_bonus_days": int(s.get("referral_bonus_days", "3")),
    }

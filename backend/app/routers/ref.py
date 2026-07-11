from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import require_api_key
from app.models import Referral, User
from app.schemas import RefApplyIn, RefRewardIn
from app.services.referral_service import apply_referral_by_telegram, reward_referrer_on_paid_plan

router = APIRouter(prefix="/ref", tags=["ref"])


@router.post("/apply", dependencies=[Depends(require_api_key)])
async def ref_apply(body: RefApplyIn, session: AsyncSession = Depends(get_db)) -> dict:
    new_u = await session.scalar(select(User).where(User.telegram_id == body.new_user_telegram_id))
    if not new_u:
        raise HTTPException(404, "New user not found")
    ok = await apply_referral_by_telegram(session, new_u, body.referrer_telegram_id)
    return {"ok": ok}


@router.post("/reward", dependencies=[Depends(require_api_key)])
async def ref_reward(body: RefRewardIn, session: AsyncSession = Depends(get_db)) -> dict:
    u = await session.get(User, body.referred_user_id)
    if not u:
        raise HTTPException(404, "User not found")
    await reward_referrer_on_paid_plan(session, u, body.plan_days)
    return {"ok": True}


@router.get("/list", dependencies=[Depends(require_api_key)])
async def ref_list(session: AsyncSession = Depends(get_db)) -> list[dict]:
    rows = list((await session.scalars(select(Referral).order_by(Referral.id.desc()).limit(500))).all())
    out = []
    for r in rows:
        out.append(
            {
                "id": r.id,
                "referrer_user_id": r.referrer_user_id,
                "referred_user_id": r.referred_user_id,
                "referred_paid": r.referred_paid,
                "bonus_days_granted": r.bonus_days_granted,
            }
        )
    return out

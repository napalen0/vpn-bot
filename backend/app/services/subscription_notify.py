"""Background Telegram notifications for trial and subscription events."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Payment, PaymentStatus, User, UserStatus
from app.services.notifier import BUY_INLINE_KEYBOARD, notify_user_telegram
from app.services.vpn_core import _as_utc, _now, refresh_user_status

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from bot.locale import t  # noqa: E402

log = logging.getLogger(__name__)

MSG_TRIAL_ENDED = t("notify.trial_ended")
MSG_SUB_EXPIRED = t("notify.sub_expired")
MSG_SUB_3D = t("notify.sub_3d_warning")


async def _user_has_paid_payment(session: AsyncSession, user_id: int) -> bool:
    n = await session.scalar(
        select(func.count())
        .select_from(Payment)
        .where(Payment.user_id == user_id, Payment.status == PaymentStatus.paid.value)
    )
    return int(n or 0) > 0


async def _expire_overdue_subscriptions(session: AsyncSession) -> None:
    now = _now()
    rows = (
        await session.scalars(
            select(User).where(
                User.subscription_end.isnot(None),
                User.subscription_end < now,
                User.status.in_([UserStatus.trial.value, UserStatus.paid.value]),
            )
        )
    ).all()
    for u in rows:
        if u.status == UserStatus.blocked.value:
            continue
        await refresh_user_status(session, u)


def _in_3d_warning_window(end: object) -> bool:
    """Returns True if 2 to 3 days remain (exclusive boundaries)."""
    end_u = _as_utc(end)  # type: ignore[arg-type]
    if end_u is None:
        return False
    now = _now()
    if end_u <= now:
        return False
    remain = end_u - now
    two = 2 * 24 * 3600
    three = 3 * 24 * 3600
    sec = remain.total_seconds()
    return two < sec <= three


async def run_subscription_notifications(session: AsyncSession) -> None:
    await _expire_overdue_subscriptions(session)

    # Trial ended (expired, never had a successful payment)
    trial_rows = (
        await session.scalars(
            select(User).where(
                User.status == UserStatus.expired.value,
                User.notify_trial_ended_sent.is_(False),
            )
        )
    ).all()
    for u in trial_rows:
        if await _user_has_paid_payment(session, u.id):
            continue
        ok = await notify_user_telegram(u.telegram_id, MSG_TRIAL_ENDED, reply_markup=BUY_INLINE_KEYBOARD)
        if ok:
            u.notify_trial_ended_sent = True
            await session.commit()

    # Paid subscription expired
    paid_exp = (
        await session.scalars(
            select(User).where(
                User.status == UserStatus.expired.value,
                User.notify_sub_expired_sent.is_(False),
            )
        )
    ).all()
    for u in paid_exp:
        if not await _user_has_paid_payment(session, u.id):
            continue
        ok = await notify_user_telegram(u.telegram_id, MSG_SUB_EXPIRED, reply_markup=BUY_INLINE_KEYBOARD)
        if ok:
            u.notify_sub_expired_sent = True
            await session.commit()

    # 3 days before active paid subscription ends
    warn_rows = (
        await session.scalars(
            select(User).where(
                User.status == UserStatus.paid.value,
                User.notify_sub_3d_before_sent.is_(False),
                User.subscription_end.isnot(None),
            )
        )
    ).all()
    for u in warn_rows:
        end = _as_utc(u.subscription_end)
        if end is None or end <= _now():
            continue
        if not _in_3d_warning_window(end):
            continue
        ok = await notify_user_telegram(u.telegram_id, MSG_SUB_3D, reply_markup=BUY_INLINE_KEYBOARD)
        if ok:
            u.notify_sub_3d_before_sent = True
            await session.commit()

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Payment, PaymentStatus, User
from app.services import settings_store
from app.services.notifier import notify_admins
from app.services.referral_service import reward_referrer_on_paid_plan
from app.services.vpn_core import create_paid_key, refresh_user_status

log = logging.getLogger(__name__)

_PAYLOAD_RE = re.compile(r"^u(?P<uid>\d+)\|d(?P<days>\d+)$")


def parse_invoice_payload(payload: str | None) -> tuple[int, int] | None:
    if not payload:
        return None
    m = _PAYLOAD_RE.match(payload.strip())
    if not m:
        return None
    return int(m.group("uid")), int(m.group("days"))


async def mark_payment_paid(
    session: AsyncSession,
    *,
    invoice_id: int | None,
    amount: str | None,
    asset: str | None,
    payload: str | None,
) -> dict[str, Any]:
    if invoice_id is not None:
        dup = await session.scalar(
            select(Payment).where(
                Payment.cryptobot_invoice_id == invoice_id,
                Payment.status == PaymentStatus.paid.value,
            )
        )
        if dup:
            return {"ok": True, "duplicate": True}

    parsed = parse_invoice_payload(payload)
    if not parsed:
        log.warning("Unknown invoice payload: %s", payload)
        return {"ok": False, "error": "bad_payload"}

    user_id, plan_days = parsed
    user = await session.scalar(select(User).where(User.id == user_id))
    if not user:
        return {"ok": False, "error": "user_not_found"}

    pay = None
    if invoice_id is not None:
        pay = await session.scalar(select(Payment).where(Payment.cryptobot_invoice_id == invoice_id))
    if not pay:
        pay = await session.scalar(
            select(Payment)
            .where(Payment.user_id == user.id, Payment.status == PaymentStatus.pending.value)
            .order_by(Payment.id.desc())
        )

    if pay and pay.status == PaymentStatus.paid.value:
        return {"ok": True, "duplicate": True}

    if not pay:
        from datetime import datetime, timezone

        pay = Payment(
            cryptobot_invoice_id=invoice_id,
            user_id=user.id,
            amount=amount or "0",
            currency=(asset or "USDT").upper(),
            status=PaymentStatus.paid.value,
            payload=payload or "",
            plan_days=plan_days,
            paid_at=datetime.now(timezone.utc),
        )
        session.add(pay)
    else:
        pay.status = PaymentStatus.paid.value
        pay.plan_days = plan_days
        if invoice_id is not None:
            pay.cryptobot_invoice_id = invoice_id
        if amount:
            pay.amount = amount
        if asset:
            pay.currency = asset.upper()
        from datetime import datetime, timezone

        pay.paid_at = datetime.now(timezone.utc)

    await session.commit()

    user = await session.scalar(select(User).options(selectinload(User.referrer)).where(User.id == user_id))
    assert user
    await create_paid_key(session, user, plan_days)
    await reward_referrer_on_paid_plan(session, user, plan_days)
    await refresh_user_status(session, user)

    await notify_admins(
        f"💳 VPN payment\n"
        f"User DB id: {user.id} · tg: {user.telegram_id}\n"
        f"Plan: {plan_days} days · amount: {amount} {asset or 'USDT'}"
    )
    return {"ok": True}


async def manual_confirm_payment(session: AsyncSession, payment_id: int) -> bool:
    pay = await session.get(Payment, payment_id)
    if not pay or pay.status == PaymentStatus.paid.value:
        return False
    user = await session.get(User, pay.user_id)
    if not user:
        return False
    parsed = parse_invoice_payload(pay.payload)
    if not parsed:
        parsed = (user.id, pay.plan_days or 30)
    user_id, plan_days = parsed
    pay.status = PaymentStatus.paid.value
    from datetime import datetime, timezone

    pay.paid_at = datetime.now(timezone.utc)
    pay.plan_days = plan_days
    await session.commit()
    await create_paid_key(session, user, plan_days)
    await reward_referrer_on_paid_plan(session, user, plan_days)
    await refresh_user_status(session, user)
    return True


async def sync_pending_from_cryptobot(session: AsyncSession) -> int:
    from app.services import cryptobot

    pending = (
        await session.scalars(
            select(Payment).where(
                Payment.status == PaymentStatus.pending.value,
                Payment.cryptobot_invoice_id.isnot(None),
            )
        )
    ).all()
    if not pending:
        return 0
    ids = [p.cryptobot_invoice_id for p in pending if p.cryptobot_invoice_id]
    if not ids:
        return 0
    try:
        items = await cryptobot.get_invoices(ids)
    except Exception as e:
        log.warning("sync invoices: %s", e)
        return 0
    updated = 0
    by_id = {int(i.get("invoice_id")): i for i in items if i.get("invoice_id") is not None}
    for p in pending:
        inv = by_id.get(int(p.cryptobot_invoice_id)) if p.cryptobot_invoice_id else None
        if inv and inv.get("status") == "paid":
            await mark_payment_paid(
                session,
                invoice_id=int(p.cryptobot_invoice_id),
                amount=str(inv.get("amount", p.amount)),
                asset=str(inv.get("asset", p.currency)),
                payload=inv.get("payload") or p.payload,
            )
            updated += 1
    return updated

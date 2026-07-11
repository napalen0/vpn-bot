from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.deps import require_api_key
from app.models import Payment, PaymentStatus, User
from app.schemas import PaymentCreateInvoiceIn
from app.services import cryptobot
from app.services.payment_processor import mark_payment_paid, sync_pending_from_cryptobot

log = logging.getLogger(__name__)

router = APIRouter(prefix="/payment", tags=["payment"])


@router.post("/create_invoice", dependencies=[Depends(require_api_key)])
async def payment_create_invoice(
    body: PaymentCreateInvoiceIn, session: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    user = await session.get(User, body.user_id)
    if not user:
        raise HTTPException(404, "User not found")

    payload = f"u{user.id}|d{body.plan_days}"
    settings = get_settings()
    paid_url = f"{settings.public_base_url.rstrip('/')}/paid?u={user.id}"

    try:
        inv = await cryptobot.create_invoice(
            amount=body.amount,
            asset=body.currency,
            description=f"VPN {body.plan_days} d.",
            payload=payload,
            paid_btn_url=paid_url,
        )
    except Exception as e:
        log.exception("create_invoice")
        raise HTTPException(502, str(e)) from e

    invoice_id = inv.get("invoice_id")
    pay = Payment(
        cryptobot_invoice_id=int(invoice_id) if invoice_id is not None else None,
        user_id=user.id,
        amount=str(inv.get("amount", body.amount)),
        currency=str(inv.get("asset", body.currency)).upper(),
        status=PaymentStatus.pending.value,
        payload=payload,
        plan_days=body.plan_days,
    )
    session.add(pay)
    await session.commit()

    return {
        "invoice_id": invoice_id,
        "bot_invoice_url": inv.get("bot_invoice_url"),
        "mini_app_invoice_url": inv.get("mini_app_invoice_url"),
        "web_app_invoice_url": inv.get("web_app_invoice_url"),
        "payload": payload,
    }


@router.post("/webhook")
async def payment_webhook(request: Request, session: AsyncSession = Depends(get_db)) -> dict[str, str]:
    raw = await request.body()
    settings = get_settings()
    sig = request.headers.get("crypto-pay-api-signature") or request.headers.get("Crypto-Pay-Api-Signature")
    if (
        settings.cryptobot_token
        and not settings.skip_webhook_signature
        and not cryptobot.verify_webhook_signature(raw, sig)
    ):
        log.warning("Invalid webhook signature")
        raise HTTPException(403, "bad signature")

    import json

    try:
        data = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        raise HTTPException(400, "invalid json")

    inv = cryptobot.extract_paid_invoice(data)
    if not inv:
        return {"ok": "ignored"}

    invoice_id = inv.get("invoice_id")
    await mark_payment_paid(
        session,
        invoice_id=int(invoice_id) if invoice_id is not None else None,
        amount=str(inv.get("amount", "")),
        asset=str(inv.get("asset", "USDT")),
        payload=str(inv.get("payload", "")),
    )
    return {"ok": "true"}


@router.post("/sync_pending", dependencies=[Depends(require_api_key)])
async def payment_sync(session: AsyncSession = Depends(get_db)) -> dict[str, int]:
    n = await sync_pending_from_cryptobot(session)
    return {"updated": n}

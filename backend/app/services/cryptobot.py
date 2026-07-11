from __future__ import annotations

import hashlib
import hmac
from typing import Any

import httpx

from app.config import get_settings


def _api_base() -> str:
    return "https://pay.crypt.bot/api"


def verify_webhook_signature(raw_body: bytes, signature_header: str | None) -> bool:
    settings = get_settings()
    token = settings.cryptobot_token
    if not token or not signature_header:
        return False
    # Crypto Pay: secret key = SHA256(api_token); signature = HMAC-SHA256(secret, body) hex
    secret = hashlib.sha256(token.encode("utf-8")).digest()
    expected = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
    try:
        return hmac.compare_digest(expected, signature_header)
    except Exception:
        return False


async def create_invoice(
    *,
    amount: str,
    asset: str = "USDT",
    description: str = "",
    payload: str = "",
    paid_btn_url: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.cryptobot_token:
        raise RuntimeError("CRYPTOBOT_TOKEN not configured")

    body: dict[str, Any] = {
        "amount": amount,
        "currency_type": "crypto",
        "asset": asset,
        "description": description or "VPN subscription",
        "payload": payload,
    }
    if paid_btn_url:
        body["paid_btn_name"] = "callback"
        body["paid_btn_url"] = paid_btn_url

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{_api_base()}/createInvoice",
            headers={"Crypto-Pay-Api-Token": settings.cryptobot_token},
            json=body,
        )
        r.raise_for_status()
        data = r.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("error", {}).get("name", "createInvoice failed"))
    return data["result"]


async def get_invoices(invoice_ids: list[int] | None = None) -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.cryptobot_token:
        raise RuntimeError("CRYPTOBOT_TOKEN not configured")
    body: dict[str, Any] = {}
    if invoice_ids:
        body["invoice_ids"] = invoice_ids
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{_api_base()}/getInvoices",
            headers={"Crypto-Pay-Api-Token": settings.cryptobot_token},
            json=body,
        )
        r.raise_for_status()
        data = r.json()
    if not data.get("ok"):
        raise RuntimeError("getInvoices failed")
    items = data.get("items") or data.get("result") or []
    if invoice_ids and items:
        wanted = set(invoice_ids)
        items = [i for i in items if int(i.get("invoice_id", 0)) in wanted]
    return items


def extract_paid_invoice(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Parse Crypto Pay webhook body (handles multiple payload formats)."""
    if not payload:
        return None
    ut = payload.get("update_type") or payload.get("type")
    if ut == "invoice_paid":
        inv = payload.get("payload") or payload.get("invoice") or payload
        if isinstance(inv, dict) and inv.get("status") == "paid":
            return inv
    inv = payload.get("invoice")
    if isinstance(inv, dict) and inv.get("status") == "paid":
        return inv
    if payload.get("status") == "paid" and payload.get("invoice_id"):
        return payload
    return None

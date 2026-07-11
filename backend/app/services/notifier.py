from __future__ import annotations

import logging

import sys
from pathlib import Path

import httpx

from app.config import get_settings

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from bot.locale import t  # noqa: E402

log = logging.getLogger(__name__)

BUY_INLINE_KEYBOARD = {
    "inline_keyboard": [[{"text": t("btn.choose_plan"), "callback_data": "buy"}]]
}


async def notify_user_telegram(
    telegram_id: int,
    text: str,
    *,
    reply_markup: dict | None = None,
) -> bool:
    settings = get_settings()
    if not settings.bot_token:
        return False
    url = f"https://api.telegram.org/bot{settings.bot_token}/sendMessage"
    payload: dict = {
        "chat_id": telegram_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(url, json=payload)
            data = r.json() if r.content else {}
            if not data.get("ok"):
                log.warning(
                    "notify_user_telegram failed chat_id=%s: %s",
                    telegram_id,
                    data.get("description") or r.text[:200],
                )
                return False
            return True
    except Exception as e:
        log.warning("notify_user_telegram error chat_id=%s: %s", telegram_id, e)
        return False


async def notify_admins(text: str) -> None:
    settings = get_settings()
    if not settings.bot_token or not settings.admin_ids_list:
        return
    url = f"https://api.telegram.org/bot{settings.bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=15.0) as client:
        for chat_id in settings.admin_ids_list:
            try:
                await client.post(
                    url,
                    json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
                )
            except Exception as e:
                log.warning("notify_admins failed for %s: %s", chat_id, e)

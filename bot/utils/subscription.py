from __future__ import annotations

import html
from datetime import datetime, timezone

from bot.locale import t


def parse_utc_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    s = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def subscription_is_live(user: dict) -> bool:
    if user.get("status") == "blocked":
        return False
    end = parse_utc_datetime(user.get("subscription_end"))
    if not end:
        return False
    return end > datetime.now(timezone.utc)


def show_profile_button(user: dict) -> bool:
    if user.get("trial_used"):
        return True
    if user.get("subscription_end"):
        return True
    st = user.get("status") or ""
    return st in ("paid", "expired")


def subscription_type_label(user: dict) -> str:
    st = user.get("status") or ""
    if st == "paid":
        return t("sub.paid")
    if st == "trial":
        return t("sub.trial")
    if st == "expired":
        return t("sub.expired")
    if st == "blocked":
        return t("sub.blocked")
    return t("sub.none")


def format_subscription_end(user: dict) -> str:
    end = parse_utc_datetime(user.get("subscription_end"))
    if not end:
        return "—"
    return end.strftime("%d.%m.%Y %H:%M UTC")


def escape_pre_block(text: str) -> str:
    return html.escape(text, quote=False)

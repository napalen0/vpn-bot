from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import CHANNEL_PUBLIC_URL
from bot.locale import t
from bot.utils.subscription import show_profile_button


def main_menu(user: dict | None = None, trial_days: int | None = None) -> InlineKeyboardMarkup:
    user = user or {}
    trial_used = bool(user.get("trial_used"))
    show_profile = show_profile_button(user)

    kb = InlineKeyboardBuilder()
    if not trial_used:
        if trial_days is not None and trial_days > 0:
            trial_label = t("btn.trial_days", trial_days=trial_days)
        else:
            trial_label = t("btn.trial")
        kb.row(InlineKeyboardButton(text=trial_label, callback_data="trial_day"))
    if show_profile:
        kb.row(InlineKeyboardButton(text=t("btn.profile"), callback_data="profile"))
    kb.row(InlineKeyboardButton(text=t("btn.buy"), callback_data="buy"))
    kb.row(InlineKeyboardButton(text=t("btn.invite"), callback_data="invite"))
    kb.row(InlineKeyboardButton(text=t("btn.channel"), callback_data="channel_page"))
    kb.row(InlineKeyboardButton(text=t("btn.help"), callback_data="help"))
    return kb.as_markup()


def channel_gate_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text=t("btn.subscribe"), url=CHANNEL_PUBLIC_URL))
    kb.row(InlineKeyboardButton(text=t("btn.check"), callback_data="check_channel"))
    return kb.as_markup()


def channel_page_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text=t("btn.go_channel"), url=CHANNEL_PUBLIC_URL))
    kb.row(InlineKeyboardButton(text=t("btn.back"), callback_data="main"))
    return kb.as_markup()


def back_main() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text=t("btn.back_menu"), callback_data="main"))
    return kb.as_markup()


def profile_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text=t("btn.config"), callback_data="profile_config"))
    kb.row(InlineKeyboardButton(text=t("btn.language"), callback_data="profile_lang"))
    kb.row(InlineKeyboardButton(text=t("btn.back_menu"), callback_data="main"))
    return kb.as_markup()


def profile_kb_expanded() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text=t("btn.refresh_config"), callback_data="profile_config"))
    kb.row(InlineKeyboardButton(text=t("btn.profile_pin"), callback_data="profile"))
    kb.row(InlineKeyboardButton(text=t("btn.back_menu"), callback_data="main"))
    return kb.as_markup()


def tariffs(prices: dict[str, str]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text=t("btn.tariff", days="7", price=prices.get('7', '?')), callback_data="pay_7"),
        InlineKeyboardButton(text=t("btn.tariff", days="30", price=prices.get('30', '?')), callback_data="pay_30"),
    )
    kb.row(InlineKeyboardButton(text=t("btn.tariff", days="90", price=prices.get('90', '?')), callback_data="pay_90"))
    kb.row(InlineKeyboardButton(text=t("btn.back_menu"), callback_data="main"))
    return kb.as_markup()


def pay_url(url: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text=t("btn.pay_crypto"), url=url))
    kb.row(InlineKeyboardButton(text=t("btn.back_menu"), callback_data="main"))
    return kb.as_markup()


def language_selector_kb(current: str = "", source: str = "start") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    ru_label = "✅ RU" if current == "ru" else "🇷🇺 RU"
    en_label = "✅ EN" if current == "en" else "🇬🇧 EN"
    kb.row(
        InlineKeyboardButton(text=ru_label, callback_data=f"lang_ru_{source}"),
        InlineKeyboardButton(text=en_label, callback_data=f"lang_en_{source}"),
    )
    if source == "profile":
        kb.row(InlineKeyboardButton(text=t("btn.back"), callback_data="profile"))
    return kb.as_markup()

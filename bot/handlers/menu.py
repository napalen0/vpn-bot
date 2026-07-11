from __future__ import annotations

import logging
import re
from html import escape as html_escape
from urllib.parse import quote

import httpx
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot.client import BackendClient
from bot.config import (
    PUBLIC_BASE_URL,
    REQUIRE_CHANNEL_SUBSCRIPTION,
    REQUIRED_CHANNEL_USERNAME,
    main_menu_image_path,
)
from bot.keyboards import (
    back_main,
    channel_gate_kb,
    channel_page_kb,
    language_selector_kb,
    main_menu,
    pay_url,
    profile_kb,
    profile_kb_expanded,
    tariffs,
)
from bot.locale import set_lang, t
from bot.utils.channel import user_subscribed_to_channel
from bot.utils.subscription import (
    escape_pre_block,
    format_subscription_end,
    show_profile_button,
    subscription_is_live,
    subscription_type_label,
)
from bot.utils.ui import render

log = logging.getLogger(__name__)
router = Router()

_REF_RE = re.compile(r"^ref_(\d+)$")


def _trial_days_from_catalog(cat: dict) -> int | None:
    try:
        return max(1, min(365, int(cat.get("trial_days", 1))))
    except (TypeError, ValueError):
        return None


async def _main_menu_markup(client: BackendClient, user: dict) -> InlineKeyboardMarkup:
    try:
        cat = await client.catalog()
        return main_menu(user, trial_days=_trial_days_from_catalog(cat))
    except Exception:
        return main_menu(user)

TG_MSG_MAX = 4096


class UiState(StatesGroup):
    main = State()


def _main_text(first_name: str | None) -> str:
    name = first_name or t("menu.default_name")
    return t("menu.greeting", name=name)


def _instruction(trial_days: int | None = None) -> str:
    trial_line = (
        t("help.trial_with_days", trial_days=trial_days)
        if trial_days
        else t("help.trial_default")
    )
    return t("help.body", trial_line=trial_line)


def _profile_text(user: dict) -> str:
    live = subscription_is_live(user)
    state_line = t("profile.access_active") if live else t("profile.access_inactive")
    return t(
        "profile.text",
        sub_type=subscription_type_label(user),
        sub_end=format_subscription_end(user),
        state_line=state_line,
    )


def _sub_url_line(user: dict) -> str:
    token = (user.get("sub_token") or "").strip()
    if not token or not PUBLIC_BASE_URL:
        return ""
    url = f"{PUBLIC_BASE_URL}/vpn/sub/{token}"
    return t("profile.sub_url_header") + f"<code>{html_escape(url)}</code>\n"


def _profile_vless_message(user: dict, blocks: list[dict]) -> str:
    live = subscription_is_live(user)
    state_line = t("profile.access_active") if live else t("profile.access_inactive")
    head = (
        f"{t('profile.heading')}\n"
        f"{html_escape(subscription_type_label(user))} · "
        f"{t('profile.until', end=html_escape(format_subscription_end(user)))}\n"
        f"{state_line}\n"
    )
    sub_line = _sub_url_line(user)
    head += sub_line
    head += t("profile.copy_manual")
    bullets = "\n".join(
        f"• {html_escape((b.get('caption') or '').strip())}" for b in blocks if b.get("vless_uri")
    )
    uris = "\n\n".join((b.get("vless_uri") or "").strip() for b in blocks if b.get("vless_uri"))
    body = f"{bullets}\n\n<pre>{escape_pre_block(uris)}</pre>"
    full = head + body
    if len(full) <= TG_MSG_MAX:
        return full
    return head + t("profile.too_many")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, client: BackendClient):
    await state.set_state(UiState.main)
    ref_tid = None
    if message.text and " " in message.text:
        arg = message.text.split(maxsplit=1)[1].strip()
        m = _REF_RE.match(arg)
        if m:
            ref_tid = int(m.group(1))

    tg_lang = (message.from_user.language_code or "")[:2].lower()
    initial_lang = tg_lang if tg_lang in ("ru", "en") else "ru"

    try:
        user_data = await client.user_create(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            referrer_telegram_id=ref_tid,
            language=initial_lang,
        )
    except Exception as e:
        log.exception("user_create")
        await message.answer(t("error.service", detail=e))
        return

    saved_lang = user_data.get("language", "ru")
    set_lang(saved_lang)
    await state.update_data(lang=saved_lang)

    fsm_data = await state.get_data()
    if not fsm_data.get("lang_chosen"):
        await render(message, state, t("lang.choose"), language_selector_kb())
        return

    if REQUIRE_CHANNEL_SUBSCRIPTION and REQUIRED_CHANNEL_USERNAME:
        if not await user_subscribed_to_channel(
            message.bot, message.from_user.id, REQUIRED_CHANNEL_USERNAME
        ):
            await render(message, state, t("gate.subscribe_prompt"), channel_gate_kb())
            return

    try:
        u = await client.user_by_telegram(message.from_user.id)
    except Exception as e:
        log.exception("user_by_telegram")
        await message.answer(t("error.load", detail=e))
        return

    await render(
        message,
        state,
        _main_text(message.from_user.first_name),
        await _main_menu_markup(client, u),
        photo=main_menu_image_path(),
    )


@router.callback_query(F.data.startswith("lang_"))
async def cb_language(call: CallbackQuery, state: FSMContext, client: BackendClient):
    parts = call.data.split("_")
    lang = parts[1] if len(parts) >= 2 else "ru"
    source = parts[2] if len(parts) >= 3 else "start"
    if lang not in ("ru", "en"):
        lang = "ru"

    set_lang(lang)
    await state.update_data(lang=lang, lang_chosen=True)

    try:
        await client.set_language(call.from_user.id, lang)
    except Exception:
        log.exception("set_language")

    if source == "profile":
        try:
            user = await client.user_by_telegram(call.from_user.id)
            if not show_profile_button(user):
                await render(
                    call, state,
                    t("profile.no_access"),
                    await _main_menu_markup(client, user),
                    photo=main_menu_image_path(),
                )
                return
            await render(call, state, _profile_text(user), profile_kb())
        except Exception as e:
            log.exception("lang→profile")
            await render(call, state, t("error.generic", detail=e), back_main())
        return

    if REQUIRE_CHANNEL_SUBSCRIPTION and REQUIRED_CHANNEL_USERNAME:
        if not await user_subscribed_to_channel(
            call.bot, call.from_user.id, REQUIRED_CHANNEL_USERNAME
        ):
            await render(call, state, t("gate.subscribe_prompt"), channel_gate_kb())
            return

    try:
        u = await client.user_by_telegram(call.from_user.id)
    except Exception as e:
        log.exception("user_by_telegram")
        await call.answer(t("error.load", detail=e))
        return

    await render(
        call,
        state,
        _main_text(call.from_user.first_name),
        await _main_menu_markup(client, u),
        photo=main_menu_image_path(),
    )


@router.callback_query(F.data == "check_channel")
async def cb_check_channel(call: CallbackQuery, state: FSMContext, client: BackendClient):
    if REQUIRE_CHANNEL_SUBSCRIPTION and REQUIRED_CHANNEL_USERNAME:
        if not await user_subscribed_to_channel(
            call.bot, call.from_user.id, REQUIRED_CHANNEL_USERNAME
        ):
            await call.answer(t("gate.not_visible"), show_alert=True)
            return
    await call.answer()
    try:
        u = await client.user_by_telegram(call.from_user.id)
    except Exception as e:
        log.exception("check_channel user_by_telegram")
        await render(call, state, t("error.generic", detail=e), back_main())
        return
    await render(
        call,
        state,
        _main_text(call.from_user.first_name),
        await _main_menu_markup(client, u),
        photo=main_menu_image_path(),
    )


@router.callback_query(F.data == "channel_page")
async def cb_channel_page(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await render(
        call,
        state,
        t("channel.page"),
        channel_page_kb(),
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data == "main")
async def cb_main(call: CallbackQuery, state: FSMContext, client: BackendClient):
    await call.answer()
    try:
        u = await client.user_by_telegram(call.from_user.id)
    except Exception as e:
        log.exception("user_by_telegram")
        await render(call, state, t("error.generic", detail=e), back_main())
        return
    await render(
        call,
        state,
        _main_text(call.from_user.first_name),
        await _main_menu_markup(client, u),
        photo=main_menu_image_path(),
    )


@router.callback_query(F.data == "help")
async def cb_help(call: CallbackQuery, state: FSMContext, client: BackendClient):
    await call.answer()
    td: int | None = None
    try:
        td = _trial_days_from_catalog(await client.catalog())
    except Exception:
        pass
    await render(call, state, _instruction(td), back_main(), parse_mode=ParseMode.HTML)


@router.callback_query(F.data == "invite")
async def cb_invite(call: CallbackQuery, state: FSMContext, client: BackendClient):
    await call.answer()
    try:
        cat = await client.catalog()
        un = (cat.get("bot_username") or "").strip().lstrip("@")
        if not un:
            un = (await call.bot.get_me()).username or "your_bot"
        me = call.from_user.id
        link = f"https://t.me/{un}?start=ref_{me}"
        bonus = cat.get("referral_bonus_days", 3)
        min_d = cat.get("referral_min_plan_days", 30)
        text = t("invite.your_link", link=link, bonus=bonus, min_days=min_d)
        share = f"https://t.me/share/url?url={quote(link)}&text={quote('VPN')}"
        from aiogram.types import InlineKeyboardButton
        from aiogram.utils.keyboard import InlineKeyboardBuilder

        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text=t("btn.share"), url=share))
        kb.row(InlineKeyboardButton(text=t("btn.back_menu"), callback_data="main"))
        await render(call, state, text, kb.as_markup())
    except Exception as e:
        log.exception("invite")
        await render(call, state, t("error.generic", detail=e), back_main())


@router.callback_query(F.data == "trial_day")
async def cb_trial_day(call: CallbackQuery, state: FSMContext, client: BackendClient):
    await call.answer()
    tg = call.from_user.id
    try:
        user = await client.user_by_telegram(tg)
        uid = user["id"]
        if user.get("trial_used"):
            await render(
                call,
                state,
                t("trial.already_used"),
                await _main_menu_markup(client, user),
                photo=main_menu_image_path(),
            )
            return
        try:
            key = await client.create_trial(uid)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400:
                user = await client.user_by_telegram(tg)
                await render(
                    call,
                    state,
                    t("trial.unavailable"),
                    await _main_menu_markup(client, user),
                    photo=main_menu_image_path(),
                )
                return
            raise
        uri = key.get("vless_uri", "")
        user = await client.user_by_telegram(tg)
        sub_line = _sub_url_line(user)
        text = (
            t("trial.activated")
            + f"{sub_line}\n"
            + t("trial.copy_link")
            + f"<pre>{escape_pre_block(uri)}</pre>"
        )
        await render(
            call,
            state,
            text,
            await _main_menu_markup(client, user),
            parse_mode=ParseMode.HTML,
            photo=main_menu_image_path(),
        )
    except Exception as e:
        log.exception("trial_day")
        try:
            u = await client.user_by_telegram(tg)
            await render(
                call,
                state,
                t("error.generic", detail=e),
                await _main_menu_markup(client, u),
                photo=main_menu_image_path(),
            )
        except Exception:
            await render(call, state, t("error.generic", detail=e), back_main())


@router.callback_query(F.data == "profile")
async def cb_profile(call: CallbackQuery, state: FSMContext, client: BackendClient):
    await call.answer()
    try:
        user = await client.user_by_telegram(call.from_user.id)
        if not show_profile_button(user):
            await render(
                call,
                state,
                t("profile.no_access"),
                await _main_menu_markup(client, user),
                photo=main_menu_image_path(),
            )
            return
        await render(call, state, _profile_text(user), profile_kb())
    except Exception as e:
        log.exception("profile")
        await render(call, state, t("error.generic", detail=e), back_main())


@router.callback_query(F.data == "profile_lang")
async def cb_profile_lang(call: CallbackQuery, state: FSMContext):
    await call.answer()
    fsm = await state.get_data()
    current = fsm.get("lang", "ru")
    await render(call, state, t("lang.choose"), language_selector_kb(current, source="profile"))


@router.callback_query(F.data == "profile_config")
async def cb_profile_config(call: CallbackQuery, state: FSMContext, client: BackendClient):
    await call.answer()
    tg = call.from_user.id
    try:
        user = await client.user_by_telegram(tg)
        uid = user["id"]
        if not subscription_is_live(user):
            await render(call, state, t("profile.sub_inactive"), profile_kb())
            return
        try:
            data = await client.vless_export(uid)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400:
                await render(call, state, t("profile.config_unavailable"), profile_kb())
                return
            raise
        blocks = data.get("blocks")
        if not isinstance(blocks, list) or not blocks:
            vless_text = (data.get("vless_text") or "").strip()
            if not vless_text:
                await render(call, state, t("profile.no_config_data"), profile_kb())
                return
            blocks = [{"caption": "", "vless_uri": line} for line in vless_text.splitlines() if line.strip()]
        text = _profile_vless_message(user, blocks)
        await render(call, state, text, profile_kb_expanded(), parse_mode=ParseMode.HTML)
    except Exception as e:
        log.exception("profile_config")
        try:
            await render(call, state, t("error.generic", detail=e), profile_kb())
        except Exception:
            await render(call, state, t("error.generic", detail=e), back_main())


@router.callback_query(F.data == "buy")
async def cb_buy(call: CallbackQuery, state: FSMContext, client: BackendClient):
    await call.answer()
    try:
        cat = await client.catalog()
        p = cat.get("prices") or {}
        await render(
            call,
            state,
            t("buy.choose_plan"),
            tariffs({str(k): str(v) for k, v in p.items()}),
        )
    except Exception as e:
        log.exception("buy")
        await render(call, state, t("error.generic", detail=e), back_main())


@router.callback_query(F.data.startswith("pay_"))
async def cb_pay_plan(call: CallbackQuery, state: FSMContext, client: BackendClient):
    await call.answer()
    plan = call.data.replace("pay_", "")
    days_map = {"7": 7, "30": 30, "90": 90}
    days = days_map.get(plan)
    if not days:
        return
    try:
        cat = await client.catalog()
        prices = cat.get("prices") or {}
        amount = str(prices.get(plan, "0"))
        user = await client.user_by_telegram(call.from_user.id)
        inv = await client.create_invoice(user["id"], days, amount)
        url = inv.get("bot_invoice_url") or inv.get("mini_app_invoice_url") or inv.get("web_app_invoice_url")
        if not url:
            await render(
                call,
                state,
                t("buy.link_error"),
                await _main_menu_markup(client, user),
                photo=main_menu_image_path(),
            )
            return
        await render(
            call,
            state,
            t("buy.payment_prompt", days=days, amount=amount),
            pay_url(url),
        )
    except Exception as e:
        log.exception("pay")
        try:
            u = await client.user_by_telegram(call.from_user.id)
            await render(
                call,
                state,
                t("error.payment", detail=e),
                await _main_menu_markup(client, u),
                photo=main_menu_image_path(),
            )
        except Exception:
            await render(call, state, t("error.payment", detail=e), back_main())

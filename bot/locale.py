"""Multi-language locale strings for the Telegram bot.

Two-level dict: lang → key → display string.  The active language is
stored in a contextvar set by the locale middleware on every update.
Existing t(key, **kwargs) calls keep working without changes.
"""

from __future__ import annotations

import contextvars

_current_lang: contextvars.ContextVar[str] = contextvars.ContextVar("lang", default="ru")

SUPPORTED_LANGS = ("ru", "en")


def set_lang(lang: str) -> None:
    _current_lang.set(lang if lang in SUPPORTED_LANGS else "ru")


def get_lang() -> str:
    return _current_lang.get()


_STRINGS: dict[str, dict[str, str]] = {
    # ── Russian ───────────────────────────────────────────────
    "ru": {
        # -- Language picker --
        "lang.choose": "🌐 Выберите язык / Choose language:",

        # -- Channel gate --
        "gate.subscribe_prompt": (
            "Чтобы пользоваться ботом, подпишись на наш канал.\n\n"
            "Нажми «Подписаться», затем «Проверить»."
        ),
        "gate.not_visible": (
            "Подписка не видна. Зайди в канал, "
            "нажми «Подписаться» и снова «Проверить»."
        ),
        "gate.subscribe_first_msg": (
            "Сначала подпишитесь на канал. "
            "Откройте /start — там будет ссылка и кнопка «Проверить»."
        ),
        "gate.subscribe_first_cb": "Нужна подписка на канал. Нажмите /start.",

        # -- Channel page --
        "channel.page": (
            "📢 <b>Канал сервиса</b>\n\n"
            "Здесь собираем всё важное:\n"
            "• новости и обновления VPN;\n"
            "• розыгрыши подписок и акции;\n"
            "• бесплатные прокси для Telegram и не только.\n\n"
            "Подпишись — не пропусти раздачи и анонсы."
        ),

        # -- Main menu --
        "menu.greeting": "👋 Привет, {name}!\n\nВыберите пункт в меню ниже.",
        "menu.default_name": "друг",

        # -- Help / instruction --
        "help.trial_with_days": (
            "Пробный период — до {trial_days} дн., выдаётся одна ссылка.\n"
        ),
        "help.trial_default": (
            "Пробный период — одна ссылка, срок задаётся сервисом.\n"
        ),
        "help.body": (
            "\U0001f4d6 Как это работает\n\n"
            "{trial_line}"
            "Подписка — в «Профиль» → «Конфиг» приходит ссылка подписки + конфиги.\n"
            "Оплата — USDT через Crypto Bot.\n\n"
            "\U0001f4f2 Как подключиться\n"
            "1. Установите V2Ray / Hiddify / Happ.\n"
            "2. В «Профиль» → «Конфиг» скопируйте ссылку подписки.\n"
            "3. В приложении: «Подписка» / «Добавить из ссылки» — "
            "вставьте и включите.\n\n"
            "Ссылка подписки автоматически обновляет список серверов."
        ),

        # -- Profile --
        "profile.heading": "👤 Профиль",
        "profile.until": "до {end}",
        "profile.access_active": "Доступ: активен",
        "profile.access_inactive": "Доступ: не активен",
        "profile.text": (
            "👤 Профиль\n"
            "{sub_type} · до {sub_end}\n"
            "{state_line}\n\n"
            "«Конфиг» — ссылки для приложения."
        ),
        "profile.sub_url_header": (
            "\n\U0001f4f2 <b>Ссылка подписки</b> "
            "(вставьте в V2Ray / Hiddify / Happ):\n"
        ),
        "profile.copy_manual": "\nИли скопируйте конфиг вручную:\n\n",
        "profile.too_many": "Много ссылок — используйте ссылку подписки выше.\n",
        "profile.no_access": (
            "Сначала включите пробный период или купите подписку."
        ),
        "profile.sub_inactive": "Подписка не активна. Раздел «Купить».",
        "profile.config_unavailable": "Конфиг сейчас недоступен. Попробуйте позже.",
        "profile.no_config_data": "Нет данных конфига.",

        # -- Subscription type labels --
        "sub.paid": "Платная подписка",
        "sub.trial": "Пробный период",
        "sub.expired": "Подписка истекла",
        "sub.blocked": "Доступ заблокирован",
        "sub.none": "Без подписки",

        # -- Trial --
        "trial.already_used": (
            "Пробный период уже был. Оформите подписку в «Купить»."
        ),
        "trial.unavailable": (
            "Пробный доступ сейчас недоступен. "
            "Попробуйте позже или оформите подписку."
        ),
        "trial.activated": "✅ Пробный доступ включён.\n",
        "trial.copy_link": "Или скопируйте ссылку в приложение:\n\n",

        # -- Buy / payment --
        "buy.choose_plan": "💳 Выберите тариф (USDT, Crypto Bot):",
        "buy.payment_prompt": "💳 {days} дн. · {amount} USDT\n\nОплата:",
        "buy.link_error": "Не удалось получить ссылку на оплату.",

        # -- Invite --
        "invite.your_link": (
            "👥 Ваша ссылка:\n{link}\n\n"
            "Бонус +{bonus} дн., если друг купит от {min_days} дн."
        ),

        # -- Errors --
        "error.service": "Сервис недоступен. {detail}",
        "error.load": "Не удалось загрузить данные. {detail}",
        "error.generic": "Ошибка: {detail}",
        "error.payment": "Ошибка оплаты: {detail}",

        # -- Keyboard buttons --
        "btn.trial_days": "🎁 Триал {trial_days} дн.",
        "btn.trial": "🎁 Пробный период",
        "btn.profile": "👤 Профиль",
        "btn.buy": "💳 Купить",
        "btn.invite": "👥 Пригласить",
        "btn.channel": "📢 Канал",
        "btn.help": "❓ Как пользоваться",
        "btn.subscribe": "📢 Подписаться",
        "btn.check": "✅ Проверить",
        "btn.go_channel": "🔗 Перейти в канал",
        "btn.back": "◀️ Назад",
        "btn.back_menu": "◀️ В меню",
        "btn.config": "📋 Конфиг",
        "btn.refresh_config": "🔄 Обновить конфиг",
        "btn.profile_pin": "📌 Профиль",
        "btn.tariff": "{days} дн. — {price} USDT",
        "btn.pay_crypto": "💳 Оплатить в CryptoBot",
        "btn.share": "📤 Поделиться",
        "btn.choose_plan": "💳 Выбрать тариф",
        "btn.language": "🌐 Язык",

        # -- Notification messages (backend → user TG) --
        "notify.trial_ended": (
            "Пробный период закончился. Продлить доступ — кнопка ниже."
        ),
        "notify.sub_expired": (
            "Подписка закончилась. Продлить — кнопка ниже."
        ),
        "notify.sub_3d_warning": (
            "Подписка скоро закончится (около 3 дней). "
            "Продлить — кнопка ниже."
        ),

        # -- Paid landing (HTML page after payment) --
        "paid.landing": (
            "✅ Оплата принята. "
            "Вернитесь в Telegram-бот — доступ обновится автоматически."
        ),
    },

    # ── English ───────────────────────────────────────────────
    "en": {
        # -- Language picker --
        "lang.choose": "🌐 Choose language / Выберите язык:",

        # -- Channel gate --
        "gate.subscribe_prompt": (
            "To use the bot, subscribe to our channel.\n\n"
            "Tap \"Subscribe\", then \"Check\"."
        ),
        "gate.not_visible": (
            "Subscription not detected. Open the channel, "
            "tap \"Subscribe\" and then \"Check\" again."
        ),
        "gate.subscribe_first_msg": (
            "Please subscribe to the channel first. "
            "Open /start — you'll find a link and a \"Check\" button."
        ),
        "gate.subscribe_first_cb": "Channel subscription required. Tap /start.",

        # -- Channel page --
        "channel.page": (
            "📢 <b>Service Channel</b>\n\n"
            "Stay updated:\n"
            "• VPN news and updates;\n"
            "• Subscription giveaways and promos;\n"
            "• Free proxies for Telegram and more.\n\n"
            "Subscribe — don't miss announcements."
        ),

        # -- Main menu --
        "menu.greeting": "👋 Hi, {name}!\n\nChoose an option below.",
        "menu.default_name": "friend",

        # -- Help / instruction --
        "help.trial_with_days": (
            "Free trial — up to {trial_days} days, one config link.\n"
        ),
        "help.trial_default": (
            "Free trial — one config link, duration set by the service.\n"
        ),
        "help.body": (
            "\U0001f4d6 How it works\n\n"
            "{trial_line}"
            "Subscription — go to \"Profile\" → \"Config\" to get your subscription link + configs.\n"
            "Payment — USDT via Crypto Bot.\n\n"
            "\U0001f4f2 How to connect\n"
            "1. Install V2Ray / Hiddify / Happ.\n"
            "2. In \"Profile\" → \"Config\" copy the subscription link.\n"
            "3. In the app: \"Subscription\" / \"Add from link\" — "
            "paste and enable.\n\n"
            "The subscription link automatically updates the server list."
        ),

        # -- Profile --
        "profile.heading": "👤 Profile",
        "profile.until": "until {end}",
        "profile.access_active": "Access: active",
        "profile.access_inactive": "Access: inactive",
        "profile.text": (
            "👤 Profile\n"
            "{sub_type} · until {sub_end}\n"
            "{state_line}\n\n"
            "\"Config\" — links for your VPN app."
        ),
        "profile.sub_url_header": (
            "\n\U0001f4f2 <b>Subscription link</b> "
            "(paste into V2Ray / Hiddify / Happ):\n"
        ),
        "profile.copy_manual": "\nOr copy the config manually:\n\n",
        "profile.too_many": "Too many links — use the subscription link above.\n",
        "profile.no_access": (
            "Activate a free trial or purchase a subscription first."
        ),
        "profile.sub_inactive": "Subscription inactive. See \"Buy\".",
        "profile.config_unavailable": "Config unavailable right now. Try again later.",
        "profile.no_config_data": "No config data.",

        # -- Subscription type labels --
        "sub.paid": "Paid subscription",
        "sub.trial": "Free trial",
        "sub.expired": "Subscription expired",
        "sub.blocked": "Access blocked",
        "sub.none": "No subscription",

        # -- Trial --
        "trial.already_used": (
            "Free trial already used. Purchase a subscription in \"Buy\"."
        ),
        "trial.unavailable": (
            "Free trial is currently unavailable. "
            "Try again later or purchase a subscription."
        ),
        "trial.activated": "✅ Free trial activated.\n",
        "trial.copy_link": "Or copy the link into your app:\n\n",

        # -- Buy / payment --
        "buy.choose_plan": "💳 Choose a plan (USDT, Crypto Bot):",
        "buy.payment_prompt": "💳 {days} days · {amount} USDT\n\nPayment:",
        "buy.link_error": "Failed to get payment link.",

        # -- Invite --
        "invite.your_link": (
            "👥 Your link:\n{link}\n\n"
            "Bonus +{bonus} days if a friend buys {min_days}+ days."
        ),

        # -- Errors --
        "error.service": "Service unavailable. {detail}",
        "error.load": "Failed to load data. {detail}",
        "error.generic": "Error: {detail}",
        "error.payment": "Payment error: {detail}",

        # -- Keyboard buttons --
        "btn.trial_days": "🎁 Trial {trial_days} days",
        "btn.trial": "🎁 Free trial",
        "btn.profile": "👤 Profile",
        "btn.buy": "💳 Buy",
        "btn.invite": "👥 Invite",
        "btn.channel": "📢 Channel",
        "btn.help": "❓ How to use",
        "btn.subscribe": "📢 Subscribe",
        "btn.check": "✅ Check",
        "btn.go_channel": "🔗 Go to channel",
        "btn.back": "◀️ Back",
        "btn.back_menu": "◀️ Menu",
        "btn.config": "📋 Config",
        "btn.refresh_config": "🔄 Refresh config",
        "btn.profile_pin": "📌 Profile",
        "btn.tariff": "{days} days — {price} USDT",
        "btn.pay_crypto": "💳 Pay via CryptoBot",
        "btn.share": "📤 Share",
        "btn.choose_plan": "💳 Choose plan",
        "btn.language": "🌐 Language",

        # -- Notification messages (backend → user TG) --
        "notify.trial_ended": (
            "Your free trial has ended. Extend access — button below."
        ),
        "notify.sub_expired": (
            "Your subscription has expired. Renew — button below."
        ),
        "notify.sub_3d_warning": (
            "Your subscription expires in about 3 days. "
            "Renew — button below."
        ),

        # -- Paid landing (HTML page after payment) --
        "paid.landing": (
            "✅ Payment received. "
            "Return to the Telegram bot — access will update automatically."
        ),
    },
}


def t(key: str, **kwargs: object) -> str:
    """Look up a locale string by key in the current language."""
    lang = _current_lang.get()
    val = _STRINGS.get(lang, {}).get(key)
    if val is None:
        val = _STRINGS.get("en", {}).get(key)
    if val is None:
        return key
    if kwargs:
        return val.format(**kwargs)
    return val

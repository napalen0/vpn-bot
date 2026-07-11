"""User-facing locale strings for the Telegram bot.

English keys map to Russian display text. Code references keys via t(),
keeping the codebase English-only while preserving Russian for end users.
"""

from __future__ import annotations

_STRINGS: dict[str, str] = {
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
}


def t(key: str, **kwargs: object) -> str:
    """Look up a locale string by key, with optional format parameters."""
    val = _STRINGS.get(key)
    if val is None:
        return key
    if kwargs:
        return val.format(**kwargs)
    return val

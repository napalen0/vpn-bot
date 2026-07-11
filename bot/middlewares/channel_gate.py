from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.config import REQUIRE_CHANNEL_SUBSCRIPTION, REQUIRED_CHANNEL_USERNAME
from bot.locale import t
from bot.utils.channel import user_subscribed_to_channel

log = logging.getLogger(__name__)


class ChannelSubscriptionMiddleware(BaseMiddleware):
    """Without channel subscription only /start and subscription check are allowed."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not REQUIRE_CHANNEL_SUBSCRIPTION or not REQUIRED_CHANNEL_USERNAME:
            return await handler(event, data)

        bot = data.get("bot")
        if bot is None:
            return await handler(event, data)

        if isinstance(event, Message):
            if event.text and event.text.startswith("/start"):
                return await handler(event, data)
            uid = event.from_user.id if event.from_user else None
            if uid is None:
                return await handler(event, data)
            if await user_subscribed_to_channel(bot, uid, REQUIRED_CHANNEL_USERNAME):
                return await handler(event, data)
            await event.answer(t("gate.subscribe_first_msg"))
            return None

        if isinstance(event, CallbackQuery):
            if event.data == "check_channel":
                return await handler(event, data)
            uid = event.from_user.id if event.from_user else None
            if uid is None:
                return await handler(event, data)
            if await user_subscribed_to_channel(bot, uid, REQUIRED_CHANNEL_USERNAME):
                return await handler(event, data)
            await event.answer(t("gate.subscribe_first_cb"), show_alert=True)
            return None

        return await handler(event, data)

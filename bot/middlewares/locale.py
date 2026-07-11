"""Middleware that sets the active locale per Telegram update."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.locale import set_lang


class LocaleMiddleware(BaseMiddleware):
    """Read language from FSM data and activate it via set_lang()."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        state = data.get("state")
        if state:
            fsm_data = await state.get_data()
            lang = fsm_data.get("lang", "ru")
            set_lang(lang)
        return await handler(event, data)

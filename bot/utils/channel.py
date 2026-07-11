from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest

log = logging.getLogger(__name__)


async def user_subscribed_to_channel(bot: Bot, user_id: int, channel_username: str) -> bool:
    """Check channel subscription (bot must be a channel admin)."""
    u = (channel_username or "").strip().lstrip("@")
    if not u:
        return True
    chat_id = f"@{u}"
    try:
        m = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
    except TelegramBadRequest as e:
        log.warning("get_chat_member %s for user %s: %s", chat_id, user_id, e)
        return False
    return m.status in (
        ChatMemberStatus.CREATOR,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.RESTRICTED,
    )

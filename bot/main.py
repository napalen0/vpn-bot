from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.fsm.storage.memory import MemoryStorage

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.client import BackendClient
from bot.config import BOT_TOKEN
from bot.handlers.menu import router as menu_router
from bot.middlewares.channel_gate import ChannelSubscriptionMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


class ClientMiddleware(BaseMiddleware):
    def __init__(self, c: BackendClient) -> None:
        self._c = c

    async def __call__(self, handler, event, data):
        data["client"] = self._c
        return await handler(event, data)


async def main() -> None:
    if not BOT_TOKEN:
        log.error("Set BOT_TOKEN in .env")
        return

    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(menu_router)

    client = BackendClient()
    dp.update.middleware(ChannelSubscriptionMiddleware())
    dp.update.middleware(ClientMiddleware(client))

    try:
        log.info("Bot starting…")
        await dp.start_polling(bot)
    finally:
        await client.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

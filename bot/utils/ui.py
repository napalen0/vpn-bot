"""Single-message UI: edit text/keyboard in place."""

from __future__ import annotations

import logging
from pathlib import Path

from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

log = logging.getLogger(__name__)


def _resolve_photo(photo: Path | str | None) -> Path | None:
    if photo is None:
        return None
    p = Path(photo)
    return p if p.is_file() else None


async def render(
    event: Message | CallbackQuery,
    state: FSMContext,
    text: str,
    reply_markup=None,
    *,
    parse_mode: str | None = None,
    photo: Path | str | None = None,
) -> None:
    data = await state.get_data()
    message = event.message if isinstance(event, CallbackQuery) else event
    msg_id = data.get("msg_id")
    msg_is_photo = data.get("msg_is_photo", False)
    photo_path = _resolve_photo(photo)

    if photo_path:
        if msg_id:
            try:
                await message.bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
            except TelegramBadRequest:
                pass
        sent = await message.answer_photo(
            FSInputFile(photo_path),
            caption=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
        await state.update_data(msg_id=sent.message_id, msg_is_photo=True)
        return

    if msg_is_photo and msg_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
        except TelegramBadRequest:
            pass
        await state.update_data(msg_id=None, msg_is_photo=False)
        msg_id = None

    if not msg_id:
        sent = await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
        await state.update_data(msg_id=sent.message_id, msg_is_photo=False)
        return

    try:
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=msg_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
    except TelegramBadRequest as e:
        err = str(e)
        if "message to edit not found" in err or "message is not modified" in err:
            if "message is not modified" not in err:
                sent = await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
                await state.update_data(msg_id=sent.message_id, msg_is_photo=False)
        else:
            log.error("render: %s", e)
    except TelegramNetworkError as e:
        log.error("render network: %s", e)
    except Exception as e:
        log.error("render: %s", e)

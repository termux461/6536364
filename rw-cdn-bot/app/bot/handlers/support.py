from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot import texts
from app.config import get_settings

router = Router(name="support")


@router.message(Command("support"))
async def support(message: Message) -> None:
    await message.answer(texts.SUPPORT.format(username=get_settings().support_username))

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.keyboards import how_it_works_keyboard, main_menu
from app.config import get_settings
from app.repositories import SettingRepository

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(texts.START, reply_markup=main_menu())
    await message.answer(texts.REQUIREMENTS, reply_markup=how_it_works_keyboard())


@router.message(F.text == "🚀 Автонастройка")
async def autosetup(message: Message) -> None:
    await message.answer(texts.START, reply_markup=how_it_works_keyboard())


@router.message(F.text == "📖 Инструкция")
async def instruction(message: Message, session: AsyncSession) -> None:
    custom = await SettingRepository(session).instruction_text()
    await message.answer(custom or texts.HOW_IT_WORKS, reply_markup=how_it_works_keyboard())


@router.callback_query(F.data == "order:how")
async def how_it_works(callback: CallbackQuery) -> None:
    await callback.message.answer(texts.HOW_IT_WORKS)
    await callback.answer()


@router.message(F.text == "🆘 Поддержка")
async def support(message: Message) -> None:
    await message.answer(texts.SUPPORT.format(username=get_settings().support_username))

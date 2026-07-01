from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.i18n import t
from bot.keyboards.admin import admin_main_keyboard
from bot.keyboards.common import main_menu_keyboard
from database.models import User
from sqlalchemy.ext.asyncio import AsyncSession

router = Router(name="admin_entry")


@router.message(Command("admin"))
async def admin_entry(message: Message, locale: str, is_admin: bool) -> None:
    if not is_admin:
        await message.answer(t(locale, "admin.not_allowed"))
        return
    await message.answer(t(locale, "admin.menu"), reply_markup=admin_main_keyboard())


@router.message(lambda m: m.text == "⬅️ Выйти из админки")
async def admin_exit(message: Message, session: AsyncSession, locale: str, user: User, is_admin: bool) -> None:
    if not is_admin:
        return
    kb = await main_menu_keyboard(session, locale)
    await message.answer("OK", reply_markup=kb)

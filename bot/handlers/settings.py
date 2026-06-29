from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters import MenuAction
from bot.i18n import t
from bot.keyboards.common import lang_keyboard, main_menu_keyboard
from database.models import User

router = Router(name="settings")


@router.message(MenuAction("settings"))
async def show_settings(message: Message, locale: str) -> None:
    await message.answer(t(locale, "settings.title"), reply_markup=lang_keyboard())


@router.callback_query(F.data.startswith("set_lang:"))
async def set_lang(callback: CallbackQuery, session: AsyncSession, user: User) -> None:
    new_locale = callback.data.split(":")[1]
    user.locale = new_locale
    await session.commit()
    kb = await main_menu_keyboard(session, new_locale)
    await callback.message.answer(t(new_locale, "settings.lang_set"), reply_markup=kb)
    await callback.answer()

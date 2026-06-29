from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from bot.db.base import async_session
from bot.keyboards.user import main_menu
from bot.services.users import get_or_create_user

router = Router(name="user_start")

WELCOME_TEXT = "Привет, {name}! Добро пожаловать в МАМОНТ ВПН. Выберите действие в меню ниже."


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    async with async_session() as session:
        user = await get_or_create_user(session, message.from_user)
    await message.answer(
        WELCOME_TEXT.format(name=message.from_user.first_name or "друг"),
        reply_markup=main_menu(user.tg_id),
    )


@router.callback_query(F.data == "menu:main")
async def cb_main_menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        WELCOME_TEXT.format(name=callback.from_user.first_name or "друг"),
        reply_markup=main_menu(callback.from_user.id),
    )
    await callback.answer()

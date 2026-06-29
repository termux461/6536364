from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.keyboards.admin import admin_main_menu
from bot.utils.helpers import is_admin

router = Router(name="admin_panel")
router.message.filter(lambda message: is_admin(message.from_user.id))
router.callback_query.filter(lambda callback: is_admin(callback.from_user.id))

ADMIN_TEXT = "Админ-панель МАМОНТ ВПН"


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    await message.answer(ADMIN_TEXT, reply_markup=admin_main_menu())


@router.callback_query(F.data == "admin:open")
async def cb_admin_open(callback: CallbackQuery) -> None:
    await callback.message.edit_text(ADMIN_TEXT, reply_markup=admin_main_menu())
    await callback.answer()

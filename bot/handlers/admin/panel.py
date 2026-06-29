from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.keyboards.admin import admin_main_menu
from bot.utils.helpers import admin_filter

router = Router(name="admin_panel")
router.message.filter(admin_filter)
router.callback_query.filter(admin_filter)

ADMIN_TEXT = "Админ-панель МАМОНТ ВПН"


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    await message.answer(ADMIN_TEXT, reply_markup=admin_main_menu())


@router.callback_query(F.data == "admin:open")
async def cb_admin_open(callback: CallbackQuery) -> None:
    await callback.message.edit_text(ADMIN_TEXT, reply_markup=admin_main_menu())
    await callback.answer()

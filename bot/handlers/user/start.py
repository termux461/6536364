from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message

from bot.db.base import async_session
from bot.keyboards.user import main_menu
from bot.services.users import get_or_create_user
from bot.utils.helpers import is_admin_async

router = Router(name="user_start")

WELCOME_TEXT = "Привет, {name}! Добро пожаловать в МАМОНТ ВПН. Выберите действие в меню ниже."


def _parse_ref_id(args: str | None) -> int | None:
    if not args or not args.startswith("ref_"):
        return None
    try:
        return int(args.removeprefix("ref_"))
    except ValueError:
        return None


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject) -> None:
    ref_by_tg_id = _parse_ref_id(command.args)
    async with async_session() as session:
        user = await get_or_create_user(session, message.from_user, ref_by_tg_id=ref_by_tg_id)
    is_admin = await is_admin_async(user.tg_id)
    await message.answer(
        WELCOME_TEXT.format(name=message.from_user.first_name or "друг"),
        reply_markup=main_menu(is_admin),
    )


@router.callback_query(F.data == "menu:main")
async def cb_main_menu(callback: CallbackQuery) -> None:
    is_admin = await is_admin_async(callback.from_user.id)
    await callback.message.edit_text(
        WELCOME_TEXT.format(name=callback.from_user.first_name or "друг"),
        reply_markup=main_menu(is_admin),
    )
    await callback.answer()

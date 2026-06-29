from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import settings
from bot.db.base import async_session
from bot.keyboards.user import main_menu, support_menu, to_menu_keyboard
from bot.models.support import SupportMessage
from bot.services.users import get_or_create_user
from bot.utils.helpers import is_admin_async
from bot.utils.states import Support

router = Router(name="user_support")

SUPPORT_TEXT = "Раздел поддержки. Если у вас возник вопрос или проблема — напишите нам, и мы ответим как можно скорее."


@router.callback_query(F.data == "support:start")
async def cb_support_start(callback: CallbackQuery) -> None:
    await callback.message.edit_text(SUPPORT_TEXT, reply_markup=support_menu())
    await callback.answer()


@router.callback_query(F.data == "support:write")
async def cb_support_write(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Support.waiting_message)
    await callback.message.edit_text(
        "Напишите ваше сообщение в одном сообщении — мы передадим его в поддержку.",
        reply_markup=to_menu_keyboard(),
    )
    await callback.answer()


@router.message(Support.waiting_message)
async def msg_support_text(message: Message, state: FSMContext) -> None:
    async with async_session() as session:
        user = await get_or_create_user(session, message.from_user)
        session.add(SupportMessage(user_id=user.id, text=message.text or ""))
        await session.commit()

    await state.clear()
    await message.answer("Сообщение отправлено в поддержку. Мы свяжемся с вами в ближайшее время.")

    for admin_id in settings.admin_ids:
        try:
            await message.bot.send_message(
                admin_id,
                f"Новое сообщение в поддержку от {message.from_user.id} "
                f"(@{message.from_user.username or '-'}):\n\n{message.text}",
            )
        except Exception:
            pass

    is_admin = await is_admin_async(message.from_user.id)
    await message.answer("Главное меню:", reply_markup=main_menu(is_admin))

import asyncio

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from bot.db.base import async_session
from bot.keyboards.admin import admin_back_menu, admin_broadcast_confirm_menu
from bot.models.user import User
from bot.utils.helpers import is_admin
from bot.utils.states import AdminBroadcast

router = Router(name="admin_broadcast")
router.message.filter(lambda message: is_admin(message.from_user.id))
router.callback_query.filter(lambda callback: is_admin(callback.from_user.id))


@router.callback_query(F.data == "admin:broadcast")
async def cb_broadcast_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminBroadcast.waiting_text)
    await callback.message.edit_text("Введите текст рассылки:", reply_markup=admin_back_menu())
    await callback.answer()


@router.message(AdminBroadcast.waiting_text)
async def msg_broadcast_text(message: Message, state: FSMContext) -> None:
    await state.update_data(text=message.text)
    await state.set_state(AdminBroadcast.confirm)
    await message.answer(
        f"Предпросмотр рассылки:\n\n{message.text}\n\nОтправить всем пользователям?",
        reply_markup=admin_broadcast_confirm_menu(),
    )


@router.callback_query(F.data == "admin:broadcast:send")
async def cb_broadcast_send(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    text = data.get("text")
    await state.clear()

    if not text:
        await callback.answer("Текст рассылки не найден", show_alert=True)
        return

    async with async_session() as session:
        result = await session.execute(select(User.tg_id).where(User.is_blocked.is_(False)))
        tg_ids = [row[0] for row in result.all()]

    await callback.message.edit_text(f"Рассылка запущена для {len(tg_ids)} пользователей...")

    sent = 0
    for i, tg_id in enumerate(tg_ids, start=1):
        try:
            await callback.bot.send_message(tg_id, text)
            sent += 1
        except Exception:
            pass
        if i % 25 == 0:
            await asyncio.sleep(0.05)

    await callback.message.answer(f"Рассылка завершена. Отправлено: {sent}/{len(tg_ids)}", reply_markup=admin_back_menu())
    await callback.answer()

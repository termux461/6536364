import asyncio

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states import AdminBroadcastFlow
from database.models import Broadcast, User

router = Router(name="admin_broadcast")


@router.message(lambda m: m.text == "📢 Рассылка")
async def broadcast_start(message: Message, is_admin: bool, state: FSMContext) -> None:
    if not is_admin:
        return
    await state.set_state(AdminBroadcastFlow.entering_text)
    await message.answer("Введите текст рассылки:")


@router.message(AdminBroadcastFlow.entering_text)
async def broadcast_preview(message: Message, state: FSMContext) -> None:
    await state.update_data(text=message.text)
    await state.set_state(AdminBroadcastFlow.confirming)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отправить всем", callback_data="broadcast_confirm")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel")],
    ])
    await message.answer(f"Предпросмотр:\n\n{message.text}", reply_markup=kb)


@router.callback_query(AdminBroadcastFlow.confirming, F.data == "broadcast_cancel")
async def broadcast_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.answer("Рассылка отменена.")
    await callback.answer()


@router.callback_query(AdminBroadcastFlow.confirming, F.data == "broadcast_confirm")
async def broadcast_confirm(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    text = data["text"]
    users = (await session.execute(select(User.tg_id).where(User.is_banned.is_(False)))).scalars().all()

    bc = Broadcast(text=text, total_count=len(users), status="running")
    session.add(bc)
    await session.commit()

    await state.clear()
    await callback.message.answer(f"Начинаю рассылку для {len(users)} пользователей...")
    await callback.answer()

    sent = 0
    for tg_id in users:
        try:
            await callback.bot.send_message(tg_id, text)
            sent += 1
        except Exception:
            pass
        await asyncio.sleep(0.05)

    bc.sent_count = sent
    bc.status = "done"
    await session.commit()
    await callback.message.answer(f"Рассылка завершена: доставлено {sent}/{len(users)}.")

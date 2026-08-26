from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.admin.filters import IsAdmin
from app.bot.handlers.admin.keyboards import back_button
from app.bot.states.order import AdminStates
from app.models.enums import BroadcastStatus
from app.repositories import BroadcastRepository, UserRepository
from app.services.queue import JobQueue

router = Router(name="admin_broadcast")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


@router.callback_query(F.data == "adm:broadcast")
async def start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.broadcast_text)
    await callback.message.answer(
        "📢 Отправьте текст рассылки (HTML разрешён).", reply_markup=back_button()
    )
    await callback.answer()


@router.message(AdminStates.broadcast_text)
async def preview(message: Message, state: FSMContext, session: AsyncSession) -> None:
    repo = BroadcastRepository(session)
    broadcast = await repo.create(admin_id=message.from_user.id, text=message.text or "")
    recipients = await UserRepository(session).all_telegram_ids()
    await repo.fill_recipients(broadcast, recipients)
    await state.clear()

    await message.answer("👀 <b>Предпросмотр:</b>")
    await message.answer(broadcast.text)
    await message.answer(
        f"Получателей: <b>{broadcast.total}</b>",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🚀 Запустить", callback_data=f"adm:bc:run:{broadcast.id}")],
                [InlineKeyboardButton(text="🛑 Остановить", callback_data=f"adm:bc:stop:{broadcast.id}")],
                [InlineKeyboardButton(text="📊 Статус", callback_data=f"adm:bc:stat:{broadcast.id}")],
            ]
        ),
    )


@router.callback_query(F.data.startswith("adm:bc:"))
async def control(callback: CallbackQuery, session: AsyncSession) -> None:
    _, _, action, raw_id = callback.data.split(":")
    repo = BroadcastRepository(session)
    broadcast = await repo.get(int(raw_id))
    if broadcast is None:
        await callback.answer("Не найдено", show_alert=True)
        return

    if action == "run":
        await repo.set_status(broadcast, BroadcastStatus.RUNNING)
        await session.commit()
        queue = JobQueue.from_settings()
        try:
            await queue.enqueue_broadcast(broadcast.id)
        finally:
            await queue.close()
        await callback.answer("Запущено", show_alert=True)
    elif action == "stop":
        await repo.set_status(broadcast, BroadcastStatus.CANCELLED)
        await repo.cancel_pending(broadcast.id)
        await callback.answer("Остановлено", show_alert=True)
    else:
        await callback.message.answer(
            f"📊 Рассылка #{broadcast.id}\n"
            f"Статус: {broadcast.status}\n"
            f"Получателей: {broadcast.total}\n"
            f"Отправлено: {broadcast.sent}\n"
            f"Ошибки: {broadcast.failed}\n"
            f"Заблокировали бота: {broadcast.blocked}\n"
            f"FloodWait: {broadcast.flood_waits}"
        )
        await callback.answer()

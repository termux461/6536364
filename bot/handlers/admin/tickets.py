from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.admin import ticket_admin_keyboard, tickets_list_keyboard
from bot.states import AdminTicketReplyFlow
from database.models import SenderType, Ticket, TicketMessage, TicketStatus, User

router = Router(name="admin_tickets")


@router.message(lambda m: m.text == "🎫 Тикеты")
async def list_tickets(message: Message, session: AsyncSession, is_admin: bool) -> None:
    if not is_admin:
        return
    tickets = (
        await session.execute(select(Ticket).where(Ticket.status != TicketStatus.CLOSED).order_by(Ticket.updated_at.desc()))
    ).scalars().all()
    if not tickets:
        await message.answer("Открытых тикетов нет.")
        return
    await message.answer("Открытые тикеты:", reply_markup=tickets_list_keyboard(tickets))


@router.callback_query(F.data.startswith("admin_ticket:"))
async def ticket_detail(callback: CallbackQuery, session: AsyncSession) -> None:
    ticket_id = int(callback.data.split(":")[1])
    ticket = (await session.execute(select(Ticket).where(Ticket.id == ticket_id))).scalar_one_or_none()
    if not ticket:
        await callback.answer()
        return
    messages = (
        await session.execute(select(TicketMessage).where(TicketMessage.ticket_id == ticket.id).order_by(TicketMessage.created_at))
    ).scalars().all()

    text = f"Тикет #{ticket.id}: {ticket.subject}\n\n"
    for m in messages:
        who = "Пользователь" if m.sender_type == SenderType.USER else "Админ"
        text += f"[{who}] {m.text or ''}\n"
    await callback.message.answer(text, reply_markup=ticket_admin_keyboard(ticket.id))

    for m in messages:
        if m.attachment_path:
            if m.attachment_type == "photo":
                await callback.message.answer_photo(FSInputFile(m.attachment_path))
            else:
                await callback.message.answer_document(FSInputFile(m.attachment_path))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_ticket_reply:"))
async def ticket_reply_start(callback: CallbackQuery, state: FSMContext) -> None:
    ticket_id = int(callback.data.split(":")[1])
    await state.update_data(ticket_id=ticket_id)
    await state.set_state(AdminTicketReplyFlow.entering_text)
    await callback.message.answer("Введите ответ пользователю:")
    await callback.answer()


@router.message(AdminTicketReplyFlow.entering_text)
async def ticket_reply_send(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    ticket_id = data["ticket_id"]
    ticket = (await session.execute(select(Ticket).where(Ticket.id == ticket_id))).scalar_one_or_none()
    if not ticket:
        await state.clear()
        return

    msg = TicketMessage(
        ticket_id=ticket.id, sender_type=SenderType.ADMIN, sender_admin_id=message.from_user.id, text=message.text,
    )
    session.add(msg)
    ticket.status = TicketStatus.IN_PROGRESS
    await session.commit()

    user = (await session.execute(select(User).where(User.id == ticket.user_id))).scalar_one()
    try:
        await message.bot.send_message(
            user.tg_id,
            f"💬 Ответ поддержки по тикету #{ticket.id}:\n{message.text}\n\nОткройте «Поддержку» в меню, чтобы продолжить диалог.",
        )
    except Exception:
        pass

    await state.clear()
    await message.answer("Ответ отправлен пользователю.")


@router.callback_query(F.data.startswith("admin_ticket_close:"))
async def ticket_close(callback: CallbackQuery, session: AsyncSession) -> None:
    ticket_id = int(callback.data.split(":")[1])
    ticket = (await session.execute(select(Ticket).where(Ticket.id == ticket_id))).scalar_one_or_none()
    if ticket:
        ticket.status = TicketStatus.CLOSED
        await session.commit()
        await callback.message.answer(f"Тикет #{ticket.id} закрыт.")
    await callback.answer()

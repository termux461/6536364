import httpx
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import settings
from database.models import SenderType, Ticket, TicketMessage, TicketStatus, User
from panel.auth import require_admin
from panel.deps import get_session, templates

router = APIRouter()


@router.get("/panel/tickets")
async def list_tickets(request: Request, session: AsyncSession = Depends(get_session), _: bool = Depends(require_admin)):
    tickets = (
        await session.execute(select(Ticket).options(selectinload(Ticket.category)).order_by(Ticket.updated_at.desc()))
    ).scalars().all()
    return templates.TemplateResponse("tickets.html", {"request": request, "tickets": tickets})


@router.get("/panel/tickets/{ticket_id}")
async def ticket_detail(
    ticket_id: int, request: Request, session: AsyncSession = Depends(get_session), _: bool = Depends(require_admin),
):
    ticket = (
        await session.execute(select(Ticket).options(selectinload(Ticket.category)).where(Ticket.id == ticket_id))
    ).scalar_one_or_none()
    messages = (
        await session.execute(select(TicketMessage).where(TicketMessage.ticket_id == ticket_id).order_by(TicketMessage.created_at))
    ).scalars().all()
    return templates.TemplateResponse("ticket_detail.html", {"request": request, "ticket": ticket, "messages": messages})


@router.post("/panel/tickets/{ticket_id}/reply")
async def reply_ticket(
    ticket_id: int, text: str = Form(...),
    session: AsyncSession = Depends(get_session), _: bool = Depends(require_admin),
):
    ticket = (await session.execute(select(Ticket).where(Ticket.id == ticket_id))).scalar_one_or_none()
    if ticket:
        session.add(TicketMessage(ticket_id=ticket.id, sender_type=SenderType.ADMIN, text=text))
        ticket.status = TicketStatus.IN_PROGRESS
        await session.commit()

        user = (await session.execute(select(User).where(User.id == ticket.user_id))).scalar_one_or_none()
        if user:
            async with httpx.AsyncClient(timeout=10.0) as client:
                try:
                    await client.post(
                        f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage",
                        json={"chat_id": user.tg_id, "text": f"💬 Ответ поддержки по тикету #{ticket.id}:\n{text}"},
                    )
                except httpx.HTTPError:
                    pass
    return RedirectResponse(f"/panel/tickets/{ticket_id}", status_code=302)


@router.post("/panel/tickets/{ticket_id}/close")
async def close_ticket(ticket_id: int, session: AsyncSession = Depends(get_session), _: bool = Depends(require_admin)):
    ticket = (await session.execute(select(Ticket).where(Ticket.id == ticket_id))).scalar_one_or_none()
    if ticket:
        ticket.status = TicketStatus.CLOSED
        await session.commit()
    return RedirectResponse("/panel/tickets", status_code=302)

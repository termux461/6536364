from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Payment, PaymentStatus, Subscription, SubscriptionStatus, Ticket, TicketStatus, User
from panel.auth import require_admin
from panel.deps import get_session, templates

router = APIRouter()


@router.get("/panel/dashboard")
async def dashboard(request: Request, session: AsyncSession = Depends(get_session), _: bool = Depends(require_admin)):
    users_count = (await session.execute(select(func.count(User.id)))).scalar_one()
    active_subs = (
        await session.execute(select(func.count(Subscription.id)).where(Subscription.status == SubscriptionStatus.ACTIVE))
    ).scalar_one()
    revenue = (
        await session.execute(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == PaymentStatus.PAID))
    ).scalar_one()
    open_tickets = (
        await session.execute(select(func.count(Ticket.id)).where(Ticket.status != TicketStatus.CLOSED))
    ).scalar_one()

    return templates.TemplateResponse("dashboard.html", {
        "request": request, "users_count": users_count, "active_subs": active_subs,
        "revenue": revenue, "open_tickets": open_tickets,
    })

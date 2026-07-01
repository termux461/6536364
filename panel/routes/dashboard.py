import datetime
import json

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Payment, PaymentStatus, Subscription, SubscriptionStatus, Ticket, TicketStatus, User
from panel.auth import require_admin
from panel.deps import get_session, templates

router = APIRouter()


@router.get("/panel/dashboard")
async def dashboard(request: Request, session: AsyncSession = Depends(get_session), _: bool = Depends(require_admin)):
    now = datetime.datetime.now(datetime.timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - datetime.timedelta(days=7)

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

    new_today = (
        await session.execute(select(func.count(User.id)).where(User.created_at >= today_start))
    ).scalar_one()
    revenue_today = (
        await session.execute(
            select(func.coalesce(func.sum(Payment.amount), 0))
            .where(Payment.status == PaymentStatus.PAID, Payment.paid_at >= today_start)
        )
    ).scalar_one()

    # Daily stats for last 7 days
    daily_revenue_rows = (
        await session.execute(
            select(func.date(Payment.paid_at).label("d"), func.sum(Payment.amount).label("s"))
            .where(Payment.status == PaymentStatus.PAID, Payment.paid_at >= week_ago)
            .group_by(func.date(Payment.paid_at))
            .order_by(func.date(Payment.paid_at))
        )
    ).all()
    daily_users_rows = (
        await session.execute(
            select(func.date(User.created_at).label("d"), func.count(User.id).label("c"))
            .where(User.created_at >= week_ago)
            .group_by(func.date(User.created_at))
            .order_by(func.date(User.created_at))
        )
    ).all()

    # Fill missing days with zeros
    def fill_days(rows, value_key: str) -> tuple[list[str], list[float]]:
        data = {str(r[0]): r[1] for r in rows}
        labels, values = [], []
        for i in range(6, -1, -1):
            day = (now - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
            labels.append((now - datetime.timedelta(days=i)).strftime("%d.%m"))
            values.append(round(data.get(day, 0), 2))
        return labels, values

    rev_labels, rev_values = fill_days(daily_revenue_rows, "s")
    usr_labels, usr_values = fill_days(daily_users_rows, "c")

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "users_count": users_count, "active_subs": active_subs,
        "revenue": revenue, "open_tickets": open_tickets,
        "new_today": new_today, "revenue_today": round(revenue_today, 2),
        "rev_labels": json.dumps(rev_labels), "rev_values": json.dumps(rev_values),
        "usr_labels": json.dumps(usr_labels), "usr_values": json.dumps(usr_values),
    })

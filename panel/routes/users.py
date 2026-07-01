import csv
import io

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import cast, or_, select, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import AuditLog, Payment, Subscription, SubscriptionStatus, User
from panel.auth import require_admin
from panel.deps import get_session, templates

router = APIRouter()


async def _audit(session: AsyncSession, action: str, target_type: str | None = None,
                 target_id: int | None = None, detail: str | None = None) -> None:
    session.add(AuditLog(actor="admin", action=action, target_type=target_type,
                         target_id=target_id, detail=detail))
    await session.flush()


@router.get("/panel/users")
async def list_users(
    request: Request,
    search: str = Query(default=""),
    offset: int = Query(default=0),
    session: AsyncSession = Depends(get_session),
    _: bool = Depends(require_admin),
):
    q = select(User).order_by(User.created_at.desc())
    if search:
        q = q.where(or_(
            User.username.ilike(f"%{search}%"),
            cast(User.tg_id, String).contains(search),
            User.full_name.ilike(f"%{search}%"),
        ))
    users = (await session.execute(q.offset(offset).limit(50))).scalars().all()
    total = (await session.execute(select(User))).scalars().all().__len__()
    return templates.TemplateResponse("users.html", {
        "request": request, "users": users, "search": search,
        "offset": offset, "has_more": len(users) == 50,
    })


@router.get("/panel/users/export")
async def export_users(
    session: AsyncSession = Depends(get_session),
    _: bool = Depends(require_admin),
):
    users = (await session.execute(select(User).order_by(User.created_at.desc()))).scalars().all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "tg_id", "username", "full_name", "locale", "balance", "is_banned", "created_at"])
    for u in users:
        writer.writerow([u.id, u.tg_id, u.username or "", u.full_name or "",
                         u.locale, u.balance, u.is_banned, u.created_at.isoformat()])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=users.csv"},
    )


@router.get("/panel/payments/export")
async def export_payments(
    session: AsyncSession = Depends(get_session),
    _: bool = Depends(require_admin),
):
    payments = (
        await session.execute(
            select(Payment).options(selectinload(Payment.user)).order_by(Payment.created_at.desc())
        )
    ).scalars().all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "user_tg_id", "provider", "amount", "currency", "status",
                     "discount_amount", "created_at", "paid_at"])
    for p in payments:
        writer.writerow([
            p.id, p.user.tg_id if p.user else "", p.provider, p.amount, p.currency,
            p.status.value if hasattr(p.status, "value") else p.status,
            p.discount_amount, p.created_at.isoformat(),
            p.paid_at.isoformat() if p.paid_at else "",
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=payments.csv"},
    )


@router.get("/panel/users/{user_id}")
async def user_detail(
    request: Request, user_id: int,
    session: AsyncSession = Depends(get_session),
    _: bool = Depends(require_admin),
):
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        return RedirectResponse("/panel/users")
    subs = (
        await session.execute(
            select(Subscription).options(selectinload(Subscription.tariff))
            .where(Subscription.user_id == user_id).order_by(Subscription.starts_at.desc())
        )
    ).scalars().all()
    payments = (
        await session.execute(
            select(Payment).where(Payment.user_id == user_id).order_by(Payment.created_at.desc()).limit(30)
        )
    ).scalars().all()
    return templates.TemplateResponse("user_detail.html", {
        "request": request, "u": user, "subs": subs, "payments": payments,
    })


@router.post("/panel/users/{user_id}/ban")
async def toggle_ban(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    _: bool = Depends(require_admin),
):
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user:
        user.is_banned = not user.is_banned
        action = "ban_user" if user.is_banned else "unban_user"
        await _audit(session, action, "user", user_id, f"tg_id={user.tg_id}")
        await session.commit()
    return RedirectResponse(f"/panel/users/{user_id}", status_code=302)


@router.post("/panel/users/{user_id}/adjust_balance")
async def adjust_balance(
    user_id: int,
    amount: float = Form(...),
    session: AsyncSession = Depends(get_session),
    _: bool = Depends(require_admin),
):
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user:
        user.balance = round(user.balance + amount, 2)
        await _audit(session, "adjust_balance", "user", user_id, f"delta={amount}, new={user.balance}")
        await session.commit()
    return RedirectResponse(f"/panel/users/{user_id}", status_code=302)


@router.post("/panel/users/{user_id}/cancel_sub")
async def cancel_sub(
    user_id: int,
    sub_id: int = Form(...),
    session: AsyncSession = Depends(get_session),
    _: bool = Depends(require_admin),
):
    sub = (
        await session.execute(select(Subscription).where(Subscription.id == sub_id, Subscription.user_id == user_id))
    ).scalar_one_or_none()
    if sub:
        sub.status = SubscriptionStatus.CANCELLED
        await _audit(session, "cancel_subscription", "subscription", sub_id, f"user_id={user_id}")
        await session.commit()
    return RedirectResponse(f"/panel/users/{user_id}", status_code=302)

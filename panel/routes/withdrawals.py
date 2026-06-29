import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.models import User, WithdrawRequest
from panel.auth import require_admin
from panel.deps import get_session, templates

router = APIRouter()


async def _notify_user(user: User, text: str) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            await client.post(
                f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage",
                json={"chat_id": user.tg_id, "text": text},
            )
        except httpx.HTTPError:
            pass


@router.get("/panel/withdrawals")
async def list_withdrawals(request: Request, session: AsyncSession = Depends(get_session), _: bool = Depends(require_admin)):
    requests_ = (
        await session.execute(
            select(WithdrawRequest, User).join(User, User.id == WithdrawRequest.user_id).order_by(WithdrawRequest.created_at.desc())
        )
    ).all()
    return templates.TemplateResponse("withdrawals.html", {"request": request, "rows": requests_})


@router.post("/panel/withdrawals/{request_id}/approve")
async def approve_withdrawal(request_id: int, session: AsyncSession = Depends(get_session), _: bool = Depends(require_admin)):
    req = (await session.execute(select(WithdrawRequest).where(WithdrawRequest.id == request_id))).scalar_one_or_none()
    if req and req.status == "pending":
        req.status = "approved"
        await session.commit()
        user = (await session.execute(select(User).where(User.id == req.user_id))).scalar_one_or_none()
        if user:
            await _notify_user(user, f"✅ Заявка на вывод {req.amount} выполнена.")
    return RedirectResponse("/panel/withdrawals", status_code=302)


@router.post("/panel/withdrawals/{request_id}/reject")
async def reject_withdrawal(request_id: int, session: AsyncSession = Depends(get_session), _: bool = Depends(require_admin)):
    req = (await session.execute(select(WithdrawRequest).where(WithdrawRequest.id == request_id))).scalar_one_or_none()
    if req and req.status == "pending":
        req.status = "rejected"
        user = (await session.execute(select(User).where(User.id == req.user_id))).scalar_one_or_none()
        if user:
            user.balance += req.amount
            await _notify_user(user, f"❌ Заявка на вывод {req.amount} отклонена, средства возвращены на баланс.")
        await session.commit()
    return RedirectResponse("/panel/withdrawals", status_code=302)

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.payments.registry import ensure_payment_methods_seeded
from database.models import PaymentMethod
from panel.auth import require_admin
from panel.deps import get_session, templates

router = APIRouter()


@router.get("/panel/payments")
async def list_payment_methods(request: Request, session: AsyncSession = Depends(get_session), _: bool = Depends(require_admin)):
    await ensure_payment_methods_seeded(session)
    methods = (await session.execute(select(PaymentMethod).order_by(PaymentMethod.sort_order))).scalars().all()
    return templates.TemplateResponse("payments.html", {"request": request, "methods": methods})


@router.post("/panel/payments/{code}/toggle")
async def toggle_method(code: str, session: AsyncSession = Depends(get_session), _: bool = Depends(require_admin)):
    method = (await session.execute(select(PaymentMethod).where(PaymentMethod.code == code))).scalar_one_or_none()
    if method:
        method.is_enabled = not method.is_enabled
        await session.commit()
    return RedirectResponse("/panel/payments", status_code=302)

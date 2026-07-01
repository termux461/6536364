import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import AuditLog, PromoCode
from panel.auth import require_admin
from panel.deps import get_session, templates

router = APIRouter()


async def _audit(session: AsyncSession, action: str, target_id: int | None = None, detail: str | None = None) -> None:
    session.add(AuditLog(actor="admin", action=action, target_type="promo_code", target_id=target_id, detail=detail))
    await session.flush()


@router.get("/panel/promos")
async def list_promos(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _: bool = Depends(require_admin),
):
    promos = (await session.execute(select(PromoCode).order_by(PromoCode.created_at.desc()))).scalars().all()
    return templates.TemplateResponse("promos.html", {"request": request, "promos": promos})


@router.post("/panel/promos/create")
async def create_promo(
    code: str = Form(...),
    discount_percent: float = Form(...),
    max_uses: str = Form(""),
    expires_at: str = Form(""),
    session: AsyncSession = Depends(get_session),
    _: bool = Depends(require_admin),
):
    max_uses_val = int(max_uses) if max_uses.strip() else None
    expires_val = datetime.datetime.fromisoformat(expires_at).replace(tzinfo=datetime.timezone.utc) if expires_at.strip() else None
    promo = PromoCode(
        code=code.strip().upper(), discount_percent=discount_percent,
        max_uses=max_uses_val, expires_at=expires_val, is_active=True,
    )
    session.add(promo)
    await session.flush()
    await _audit(session, "create_promo", promo.id, f"code={promo.code} discount={discount_percent}%")
    await session.commit()
    return RedirectResponse("/panel/promos", status_code=302)


@router.post("/panel/promos/{promo_id}/toggle")
async def toggle_promo(
    promo_id: int,
    session: AsyncSession = Depends(get_session),
    _: bool = Depends(require_admin),
):
    promo = (await session.execute(select(PromoCode).where(PromoCode.id == promo_id))).scalar_one_or_none()
    if promo:
        promo.is_active = not promo.is_active
        await _audit(session, "toggle_promo", promo_id, f"active={promo.is_active}")
        await session.commit()
    return RedirectResponse("/panel/promos", status_code=302)


@router.post("/panel/promos/{promo_id}/delete")
async def delete_promo(
    promo_id: int,
    session: AsyncSession = Depends(get_session),
    _: bool = Depends(require_admin),
):
    promo = (await session.execute(select(PromoCode).where(PromoCode.id == promo_id))).scalar_one_or_none()
    if promo:
        await _audit(session, "delete_promo", promo_id, f"code={promo.code}")
        await session.delete(promo)
        await session.commit()
    return RedirectResponse("/panel/promos", status_code=302)

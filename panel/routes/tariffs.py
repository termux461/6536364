from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Host, Tariff
from panel.auth import require_admin
from panel.deps import get_session, templates

router = APIRouter()


@router.get("/panel/tariffs")
async def list_tariffs(request: Request, session: AsyncSession = Depends(get_session), _: bool = Depends(require_admin)):
    tariffs = (await session.execute(select(Tariff))).scalars().all()
    hosts = (await session.execute(select(Host))).scalars().all()
    return templates.TemplateResponse("tariffs.html", {"request": request, "tariffs": tariffs, "hosts": hosts})


@router.post("/panel/tariffs/create")
async def create_tariff(
    host_id: int = Form(...), name: str = Form(...), description: str = Form(""),
    price: float = Form(...), duration_days: int = Form(...), traffic_limit_gb: int = Form(0),
    session: AsyncSession = Depends(get_session), _: bool = Depends(require_admin),
):
    session.add(Tariff(
        host_id=host_id, name=name, description=description or None,
        price=price, duration_days=duration_days, traffic_limit_gb=traffic_limit_gb,
    ))
    await session.commit()
    return RedirectResponse("/panel/tariffs", status_code=302)


@router.post("/panel/tariffs/{tariff_id}/toggle")
async def toggle_tariff(tariff_id: int, session: AsyncSession = Depends(get_session), _: bool = Depends(require_admin)):
    tariff = (await session.execute(select(Tariff).where(Tariff.id == tariff_id))).scalar_one_or_none()
    if tariff:
        tariff.is_active = not tariff.is_active
        await session.commit()
    return RedirectResponse("/panel/tariffs", status_code=302)


@router.post("/panel/tariffs/{tariff_id}/delete")
async def delete_tariff(tariff_id: int, session: AsyncSession = Depends(get_session), _: bool = Depends(require_admin)):
    tariff = (await session.execute(select(Tariff).where(Tariff.id == tariff_id))).scalar_one_or_none()
    if tariff:
        await session.delete(tariff)
        await session.commit()
    return RedirectResponse("/panel/tariffs", status_code=302)

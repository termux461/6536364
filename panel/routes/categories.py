from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.support import ensure_categories_seeded
from database.models import TicketCategory
from panel.auth import require_admin
from panel.deps import get_session, templates

router = APIRouter()


@router.get("/panel/categories")
async def list_categories(request: Request, session: AsyncSession = Depends(get_session), _: bool = Depends(require_admin)):
    await ensure_categories_seeded(session)
    categories = (await session.execute(select(TicketCategory).order_by(TicketCategory.sort_order))).scalars().all()
    return templates.TemplateResponse("categories.html", {"request": request, "categories": categories})


@router.post("/panel/categories/create")
async def create_category(
    title_ru: str = Form(...), title_en: str = Form(...), sort_order: int = Form(0),
    session: AsyncSession = Depends(get_session), _: bool = Depends(require_admin),
):
    session.add(TicketCategory(title_ru=title_ru, title_en=title_en, sort_order=sort_order, is_active=True))
    await session.commit()
    return RedirectResponse("/panel/categories", status_code=302)


@router.post("/panel/categories/{category_id}/update")
async def update_category(
    category_id: int, title_ru: str = Form(...), title_en: str = Form(...),
    sort_order: int = Form(0), is_active: bool = Form(False),
    session: AsyncSession = Depends(get_session), _: bool = Depends(require_admin),
):
    category = (await session.execute(select(TicketCategory).where(TicketCategory.id == category_id))).scalar_one_or_none()
    if category:
        category.title_ru = title_ru
        category.title_en = title_en
        category.sort_order = sort_order
        category.is_active = is_active
        await session.commit()
    return RedirectResponse("/panel/categories", status_code=302)


@router.post("/panel/categories/{category_id}/delete")
async def delete_category(category_id: int, session: AsyncSession = Depends(get_session), _: bool = Depends(require_admin)):
    category = (await session.execute(select(TicketCategory).where(TicketCategory.id == category_id))).scalar_one_or_none()
    if category:
        await session.delete(category)
        await session.commit()
    return RedirectResponse("/panel/categories", status_code=302)

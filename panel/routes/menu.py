from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.common import ensure_menu_seeded
from database.models import MenuButton
from panel.auth import require_admin
from panel.deps import get_session, templates

router = APIRouter()


@router.get("/panel/menu")
async def list_menu(request: Request, session: AsyncSession = Depends(get_session), _: bool = Depends(require_admin)):
    await ensure_menu_seeded(session)
    buttons = (await session.execute(select(MenuButton).order_by(MenuButton.sort_order))).scalars().all()
    return templates.TemplateResponse("menu.html", {"request": request, "buttons": buttons})


@router.post("/panel/menu/{button_id}/update")
async def update_button(
    button_id: int, title_ru: str = Form(...), title_en: str = Form(...),
    sort_order: int = Form(...), is_visible: bool = Form(False),
    session: AsyncSession = Depends(get_session), _: bool = Depends(require_admin),
):
    btn = (await session.execute(select(MenuButton).where(MenuButton.id == button_id))).scalar_one_or_none()
    if btn:
        btn.title_ru = title_ru
        btn.title_en = title_en
        btn.sort_order = sort_order
        btn.is_visible = is_visible
        await session.commit()
    return RedirectResponse("/panel/menu", status_code=302)

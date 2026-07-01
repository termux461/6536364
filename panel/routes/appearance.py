from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.app_settings import get_appearance, set_setting
from panel.auth import require_admin
from panel.deps import get_session, templates

router = APIRouter()


@router.get("/panel/appearance")
async def show_appearance(request: Request, session: AsyncSession = Depends(get_session), _: bool = Depends(require_admin)):
    appearance = await get_appearance(session)
    return templates.TemplateResponse("appearance.html", {"request": request, "appearance": appearance})


@router.post("/panel/appearance")
async def save_appearance(
    brand_name: str = Form(...), accent_color: str = Form(...), logo_url: str = Form(""),
    session: AsyncSession = Depends(get_session), _: bool = Depends(require_admin),
):
    await set_setting(session, "webapp_brand_name", brand_name)
    await set_setting(session, "webapp_accent_color", accent_color)
    await set_setting(session, "webapp_logo_url", logo_url)
    return RedirectResponse("/panel/appearance", status_code=302)

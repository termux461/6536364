import asyncio

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.db import async_session
from database.models import Broadcast, User
from panel.auth import require_admin
from panel.deps import get_session, templates

router = APIRouter()


@router.get("/panel/broadcasts")
async def list_broadcasts(request: Request, session: AsyncSession = Depends(get_session), _: bool = Depends(require_admin)):
    broadcasts = (await session.execute(select(Broadcast).order_by(Broadcast.created_at.desc()))).scalars().all()
    return templates.TemplateResponse("broadcasts.html", {"request": request, "broadcasts": broadcasts})


async def _run_broadcast(broadcast_id: int) -> None:
    async with async_session() as session:
        bc = (await session.execute(select(Broadcast).where(Broadcast.id == broadcast_id))).scalar_one()
        users = (await session.execute(select(User.tg_id).where(User.is_banned.is_(False)))).scalars().all()
        bc.total_count = len(users)
        bc.status = "running"
        await session.commit()

        sent = 0
        async with httpx.AsyncClient(timeout=10.0) as client:
            for tg_id in users:
                try:
                    resp = await client.post(
                        f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage",
                        json={"chat_id": tg_id, "text": bc.text},
                    )
                    if resp.status_code == 200:
                        sent += 1
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.05)

        bc.sent_count = sent
        bc.status = "done"
        await session.commit()


@router.post("/panel/broadcasts/create")
async def create_broadcast(
    background_tasks: BackgroundTasks, text: str = Form(...),
    session: AsyncSession = Depends(get_session), _: bool = Depends(require_admin),
):
    bc = Broadcast(text=text, status="pending")
    session.add(bc)
    await session.commit()
    await session.refresh(bc)
    background_tasks.add_task(_run_broadcast, bc.id)
    return RedirectResponse("/panel/broadcasts", status_code=302)

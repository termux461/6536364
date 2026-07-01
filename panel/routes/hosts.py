from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Host
from panel.auth import require_admin
from panel.deps import get_session, templates

router = APIRouter()


@router.get("/panel/hosts")
async def list_hosts(request: Request, session: AsyncSession = Depends(get_session), _: bool = Depends(require_admin)):
    hosts = (await session.execute(select(Host))).scalars().all()
    return templates.TemplateResponse("hosts.html", {"request": request, "hosts": hosts})


@router.post("/panel/hosts/create")
async def create_host(
    name: str = Form(...), api_url: str = Form(...), api_token: str = Form(...),
    ssh_host: str = Form(""), ssh_port: int = Form(22), ssh_user: str = Form(""), ssh_password: str = Form(""),
    session: AsyncSession = Depends(get_session), _: bool = Depends(require_admin),
):
    host = Host(
        name=name, api_url=api_url, api_token=api_token,
        ssh_host=ssh_host or None, ssh_port=ssh_port, ssh_user=ssh_user or None, ssh_password=ssh_password or None,
    )
    session.add(host)
    await session.commit()
    return RedirectResponse("/panel/hosts", status_code=302)


@router.post("/panel/hosts/{host_id}/toggle")
async def toggle_host(host_id: int, session: AsyncSession = Depends(get_session), _: bool = Depends(require_admin)):
    host = (await session.execute(select(Host).where(Host.id == host_id))).scalar_one_or_none()
    if host:
        host.is_active = not host.is_active
        await session.commit()
    return RedirectResponse("/panel/hosts", status_code=302)


@router.post("/panel/hosts/{host_id}/delete")
async def delete_host(host_id: int, session: AsyncSession = Depends(get_session), _: bool = Depends(require_admin)):
    host = (await session.execute(select(Host).where(Host.id == host_id))).scalar_one_or_none()
    if host:
        await session.delete(host)
        await session.commit()
    return RedirectResponse("/panel/hosts", status_code=302)

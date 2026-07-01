from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import AuditLog
from panel.auth import require_admin
from panel.deps import get_session, templates

router = APIRouter()


@router.get("/panel/audit")
async def list_audit(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _: bool = Depends(require_admin),
):
    logs = (
        await session.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(300))
    ).scalars().all()
    return templates.TemplateResponse("audit.html", {"request": request, "logs": logs})

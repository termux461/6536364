from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import redact
from app.models import AuditLog


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def log(
        self,
        action: str,
        *,
        user_id: int | None = None,
        admin_id: int | None = None,
        order_id: int | None = None,
        status: str = "ok",
        message: str | None = None,
    ) -> None:
        self.session.add(
            AuditLog(
                action=action,
                user_id=user_id,
                admin_id=admin_id,
                order_id=order_id,
                status=status,
                message=redact(message)[:4000] if message else None,
            )
        )
        await self.session.flush()

    async def recent(self, limit: int = 20, order_id: int | None = None) -> list[AuditLog]:
        query = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
        if order_id is not None:
            query = query.where(AuditLog.order_id == order_id)
        return list(await self.session.scalars(query))

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Broadcast, BroadcastRecipient
from app.models.enums import BroadcastStatus, RecipientStatus


class BroadcastRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, broadcast_id: int) -> Broadcast | None:
        return await self.session.get(Broadcast, broadcast_id)

    async def create(self, *, admin_id: int, text: str, parse_mode: str | None = "HTML") -> Broadcast:
        broadcast = Broadcast(admin_id=admin_id, text=text, parse_mode=parse_mode)
        self.session.add(broadcast)
        await self.session.flush()
        return broadcast

    async def fill_recipients(self, broadcast: Broadcast, telegram_ids: list[int]) -> None:
        self.session.add_all(
            BroadcastRecipient(broadcast_id=broadcast.id, telegram_id=tid) for tid in telegram_ids
        )
        broadcast.total = len(telegram_ids)
        await self.session.flush()

    async def next_batch(self, broadcast_id: int, limit: int = 25) -> list[BroadcastRecipient]:
        result = await self.session.scalars(
            select(BroadcastRecipient)
            .where(
                BroadcastRecipient.broadcast_id == broadcast_id,
                BroadcastRecipient.status == RecipientStatus.PENDING,
            )
            .order_by(BroadcastRecipient.id)
            .limit(limit)
        )
        return list(result)

    async def mark_recipient(
        self, recipient: BroadcastRecipient, status: RecipientStatus, error: str | None = None
    ) -> None:
        recipient.status = status
        recipient.error = error
        await self.session.flush()

    async def bump(self, broadcast: Broadcast, field: str, delta: int = 1) -> None:
        setattr(broadcast, field, getattr(broadcast, field) + delta)
        await self.session.flush()

    async def set_status(self, broadcast: Broadcast, status: BroadcastStatus) -> None:
        broadcast.status = status
        if status == BroadcastStatus.RUNNING and broadcast.started_at is None:
            broadcast.started_at = datetime.now(UTC)
        if status in (BroadcastStatus.FINISHED, BroadcastStatus.CANCELLED):
            broadcast.finished_at = datetime.now(UTC)
        await self.session.flush()

    async def cancel_pending(self, broadcast_id: int) -> None:
        await self.session.execute(
            update(BroadcastRecipient)
            .where(
                BroadcastRecipient.broadcast_id == broadcast_id,
                BroadcastRecipient.status == RecipientStatus.PENDING,
            )
            .values(status=RecipientStatus.FAILED, error="cancelled")
        )

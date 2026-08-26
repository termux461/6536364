from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order
from app.models.enums import ACTIVE_ORDER_STATUSES, OrderStatus


class OrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, order_id: int) -> Order | None:
        return await self.session.get(Order, order_id)

    async def create(self, *, user_id: int, tariff_id: int, amount: int, currency: str) -> Order:
        order = Order(
            user_id=user_id,
            tariff_id=tariff_id,
            amount=amount,
            currency=currency,
            status=OrderStatus.CREATED,
        )
        self.session.add(order)
        await self.session.flush()
        return order

    async def set_status(self, order: Order, status: OrderStatus, *, error: str | None = None) -> Order:
        order.status = status
        if error is not None:
            order.error_message = error
        if status == OrderStatus.PAID and order.paid_at is None:
            order.paid_at = datetime.now(UTC)
        if status == OrderStatus.COMPLETED:
            order.completed_at = datetime.now(UTC)
        await self.session.flush()
        return order

    async def list_for_user(self, user_id: int, limit: int = 20) -> list[Order]:
        result = await self.session.scalars(
            select(Order).where(Order.user_id == user_id).order_by(Order.id.desc()).limit(limit)
        )
        return list(result)

    async def list_by_status(
        self, statuses: list[str] | None = None, offset: int = 0, limit: int = 10
    ) -> list[Order]:
        query = select(Order).order_by(Order.id.desc())
        if statuses:
            query = query.where(Order.status.in_(statuses))
        result = await self.session.scalars(query.offset(offset).limit(limit))
        return list(result)

    async def has_active(self, user_id: int) -> bool:
        count = await self.session.scalar(
            select(func.count(Order.id)).where(
                Order.user_id == user_id, Order.status.in_(list(ACTIVE_ORDER_STATUSES))
            )
        )
        return bool(count)

    async def counters(self, since: datetime | None = None) -> dict[str, int]:
        query = select(Order.status, func.count(Order.id), func.coalesce(func.sum(Order.amount), 0))
        if since is not None:
            query = query.where(Order.created_at >= since)
        rows = (await self.session.execute(query.group_by(Order.status))).all()
        result = {"total": 0, "revenue": 0}
        for status, count, amount in rows:
            result[str(status)] = int(count)
            result["total"] += int(count)
            if status in (OrderStatus.COMPLETED, OrderStatus.PAID):
                result["revenue"] += int(amount)
        return result

    @staticmethod
    def period_start(days: int | None) -> datetime | None:
        if days is None:
            return None
        return datetime.now(UTC) - timedelta(days=days)

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Payment, PaymentEvent
from app.models.enums import PaymentStatus

logger = logging.getLogger(__name__)


class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        provider: str,
        payment_id: str,
        order_id: int,
        user_id: int,
        amount: int,
        currency: str,
        payment_url: str | None,
        idempotence_key: str | None,
        raw_create_response: dict | None,
    ) -> Payment:
        payment = Payment(
            provider=provider,
            payment_id=payment_id,
            order_id=order_id,
            user_id=user_id,
            amount=amount,
            currency=currency,
            payment_url=payment_url,
            idempotence_key=idempotence_key,
            raw_create_response=raw_create_response,
            status=PaymentStatus.PENDING,
        )
        self.session.add(payment)
        await self.session.flush()
        return payment

    async def get_by_provider_id(self, provider: str, payment_id: str) -> Payment | None:
        return await self.session.scalar(
            select(Payment).where(Payment.provider == provider, Payment.payment_id == payment_id)
        )

    async def mark_paid(self, payment: Payment, raw_webhook: dict) -> bool:
        """Returns True only the first time. Repeat webhooks are ignored."""
        if payment.status == PaymentStatus.PAID:
            return False
        payment.status = PaymentStatus.PAID
        payment.paid_at = datetime.now(UTC)
        payment.raw_webhook = raw_webhook
        await self.session.flush()
        return True

    async def mark_status(self, payment: Payment, status: PaymentStatus, raw_webhook: dict) -> None:
        payment.status = status
        payment.raw_webhook = raw_webhook
        await self.session.flush()

    async def register_event(
        self,
        *,
        provider: str,
        event_key: str,
        payment_id: str | None,
        payment_row_id: int | None,
        payload: dict | None,
        result: str = "processed",
        message: str | None = None,
    ) -> bool:
        """Insert an event row. Returns False if this exact event was already handled.

        The insert runs inside a SAVEPOINT: a replay violates the unique constraint, and
        rolling the whole transaction back instead would discard everything the caller has
        already done and expire every object it still holds — the next attribute read then
        fails with MissingGreenlet instead of returning a clean "duplicate".
        """
        event = PaymentEvent(
            provider=provider,
            event_key=event_key,
            payment_id=payment_id,
            payment_row_id=payment_row_id,
            payload=payload,
            result=result,
            message=message,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(event)
                await self.session.flush()
        except IntegrityError:
            logger.info("Duplicate %s payment event %s ignored", provider, event_key)
            return False
        return True

    async def list_for_order(self, order_id: int) -> list[Payment]:
        result = await self.session.scalars(
            select(Payment).where(Payment.order_id == order_id).order_by(Payment.id.desc())
        )
        return list(result)

    async def stats(self, since: datetime | None = None) -> dict[str, int]:
        query = select(Payment.status, func.count(Payment.id), func.coalesce(func.sum(Payment.amount), 0))
        if since is not None:
            query = query.where(Payment.created_at >= since)
        rows = (await self.session.execute(query.group_by(Payment.status))).all()
        stats = {"paid": 0, "failed": 0, "pending": 0, "revenue": 0}
        for status, count, amount in rows:
            stats[str(status)] = int(count)
            if status == PaymentStatus.PAID:
                stats["revenue"] += int(amount)
        return stats

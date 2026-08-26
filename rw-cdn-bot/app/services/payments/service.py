"""Payment orchestration: creation, webhook validation, idempotent crediting."""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import PaymentValidationError
from app.models import Order, User
from app.models.enums import OrderStatus, PaymentProvider, PaymentStatus
from app.repositories import AuditRepository, OrderRepository, PaymentRepository
from app.services.payments.base import PaymentGateway, WebhookResult
from app.services.payments.platega import PlategaGateway
from app.services.payments.yookassa import YooKassaGateway

logger = logging.getLogger(__name__)


def build_gateways() -> dict[str, PaymentGateway]:
    return {
        PaymentProvider.PLATEGA: PlategaGateway(),
        PaymentProvider.YOOKASSA: YooKassaGateway(),
    }


class PaymentService:
    def __init__(self, session: AsyncSession, gateways: dict[str, PaymentGateway] | None = None) -> None:
        self.session = session
        self.gateways = gateways or build_gateways()
        self.payments = PaymentRepository(session)
        self.orders = OrderRepository(session)
        self.audit = AuditRepository(session)

    def gateway(self, provider: str) -> PaymentGateway:
        gateway = self.gateways.get(provider)
        if gateway is None:
            raise PaymentValidationError(f"Unknown payment provider: {provider}")
        return gateway

    def available(self) -> list[PaymentGateway]:
        return [gateway for gateway in self.gateways.values() if gateway.configured]

    async def create(
        self, *, order: Order, user: User, provider: str, description: str, return_url: str
    ):
        gateway = self.gateway(provider)
        created = await gateway.create_payment(
            order_id=order.id,
            amount=order.amount,
            currency=order.currency,
            description=description,
            user_telegram_id=user.telegram_id,
            return_url=return_url,
        )
        payment = await self.payments.create(
            provider=provider,
            payment_id=created.payment_id,
            order_id=order.id,
            user_id=user.id,
            amount=order.amount,
            currency=order.currency,
            payment_url=created.payment_url,
            idempotence_key=created.idempotence_key,
            raw_create_response=created.raw,
        )
        await self.orders.set_status(order, OrderStatus.WAITING_PAYMENT)
        await self.audit.log(
            "payment.created",
            user_id=user.telegram_id,
            order_id=order.id,
            message=f"{provider} payment {created.payment_id} for {order.amount_display}",
        )
        return payment

    async def handle_webhook(
        self, provider: str, headers: dict[str, str], body: bytes, remote_ip: str
    ) -> tuple[bool, int | None]:
        """Validate and apply a callback.

        Returns (order_should_be_deployed, order_id). Never raises for duplicates —
        replays are recorded and ignored.
        """
        gateway = self.gateway(provider)
        result: WebhookResult = await gateway.parse_webhook(headers, body, remote_ip)

        payment = await self.payments.get_by_provider_id(provider, result.payment_id)
        if payment is None:
            await self.payments.register_event(
                provider=provider,
                event_key=f"unknown:{result.event_key}",
                payment_id=result.payment_id,
                payment_row_id=None,
                payload=result.raw,
                result="unknown_payment",
            )
            raise PaymentValidationError(f"Unknown {provider} payment {result.payment_id}")

        fresh = await self.payments.register_event(
            provider=provider,
            event_key=result.event_key,
            payment_id=result.payment_id,
            payment_row_id=payment.id,
            payload=result.raw,
        )
        if not fresh:
            logger.info("Duplicate %s webhook for %s ignored", provider, result.payment_id)
            return False, payment.order_id

        order = await self.orders.get(payment.order_id)
        if order is None:
            raise PaymentValidationError(f"Payment {payment.id} references a missing order")

        if result.amount is not None and result.amount != payment.amount:
            await self.audit.log(
                "payment.amount_mismatch",
                order_id=order.id,
                status="error",
                message=f"expected {payment.amount}, callback said {result.amount}",
            )
            raise PaymentValidationError("Callback amount does not match the stored payment amount")

        if result.currency is not None and result.currency.upper() != payment.currency.upper():
            raise PaymentValidationError("Callback currency does not match the stored payment currency")

        if result.status is not PaymentStatus.PAID:
            await self.payments.mark_status(payment, result.status, result.raw)
            if result.status in (PaymentStatus.CANCELLED, PaymentStatus.FAILED):
                if order.status in (OrderStatus.CREATED, OrderStatus.WAITING_PAYMENT):
                    await self.orders.set_status(order, OrderStatus.CANCELLED)
            elif result.status is PaymentStatus.REFUNDED:
                await self.orders.set_status(order, OrderStatus.REFUNDED)
            return False, order.id

        # Never trust the callback alone — confirm against the provider API.
        confirmed = await gateway.fetch_status(result.payment_id)
        if confirmed is not PaymentStatus.PAID:
            await self.audit.log(
                "payment.status_mismatch",
                order_id=order.id,
                status="error",
                message=f"callback said paid, API said {confirmed}",
            )
            raise PaymentValidationError("Provider API does not confirm the payment")

        first_time = await self.payments.mark_paid(payment, result.raw)
        if not first_time:
            return False, order.id

        if order.status in (OrderStatus.CREATED, OrderStatus.WAITING_PAYMENT):
            await self.orders.set_status(order, OrderStatus.PAID)
        await self.audit.log(
            "payment.paid", order_id=order.id, message=f"{provider} {result.payment_id}"
        )
        return True, order.id

import json

import pytest

from app.models.enums import PaymentStatus
from app.repositories import PaymentRepository
from app.services.payments import PaymentService
from app.services.payments.base import PaymentGateway, WebhookResult


class FakeGateway(PaymentGateway):
    provider = "platega"
    title = "fake"

    @property
    def configured(self) -> bool:
        return True

    async def create_payment(self, **kwargs):  # pragma: no cover - unused here
        raise NotImplementedError

    async def parse_webhook(self, headers, body, remote_ip) -> WebhookResult:
        data = json.loads(body)
        return WebhookResult(
            payment_id=data["id"],
            status=PaymentStatus.PAID,
            amount=data["amount"],
            currency="RUB",
            event_key=f"{data['id']}:CONFIRMED",
            raw=data,
        )

    async def fetch_status(self, payment_id: str) -> PaymentStatus:
        return PaymentStatus.PAID


@pytest.fixture
def service(session):
    return PaymentService(session, gateways={"platega": FakeGateway()})


async def test_repeat_webhook_credits_once(session, seeded, service):
    order, user = seeded["order"], seeded["user"]
    await PaymentRepository(session).create(
        provider="platega", payment_id="abc123", order_id=order.id, user_id=user.id,
        amount=150000, currency="RUB", payment_url="https://pay", idempotence_key="k",
        raw_create_response={},
    )
    await session.commit()

    body = json.dumps({"id": "abc123", "amount": 150000}).encode()

    first, _ = await service.handle_webhook("platega", {}, body, "1.1.1.1")
    assert first is True

    for _ in range(5):
        again, _ = await service.handle_webhook("platega", {}, body, "1.1.1.1")
        assert again is False


async def test_amount_mismatch_is_rejected(session, seeded, service):
    from app.core.exceptions import PaymentValidationError

    order, user = seeded["order"], seeded["user"]
    await PaymentRepository(session).create(
        provider="platega", payment_id="abc999", order_id=order.id, user_id=user.id,
        amount=150000, currency="RUB", payment_url="https://pay", idempotence_key="k2",
        raw_create_response={},
    )
    await session.commit()

    body = json.dumps({"id": "abc999", "amount": 100}).encode()
    with pytest.raises(PaymentValidationError):
        await service.handle_webhook("platega", {}, body, "1.1.1.1")

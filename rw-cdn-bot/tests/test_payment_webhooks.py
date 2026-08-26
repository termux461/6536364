import json

import pytest

from app.core.exceptions import PaymentValidationError
from app.models.enums import PaymentStatus
from app.services.payments.platega import PlategaGateway
from app.services.payments.yookassa import YooKassaGateway


async def test_platega_rejects_wrong_secret():
    gateway = PlategaGateway()
    body = json.dumps({"id": "tx1", "amount": 1500, "currency": "RUB", "status": "CONFIRMED"}).encode()
    with pytest.raises(PaymentValidationError):
        await gateway.parse_webhook(
            {"X-MerchantId": "merchant-1", "X-Secret": "wrong"}, body, "1.2.3.4"
        )


async def test_platega_parses_confirmed():
    gateway = PlategaGateway()
    body = json.dumps({"id": "tx1", "amount": 1500, "currency": "RUB", "status": "CONFIRMED"}).encode()
    result = await gateway.parse_webhook(
        {"X-MerchantId": "merchant-1", "X-Secret": "secret-1"}, body, "1.2.3.4"
    )
    assert result.status is PaymentStatus.PAID
    assert result.amount == 150000
    assert result.event_key == "tx1:CONFIRMED"


async def test_yookassa_rejects_foreign_ip():
    gateway = YooKassaGateway()
    body = json.dumps(
        {"event": "payment.succeeded", "object": {"id": "p1", "amount": {"value": "1500.00", "currency": "RUB"}}}
    ).encode()
    with pytest.raises(PaymentValidationError):
        await gateway.parse_webhook({}, body, "8.8.8.8")


async def test_yookassa_accepts_documented_range():
    gateway = YooKassaGateway()
    body = json.dumps(
        {"event": "payment.succeeded", "object": {"id": "p1", "amount": {"value": "1500.00", "currency": "RUB"}}}
    ).encode()
    result = await gateway.parse_webhook({}, body, "185.71.76.5")
    assert result.status is PaymentStatus.PAID
    assert result.amount == 150000

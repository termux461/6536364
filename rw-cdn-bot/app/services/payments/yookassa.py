"""YooKassa gateway (API v3, https://yookassa.ru/developers/api).

  POST https://api.yookassa.ru/v3/payments   Basic auth shopId:secretKey + Idempotence-Key
  GET  https://api.yookassa.ru/v3/payments/{id}
Notifications are unsigned; authenticity is established by the source IP range published by
YooKassa (YOOKASSA_ALLOWED_IPS) plus a server-side status re-check before the order is credited.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import uuid

import httpx

from app.config import get_settings
from app.core.exceptions import PaymentError, PaymentValidationError, TransientError
from app.core.retry import retry_async
from app.models.enums import PaymentStatus
from app.services.payments.base import (
    CreatedPayment,
    PaymentGateway,
    WebhookResult,
    kopecks_from_rubles,
    rubles_from_kopecks,
)

logger = logging.getLogger(__name__)

API_URL = "https://api.yookassa.ru/v3"

STATUS_MAP = {
    "succeeded": PaymentStatus.PAID,
    "canceled": PaymentStatus.CANCELLED,
    "pending": PaymentStatus.PENDING,
    "waiting_for_capture": PaymentStatus.PENDING,
}

EVENT_MAP = {
    "payment.succeeded": PaymentStatus.PAID,
    "payment.canceled": PaymentStatus.CANCELLED,
    "payment.waiting_for_capture": PaymentStatus.PENDING,
    "refund.succeeded": PaymentStatus.REFUNDED,
}


class YooKassaGateway(PaymentGateway):
    provider = "yookassa"
    title = "💳 ЮKassa"

    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def configured(self) -> bool:
        return bool(self.settings.yookassa_shop_id and self.settings.yookassa_secret_key)

    @property
    def _auth(self) -> tuple[str, str]:
        return self.settings.yookassa_shop_id, self.settings.yookassa_secret_key

    async def create_payment(
        self,
        *,
        order_id: int,
        amount: int,
        currency: str,
        description: str,
        user_telegram_id: int,
        return_url: str,
    ) -> CreatedPayment:
        idempotence_key = str(uuid.uuid4())
        payload: dict = {
            "amount": {"value": rubles_from_kopecks(amount), "currency": currency},
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": return_url},
            "description": description[:128],
            "metadata": {"order_id": str(order_id), "telegram_id": str(user_telegram_id)},
        }
        if self.settings.yookassa_receipt_email:
            payload["receipt"] = {
                "customer": {"email": self.settings.yookassa_receipt_email},
                "items": [
                    {
                        "description": description[:128],
                        "quantity": "1.00",
                        "amount": {"value": rubles_from_kopecks(amount), "currency": currency},
                        "vat_code": 1,
                        "payment_mode": "full_payment",
                        "payment_subject": "service",
                    }
                ],
            }

        async def _call() -> dict:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{API_URL}/payments",
                    json=payload,
                    auth=self._auth,
                    headers={"Idempotence-Key": idempotence_key},
                )
            if response.status_code >= 500:
                raise TransientError(f"YooKassa HTTP {response.status_code}")
            if response.status_code >= 400:
                raise PaymentError(f"YooKassa refused the payment: {response.text[:500]}")
            return response.json()

        data = await retry_async(_call, attempts=3, label="yookassa.create")
        url = (data.get("confirmation") or {}).get("confirmation_url")
        if not url:
            raise PaymentError(f"YooKassa returned no confirmation_url: {data}")
        return CreatedPayment(
            payment_id=str(data["id"]),
            payment_url=url,
            raw=data,
            idempotence_key=idempotence_key,
        )

    def _ip_allowed(self, remote_ip: str) -> bool:
        networks = self.settings.yookassa_allowed_ips
        if not networks:
            return True  # not configured — rely on the server-side status re-check
        try:
            address = ipaddress.ip_address(remote_ip)
        except ValueError:
            return False
        for entry in networks:
            try:
                if address in ipaddress.ip_network(entry, strict=False):
                    return True
            except ValueError:
                continue
        return False

    async def parse_webhook(self, headers: dict[str, str], body: bytes, remote_ip: str) -> WebhookResult:
        if not self._ip_allowed(remote_ip):
            raise PaymentValidationError(f"YooKassa notification from untrusted IP {remote_ip}")

        try:
            data = json.loads(body.decode("utf-8"))
        except ValueError as exc:
            raise PaymentValidationError("YooKassa notification is not valid JSON") from exc

        event = str(data.get("event") or "")
        payment_object = data.get("object") or {}
        payment_id = str(payment_object.get("id") or "")
        if not payment_id:
            raise PaymentValidationError("YooKassa notification has no payment id")

        status = EVENT_MAP.get(event)
        if status is None:
            raise PaymentValidationError(f"Unsupported YooKassa event: {event}")

        amount_block = payment_object.get("amount") or {}
        amount = (
            kopecks_from_rubles(amount_block["value"]) if amount_block.get("value") is not None else None
        )

        return WebhookResult(
            payment_id=payment_id,
            status=status,
            amount=amount,
            currency=amount_block.get("currency"),
            event_key=f"{payment_id}:{event}",
            raw=data,
        )

    async def fetch_status(self, payment_id: str) -> PaymentStatus:
        async def _call() -> dict:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(f"{API_URL}/payments/{payment_id}", auth=self._auth)
            if response.status_code >= 500:
                raise TransientError(f"YooKassa HTTP {response.status_code}")
            if response.status_code >= 400:
                raise PaymentError(f"YooKassa status check failed: {response.text[:300]}")
            return response.json()

        data = await retry_async(_call, attempts=3, label="yookassa.status")
        return STATUS_MAP.get(str(data.get("status", "")), PaymentStatus.PENDING)

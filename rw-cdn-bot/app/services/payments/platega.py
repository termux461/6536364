"""Platega gateway.

Documented surface used here (docs.platega.io):
  POST {base}/transaction/process   headers: X-MerchantId, X-Secret
  GET  {base}/transaction/{id}      headers: X-MerchantId, X-Secret
  Callback: POST to the merchant URL with X-MerchantId / X-Secret headers and
            {"id", "amount", "currency", "status", "paymentMethod"}.
Platega operates in major units (rubles), the database stores kopecks — conversion happens here.
"""
from __future__ import annotations

import hmac
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

PAYMENT_METHOD_SBP = 2

STATUS_MAP = {
    "CONFIRMED": PaymentStatus.PAID,
    "SUCCESS": PaymentStatus.PAID,
    "CANCELED": PaymentStatus.CANCELLED,
    "CANCELLED": PaymentStatus.CANCELLED,
    "REJECTED": PaymentStatus.FAILED,
    "ERROR": PaymentStatus.FAILED,
    "CHARGEBACKED": PaymentStatus.REFUNDED,
    "PENDING": PaymentStatus.PENDING,
    "CREATED": PaymentStatus.PENDING,
    "PROCESSING": PaymentStatus.PENDING,
}


class PlategaGateway(PaymentGateway):
    provider = "platega"
    title = "💳 Platega"

    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def configured(self) -> bool:
        return bool(self.settings.platega_merchant_id and self.settings.platega_api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "X-MerchantId": self.settings.platega_merchant_id,
            "X-Secret": self.settings.platega_api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

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
        transaction_id = str(uuid.uuid4())
        payload = {
            "id": transaction_id,
            "paymentMethod": PAYMENT_METHOD_SBP,
            "paymentDetails": {"amount": float(rubles_from_kopecks(amount)), "currency": currency},
            "description": description,
            "return": return_url,
            "failedUrl": return_url,
            "payload": f"order:{order_id}",
            "metadata": {"orderId": str(order_id), "userId": str(user_telegram_id)},
        }

        async def _call() -> dict:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.settings.platega_api_url.rstrip('/')}/transaction/process",
                    json=payload,
                    headers=self._headers(),
                )
            if response.status_code >= 500:
                raise TransientError(f"Platega HTTP {response.status_code}")
            if response.status_code >= 400:
                raise PaymentError(f"Platega refused the transaction: {response.text[:500]}")
            return response.json()

        data = await retry_async(_call, attempts=3, label="platega.create")

        # v1 returns "redirect", v2 returns "url"
        url = data.get("redirect") or data.get("url") or data.get("paymentUrl")
        payment_id = str(data.get("transactionId") or data.get("id") or transaction_id)
        if not url:
            raise PaymentError(f"Platega returned no payment URL: {data}")
        return CreatedPayment(
            payment_id=payment_id, payment_url=url, raw=data, idempotence_key=transaction_id
        )

    async def parse_webhook(self, headers: dict[str, str], body: bytes, remote_ip: str) -> WebhookResult:
        import json

        lower = {key.lower(): value for key, value in headers.items()}
        merchant = lower.get("x-merchantid", "")
        secret = lower.get("x-secret", "")

        expected_secret = self.settings.platega_webhook_secret or self.settings.platega_api_key
        if not hmac.compare_digest(merchant, self.settings.platega_merchant_id) or not hmac.compare_digest(
            secret, expected_secret
        ):
            raise PaymentValidationError("Platega callback credentials do not match")

        try:
            data = json.loads(body.decode("utf-8"))
        except ValueError as exc:
            raise PaymentValidationError("Platega callback body is not valid JSON") from exc

        payment_id = str(data.get("id") or "")
        if not payment_id:
            raise PaymentValidationError("Platega callback has no transaction id")

        raw_status = str(data.get("status") or "").upper()
        status = STATUS_MAP.get(raw_status)
        if status is None:
            raise PaymentValidationError(f"Unknown Platega status: {raw_status}")

        amount_raw = data.get("amount")
        amount = kopecks_from_rubles(amount_raw) if amount_raw is not None else None

        return WebhookResult(
            payment_id=payment_id,
            status=status,
            amount=amount,
            currency=data.get("currency"),
            event_key=f"{payment_id}:{raw_status}",
            raw=data,
        )

    async def fetch_status(self, payment_id: str) -> PaymentStatus:
        async def _call() -> dict:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self.settings.platega_api_url.rstrip('/')}/transaction/{payment_id}",
                    headers=self._headers(),
                )
            if response.status_code >= 500:
                raise TransientError(f"Platega HTTP {response.status_code}")
            if response.status_code >= 400:
                raise PaymentError(f"Platega status check failed: {response.text[:300]}")
            return response.json()

        data = await retry_async(_call, attempts=3, label="platega.status")
        return STATUS_MAP.get(str(data.get("status", "")).upper(), PaymentStatus.PENDING)

import hashlib
import hmac
import json
import logging
import uuid
from dataclasses import dataclass

import aiohttp

from bot.config import settings

logger = logging.getLogger(__name__)


@dataclass
class Invoice:
    external_id: str
    pay_url: str


class PaymentError(Exception):
    pass


class BaseProvider:
    method = "base"

    async def create_invoice(self, amount: float, description: str, payload: str) -> Invoice:
        raise NotImplementedError

    async def is_paid(self, body: dict, headers: dict) -> tuple[bool, str]:
        """Returns (is_paid, external_id) for a webhook payload that has already been logged."""
        raise NotImplementedError


class PlategaProvider(BaseProvider):
    """Generic card-payment aggregator client.

    Endpoint/field names follow Platega's merchant API conventions; confirm exact
    field names against the credentials issued in your Platega merchant dashboard
    before going live.
    """

    method = "platega"
    base_url = "https://app.platega.io/api/v1"

    async def create_invoice(self, amount: float, description: str, payload: str) -> Invoice:
        external_id = str(uuid.uuid4())
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/payments",
                headers={
                    "X-Merchant-Id": settings.PLATEGA_SHOP_ID,
                    "X-Secret-Key": settings.PLATEGA_API_KEY,
                },
                json={
                    "amount": float(amount),
                    "currency": "RUB",
                    "description": description,
                    "orderId": external_id,
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                if resp.status >= 400:
                    raise PaymentError(f"Platega error: {data}")
                return Invoice(external_id=external_id, pay_url=data.get("paymentUrl") or data.get("url", ""))

    async def is_paid(self, body: dict, headers: dict) -> tuple[bool, str]:
        external_id = body.get("orderId", "")
        status = (body.get("status") or "").lower()
        return status in ("succeeded", "paid", "completed"), external_id


class YooKassaProvider(BaseProvider):
    method = "yookassa"
    base_url = "https://api.yookassa.ru/v3"

    async def create_invoice(self, amount: float, description: str, payload: str) -> Invoice:
        idempotence_key = str(uuid.uuid4())
        auth = aiohttp.BasicAuth(settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/payments",
                auth=auth,
                headers={"Idempotence-Key": idempotence_key},
                json={
                    "amount": {"value": f"{float(amount):.2f}", "currency": "RUB"},
                    "confirmation": {"type": "redirect", "return_url": settings.WEBHOOK_BASE_URL or "https://t.me"},
                    "capture": True,
                    "description": description,
                    "metadata": {"payload": payload},
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                if resp.status >= 400:
                    raise PaymentError(f"YooKassa error: {data}")
                return Invoice(
                    external_id=data["id"],
                    pay_url=data["confirmation"]["confirmation_url"],
                )

    async def is_paid(self, body: dict, headers: dict) -> tuple[bool, str]:
        # YooKassa does not sign webhooks; re-fetch the payment from the API to confirm status.
        obj = body.get("object", {})
        payment_id = obj.get("id", "")
        if not payment_id:
            return False, ""
        auth = aiohttp.BasicAuth(settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY)
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/payments/{payment_id}", auth=auth, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                data = await resp.json()
                return data.get("status") == "succeeded", payment_id


class CryptoBotProvider(BaseProvider):
    method = "cryptobot"
    base_url = "https://pay.crypt.bot/api"

    async def create_invoice(self, amount: float, description: str, payload: str) -> Invoice:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/createInvoice",
                headers={"Crypto-Pay-API-Token": settings.CRYPTOBOT_TOKEN},
                json={
                    "currency_type": "fiat",
                    "fiat": "RUB",
                    "amount": str(amount),
                    "description": description,
                    "payload": payload,
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                if not data.get("ok"):
                    raise PaymentError(f"CryptoBot error: {data}")
                result = data["result"]
                return Invoice(external_id=str(result["invoice_id"]), pay_url=result["pay_url"])

    def verify_signature(self, body_raw: bytes, signature: str) -> bool:
        secret = hashlib.sha256(settings.CRYPTOBOT_TOKEN.encode()).digest()
        expected = hmac.new(secret, body_raw, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def is_paid(self, body: dict, headers: dict) -> tuple[bool, str]:
        payload = body.get("payload", {})
        status = (payload.get("status") or "").lower()
        return status == "paid", str(payload.get("invoice_id", ""))


PROVIDERS: dict[str, BaseProvider] = {
    "platega": PlategaProvider(),
    "yookassa": YooKassaProvider(),
    "cryptobot": CryptoBotProvider(),
}


def get_provider(method: str) -> BaseProvider:
    provider = PROVIDERS.get(method)
    if provider is None:
        raise PaymentError(f"Unknown payment method: {method}")
    return provider

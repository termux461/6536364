import uuid

import httpx

from bot.services.payments.base import PaymentProvider, PaymentResult


class YooKassaProvider(PaymentProvider):
    code = "yookassa"
    title = "ЮKassa"

    def __init__(self, shop_id: str, secret_key: str, return_url: str = "https://t.me"):
        self.return_url = return_url
        self._client = httpx.AsyncClient(
            base_url="https://api.yookassa.ru/v3",
            auth=(shop_id, secret_key),
            timeout=15.0,
        )

    async def create_payment(self, *, amount: float, currency: str, description: str, payload: dict) -> PaymentResult:
        idempotence_key = str(uuid.uuid4())
        resp = await self._client.post(
            "/payments",
            headers={"Idempotence-Key": idempotence_key},
            json={
                "amount": {"value": f"{amount:.2f}", "currency": currency},
                "confirmation": {"type": "redirect", "return_url": self.return_url},
                "capture": True,
                "description": description,
                "metadata": {"payment_id": str(payload.get("payment_id", ""))},
            },
        )
        data = resp.json()
        return PaymentResult(
            external_id=data.get("id", ""),
            pay_url=data.get("confirmation", {}).get("confirmation_url"),
            raw=data,
        )

    async def check_payment(self, external_id: str) -> bool:
        resp = await self._client.get(f"/payments/{external_id}")
        data = resp.json()
        return data.get("status") == "succeeded"

    async def webhook_handler(self, data: dict) -> tuple[str, bool] | None:
        if data.get("event") != "payment.succeeded":
            return None
        obj = data.get("object", {})
        return obj.get("id", ""), True

import httpx

from bot.services.payments.base import PaymentProvider, PaymentResult


class CryptoBotProvider(PaymentProvider):
    code = "cryptobot"
    title = "CryptoBot"

    def __init__(self, api_token: str, api_url: str = "https://pay.crypt.bot/api"):
        self.api_url = api_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.api_url, headers={"Crypto-Pay-API-Token": api_token}, timeout=15.0)

    async def create_payment(self, *, amount: float, currency: str, description: str, payload: dict) -> PaymentResult:
        resp = await self._client.post("/createInvoice", json={
            "amount": str(amount),
            "currency_type": "fiat" if currency != "USDT" else "crypto",
            "fiat": currency if currency != "USDT" else None,
            "asset": "USDT" if currency == "USDT" else None,
            "description": description,
            "payload": str(payload.get("payment_id", "")),
        })
        data = resp.json()
        result = data.get("result", {})
        return PaymentResult(
            external_id=str(result.get("invoice_id")),
            pay_url=result.get("pay_url") or result.get("bot_invoice_url"),
            raw=result,
        )

    async def check_payment(self, external_id: str) -> bool:
        resp = await self._client.get("/getInvoices", params={"invoice_ids": external_id})
        data = resp.json()
        items = data.get("result", {}).get("items", [])
        if not items:
            return False
        return items[0].get("status") == "paid"

    async def webhook_handler(self, data: dict) -> tuple[str, bool] | None:
        payload = data.get("payload", {})
        if payload.get("update_type") != "invoice_paid":
            return None
        invoice = payload.get("payload", {})
        return str(invoice.get("invoice_id")), True

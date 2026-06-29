"""Telegram Stars (XTR) payments.

Stars invoices are created via Bot.create_invoice_link with currency="XTR" and
confirmed via the regular Telegram payment flow (pre_checkout_query +
successful_payment updates), handled in bot/handlers/payments.py. This adapter
only creates the invoice link; `check_payment` reads the stored DB status that
the successful_payment handler updates.
"""
from aiogram import Bot
from aiogram.types import LabeledPrice

from bot.services.payments.base import PaymentProvider, PaymentResult


class StarsProvider(PaymentProvider):
    code = "stars"
    title = "Telegram Stars"

    def __init__(self, bot: Bot):
        self.bot = bot

    async def create_payment(self, *, amount: float, currency: str, description: str, payload: dict) -> PaymentResult:
        stars_amount = max(1, int(round(amount)))
        link = await self.bot.create_invoice_link(
            title="VPN",
            description=description,
            payload=str(payload.get("payment_id", "")),
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label="VPN", amount=stars_amount)],
        )
        return PaymentResult(external_id=str(payload.get("payment_id", "")), pay_url=link)

    async def check_payment(self, external_id: str) -> bool:
        # Confirmation is delivered via the successful_payment update, handled
        # in bot/handlers/payments.py which marks the Payment row as PAID.
        return False

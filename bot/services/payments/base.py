from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class PaymentResult:
    external_id: str
    pay_url: str | None = None
    raw: dict | None = None


class PaymentProvider(ABC):
    code: str
    title: str

    @abstractmethod
    async def create_payment(self, *, amount: float, currency: str, description: str, payload: dict) -> PaymentResult:
        """Create a payment/invoice and return identifiers needed to check/track it."""

    @abstractmethod
    async def check_payment(self, external_id: str) -> bool:
        """Return True if the payment has been confirmed as paid."""

    async def webhook_handler(self, data: dict) -> tuple[str, bool] | None:
        """Parse a provider webhook payload. Returns (external_id, is_paid) or None if irrelevant."""
        return None

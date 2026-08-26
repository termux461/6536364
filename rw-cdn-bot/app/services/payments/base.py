from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.models.enums import PaymentStatus


@dataclass(slots=True)
class CreatedPayment:
    payment_id: str
    payment_url: str
    raw: dict
    idempotence_key: str | None = None


@dataclass(slots=True)
class WebhookResult:
    """Normalised view of a provider callback."""

    payment_id: str
    status: PaymentStatus
    amount: int | None  # kopecks
    currency: str | None
    event_key: str
    raw: dict = field(default_factory=dict)


class PaymentGateway(ABC):
    provider: str
    title: str

    @property
    @abstractmethod
    def configured(self) -> bool: ...

    @abstractmethod
    async def create_payment(
        self,
        *,
        order_id: int,
        amount: int,
        currency: str,
        description: str,
        user_telegram_id: int,
        return_url: str,
    ) -> CreatedPayment: ...

    @abstractmethod
    async def parse_webhook(self, headers: dict[str, str], body: bytes, remote_ip: str) -> WebhookResult:
        """Validate authenticity and return a normalised result.

        Must raise PaymentValidationError when the callback cannot be trusted.
        """

    @abstractmethod
    async def fetch_status(self, payment_id: str) -> PaymentStatus:
        """Server-side confirmation. Client-supplied data is never trusted on its own."""


def rubles_from_kopecks(amount: int) -> str:
    return f"{amount // 100}.{amount % 100:02d}"


def kopecks_from_rubles(value: str | float | int) -> int:
    """Convert a decimal money string to integer kopecks without float rounding drift."""
    from decimal import ROUND_HALF_UP, Decimal

    return int(
        (Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, IntPK, JSONType, TimestampMixin
from app.models.enums import PaymentStatus


class Payment(IntPK, TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("provider", "payment_id", name="uq_payments_provider_payment_id"),
    )

    provider: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    payment_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)

    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)  # kopecks
    currency: Mapped[str] = mapped_column(String(8), default="RUB", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=PaymentStatus.PENDING, index=True)

    payment_url: Mapped[str | None] = mapped_column(Text)
    idempotence_key: Mapped[str | None] = mapped_column(String(64), unique=True)
    raw_create_response: Mapped[dict | None] = mapped_column(JSONType)
    raw_webhook: Mapped[dict | None] = mapped_column(JSONType)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    order = relationship("Order", back_populates="payments", lazy="selectin")


class PaymentEvent(IntPK, TimestampMixin, Base):
    """Append-only log of every webhook delivery. Guarantees idempotency."""

    __tablename__ = "payment_events"
    __table_args__ = (
        UniqueConstraint("provider", "event_key", name="uq_payment_events_provider_event_key"),
    )

    provider: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    event_key: Mapped[str] = mapped_column(String(255), nullable=False)
    payment_id: Mapped[str | None] = mapped_column(String(128), index=True)
    payment_row_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id", ondelete="SET NULL"))
    result: Mapped[str] = mapped_column(String(32), default="processed", nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSONType)

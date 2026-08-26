from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, IntPK, TimestampMixin
from app.models.enums import OrderStatus


class Order(IntPK, TimestampMixin, Base):
    __tablename__ = "orders"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    tariff_id: Mapped[int] = mapped_column(ForeignKey("tariffs.id", ondelete="RESTRICT"))

    status: Mapped[str] = mapped_column(String(32), default=OrderStatus.CREATED, index=True, nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)  # kopecks, frozen at creation
    currency: Mapped[str] = mapped_column(String(8), default="RUB", nullable=False)

    # Progress message that gets edited in place instead of spamming the chat
    progress_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    progress_message_id: Mapped[int | None] = mapped_column(BigInteger)

    error_message: Mapped[str | None] = mapped_column(Text)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user = relationship("User", lazy="selectin")
    tariff = relationship("Tariff", lazy="selectin")
    payments = relationship("Payment", back_populates="order", lazy="selectin")
    origin_server = relationship("OriginServer", back_populates="order", uselist=False, lazy="selectin")
    deployment = relationship("Deployment", back_populates="order", uselist=False, lazy="selectin")

    @property
    def amount_display(self) -> str:
        major, minor = divmod(self.amount, 100)
        return f"{major:,}".replace(",", " ") + (f",{minor:02d}" if minor else "") + f" {self.currency}"

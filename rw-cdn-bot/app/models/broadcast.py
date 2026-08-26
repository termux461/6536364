from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, IntPK, TimestampMixin
from app.models.enums import BroadcastStatus, RecipientStatus


class Broadcast(IntPK, TimestampMixin, Base):
    __tablename__ = "broadcasts"

    admin_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    parse_mode: Mapped[str | None] = mapped_column(String(16), default="HTML")
    status: Mapped[str] = mapped_column(String(32), default=BroadcastStatus.DRAFT, index=True)
    total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    blocked: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    flood_waits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    recipients = relationship("BroadcastRecipient", back_populates="broadcast", lazy="noload")


class BroadcastRecipient(IntPK, Base):
    __tablename__ = "broadcast_recipients"

    broadcast_id: Mapped[int] = mapped_column(
        ForeignKey("broadcasts.id", ondelete="CASCADE"), index=True
    )
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=RecipientStatus.PENDING, index=True)
    error: Mapped[str | None] = mapped_column(Text)

    broadcast = relationship("Broadcast", back_populates="recipients", lazy="noload")

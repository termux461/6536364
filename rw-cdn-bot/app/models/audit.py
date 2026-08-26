from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, IntPK, TimestampMixin
from app.models.enums import StepStatus


class DeploymentStep(IntPK, Base):
    __tablename__ = "deployment_steps"

    deployment_id: Mapped[int] = mapped_column(
        ForeignKey("deployments.id", ondelete="CASCADE"), index=True
    )
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    step: Mapped[str] = mapped_column(String(64), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=StepStatus.PENDING, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)

    deployment = relationship("Deployment", back_populates="steps", lazy="selectin")


class AuditLog(IntPK, TimestampMixin, Base):
    """Never contains secrets — payloads are redacted before they get here."""

    __tablename__ = "audit_logs"

    user_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    admin_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    order_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="ok", nullable=False)
    message: Mapped[str | None] = mapped_column(Text)

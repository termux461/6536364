from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, IntPK, JSONType, TimestampMixin
from app.models.enums import DeploymentStatus


class Deployment(IntPK, TimestampMixin, Base):
    __tablename__ = "deployments"

    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(32), default=DeploymentStatus.QUEUED, index=True)
    current_step: Mapped[str | None] = mapped_column(String(64))
    attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    context: Mapped[dict | None] = mapped_column(JSONType, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    order = relationship("Order", back_populates="deployment", lazy="selectin")
    steps = relationship(
        "DeploymentStep",
        back_populates="deployment",
        lazy="selectin",
        order_by="DeploymentStep.id",
        cascade="all, delete-orphan",
    )

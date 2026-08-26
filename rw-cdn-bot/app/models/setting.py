from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, IntPK, TimestampMixin


class Setting(IntPK, TimestampMixin, Base):
    """Runtime settings editable from the in-bot admin panel (maintenance mode, texts, …)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    value: Mapped[str | None] = mapped_column(Text)


# Well-known keys
MAINTENANCE_ENABLED = "maintenance_enabled"
MAINTENANCE_TEXT = "maintenance_text"
INSTRUCTION_TEXT = "instruction_text"

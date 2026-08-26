from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, IntPK, TimestampMixin


class Tariff(IntPK, TimestampMixin, Base):
    """Price is always an integer amount of minor units (kopecks). Never a float."""

    __tablename__ = "tariffs"

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="RUB", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    @property
    def price_display(self) -> str:
        major, minor = divmod(self.price, 100)
        return f"{major:,}".replace(",", " ") + (f",{minor:02d}" if minor else "") + f" {self.currency}"

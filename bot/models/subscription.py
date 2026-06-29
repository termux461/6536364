from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from bot.db.base import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    plan: Mapped[str] = mapped_column(String(16))
    protocol: Mapped[str] = mapped_column(String(8), default="awg")
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id"))

    peer_id: Mapped[str] = mapped_column(String(64), default="")
    peer_private_key_enc: Mapped[str] = mapped_column(String(512), default="")
    peer_ip: Mapped[str] = mapped_column(String(32), default="")

    expires_at: Mapped[datetime] = mapped_column(DateTime)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

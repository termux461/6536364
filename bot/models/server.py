from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from bot.db.base import Base


class Server(Base):
    __tablename__ = "servers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    country: Mapped[str] = mapped_column(String(64))
    flag: Mapped[str] = mapped_column(String(8), default="🏳️")
    protocol: Mapped[str] = mapped_column(String(8), default="awg")
    endpoint: Mapped[str] = mapped_column(String(64), default="")

    api_url: Mapped[str] = mapped_column(String(128), default="")
    api_token: Mapped[str] = mapped_column(String(256), default="")
    public_key: Mapped[str] = mapped_column(String(64), default="")

    ssh_host: Mapped[str] = mapped_column(String(64), default="")
    ssh_port: Mapped[int] = mapped_column(Integer, default=22)
    ssh_user: Mapped[str] = mapped_column(String(32), default="root")
    ssh_password_enc: Mapped[str] = mapped_column(String(512), default="")

    wg_port: Mapped[int] = mapped_column(Integer, default=51820)

    active: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)

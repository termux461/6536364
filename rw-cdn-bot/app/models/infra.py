"""Infrastructure entities.

Terminology: the customer machine is always an **Origin Server**.
The object created inside the panel is a **Remnawave Node**, and it is installed on the Origin Server.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, IntPK, TimestampMixin
from app.models.enums import DNSRecordStatus, OriginStatus, SSHAuthType


class OriginServer(IntPK, TimestampMixin, Base):
    __tablename__ = "origin_servers"

    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), unique=True)

    origin_ip: Mapped[str | None] = mapped_column(String(64))
    origin_domain: Mapped[str | None] = mapped_column(String(255))
    cdn_domain: Mapped[str | None] = mapped_column(String(255))
    origin_port: Mapped[int] = mapped_column(Integer, default=443, nullable=False)

    ssh_port: Mapped[int] = mapped_column(Integer, default=2222, nullable=False)
    ssh_username: Mapped[str] = mapped_column(String(64), default="root", nullable=False)
    ssh_auth_type: Mapped[str] = mapped_column(String(16), default=SSHAuthType.KEY, nullable=False)
    # Encrypted at rest — see app.core.crypto
    ssh_private_key_enc: Mapped[str | None] = mapped_column(Text)
    ssh_passphrase_enc: Mapped[str | None] = mapped_column(Text)
    ssh_password_enc: Mapped[str | None] = mapped_column(Text)

    letsencrypt_email: Mapped[str | None] = mapped_column(String(255))

    origin_status: Mapped[str] = mapped_column(String(32), default=OriginStatus.NEW, nullable=False)
    os_info: Mapped[str | None] = mapped_column(String(255))
    cpu_cores: Mapped[int | None] = mapped_column(Integer)
    ram_mb: Mapped[int | None] = mapped_column(Integer)
    disk_free_mb: Mapped[int | None] = mapped_column(BigInteger)

    order = relationship("Order", back_populates="origin_server", lazy="selectin")


class RemnawaveInstance(IntPK, TimestampMixin, Base):
    """Customer's Remnawave panel credentials for one order."""

    __tablename__ = "remnawave_instances"

    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), unique=True)
    panel_url: Mapped[str | None] = mapped_column(String(512))
    api_token_enc: Mapped[str | None] = mapped_column(Text)
    caddy_token_enc: Mapped[str | None] = mapped_column(Text)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class RemnawaveResource(IntPK, TimestampMixin, Base):
    """UUIDs of everything created inside the panel, so a restarted worker reuses them."""

    __tablename__ = "remnawave_resources"

    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), unique=True)
    profile_uuid: Mapped[str | None] = mapped_column(String(64))
    profile_name: Mapped[str | None] = mapped_column(String(128))
    inbound_uuid: Mapped[str | None] = mapped_column(String(64))
    inbound_tag: Mapped[str | None] = mapped_column(String(128))
    node_uuid: Mapped[str | None] = mapped_column(String(64))
    node_name: Mapped[str | None] = mapped_column(String(128))
    host_uuid: Mapped[str | None] = mapped_column(String(64))
    node_compose_enc: Mapped[str | None] = mapped_column(Text)
    node_secret_enc: Mapped[str | None] = mapped_column(Text)


class YandexProject(IntPK, TimestampMixin, Base):
    __tablename__ = "yandex_projects"

    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), unique=True)
    cloud_id: Mapped[str | None] = mapped_column(String(128))
    folder_id: Mapped[str | None] = mapped_column(String(128))
    # How this order authenticates to Yandex Cloud: service_account | oauth | cookie
    auth_type: Mapped[str] = mapped_column(String(32), default="service_account", nullable=False)
    service_account_key_enc: Mapped[str | None] = mapped_column(Text)
    oauth_token_enc: Mapped[str | None] = mapped_column(Text)
    auth_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Only used to resolve the account id when granting roles — never for authentication.
    yandex_login: Mapped[str | None] = mapped_column(String(128))

    certificate_id: Mapped[str | None] = mapped_column(String(128))
    certificate_status: Mapped[str | None] = mapped_column(String(32))
    acme_challenge_name: Mapped[str | None] = mapped_column(String(255))
    acme_challenge_type: Mapped[str | None] = mapped_column(String(16))
    acme_challenge_value: Mapped[str | None] = mapped_column(String(512))

    origin_group_id: Mapped[str | None] = mapped_column(String(128))
    cdn_resource_id: Mapped[str | None] = mapped_column(String(128))
    cdn_cname: Mapped[str | None] = mapped_column(String(255))
    provider_activated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class DNSRecord(IntPK, TimestampMixin, Base):
    __tablename__ = "dns_records"

    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    record_type: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str] = mapped_column(String(512), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default=DNSRecordStatus.PLANNED, nullable=False)

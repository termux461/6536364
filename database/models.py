import datetime
import enum

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Enum, Float, ForeignKey, Integer,
    JSON, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    locale: Mapped[str] = mapped_column(String(8), default="ru")
    balance: Mapped[float] = mapped_column(Float, default=0)
    referrer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_subscribed_channel: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="user")
    payments: Mapped[list["Payment"]] = relationship(back_populates="user")
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="user")


class Host(Base):
    __tablename__ = "hosts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    api_url: Mapped[str] = mapped_column(String(255))
    api_token: Mapped[str] = mapped_column(Text)
    ssh_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ssh_port: Mapped[int] = mapped_column(Integer, default=22)
    ssh_user: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ssh_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_ping_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_checked_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tariffs: Mapped[list["Tariff"]] = relationship(back_populates="host")


class Tariff(Base):
    __tablename__ = "tariffs"

    id: Mapped[int] = mapped_column(primary_key=True)
    host_id: Mapped[int] = mapped_column(ForeignKey("hosts.id"))
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[float] = mapped_column(Float)
    duration_days: Mapped[int] = mapped_column(Integer)
    traffic_limit_gb: Mapped[int] = mapped_column(Integer, default=0)  # 0 = unlimited
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    host: Mapped["Host"] = relationship(back_populates="tariffs")


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    tariff_id: Mapped[int] = mapped_column(ForeignKey("tariffs.id"))
    host_id: Mapped[int] = mapped_column(ForeignKey("hosts.id"))
    remnawave_uuid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subscription_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[SubscriptionStatus] = mapped_column(Enum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE)
    starts_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="subscriptions")
    tariff: Mapped["Tariff"] = relationship()
    host: Mapped["Host"] = relationship()


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    tariff_id: Mapped[int | None] = mapped_column(ForeignKey("tariffs.id"), nullable=True)
    provider: Mapped[str] = mapped_column(String(32))
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus), default=PaymentStatus.PENDING)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    paid_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="payments")


class PaymentMethod(Base):
    """Admin-toggleable payment providers shown to users."""
    __tablename__ = "payment_methods"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)  # stars / cryptobot / yookassa
    title: Mapped[str] = mapped_column(String(64))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    config: Mapped[dict] = mapped_column(JSON, default=dict)


class ReferralEarning(Base):
    __tablename__ = "referral_earnings"

    id: Mapped[int] = mapped_column(primary_key=True)
    referrer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    referral_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"), nullable=True)
    amount: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WithdrawRequest(Base):
    __tablename__ = "withdraw_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    amount: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/approved/rejected
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TicketStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"


class TicketCategory(Base):
    """Admin-configurable ticket topics offered to users in the support Mini App."""
    __tablename__ = "ticket_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    title_ru: Mapped[str] = mapped_column(String(64))
    title_en: Mapped[str] = mapped_column(String(64))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("ticket_categories.id", ondelete="SET NULL"), nullable=True)
    subject: Mapped[str] = mapped_column(String(255))
    status: Mapped[TicketStatus] = mapped_column(Enum(TicketStatus), default=TicketStatus.OPEN)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="tickets")
    category: Mapped["TicketCategory"] = relationship()
    messages: Mapped[list["TicketMessage"]] = relationship(back_populates="ticket", order_by="TicketMessage.created_at")


class SenderType(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"


class TicketMessage(Base):
    __tablename__ = "ticket_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    sender_type: Mapped[SenderType] = mapped_column(Enum(SenderType))
    sender_admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachment_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attachment_type: Mapped[str | None] = mapped_column(String(16), nullable=True)  # photo / file
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ticket: Mapped["Ticket"] = relationship(back_populates="messages")


class MenuButton(Base):
    """Configurable main-menu buttons (constructor)."""
    __tablename__ = "menu_buttons"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True)
    title_ru: Mapped[str] = mapped_column(String(64))
    title_en: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))  # buy / profile / renew / referral / support / settings / speedtest
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)


class Setting(Base):
    """Generic key/value store for editable texts & feature flags."""
    __tablename__ = "settings"
    __table_args__ = (UniqueConstraint("key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(128), unique=True)
    value: Mapped[str] = mapped_column(Text, default="")


class Broadcast(Base):
    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/running/done
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

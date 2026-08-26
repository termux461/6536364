from __future__ import annotations

from enum import StrEnum


class OrderStatus(StrEnum):
    CREATED = "created"
    WAITING_PAYMENT = "waiting_payment"
    PAID = "paid"
    COLLECTING_DATA = "collecting_data"
    DEPLOYING = "deploying"
    CONFIGURING_ORIGIN = "configuring_origin"
    CONFIGURING_REMNAWAVE = "configuring_remnawave"
    CONFIGURING_YANDEX = "configuring_yandex"
    CONFIGURING_DNS = "configuring_dns"
    CHECKING = "checking"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


ACTIVE_ORDER_STATUSES = {
    OrderStatus.COLLECTING_DATA,
    OrderStatus.DEPLOYING,
    OrderStatus.CONFIGURING_ORIGIN,
    OrderStatus.CONFIGURING_REMNAWAVE,
    OrderStatus.CONFIGURING_YANDEX,
    OrderStatus.CONFIGURING_DNS,
    OrderStatus.CHECKING,
}


class PaymentProvider(StrEnum):
    PLATEGA = "platega"
    YOOKASSA = "yookassa"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class DeploymentStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_DNS = "waiting_dns"
    WAITING_CERTIFICATE = "waiting_certificate"
    WAITING_REAUTH = "waiting_reauth"
    FAILED = "failed"
    COMPLETED = "completed"
    STOPPED = "stopped"


class StepStatus(StrEnum):
    PENDING = "pending"
    STARTED = "started"
    SUCCESS = "success"
    FAILED = "failed"
    RETRY = "retry"
    WAITING = "waiting"
    SKIPPED = "skipped"


class OriginStatus(StrEnum):
    NEW = "new"
    CHECKING = "checking"
    READY = "ready"
    CONFIGURED = "configured"
    UNREACHABLE = "unreachable"


class SSHAuthType(StrEnum):
    KEY = "key"
    PASSWORD = "password"


class DNSProviderType(StrEnum):
    CLOUDFLARE = "cloudflare"
    YANDEX = "yandex"
    MANUAL = "manual"


class DNSRecordStatus(StrEnum):
    PLANNED = "planned"
    CREATED = "created"
    VERIFIED = "verified"
    MANUAL_REQUIRED = "manual_required"
    FAILED = "failed"


class BroadcastStatus(StrEnum):
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"
    CANCELLED = "cancelled"


class RecipientStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    BLOCKED = "blocked"


class YandexAuthType(StrEnum):
    """How an order authenticates to Yandex Cloud."""

    SERVICE_ACCOUNT = "service_account"
    OAUTH = "oauth"
    COOKIE = "cookie"

"""initial schema

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def _stamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("telegram_id", sa.BigInteger, nullable=False, unique=True),
        sa.Column("username", sa.String(64)),
        sa.Column("first_name", sa.String(128)),
        sa.Column("last_name", sa.String(128)),
        sa.Column("language_code", sa.String(8)),
        sa.Column("is_blocked", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("block_reason", sa.Text),
        *_stamps(),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"])

    op.create_table(
        "admins",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("telegram_id", sa.BigInteger, nullable=False, unique=True),
        sa.Column("note", sa.String(255)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        *_stamps(),
    )

    op.create_table(
        "tariffs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("price", sa.BigInteger, nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="RUB"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        *_stamps(),
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("tariff_id", sa.BigInteger, sa.ForeignKey("tariffs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="created"),
        sa.Column("amount", sa.BigInteger, nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="RUB"),
        sa.Column("progress_chat_id", sa.BigInteger),
        sa.Column("progress_message_id", sa.BigInteger),
        sa.Column("error_message", sa.Text),
        sa.Column("paid_at", TS),
        sa.Column("completed_at", TS),
        *_stamps(),
    )
    op.create_index("ix_orders_user_id", "orders", ["user_id"])
    op.create_index("ix_orders_status", "orders", ["status"])

    op.create_table(
        "payments",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("payment_id", sa.String(128), nullable=False),
        sa.Column("order_id", sa.BigInteger, sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amount", sa.BigInteger, nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="RUB"),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("payment_url", sa.Text),
        sa.Column("idempotence_key", sa.String(64), unique=True),
        sa.Column("raw_create_response", postgresql.JSONB),
        sa.Column("raw_webhook", postgresql.JSONB),
        sa.Column("paid_at", TS),
        *_stamps(),
        sa.UniqueConstraint("provider", "payment_id", name="uq_payments_provider_payment_id"),
    )
    op.create_index("ix_payments_order_id", "payments", ["order_id"])
    op.create_index("ix_payments_payment_id", "payments", ["payment_id"])

    op.create_table(
        "payment_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("event_key", sa.String(255), nullable=False),
        sa.Column("payment_id", sa.String(128)),
        sa.Column("payment_row_id", sa.BigInteger, sa.ForeignKey("payments.id", ondelete="SET NULL")),
        sa.Column("result", sa.String(32), nullable=False, server_default="processed"),
        sa.Column("message", sa.Text),
        sa.Column("payload", postgresql.JSONB),
        *_stamps(),
        sa.UniqueConstraint("provider", "event_key", name="uq_payment_events_provider_event_key"),
    )

    op.create_table(
        "deployments",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.BigInteger, sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("current_step", sa.String(64)),
        sa.Column("attempt", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text),
        sa.Column("context", postgresql.JSONB),
        sa.Column("started_at", TS),
        sa.Column("finished_at", TS),
        *_stamps(),
    )

    op.create_table(
        "deployment_steps",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("deployment_id", sa.BigInteger, sa.ForeignKey("deployments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_id", sa.BigInteger, sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step", sa.String(64), nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("attempt", sa.Integer, nullable=False, server_default="0"),
        sa.Column("started_at", TS),
        sa.Column("finished_at", TS),
        sa.Column("error", sa.Text),
    )
    op.create_index("ix_deployment_steps_deployment_id", "deployment_steps", ["deployment_id"])

    op.create_table(
        "origin_servers",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.BigInteger, sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("origin_ip", sa.String(64)),
        sa.Column("origin_domain", sa.String(255)),
        sa.Column("cdn_domain", sa.String(255)),
        sa.Column("origin_port", sa.Integer, nullable=False, server_default="443"),
        sa.Column("ssh_port", sa.Integer, nullable=False, server_default="2222"),
        sa.Column("ssh_username", sa.String(64), nullable=False, server_default="root"),
        sa.Column("ssh_auth_type", sa.String(16), nullable=False, server_default="key"),
        sa.Column("ssh_private_key_enc", sa.Text),
        sa.Column("ssh_passphrase_enc", sa.Text),
        sa.Column("ssh_password_enc", sa.Text),
        sa.Column("letsencrypt_email", sa.String(255)),
        sa.Column("origin_status", sa.String(32), nullable=False, server_default="new"),
        sa.Column("os_info", sa.String(255)),
        sa.Column("cpu_cores", sa.Integer),
        sa.Column("ram_mb", sa.Integer),
        sa.Column("disk_free_mb", sa.BigInteger),
        *_stamps(),
    )

    op.create_table(
        "remnawave_instances",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.BigInteger, sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("panel_url", sa.String(512)),
        sa.Column("api_token_enc", sa.Text),
        sa.Column("caddy_token_enc", sa.Text),
        sa.Column("verified", sa.Boolean, nullable=False, server_default=sa.false()),
        *_stamps(),
    )

    op.create_table(
        "remnawave_resources",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.BigInteger, sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("profile_uuid", sa.String(64)),
        sa.Column("profile_name", sa.String(128)),
        sa.Column("inbound_uuid", sa.String(64)),
        sa.Column("inbound_tag", sa.String(128)),
        sa.Column("node_uuid", sa.String(64)),
        sa.Column("node_name", sa.String(128)),
        sa.Column("host_uuid", sa.String(64)),
        sa.Column("node_compose_enc", sa.Text),
        sa.Column("node_secret_enc", sa.Text),
        *_stamps(),
    )

    op.create_table(
        "yandex_projects",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.BigInteger, sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("cloud_id", sa.String(128)),
        sa.Column("folder_id", sa.String(128)),
        sa.Column("service_account_key_enc", sa.Text),
        sa.Column("certificate_id", sa.String(128)),
        sa.Column("certificate_status", sa.String(32)),
        sa.Column("acme_challenge_name", sa.String(255)),
        sa.Column("acme_challenge_type", sa.String(16)),
        sa.Column("acme_challenge_value", sa.String(512)),
        sa.Column("origin_group_id", sa.String(128)),
        sa.Column("cdn_resource_id", sa.String(128)),
        sa.Column("cdn_cname", sa.String(255)),
        sa.Column("provider_activated", sa.Boolean, nullable=False, server_default=sa.false()),
        *_stamps(),
    )

    op.create_table(
        "dns_records",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.BigInteger, sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("record_type", sa.String(16), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("value", sa.String(512), nullable=False),
        sa.Column("external_id", sa.String(128)),
        sa.Column("status", sa.String(32), nullable=False, server_default="planned"),
        *_stamps(),
    )
    op.create_index("ix_dns_records_order_id", "dns_records", ["order_id"])

    op.create_table(
        "broadcasts",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("admin_id", sa.BigInteger, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("parse_mode", sa.String(16), server_default="HTML"),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("total", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sent", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("blocked", sa.Integer, nullable=False, server_default="0"),
        sa.Column("flood_waits", sa.Integer, nullable=False, server_default="0"),
        sa.Column("started_at", TS),
        sa.Column("finished_at", TS),
        *_stamps(),
    )

    op.create_table(
        "broadcast_recipients",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("broadcast_id", sa.BigInteger, sa.ForeignKey("broadcasts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("telegram_id", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text),
    )
    op.create_index("ix_broadcast_recipients_broadcast_id", "broadcast_recipients", ["broadcast_id"])
    op.create_index("ix_broadcast_recipients_status", "broadcast_recipients", ["status"])

    op.create_table(
        "settings",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(64), nullable=False, unique=True),
        sa.Column("value", sa.Text),
        *_stamps(),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger),
        sa.Column("admin_id", sa.BigInteger),
        sa.Column("order_id", sa.BigInteger),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="ok"),
        sa.Column("message", sa.Text),
        *_stamps(),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_order_id", "audit_logs", ["order_id"])


def downgrade() -> None:
    for table in (
        "audit_logs", "settings", "broadcast_recipients", "broadcasts", "dns_records",
        "yandex_projects", "remnawave_resources", "remnawave_instances", "origin_servers",
        "deployment_steps", "deployments", "payment_events", "payments", "orders",
        "tariffs", "admins", "users",
    ):
        op.drop_table(table)

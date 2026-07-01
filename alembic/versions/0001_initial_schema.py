"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tg_id", sa.BigInteger, nullable=False, unique=True, index=True),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("locale", sa.String(8), nullable=False, server_default="ru"),
        sa.Column("balance", sa.Float, nullable=False, server_default="0"),
        sa.Column("referrer_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("is_banned", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_subscribed_channel", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "hosts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("api_url", sa.String(255), nullable=False),
        sa.Column("api_token", sa.Text, nullable=False),
        sa.Column("ssh_host", sa.String(255), nullable=True),
        sa.Column("ssh_port", sa.Integer, nullable=False, server_default="22"),
        sa.Column("ssh_user", sa.String(64), nullable=True),
        sa.Column("ssh_password", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_ping_ms", sa.Integer, nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "tariffs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("host_id", sa.Integer, sa.ForeignKey("hosts.id"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("price", sa.Float, nullable=False),
        sa.Column("duration_days", sa.Integer, nullable=False),
        sa.Column("traffic_limit_gb", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("tariff_id", sa.Integer, sa.ForeignKey("tariffs.id"), nullable=False),
        sa.Column("host_id", sa.Integer, sa.ForeignKey("hosts.id"), nullable=False),
        sa.Column("remnawave_uuid", sa.String(64), nullable=True),
        sa.Column("subscription_url", sa.Text, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("starts_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reminder_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "payment_methods",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("title", sa.String(64), nullable=False),
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("config", sa.JSON, nullable=False, server_default="{}"),
    )
    op.create_table(
        "promo_codes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True, index=True),
        sa.Column("discount_percent", sa.Float, nullable=False, server_default="0"),
        sa.Column("max_uses", sa.Integer, nullable=True),
        sa.Column("uses_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("tariff_id", sa.Integer, sa.ForeignKey("tariffs.id"), nullable=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="RUB"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("external_id", sa.String(255), nullable=True, index=True),
        sa.Column("payload", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("promo_code_id", sa.Integer, sa.ForeignKey("promo_codes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("discount_amount", sa.Float, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "referral_earnings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("referrer_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("referral_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("payment_id", sa.Integer, sa.ForeignKey("payments.id"), nullable=True),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "withdraw_requests",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "ticket_categories",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title_ru", sa.String(64), nullable=False),
        sa.Column("title_en", sa.String(64), nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
    )
    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("category_id", sa.Integer, sa.ForeignKey("ticket_categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "ticket_messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("ticket_id", sa.Integer, sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("sender_type", sa.String(8), nullable=False),
        sa.Column("sender_admin_id", sa.BigInteger, nullable=True),
        sa.Column("text", sa.Text, nullable=True),
        sa.Column("attachment_path", sa.String(255), nullable=True),
        sa.Column("attachment_type", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "menu_buttons",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("key", sa.String(64), nullable=False, unique=True),
        sa.Column("title_ru", sa.String(64), nullable=False),
        sa.Column("title_en", sa.String(64), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_visible", sa.Boolean, nullable=False, server_default="true"),
    )
    op.create_table(
        "settings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("key", sa.String(128), nullable=False, unique=True),
        sa.Column("value", sa.Text, nullable=False, server_default=""),
        sa.UniqueConstraint("key"),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=True),
        sa.Column("target_id", sa.Integer, nullable=True),
        sa.Column("detail", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "broadcasts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("sent_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    for t in [
        "broadcasts", "audit_logs", "settings", "menu_buttons",
        "ticket_messages", "tickets", "ticket_categories",
        "withdraw_requests", "referral_earnings", "payments", "promo_codes",
        "payment_methods", "subscriptions", "tariffs", "hosts", "users",
    ]:
        op.drop_table(t)

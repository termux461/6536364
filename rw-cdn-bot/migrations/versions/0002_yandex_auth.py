"""yandex auth methods: oauth + cookie session

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "yandex_projects",
        sa.Column("auth_type", sa.String(32), nullable=False, server_default="service_account"),
    )
    op.add_column("yandex_projects", sa.Column("oauth_token_enc", sa.Text))
    op.add_column(
        "yandex_projects",
        sa.Column("auth_checked_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    for column in ("auth_checked_at", "oauth_token_enc", "auth_type"):
        op.drop_column("yandex_projects", column)

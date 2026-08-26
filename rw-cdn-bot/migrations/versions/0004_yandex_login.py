"""store the Yandex login used to resolve an account id when granting roles

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("yandex_projects", sa.Column("yandex_login", sa.String(128)))


def downgrade() -> None:
    op.drop_column("yandex_projects", "yandex_login")

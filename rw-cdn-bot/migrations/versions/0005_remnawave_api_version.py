"""record which Remnawave API major a panel speaks

The client supports both v2 and v3 and detects the version from GET /system/metadata, which
only v3 has. Storing the answer means the worker does not repeat the probe on every step, and
an operator can pin a value when something in front of the panel swallows it.

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "remnawave_instances",
        sa.Column("api_version", sa.String(16), nullable=False, server_default="auto"),
    )


def downgrade() -> None:
    op.drop_column("remnawave_instances", "api_version")

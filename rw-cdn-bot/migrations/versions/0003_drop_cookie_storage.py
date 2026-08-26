"""cookies are never persisted

Session cookies live only in the Redis vault under a TTL, for the duration of a single
deployment. This revision removes the column from any database created before that decision
and is a no-op on fresh installs.

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import context, op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        # `alembic upgrade --sql` has no connection to inspect. Emit the conditional drop as
        # SQL instead of blowing up, so an offline upgrade script can still be generated.
        op.execute(
            "ALTER TABLE yandex_projects DROP COLUMN IF EXISTS session_cookies_enc"
        )
        return

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("yandex_projects")}
    if "session_cookies_enc" in columns:
        op.drop_column("yandex_projects", "session_cookies_enc")


def downgrade() -> None:
    pass

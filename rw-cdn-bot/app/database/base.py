from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# JSONB on PostgreSQL, plain JSON on SQLite so the test-suite can run without a server.
JSONType = JSONB().with_variant(JSON(), "sqlite")

# SQLite only auto-assigns a primary key for a column declared exactly `INTEGER PRIMARY KEY`
# (the rowid alias). A `BIGINT PRIMARY KEY` is an ordinary column there, so every insert that
# omits the id fails with "NOT NULL constraint failed". PostgreSQL keeps the 64-bit type.
BigIntPKType = BigInteger().with_variant(Integer(), "sqlite")


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class IntPK:
    id: Mapped[int] = mapped_column(BigIntPKType, primary_key=True, autoincrement=True)

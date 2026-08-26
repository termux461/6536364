from __future__ import annotations

import os

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ.setdefault("BOT_TOKEN", "123:test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("SECRET_ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("ADMIN_IDS", "111,222")
os.environ.setdefault("PLATEGA_MERCHANT_ID", "merchant-1")
os.environ.setdefault("PLATEGA_API_KEY", "secret-1")
os.environ.setdefault("PLATEGA_WEBHOOK_SECRET", "secret-1")
os.environ.setdefault("YOOKASSA_SHOP_ID", "shop-1")
os.environ.setdefault("YOOKASSA_SECRET_KEY", "key-1")
os.environ.setdefault("YOOKASSA_ALLOWED_IPS", "185.71.76.0/27")

from app.models import Base
from app.services.yandex.auth import forget_discovered_endpoint


@pytest.fixture(autouse=True)
def _no_discovery_cache():
    """The discovered cookie-exchange endpoint is cached for the process on purpose.

    That makes tests order-dependent unless it is cleared between them.
    """
    forget_discovered_endpoint()
    yield
    forget_discovered_endpoint()


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded(session):
    from app.repositories import OrderRepository, TariffRepository, UserRepository

    user = await UserRepository(session).upsert(555, username="tester")
    tariff = await TariffRepository(session).create(
        code="auto_setup", name="Автонастройка", description="", price=150000, currency="RUB"
    )
    order = await OrderRepository(session).create(
        user_id=user.id, tariff_id=tariff.id, amount=tariff.price, currency="RUB"
    )
    await session.commit()
    return {"user": user, "tariff": tariff, "order": order}

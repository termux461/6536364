from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Tariff

DEFAULT_TARIFF_CODE = "auto_setup"


class TariffRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, tariff_id: int) -> Tariff | None:
        return await self.session.get(Tariff, tariff_id)

    async def get_by_code(self, code: str) -> Tariff | None:
        return await self.session.scalar(select(Tariff).where(Tariff.code == code))

    async def list_enabled(self) -> list[Tariff]:
        result = await self.session.scalars(
            select(Tariff).where(Tariff.enabled.is_(True)).order_by(Tariff.id)
        )
        return list(result)

    async def list_all(self) -> list[Tariff]:
        result = await self.session.scalars(select(Tariff).order_by(Tariff.id))
        return list(result)

    async def create(self, **kwargs) -> Tariff:
        tariff = Tariff(**kwargs)
        self.session.add(tariff)
        await self.session.flush()
        return tariff

    async def ensure_default(self) -> Tariff:
        tariff = await self.get_by_code(DEFAULT_TARIFF_CODE)
        if tariff is None:
            tariff = await self.create(
                code=DEFAULT_TARIFF_CODE,
                name="Автонастройка Remnawave + Yandex CDN",
                description=(
                    "Полная автоматическая настройка Origin Server, Remnawave Node, "
                    "XHTTP и Yandex Cloud CDN под ключ."
                ),
                price=0,
                currency="RUB",
                enabled=False,  # admin sets the price first, then enables
            )
        return tariff

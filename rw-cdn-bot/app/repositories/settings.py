from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.setting import (
    INSTRUCTION_TEXT,
    MAINTENANCE_ENABLED,
    MAINTENANCE_TEXT,
    Setting,
)

DEFAULT_MAINTENANCE_TEXT = (
    "🔧 Сейчас проводятся технические работы.\n\n"
    "Покупка временно недоступна.\nПопробуйте позже."
)


class SettingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, key: str, default: str | None = None) -> str | None:
        row = await self.session.scalar(select(Setting).where(Setting.key == key))
        return row.value if row and row.value is not None else default

    async def set(self, key: str, value: str | None) -> None:
        row = await self.session.scalar(select(Setting).where(Setting.key == key))
        if row is None:
            row = Setting(key=key)
            self.session.add(row)
        row.value = value
        await self.session.flush()

    async def maintenance_enabled(self) -> bool:
        return (await self.get(MAINTENANCE_ENABLED, "0")) == "1"

    async def set_maintenance(self, enabled: bool) -> None:
        await self.set(MAINTENANCE_ENABLED, "1" if enabled else "0")

    async def maintenance_text(self) -> str:
        return await self.get(MAINTENANCE_TEXT, DEFAULT_MAINTENANCE_TEXT) or DEFAULT_MAINTENANCE_TEXT

    async def instruction_text(self) -> str | None:
        return await self.get(INSTRUCTION_TEXT)

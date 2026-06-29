from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Setting

APPEARANCE_DEFAULTS = {
    "webapp_brand_name": "Поддержка",
    "webapp_accent_color": "#2481cc",
    "webapp_logo_url": "",
}


async def get_settings(session: AsyncSession, keys: list[str]) -> dict[str, str]:
    rows = (await session.execute(select(Setting).where(Setting.key.in_(keys)))).scalars().all()
    values = {row.key: row.value for row in rows}
    return {key: values.get(key, "") for key in keys}


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    row = (await session.execute(select(Setting).where(Setting.key == key))).scalar_one_or_none()
    if row:
        row.value = value
    else:
        session.add(Setting(key=key, value=value))
    await session.commit()


async def get_appearance(session: AsyncSession) -> dict[str, str]:
    values = await get_settings(session, list(APPEARANCE_DEFAULTS))
    return {key: values.get(key) or default for key, default in APPEARANCE_DEFAULTS.items()}

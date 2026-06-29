from sqlalchemy import select

from bot.config import settings
from bot.db.base import async_session
from bot.models.admin import Admin


def is_admin(tg_id: int) -> bool:
    """Sync check against the static ADMIN_IDS env list (used for the very first /admin bootstrap)."""
    return tg_id in settings.admin_ids


async def is_admin_async(tg_id: int) -> bool:
    if tg_id in settings.admin_ids:
        return True
    async with async_session() as session:
        result = await session.execute(select(Admin).where(Admin.tg_id == tg_id))
        return result.scalar_one_or_none() is not None


async def admin_filter(event) -> bool:
    return await is_admin_async(event.from_user.id)

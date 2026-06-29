from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import MenuButton


async def resolve_action(session: AsyncSession, text: str) -> str | None:
    """Map a pressed reply-keyboard button's text back to its action, regardless of locale."""
    rows = (await session.execute(select(MenuButton))).scalars().all()
    for btn in rows:
        if text in (btn.title_ru, btn.title_en):
            return btn.action
    return None

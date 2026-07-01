from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import TicketCategory

DEFAULT_CATEGORIES = [
    {"title_ru": "Оплата", "title_en": "Payment", "sort_order": 1},
    {"title_ru": "Техническая проблема", "title_en": "Technical issue", "sort_order": 2},
    {"title_ru": "Другое", "title_en": "Other", "sort_order": 3},
]


async def ensure_categories_seeded(session: AsyncSession) -> None:
    existing = (await session.execute(select(TicketCategory.id))).first()
    if existing:
        return
    for c in DEFAULT_CATEGORIES:
        session.add(TicketCategory(**c, is_active=True))
    await session.commit()

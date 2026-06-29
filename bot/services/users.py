from aiogram.types import User as TgUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.user import User


async def get_or_create_user(session: AsyncSession, tg_user: TgUser) -> User:
    result = await session.execute(select(User).where(User.tg_id == tg_user.id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(tg_id=tg_user.id, username=tg_user.username, first_name=tg_user.first_name)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def get_user_by_tg_id(session: AsyncSession, tg_id: int) -> User | None:
    result = await session.execute(select(User).where(User.tg_id == tg_id))
    return result.scalar_one_or_none()

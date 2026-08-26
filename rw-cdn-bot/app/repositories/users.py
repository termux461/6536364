from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order, Payment, User
from app.models.enums import PaymentStatus


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        return await self.session.scalar(select(User).where(User.telegram_id == telegram_id))

    async def get(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def upsert(
        self,
        telegram_id: int,
        *,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        language_code: str | None = None,
    ) -> User:
        user = await self.get_by_telegram_id(telegram_id)
        if user is None:
            user = User(telegram_id=telegram_id)
            self.session.add(user)
        user.username = username
        user.first_name = first_name
        user.last_name = last_name
        user.language_code = language_code
        await self.session.flush()
        return user

    async def set_blocked(self, telegram_id: int, blocked: bool, reason: str | None = None) -> None:
        user = await self.get_by_telegram_id(telegram_id)
        if user:
            user.is_blocked = blocked
            user.block_reason = reason if blocked else None
            await self.session.flush()

    async def list_page(self, offset: int = 0, limit: int = 10) -> list[User]:
        result = await self.session.scalars(
            select(User).order_by(User.id.desc()).offset(offset).limit(limit)
        )
        return list(result)

    async def count(self) -> int:
        return int(await self.session.scalar(select(func.count(User.id))) or 0)

    async def all_telegram_ids(self) -> list[int]:
        result = await self.session.scalars(
            select(User.telegram_id).where(User.is_blocked.is_(False)).order_by(User.id)
        )
        return list(result)

    async def stats(self, user_id: int) -> dict[str, int]:
        orders = int(
            await self.session.scalar(select(func.count(Order.id)).where(Order.user_id == user_id)) or 0
        )
        spent = int(
            await self.session.scalar(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(
                    Payment.user_id == user_id, Payment.status == PaymentStatus.PAID
                )
            )
            or 0
        )
        return {"orders": orders, "spent": spent}

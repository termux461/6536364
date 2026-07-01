from aiogram import Router
from aiogram.types import Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Payment, PaymentStatus, Subscription, SubscriptionStatus, User

router = Router(name="admin_stats")


@router.message(lambda m: m.text == "📈 Статистика")
async def show_stats(message: Message, session: AsyncSession, is_admin: bool) -> None:
    if not is_admin:
        return
    users_count = (await session.execute(select(func.count(User.id)))).scalar_one()
    active_subs = (
        await session.execute(select(func.count(Subscription.id)).where(Subscription.status == SubscriptionStatus.ACTIVE))
    ).scalar_one()
    revenue = (
        await session.execute(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == PaymentStatus.PAID))
    ).scalar_one()
    payments_count = (
        await session.execute(select(func.count(Payment.id)).where(Payment.status == PaymentStatus.PAID))
    ).scalar_one()

    await message.answer(
        "📈 Статистика\n\n"
        f"Пользователей: {users_count}\n"
        f"Активных подписок: {active_subs}\n"
        f"Оплаченных платежей: {payments_count}\n"
        f"Общая выручка: {revenue} ₽"
    )

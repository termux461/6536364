from aiogram import Router
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters import MenuAction
from bot.i18n import t
from database.models import Subscription, SubscriptionStatus, Tariff, User

router = Router(name="profile")


@router.message(MenuAction("profile"))
async def show_profile(message: Message, session: AsyncSession, locale: str, user: User) -> None:
    text = t(locale, "profile.title", tg_id=user.tg_id, balance=user.balance)
    subs = (
        await session.execute(
            select(Subscription, Tariff)
            .join(Tariff, Tariff.id == Subscription.tariff_id)
            .where(Subscription.user_id == user.id, Subscription.status == SubscriptionStatus.ACTIVE)
        )
    ).all()
    if not subs:
        text += "\n" + t(locale, "profile.no_subs")
    else:
        for sub, tariff in subs:
            text += "\n" + t(locale, "profile.sub_line", tariff=tariff.name, expires=sub.expires_at.strftime("%Y-%m-%d"))
    await message.answer(text)

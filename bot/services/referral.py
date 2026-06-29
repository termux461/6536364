from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.models.user import User


async def accrue_referral_bonus(session: AsyncSession, user: User, amount: Decimal) -> None:
    if not user.ref_by:
        return
    referrer = await session.get(User, user.ref_by)
    if referrer is None:
        return
    bonus = (amount * Decimal(settings.REFERRAL_PERCENT) / Decimal(100)).quantize(Decimal("0.01"))
    referrer.balance = Decimal(str(referrer.balance)) + bonus
    referrer.referral_earned = Decimal(str(referrer.referral_earned)) + bonus
    await session.commit()

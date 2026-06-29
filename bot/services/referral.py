from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.models import Payment, ReferralEarning, User, WithdrawRequest


def parse_referrer_id(start_param: str | None) -> int | None:
    if not start_param or not start_param.startswith("ref_"):
        return None
    try:
        return int(start_param.removeprefix("ref_"))
    except ValueError:
        return None


async def get_or_create_user(session: AsyncSession, tg_id: int, username: str | None, full_name: str | None,
                              referrer_tg_id: int | None = None, locale: str = "ru") -> User:
    user = (await session.execute(select(User).where(User.tg_id == tg_id))).scalar_one_or_none()
    if user:
        return user

    referrer = None
    if referrer_tg_id and referrer_tg_id != tg_id:
        referrer = (await session.execute(select(User).where(User.tg_id == referrer_tg_id))).scalar_one_or_none()

    user = User(
        tg_id=tg_id,
        username=username,
        full_name=full_name,
        locale=locale,
        referrer_id=referrer.id if referrer else None,
        balance=settings.REFERRAL_SIGNUP_BONUS if referrer else 0,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def accrue_referral_bonus(session: AsyncSession, payment: Payment) -> None:
    buyer = (await session.execute(select(User).where(User.id == payment.user_id))).scalar_one()
    if not buyer.referrer_id:
        return
    bonus = round(payment.amount * settings.REFERRAL_BONUS_PERCENT / 100, 2)
    if bonus <= 0:
        return
    referrer = (await session.execute(select(User).where(User.id == buyer.referrer_id))).scalar_one_or_none()
    if not referrer:
        return
    referrer.balance += bonus
    session.add(ReferralEarning(referrer_id=referrer.id, referral_id=buyer.id, payment_id=payment.id, amount=bonus))
    await session.commit()


async def referral_stats(session: AsyncSession, user: User) -> dict:
    count = (await session.execute(select(ReferralEarning).where(ReferralEarning.referrer_id == user.id))).scalars().all()
    earned = sum(r.amount for r in count)
    invited = (await session.execute(select(User).where(User.referrer_id == user.id))).scalars().all()
    return {"count": len(invited), "earned": earned, "balance": user.balance}


async def request_withdraw(session: AsyncSession, user: User, amount: float) -> WithdrawRequest:
    req = WithdrawRequest(user_id=user.id, amount=amount)
    user.balance -= amount
    session.add(req)
    await session.commit()
    await session.refresh(req)
    return req

import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.referral import accrue_referral_bonus
from bot.services.remnawave import RemnawaveClient
from database.models import Host, Payment, PaymentStatus, Subscription, SubscriptionStatus, Tariff, User


async def fulfil_payment(session: AsyncSession, payment: Payment) -> Subscription:
    """Provision the Remnawave user, create the Subscription row and mark the
    payment as paid. Used both by the bot's polling check and by payment
    webhooks, so it must not depend on aiogram."""
    tariff = (await session.execute(select(Tariff).where(Tariff.id == payment.tariff_id))).scalar_one()
    host = (await session.execute(select(Host).where(Host.id == tariff.host_id))).scalar_one()
    user = (await session.execute(select(User).where(User.id == payment.user_id))).scalar_one()

    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=tariff.duration_days)
    client = RemnawaveClient(host.api_url, host.api_token)
    try:
        data = await client.create_user(
            telegram_id=user.tg_id,
            username=user.username or "",
            expire_at_iso=expires_at.isoformat(),
            traffic_limit_bytes=tariff.traffic_limit_gb * 1024 ** 3,
        )
    finally:
        await client.close()

    sub = Subscription(
        user_id=user.id, tariff_id=tariff.id, host_id=host.id,
        remnawave_uuid=data.get("uuid") or data.get("id"),
        subscription_url=data.get("subscriptionUrl") or data.get("subscription_url"),
        status=SubscriptionStatus.ACTIVE, expires_at=expires_at,
    )
    session.add(sub)
    payment.status = PaymentStatus.PAID
    payment.paid_at = datetime.datetime.now(datetime.timezone.utc)
    await session.commit()
    await session.refresh(sub)

    await accrue_referral_bonus(session, payment)
    return sub

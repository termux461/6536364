import datetime
import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from bot.services.remnawave import RemnawaveClient, http_ping
from database.db import async_session
from database.models import Host, Subscription, SubscriptionStatus, User

logger = logging.getLogger(__name__)


async def check_expired_subscriptions(bot: Bot) -> None:
    now = datetime.datetime.now(datetime.timezone.utc)
    async with async_session() as session:
        subs = (
            await session.execute(
                select(Subscription).where(Subscription.status == SubscriptionStatus.ACTIVE, Subscription.expires_at < now)
            )
        ).scalars().all()
        for sub in subs:
            sub.status = SubscriptionStatus.EXPIRED
            host = (await session.execute(select(Host).where(Host.id == sub.host_id))).scalar_one_or_none()
            if host and sub.remnawave_uuid:
                client = RemnawaveClient(host.api_url, host.api_token)
                try:
                    await client.delete_user(sub.remnawave_uuid)
                except Exception:
                    logger.exception("Failed to delete expired remnawave user %s", sub.remnawave_uuid)
                finally:
                    await client.close()
            user = (await session.execute(select(User).where(User.id == sub.user_id))).scalar_one_or_none()
            if user:
                try:
                    expired_text = "⌛ Ваша подписка истекла." if user.locale == "ru" else "⌛ Your subscription has expired."
                    await bot.send_message(user.tg_id, expired_text)
                except Exception:
                    pass
        await session.commit()


async def check_hosts_status() -> None:
    async with async_session() as session:
        hosts = (await session.execute(select(Host))).scalars().all()
        for host in hosts:
            ms = await http_ping(host.api_url)
            host.last_ping_ms = ms
            host.last_checked_at = datetime.datetime.now(datetime.timezone.utc)
        await session.commit()


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(check_expired_subscriptions, "interval", minutes=10, args=[bot])
    scheduler.add_job(check_hosts_status, "interval", minutes=5)
    return scheduler

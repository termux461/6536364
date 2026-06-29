import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from bot.config import settings
from bot.db.base import async_session, init_db
from bot.handlers.admin import admins as admin_admins
from bot.handlers.admin import backup as admin_backup
from bot.handlers.admin import broadcast as admin_broadcast
from bot.handlers.admin import issue as admin_issue
from bot.handlers.admin import keys as admin_keys
from bot.handlers.admin import monitor as admin_monitor
from bot.handlers.admin import panel as admin_panel
from bot.handlers.admin import promo as admin_promo
from bot.handlers.admin import servers as admin_servers
from bot.handlers.admin import stats as admin_stats
from bot.handlers.admin import users as admin_users
from bot.handlers.user import buy, profile, referral, start, subscriptions, support, topup
from bot.models.server import Server
from bot.models.subscription import Subscription
from bot.models.user import User
from bot.services.backup import create_backup
from bot.services.node_manager import node_manager
from bot.webhook_app import create_webhook_app

logging.basicConfig(level=logging.ERROR, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def check_expiring_subscriptions(bot: Bot) -> None:
    now = datetime.utcnow()
    async with async_session() as session:
        result = await session.execute(select(Subscription).where(Subscription.active.is_(True)))
        for subscription in result.scalars().all():
            days_left = (subscription.expires_at - now).days
            user = await session.get(User, subscription.user_id)
            if user is None:
                continue
            try:
                if days_left == 3 or days_left == 1:
                    await bot.send_message(
                        user.tg_id,
                        f"Подписка #{subscription.id} истекает через {days_left} "
                        f"{'день' if days_left == 1 else 'дня'}. Не забудьте продлить.",
                    )
                elif subscription.expires_at <= now:
                    server = await session.get(Server, subscription.server_id)
                    if server is not None and subscription.peer_id:
                        try:
                            await node_manager.delete_peer(server, subscription.peer_id)
                        except Exception as exc:
                            logger.error("Failed to delete peer on expiry: %s", exc)
                    subscription.active = False
                    await session.commit()
                    await bot.send_message(user.tg_id, f"Подписка #{subscription.id} истекла.")
            except Exception as exc:
                logger.error("Failed to notify user about subscription expiry: %s", exc)


async def daily_backup_job() -> None:
    try:
        zip_path = await create_backup()
        logger.info("Backup created: %s", zip_path)
    except Exception as exc:
        logger.error("Scheduled backup failed: %s", exc)


async def main() -> None:
    if not settings.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set. Fill it in .env")

    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(admin_panel.router)
    dp.include_router(admin_users.router)
    dp.include_router(admin_servers.router)
    dp.include_router(admin_keys.router)
    dp.include_router(admin_issue.router)
    dp.include_router(admin_promo.router)
    dp.include_router(admin_monitor.router)
    dp.include_router(admin_backup.router)
    dp.include_router(admin_admins.router)
    dp.include_router(admin_stats.router)
    dp.include_router(admin_broadcast.router)

    dp.include_router(start.router)
    dp.include_router(buy.router)
    dp.include_router(topup.router)
    dp.include_router(subscriptions.router)
    dp.include_router(profile.router)
    dp.include_router(referral.router)
    dp.include_router(support.router)

    await init_db()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_expiring_subscriptions, "cron", hour=9, args=[bot])
    scheduler.add_job(daily_backup_job, "cron", hour=3)
    scheduler.start()

    webhook_app = create_webhook_app(bot)
    runner = web.AppRunner(webhook_app)
    await runner.setup()
    site = web.TCPSite(runner, settings.WEBHOOK_HOST, settings.WEBHOOK_PORT)
    await site.start()
    logger.error("Webhook server listening on %s:%s", settings.WEBHOOK_HOST, settings.WEBHOOK_PORT)

    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())

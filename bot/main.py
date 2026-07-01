import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from bot.handlers import admin, buy, payments, profile, referral, settings, speedtest, start
from bot.middlewares.antiflood import AntiFloodMiddleware
from bot.middlewares.db import DbSessionMiddleware
from bot.middlewares.subscription import ForceSubscriptionMiddleware
from bot.middlewares.user_context import UserContextMiddleware
from bot.scheduler import setup_scheduler
from config import settings as cfg
from database.db import init_db

logging.basicConfig(level=cfg.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    await init_db()

    bot = Bot(token=cfg.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    storage = RedisStorage.from_url(cfg.REDIS_URL)
    dp = Dispatcher(storage=storage)

    dp.update.middleware(DbSessionMiddleware())
    dp.update.middleware(AntiFloodMiddleware())
    dp.update.middleware(UserContextMiddleware())
    dp.update.middleware(ForceSubscriptionMiddleware())

    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(buy.router)
    dp.include_router(payments.router)
    dp.include_router(profile.router)
    dp.include_router(referral.router)
    dp.include_router(settings.router)
    dp.include_router(speedtest.router)

    scheduler = setup_scheduler(bot)
    scheduler.start()

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import Config
from handlers import start, buy, balance, promo, admin, webhook
from handlers.webhook import start_webhook_server
from services.database import Database
from services.scheduler import check_expired

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    config = Config()
    db = Database(config.DB_PATH)
    await db.init()

    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp["config"] = config
    dp["db"] = db

    dp.include_router(start.router)
    dp.include_router(buy.router)
    dp.include_router(balance.router)
    dp.include_router(promo.router)
    dp.include_router(admin.router)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_expired, "interval", hours=1, args=[bot, db, config])
    scheduler.start()

    logger.info("Bot started")
    await asyncio.gather(
        dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query", "pre_checkout_query"]
        ),
        start_webhook_server(bot, db, config)
    )


if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import settings
from bot.db.base import init_db
from bot.handlers.admin import broadcast as admin_broadcast
from bot.handlers.admin import panel as admin_panel
from bot.handlers.admin import servers as admin_servers
from bot.handlers.admin import stats as admin_stats
from bot.handlers.admin import users as admin_users
from bot.handlers.user import buy, profile, start, subscriptions, support

logging.basicConfig(level=logging.ERROR, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def main() -> None:
    if not settings.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set. Fill it in .env")

    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(admin_panel.router)
    dp.include_router(admin_users.router)
    dp.include_router(admin_servers.router)
    dp.include_router(admin_stats.router)
    dp.include_router(admin_broadcast.router)

    dp.include_router(start.router)
    dp.include_router(buy.router)
    dp.include_router(subscriptions.router)
    dp.include_router(profile.router)
    dp.include_router(support.router)

    await init_db()

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

"""Bot entrypoint. Runs polling plus the payment webhook HTTP server in one process."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.redis import RedisStorage
from aiohttp import web

from app.bot.handlers import register_handlers
from app.bot.middlewares import register_middlewares
from app.config import get_settings
from app.core.logging import setup_logging
from app.database import session_scope
from app.repositories import TariffRepository
from app.webhooks.server import build_app

logger = logging.getLogger(__name__)


async def bootstrap() -> None:
    async with session_scope() as session:
        await TariffRepository(session).ensure_default()


async def main() -> None:
    settings = get_settings()

    mismatch = settings.webhook_domain_mismatch()
    if mismatch:
        logger.warning("Проверьте конфигурацию: %s", mismatch)
    setup_logging(settings.log_level)
    await bootstrap()

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    storage = RedisStorage.from_url(settings.redis_url)
    dp = Dispatcher(storage=storage)

    register_middlewares(dp)
    register_handlers(dp)

    bot_id = (await bot.me()).id

    def key_factory(user_id: int) -> StorageKey:
        return StorageKey(bot_id=bot_id, chat_id=user_id, user_id=user_id)

    web_app = build_app(bot, storage, key_factory)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, settings.webhook_host, settings.webhook_port)
    await site.start()
    logger.info("Webhook server listening on %s:%s", settings.webhook_host, settings.webhook_port)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

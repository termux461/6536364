"""Rate-limited Telegram broadcast worker."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from app.config import get_settings
from app.core.logging import setup_logging
from app.database import session_scope
from app.models.enums import BroadcastStatus, RecipientStatus
from app.repositories import BroadcastRepository
from app.services.queue import BROADCAST_QUEUE, JobQueue

logger = logging.getLogger(__name__)

MESSAGES_PER_SECOND = 20
BATCH = 25


async def run_broadcast(broadcast_id: int, bot: Bot) -> None:
    while True:
        async with session_scope() as session:
            repo = BroadcastRepository(session)
            broadcast = await repo.get(broadcast_id)
            if broadcast is None or broadcast.status != BroadcastStatus.RUNNING:
                return
            batch = await repo.next_batch(broadcast_id, BATCH)
            if not batch:
                await repo.set_status(broadcast, BroadcastStatus.FINISHED)
                logger.info("Broadcast %s finished: %s sent", broadcast_id, broadcast.sent)
                return

            for recipient in batch:
                try:
                    await bot.send_message(
                        recipient.telegram_id, broadcast.text, parse_mode=broadcast.parse_mode
                    )
                except TelegramRetryAfter as exc:
                    await repo.bump(broadcast, "flood_waits")
                    await asyncio.sleep(exc.retry_after + 1)
                    continue
                except TelegramForbiddenError:
                    await repo.mark_recipient(recipient, RecipientStatus.BLOCKED, "bot blocked")
                    await repo.bump(broadcast, "blocked")
                except Exception as exc:  # noqa: BLE001
                    await repo.mark_recipient(recipient, RecipientStatus.FAILED, str(exc)[:500])
                    await repo.bump(broadcast, "failed")
                else:
                    await repo.mark_recipient(recipient, RecipientStatus.SENT)
                    await repo.bump(broadcast, "sent")
                await asyncio.sleep(1 / MESSAGES_PER_SECOND)


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    queue = JobQueue.from_settings()
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    logger.info("Broadcast worker started")
    try:
        while True:
            job = await queue.pop(BROADCAST_QUEUE, timeout=5)
            if job is None:
                continue
            await run_broadcast(int(job["broadcast_id"]), bot)
    finally:
        await bot.session.close()
        await queue.close()


if __name__ == "__main__":
    asyncio.run(main())

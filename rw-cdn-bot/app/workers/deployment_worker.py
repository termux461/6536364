"""Deployment worker.

Consumes order ids from Redis, runs DeploymentService, and re-parks deployments that are
waiting on DNS propagation or certificate issuance. A restart never re-runs completed steps.
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import get_settings
from app.core.logging import setup_logging
from app.database import session_scope
from app.models.enums import DeploymentStatus
from app.services.deployment import DeploymentService
from app.services.queue import DEPLOY_QUEUE, JobQueue

logger = logging.getLogger(__name__)

WAITING_RETRY_DELAY = 180


async def _progress_hook(bot: Bot):
    from app.bot.notifications import refresh_progress_message

    async def hook(order_id: int) -> None:
        await refresh_progress_message(bot, order_id)

    return hook


async def process_order(order_id: int, queue: JobQueue, bot: Bot) -> None:
    if not await queue.acquire_deploy_lock(order_id):
        logger.info("Order %s is already being deployed elsewhere", order_id)
        return
    try:
        hook = await _progress_hook(bot)
        async with session_scope() as session:
            service = DeploymentService(session, on_progress=hook)
            status = await service.run(order_id)

        if status is DeploymentStatus.WAITING_REAUTH:
            # No retry schedule here on purpose: retrying a dead session just burns requests.
            # The order resumes when the customer sends fresh credentials via /reauth.
            from app.bot.notifications import notify_reauth_needed

            await notify_reauth_needed(bot, order_id)
            logger.info("Order %s parked: Yandex credentials need a refresh", order_id)
        elif status in (DeploymentStatus.WAITING_DNS, DeploymentStatus.WAITING_CERTIFICATE):
            await queue.schedule_retry(order_id, WAITING_RETRY_DELAY, reason=str(status))
            logger.info("Order %s parked (%s), will retry in %ss", order_id, status, WAITING_RETRY_DELAY)
        elif status is DeploymentStatus.FAILED:
            from app.bot.notifications import notify_failure

            await notify_failure(bot, order_id)
        elif status is DeploymentStatus.COMPLETED:
            from app.bot.notifications import notify_success

            await notify_success(bot, order_id)
    except Exception:
        logger.exception("Unhandled error while deploying order %s", order_id)
    finally:
        await queue.release_deploy_lock(order_id)


async def delayed_pump(queue: JobQueue) -> None:
    while True:
        try:
            for job in await queue.due_delayed():
                await queue.enqueue_deployment(job["order_id"], reason=job.get("reason", "retry"))
        except Exception:
            logger.exception("Delayed queue pump failed")
        await asyncio.sleep(15)


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    queue = JobQueue.from_settings()
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    logger.info("Deployment worker started")

    pump = asyncio.create_task(delayed_pump(queue))
    try:
        while True:
            job = await queue.pop(DEPLOY_QUEUE, timeout=5)
            if job is None:
                continue
            await process_order(int(job["order_id"]), queue, bot)
    finally:
        pump.cancel()
        await bot.session.close()
        await queue.close()


if __name__ == "__main__":
    asyncio.run(main())

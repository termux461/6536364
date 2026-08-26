"""HTTP server for payment callbacks.

The handler does the minimum: validate, open one DB transaction, mark the payment paid,
queue the next action, return 200. No SSH, no Docker, no cloud API calls happen here.
"""
from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiohttp import web

from app.config import get_settings
from app.core.exceptions import PaymentValidationError
from app.core.logging import setup_logging
from app.database import session_scope
from app.models.enums import OrderStatus, YandexAuthType
from app.repositories import InfraRepository, OrderRepository, UserRepository
from app.services.payments import PaymentService
from app.services.queue import JobQueue
from app.services.vault import read_yandex_cookies

logger = logging.getLogger(__name__)


def _client_ip(request: web.Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote or ""


async def _yandex_credentials_present(yandex, order_id: int) -> bool:
    """Each auth method keeps its credential in a different place."""
    auth_type = (yandex.auth_type or YandexAuthType.SERVICE_ACCOUNT) if yandex else None
    if auth_type == YandexAuthType.COOKIE:
        # Cookies are never persisted — they live in the vault for the run only.
        return bool(await read_yandex_cookies(order_id))
    if auth_type == YandexAuthType.OAUTH:
        return bool(yandex.oauth_token_enc)
    return bool(yandex and yandex.service_account_key_enc)


async def _data_is_complete(order_id: int) -> bool:
    async with session_scope() as session:
        infra = InfraRepository(session)
        origin = await infra.origin(order_id)
        remnawave = await infra.remnawave(order_id)
        yandex = await infra.yandex(order_id)

    if not (yandex and yandex.folder_id and await _yandex_credentials_present(yandex, order_id)):
        return False

    return bool(
        origin
        and origin.origin_ip
        and origin.origin_domain
        and origin.cdn_domain
        and origin.letsencrypt_email
        and (origin.ssh_private_key_enc or origin.ssh_password_enc)
        and remnawave
        and remnawave.panel_url
        and remnawave.api_token_enc
    )


async def _after_payment(app: web.Application, order_id: int) -> None:
    """Either resume a deployment that already has its data, or ask the user for it."""
    bot: Bot = app["bot"]
    queue: JobQueue = app["queue"]

    if await _data_is_complete(order_id):
        await queue.enqueue_deployment(order_id, reason="payment_confirmed")
        return

    async with session_scope() as session:
        orders = OrderRepository(session)
        order = await orders.get(order_id)
        if order is None:
            return
        await orders.set_status(order, OrderStatus.COLLECTING_DATA)
        user = await UserRepository(session).get(order.user_id)

    if user is None:
        return
    from app.bot import texts

    await bot.send_message(
        user.telegram_id,
        f"✅ Оплата заказа <b>#{order_id}</b> подтверждена.\n\nТеперь нужны данные для настройки.",
    )
    await bot.send_message(user.telegram_id, texts.ASK_PANEL_URL)
    # Hand the FSM the order it belongs to.
    storage_key = app["storage_key_factory"](user.telegram_id)
    await app["storage"].set_state(storage_key, "CollectData:panel_url")
    await app["storage"].set_data(storage_key, {"order_id": order_id})


async def _handle(request: web.Request, provider: str) -> web.Response:
    body = await request.read()
    headers = dict(request.headers)
    remote = _client_ip(request)

    try:
        async with session_scope() as session:
            service = PaymentService(session)
            should_continue, order_id = await service.handle_webhook(provider, headers, body, remote)
    except PaymentValidationError as exc:
        logger.warning("Rejected %s webhook from %s: %s", provider, remote, exc)
        return web.json_response({"status": "rejected"}, status=400)
    except Exception:
        logger.exception("Error handling %s webhook", provider)
        return web.json_response({"status": "error"}, status=500)

    if should_continue and order_id is not None:
        try:
            await _after_payment(request.app, order_id)
        except Exception:
            logger.exception("Post-payment handoff failed for order %s", order_id)

    return web.json_response({"status": "ok"})


async def platega_webhook(request: web.Request) -> web.Response:
    return await _handle(request, "platega")


async def yookassa_webhook(request: web.Request) -> web.Response:
    return await _handle(request, "yookassa")


async def healthz(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


def build_app(bot: Bot, storage, storage_key_factory) -> web.Application:
    app = web.Application()
    app["bot"] = bot
    app["queue"] = JobQueue.from_settings()
    app["storage"] = storage
    app["storage_key_factory"] = storage_key_factory
    app.router.add_post("/webhooks/platega", platega_webhook)
    app.router.add_post("/webhooks/yookassa", yookassa_webhook)
    app.router.add_get("/healthz", healthz)

    async def _cleanup(app: web.Application) -> None:
        await app["queue"].close()

    app.on_cleanup.append(_cleanup)
    return app


async def run() -> None:
    """Standalone mode — useful when the webhook server runs in its own container."""
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.fsm.storage.redis import RedisStorage

    settings = get_settings()
    setup_logging(settings.log_level)
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    storage = RedisStorage.from_url(settings.redis_url)
    bot_id = (await bot.me()).id

    def key_factory(user_id: int) -> StorageKey:
        return StorageKey(bot_id=bot_id, chat_id=user_id, user_id=user_id)

    app = build_app(bot, storage, key_factory)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, settings.webhook_host, settings.webhook_port)
    await site.start()
    logger.info("Webhook server listening on %s:%s", settings.webhook_host, settings.webhook_port)

    import asyncio

    await asyncio.Event().wait()

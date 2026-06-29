import json
import logging
from datetime import timedelta
from decimal import Decimal

from aiogram import Bot
from aiohttp import web

from bot.config import PLANS
from bot.db.base import async_session
from bot.models.payment import Payment
from bot.models.server import Server
from bot.models.subscription import Subscription
from bot.models.user import User
from bot.services.fulfillment import FulfillmentError, fulfill_purchase, fulfill_topup
from bot.services.payment import get_provider
from bot.services.webhook_logger import log_incoming_webhook
from sqlalchemy import select

logger = logging.getLogger(__name__)


async def _handle_webhook(request: web.Request, provider_name: str) -> web.Response:
    body = await request.read()
    await log_incoming_webhook(provider_name, request, body)

    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError:
        return web.json_response({"ok": False, "error": "invalid json"}, status=400)

    provider = get_provider(provider_name)

    if provider_name == "cryptobot":
        signature = request.headers.get("Crypto-Pay-API-Signature", "")
        if not provider.verify_signature(body, signature):
            return web.json_response({"ok": False, "error": "bad signature"}, status=403)

    try:
        is_paid, external_id = await provider.is_paid(payload, dict(request.headers))
    except Exception as exc:
        logger.error("Payment verification failed for %s: %s", provider_name, exc)
        return web.json_response({"ok": False}, status=502)

    if not is_paid or not external_id:
        return web.json_response({"ok": True, "ignored": True})

    bot: Bot = request.app["bot"]

    async with async_session() as session:
        result = await session.execute(select(Payment).where(Payment.external_id == external_id))
        payment = result.scalar_one_or_none()
        if payment is None or payment.status == "succeeded":
            return web.json_response({"ok": True, "idempotent": True})

        payment.status = "succeeded"
        await session.commit()

        user = await session.get(User, payment.user_id)
        if user is None:
            return web.json_response({"ok": True})

        if payment.purpose == "topup":
            await fulfill_topup(session, user, Decimal(str(payment.amount)))
            try:
                await bot.send_message(user.tg_id, f"Баланс пополнен на {payment.amount}₽.")
            except Exception:
                pass

        elif payment.purpose == "buy":
            plan_key, server_id = payment.payload.split(":")
            server = await session.get(Server, int(server_id))
            try:
                subscription = await fulfill_purchase(session, user, plan_key, server)
                plan = PLANS[plan_key]
                try:
                    await bot.send_message(
                        user.tg_id,
                        f"Оплата получена! Подписка «{plan['title']}» #{subscription.id} активирована. "
                        "Конфигурацию можно скачать в «Мои подписки».",
                    )
                except Exception:
                    pass
            except FulfillmentError as exc:
                try:
                    await bot.send_message(user.tg_id, f"Оплата получена, но сервер недоступен: {exc}. Обратитесь в поддержку.")
                except Exception:
                    pass

        elif payment.purpose == "extend":
            sub_id = int(payment.payload)
            subscription = await session.get(Subscription, sub_id)
            if subscription is not None:
                plan = PLANS.get(subscription.plan, {"days": 30})
                subscription.expires_at = subscription.expires_at + timedelta(days=plan["days"])
                subscription.active = True
                await session.commit()
                try:
                    await bot.send_message(
                        user.tg_id,
                        f"Оплата получена! Подписка #{subscription.id} продлена до "
                        f"{subscription.expires_at.strftime('%d.%m.%Y')}.",
                    )
                except Exception:
                    pass

    return web.json_response({"ok": True})


async def platega_webhook(request: web.Request) -> web.Response:
    return await _handle_webhook(request, "platega")


async def yookassa_webhook(request: web.Request) -> web.Response:
    return await _handle_webhook(request, "yookassa")


async def cryptobot_webhook(request: web.Request) -> web.Response:
    return await _handle_webhook(request, "cryptobot")


def create_webhook_app(bot: Bot) -> web.Application:
    app = web.Application()
    app["bot"] = bot
    app.router.add_post("/webhook/platega", platega_webhook)
    app.router.add_post("/webhook/yookassa", yookassa_webhook)
    app.router.add_post("/webhook/cryptobot", cryptobot_webhook)
    return app

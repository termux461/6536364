import logging
from aiohttp import web
from aiogram import Bot
from services.database import Database
from services.platega import PlategaService
from config import Config

logger = logging.getLogger(__name__)


async def platega_webhook(request: web.Request) -> web.Response:
    bot: Bot = request.app["bot"]
    db: Database = request.app["db"]
    config: Config = request.app["config"]

    try:
        data = dict(await request.post())
        logger.info(f"Platega webhook: {data}")
    except Exception as e:
        logger.error(f"Webhook parse: {e}")
        return web.Response(text="error", status=400)

    platega = PlategaService(config.PLATEGA_SHOP_ID, config.PLATEGA_SECRET)
    if not platega.verify(data):
        return web.Response(text="bad sign", status=403)

    order_id = data.get("o")
    payment = await db.get_payment(order_id)
    if not payment or payment["status"] == "paid":
        return web.Response(text="ok")

    user_id = PlategaService.user_id_from(data) or payment["user_id"]
    amount = payment["amount"]

    await db.confirm_payment(order_id)
    await db.change_balance(user_id, amount, f"пополнение Platega {order_id}")

    user = await db.get_user(user_id)
    try:
        await bot.send_message(
            user_id,
            f"✅ Баланс пополнен на <b>{amount}₽</b>\n"
            f"💰 Текущий баланс: <b>{user['balance']}₽</b>\n\n"
            "Нажмите /start для покупки подписки.",
            parse_mode="HTML"
        )
    except Exception:
        pass

    logger.info(f"Balance topped up: user={user_id} amount={amount}")
    return web.Response(text="ok")


async def start_webhook_server(bot: Bot, db: Database, config: Config):
    import asyncio
    app = web.Application()
    app["bot"] = bot
    app["db"] = db
    app["config"] = config
    app.router.add_post("/platega/webhook", platega_webhook)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", config.WEBHOOK_PORT)
    await site.start()
    logger.info(f"Webhook server on :{config.WEBHOOK_PORT}")

    while True:
        await asyncio.sleep(3600)

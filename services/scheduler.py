import logging
from aiogram import Bot
from services.database import Database
from services.wgeasy import WgEasyClient
from config import Config

logger = logging.getLogger(__name__)


async def check_expired(bot: Bot, db: Database, config: Config):
    wg = WgEasyClient(config.WG_EASY_URL, config.WG_EASY_PASSWORD)
    expired = await db.get_expired_subscriptions()

    for sub in expired:
        try:
            if sub["wg_peer_id"]:
                await wg.delete_peer(sub["wg_peer_id"])
        except Exception as e:
            logger.warning(f"Delete peer error {sub['wg_peer_id']}: {e}")

        await db.deactivate_subscription(sub["id"])

        try:
            await bot.send_message(
                sub["user_id"],
                "⚠️ <b>Ваша подписка истекла.</b>\n\n"
                "Нажмите /start → <b>Купить подписку</b> для продления.",
                parse_mode="HTML"
            )
        except Exception:
            pass

    await wg.close()
    if expired:
        logger.info(f"Expired {len(expired)} subscriptions")

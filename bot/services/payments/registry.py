from aiogram import Bot
from sqlalchemy import select

from config import settings
from database.models import PaymentMethod
from bot.services.payments.base import PaymentProvider
from bot.services.payments.cryptobot import CryptoBotProvider
from bot.services.payments.stars import StarsProvider
from bot.services.payments.yookassa import YooKassaProvider

DEFAULT_METHODS = [
    {"code": "stars", "title": "Telegram Stars", "sort_order": 1},
    {"code": "cryptobot", "title": "CryptoBot", "sort_order": 2},
    {"code": "yookassa", "title": "ЮKassa", "sort_order": 3},
]


async def ensure_payment_methods_seeded(session) -> None:
    existing = (await session.execute(select(PaymentMethod.code))).scalars().all()
    for m in DEFAULT_METHODS:
        if m["code"] not in existing:
            session.add(PaymentMethod(code=m["code"], title=m["title"], sort_order=m["sort_order"], is_enabled=True))
    await session.commit()


def build_provider(code: str, bot: Bot) -> PaymentProvider | None:
    if code == "stars":
        return StarsProvider(bot)
    if code == "cryptobot" and settings.CRYPTOBOT_API_TOKEN:
        return CryptoBotProvider(settings.CRYPTOBOT_API_TOKEN, settings.CRYPTOBOT_API_URL)
    if code == "yookassa" and settings.YOOKASSA_SHOP_ID and settings.YOOKASSA_SECRET_KEY:
        return YooKassaProvider(settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY)
    return None


async def get_enabled_methods(session) -> list[PaymentMethod]:
    result = await session.execute(
        select(PaymentMethod).where(PaymentMethod.is_enabled.is_(True)).order_by(PaymentMethod.sort_order)
    )
    return list(result.scalars().all())

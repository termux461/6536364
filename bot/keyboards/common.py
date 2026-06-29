from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton,
    ReplyKeyboardMarkup, WebAppInfo,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.i18n import t
from config import settings
from database.models import MenuButton

ACTION_TITLE_KEY = {
    "buy": "menu.buy",
    "profile": "menu.profile",
    "renew": "menu.renew",
    "referral": "menu.referral",
    "support": "menu.support",
    "settings": "menu.settings",
    "speedtest": "menu.speedtest",
}

DEFAULT_BUTTONS = [
    {"key": "buy", "action": "buy", "title_ru": "🛒 Купить VPN", "title_en": "🛒 Buy VPN", "sort_order": 1},
    {"key": "profile", "action": "profile", "title_ru": "👤 Мой профиль", "title_en": "👤 My profile", "sort_order": 2},
    {"key": "renew", "action": "renew", "title_ru": "🔄 Продлить/Сменить тариф", "title_en": "🔄 Renew / Change plan", "sort_order": 3},
    {"key": "referral", "action": "referral", "title_ru": "🎁 Реферальная программа", "title_en": "🎁 Referral program", "sort_order": 4},
    {"key": "support", "action": "support", "title_ru": "🆘 Поддержка", "title_en": "🆘 Support", "sort_order": 5},
    {"key": "speedtest", "action": "speedtest", "title_ru": "📊 Статус серверов", "title_en": "📊 Server status", "sort_order": 6},
    {"key": "settings", "action": "settings", "title_ru": "⚙️ Настройки", "title_en": "⚙️ Settings", "sort_order": 7},
]


async def ensure_menu_seeded(session: AsyncSession) -> None:
    existing = (await session.execute(select(MenuButton.key))).scalars().all()
    for b in DEFAULT_BUTTONS:
        if b["key"] not in existing:
            session.add(MenuButton(**b))
    await session.commit()


async def main_menu_keyboard(session: AsyncSession, locale: str) -> ReplyKeyboardMarkup:
    rows = (
        await session.execute(
            select(MenuButton).where(MenuButton.is_visible.is_(True)).order_by(MenuButton.sort_order)
        )
    ).scalars().all()

    buttons: list[list[KeyboardButton]] = []
    row: list[KeyboardButton] = []
    for btn in rows:
        title = btn.title_ru if locale == "ru" else btn.title_en
        if btn.action == "support":
            kb = KeyboardButton(text=title, web_app=WebAppInfo(url=settings.WEBAPP_URL))
        else:
            kb = KeyboardButton(text=title)
        row.append(kb)
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def subscribe_keyboard(locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(locale, "subscribe.check_button"), callback_data="check_sub")]
    ])


def lang_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_lang:ru"),
            InlineKeyboardButton(text="🇬🇧 English", callback_data="set_lang:en"),
        ]
    ])

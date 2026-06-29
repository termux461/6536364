from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import PLANS
from bot.models.server import Server
from bot.utils.helpers import is_admin


def main_menu(tg_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Купить VPN", callback_data="buy:start")],
        [InlineKeyboardButton(text="Мои подписки", callback_data="subs:list")],
        [InlineKeyboardButton(text="Профиль", callback_data="profile:show")],
        [InlineKeyboardButton(text="Поддержка", callback_data="support:start")],
    ]
    if is_admin(tg_id):
        rows.append([InlineKeyboardButton(text="🛠 Админ-панель", callback_data="admin:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_button(callback_data: str = "menu:main") -> InlineKeyboardButton:
    return InlineKeyboardButton(text="« Назад", callback_data=callback_data)


def plans_menu() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"{p['title']} — {p['price']}₽", callback_data=f"buy:plan:{key}")]
        for key, p in PLANS.items()
    ]
    rows.append([back_button()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def servers_menu(servers: list[Server]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{s.flag} {s.name} [{s.protocol.upper()}]",
                callback_data=f"buy:server:{s.id}",
            )
        ]
        for s in servers
    ]
    rows.append([back_button("buy:start")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_purchase_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data="buy:confirm")],
            [back_button("buy:start")],
        ]
    )


def subscriptions_menu(subs) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"#{s.id} — {s.plan} ({'активна' if s.active else 'истекла'})",
                callback_data=f"subs:show:{s.id}",
            )
        ]
        for s in subs
    ]
    rows.append([back_button()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def to_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[back_button()]])


def support_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Написать в поддержку", callback_data="support:write")],
            [back_button()],
        ]
    )

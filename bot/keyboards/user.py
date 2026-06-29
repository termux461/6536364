from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import PAYMENT_METHODS, PLANS
from bot.models.server import Server


def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Купить VPN", callback_data="buy:start")],
        [InlineKeyboardButton(text="Пополнить баланс", callback_data="topup:start")],
        [InlineKeyboardButton(text="Мои подписки", callback_data="subs:list")],
        [InlineKeyboardButton(text="Профиль", callback_data="profile:show")],
        [InlineKeyboardButton(text="Пригласить друга", callback_data="ref:show")],
        [InlineKeyboardButton(text="Поддержка", callback_data="support:start")],
    ]
    if is_admin:
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


def payment_methods_menu(prefix: str, balance_enough: bool) -> InlineKeyboardMarkup:
    rows = []
    for key, m in PAYMENT_METHODS.items():
        if not m["enabled"]:
            continue
        if key == "balance" and not balance_enough:
            continue
        rows.append([InlineKeyboardButton(text=m["title"], callback_data=f"{prefix}:{key}")])
    rows.append([back_button("buy:start" if prefix == "buy:pay" else "menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pay_link_menu(pay_url: str, back_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", url=pay_url)],
            [back_button(back_data)],
        ]
    )


def config_delivery_menu(sub_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📄 Скачать конфиг", callback_data=f"subs:config:{sub_id}")],
            [InlineKeyboardButton(text="📷 QR-код", callback_data=f"subs:qr:{sub_id}")],
            [InlineKeyboardButton(text="🔁 Продлить", callback_data=f"subs:extend:{sub_id}")],
            [back_button("subs:list")],
        ]
    )


def topup_amounts_menu() -> InlineKeyboardMarkup:
    amounts = [100, 300, 500, 1000, 2000]
    rows = [[InlineKeyboardButton(text=f"{a}₽", callback_data=f"topup:amount:{a}")] for a in amounts]
    rows.append([back_button()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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

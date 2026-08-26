from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.services.payments.base import PaymentGateway


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚀 Автонастройка")],
            [KeyboardButton(text="💰 Купить настройку"), KeyboardButton(text="📋 Мои заказы")],
            [KeyboardButton(text="📖 Инструкция"), KeyboardButton(text="🆘 Поддержка")],
        ],
        resize_keyboard=True,
    )


def how_it_works_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Заказать настройку", callback_data="order:new")],
            [InlineKeyboardButton(text="📖 Как это работает", callback_data="order:how")],
        ]
    )


def confirm_order_keyboard(tariff_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"order:confirm:{tariff_id}")],
            [InlineKeyboardButton(text="✖️ Отмена", callback_data="order:cancel")],
        ]
    )


def payment_methods_keyboard(order_id: int, gateways: list[PaymentGateway]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=gateway.title, callback_data=f"pay:{gateway.provider}:{order_id}")]
        for gateway in gateways
    ]
    rows.append([InlineKeyboardButton(text="✖️ Отмена", callback_data=f"order:cancel:{order_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def payment_keyboard(url: str, order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Перейти к оплате", url=url)],
            [InlineKeyboardButton(text="🔄 Я оплатил — проверить", callback_data=f"pay:check:{order_id}")],
        ]
    )


def ssh_auth_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔑 SSH-ключ (рекомендуется)", callback_data="ssh:key")],
            [InlineKeyboardButton(text="🔒 Пароль", callback_data="ssh:password")],
        ]
    )


def dns_mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡️ Cloudflare API", callback_data="dns:cloudflare")],
            [InlineKeyboardButton(text="☁️ Yandex Cloud DNS", callback_data="dns:yandex")],
            [InlineKeyboardButton(text="✍️ Добавлю записи сам", callback_data="dns:manual")],
        ]
    )


def dns_check_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Проверить DNS", callback_data=f"dns:check:{order_id}")]
        ]
    )


def order_actions_keyboard(order_id: int, *, failed: bool, support: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if failed:
        rows.append(
            [InlineKeyboardButton(text="🔄 Продолжить", callback_data=f"order:retry:{order_id}")]
        )
    rows.append([InlineKeyboardButton(text="🆘 Поддержка", url=f"https://t.me/{support}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def yandex_auth_keyboard(cookie_enabled: bool) -> InlineKeyboardMarkup:
    """Ways to authenticate to Yandex Cloud, best first."""
    rows = [
        [InlineKeyboardButton(text="🔑 Ключ сервисного аккаунта", callback_data="yauth:service_account")],
        [InlineKeyboardButton(text="🎫 OAuth-токен Yandex", callback_data="yauth:oauth")],
    ]
    if cookie_enabled:
        rows.append([InlineKeyboardButton(text="🍪 Cookie браузера", callback_data="yauth:cookie")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

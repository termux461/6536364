from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def admin_menu() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="adm:users:0")],
        [InlineKeyboardButton(text="📦 Заказы", callback_data="adm:orders:all:0")],
        [InlineKeyboardButton(text="💰 Цены", callback_data="adm:prices")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="adm:broadcast")],
        [InlineKeyboardButton(text="🔧 Техработы", callback_data="adm:maintenance")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="adm:stats:0")],
        [InlineKeyboardButton(text="📋 Логи", callback_data="adm:logs")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Меню", callback_data="adm:menu")]]
    )

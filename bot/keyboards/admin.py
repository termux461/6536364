from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.keyboards.user import back_button


def admin_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin:users")],
            [InlineKeyboardButton(text="🌍 Серверы", callback_data="admin:servers")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")],
            [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin:broadcast")],
            [InlineKeyboardButton(text="↩️ Назад в меню", callback_data="menu:main")],
        ]
    )


def admin_users_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔎 Найти по TG ID", callback_data="admin:users:find")],
            [back_button("admin:open")],
        ]
    )


def admin_user_card_menu(tg_id: int, is_blocked: bool) -> InlineKeyboardMarkup:
    block_text = "✅ Разблокировать" if is_blocked else "🚫 Заблокировать"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💰 Изменить баланс", callback_data=f"admin:user:balance:{tg_id}")],
            [InlineKeyboardButton(text=block_text, callback_data=f"admin:user:toggleblock:{tg_id}")],
            [back_button("admin:users")],
        ]
    )


def admin_servers_menu(servers) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"{s.flag} {s.name} [{s.protocol.upper()}]", callback_data=f"admin:server:{s.id}")]
        for s in servers
    ]
    rows.append([InlineKeyboardButton(text="➕ Добавить сервер", callback_data="admin:servers:add")])
    rows.append([back_button("admin:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_back_menu(callback_data: str = "admin:open") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[back_button(callback_data)]])


def admin_broadcast_confirm_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Отправить всем", callback_data="admin:broadcast:send")],
            [back_button("admin:open")],
        ]
    )

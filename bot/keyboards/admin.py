from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.keyboards.user import back_button

# Data-driven layout: each row is a list of (text, callback_data) tuples.
# Add/remove/reorder sections here without touching handler code.
ADMIN_MENU_LAYOUT: list[list[tuple[str, str]]] = [
    [("👥 Пользователи", "admin:users"), ("🔑 Ключи на хосте", "admin:keys")],
    [("🎁 Выдать ключ", "admin:issue"), ("🏷 Промокоды", "admin:promo")],
    [("📊 Мониторинг", "admin:monitor"), ("💾 Бэкап БД", "admin:backup")],
    [("♻️ Восстановить БД", "admin:restore"), ("🛡 Администраторы", "admin:admins")],
    [("🌍 Серверы", "admin:servers"), ("📈 Статистика", "admin:stats")],
    [("📢 Рассылка", "admin:broadcast")],
    [("↩️ Назад в меню", "menu:main")],
]


def build_menu(layout: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=data) for text, data in row] for row in layout]
    )


def admin_main_menu() -> InlineKeyboardMarkup:
    return build_menu(ADMIN_MENU_LAYOUT)


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
            [InlineKeyboardButton(text="✉️ Написать", callback_data=f"admin:user:message:{tg_id}")],
            [InlineKeyboardButton(text=block_text, callback_data=f"admin:user:toggleblock:{tg_id}")],
            [back_button("admin:users")],
        ]
    )


def admin_servers_menu(servers) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"{s.flag} {s.name} [{s.protocol.upper()}]", callback_data=f"admin:server:{s.id}")]
        for s in servers
    ]
    rows.append([InlineKeyboardButton(text="➕ Добавить сервер (автоустановка)", callback_data="admin:servers:add")])
    rows.append([back_button("admin:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_server_card_menu(server_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔑 Ключи на этой ноде", callback_data=f"admin:keys:{server_id}")],
            [InlineKeyboardButton(text="🗑 Удалить сервер", callback_data=f"admin:server:delete:{server_id}")],
            [back_button("admin:servers")],
        ]
    )


def admin_back_menu(callback_data: str = "admin:open") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[back_button(callback_data)]])


def admin_broadcast_filters_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Все пользователи", callback_data="admin:broadcast:filter:all")],
            [InlineKeyboardButton(text="С активной подпиской", callback_data="admin:broadcast:filter:active")],
            [InlineKeyboardButton(text="С истёкшей подпиской", callback_data="admin:broadcast:filter:expired")],
            [back_button("admin:open")],
        ]
    )


def admin_broadcast_confirm_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Отправить", callback_data="admin:broadcast:send")],
            [back_button("admin:open")],
        ]
    )


def admin_keys_menu(servers) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"{s.flag} {s.name}", callback_data=f"admin:keys:{s.id}:0")] for s in servers
    ]
    rows.append([back_button("admin:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_keys_list_menu(server_id: int, peers: list[dict], offset: int, page_size: int = 10) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"{p.get('name', p.get('id'))}", callback_data=f"admin:key:{server_id}:{p.get('id')}")]
        for p in peers[offset : offset + page_size]
    ]
    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton(text="« Назад", callback_data=f"admin:keys:{server_id}:{offset - page_size}"))
    if offset + page_size < len(peers):
        nav.append(InlineKeyboardButton(text="Вперёд »", callback_data=f"admin:keys:{server_id}:{offset + page_size}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="🗑 Удалить истекшие", callback_data=f"admin:keys:cleanup:{server_id}")])
    rows.append([back_button("admin:keys")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_promo_menu(promos) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"{p.code} (-{p.discount_percent}%)", callback_data=f"admin:promo:show:{p.id}")]
        for p in promos
    ]
    rows.append([InlineKeyboardButton(text="➕ Создать промокод", callback_data="admin:promo:add")])
    rows.append([back_button("admin:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_promo_card_menu(promo_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin:promo:delete:{promo_id}")],
            [back_button("admin:promo")],
        ]
    )


def admin_admins_menu(admins) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"{a.tg_id} ({a.role})", callback_data=f"admin:admins:remove:{a.tg_id}")]
        for a in admins
    ]
    rows.append([InlineKeyboardButton(text="➕ Добавить администратора", callback_data="admin:admins:add")])
    rows.append([back_button("admin:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_restore_confirm_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, восстановить", callback_data="admin:restore:confirm")],
            [back_button("admin:open")],
        ]
    )

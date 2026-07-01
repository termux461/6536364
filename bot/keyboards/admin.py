from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from database.models import Host, PaymentMethod, Ticket


def admin_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🖥 Хосты"), KeyboardButton(text="📦 Тарифы")],
        [KeyboardButton(text="💳 Платёжки"), KeyboardButton(text="🎫 Тикеты")],
        [KeyboardButton(text="📢 Рассылка"), KeyboardButton(text="📈 Статистика")],
        [KeyboardButton(text="🧩 Меню бота"), KeyboardButton(text="⬅️ Выйти из админки")],
    ], resize_keyboard=True)


def hosts_list_keyboard(hosts: list[Host]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"{h.name} {'✅' if h.is_active else '🚫'}", callback_data=f"admin_host:{h.id}")] for h in hosts]
    rows.append([InlineKeyboardButton(text="➕ Добавить хост", callback_data="admin_host_add")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def host_detail_keyboard(host: Host) -> InlineKeyboardMarkup:
    toggle = "🚫 Деактивировать" if host.is_active else "✅ Активировать"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle, callback_data=f"admin_host_toggle:{host.id}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_host_delete:{host.id}")],
    ])


def payment_methods_admin_keyboard(methods: list[PaymentMethod]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"{m.title} — {'включено ✅' if m.is_enabled else 'отключено 🚫'}",
            callback_data=f"admin_pm_toggle:{m.code}",
        )]
        for m in methods
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def tickets_list_keyboard(tickets: list[Ticket]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"#{tk.id} {tk.subject} [{tk.status.value}]", callback_data=f"admin_ticket:{tk.id}")]
        for tk in tickets
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ticket_admin_keyboard(ticket_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Ответить", callback_data=f"admin_ticket_reply:{ticket_id}")],
        [InlineKeyboardButton(text="✅ Закрыть тикет", callback_data=f"admin_ticket_close:{ticket_id}")],
    ])

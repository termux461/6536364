from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ── Главное меню ─────────────────────────────────────────────────────────────

def main_menu(balance: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Купить подписку",  callback_data="buy")],
        [InlineKeyboardButton(text=f"💰 Баланс: {balance}₽", callback_data="balance")],
        [
            InlineKeyboardButton(text="📋 Мои подписки", callback_data="my_subs"),
            InlineKeyboardButton(text="🎟 Промокод",      callback_data="promo"),
        ],
        [
            InlineKeyboardButton(text="🤝 Партнёрка",    callback_data="referral"),
            InlineKeyboardButton(text="🔧 Техподдержка", callback_data="support"),
        ],
        [InlineKeyboardButton(text="ℹ️ Инфо",            callback_data="info")],
    ])

# ── Шаг 1: выбор протокола ───────────────────────────────────────────────────

def protocol_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="⚡ WireGuard  —  от 79₽/мес",
            callback_data="proto:wg"
        )],
        [InlineKeyboardButton(
            text="🛡 AmneziaWG 2.0  —  от 129₽/мес",
            callback_data="proto:awg"
        )],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main")],
    ])

# ── Шаг 2: выбор тарифа ─────────────────────────────────────────────────────

def plans_kb(plans: list[dict], protocol: str) -> InlineKeyboardMarkup:
    rows = []
    for p in plans:
        rows.append([InlineKeyboardButton(
            text=f"{p['name']}  —  {p['price']}₽",
            callback_data=f"plan:{p['id']}"
        )])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="buy")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ── Шаг 3: подтверждение покупки ─────────────────────────────────────────────

def confirm_buy_kb(plan_id: int, has_balance: bool, renew: bool = False) -> InlineKeyboardMarkup:
    rows = []
    if has_balance:
        rows.append([InlineKeyboardButton(
            text="🔄 Продлить с баланса" if renew else "✅ Оплатить с баланса",
            callback_data=f"confirm_buy:{plan_id}"
        )])
    rows.append([InlineKeyboardButton(
        text="💳 Пополнить баланс",
        callback_data="balance"
    )])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="buy")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ── Пополнение баланса ────────────────────────────────────────────────────────

def topup_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Telegram Stars",         callback_data="topup:stars")],
        [InlineKeyboardButton(text="🏦 СБП (QR) (Platega)",     callback_data="topup:platega_sbp")],
        [InlineKeyboardButton(text="💳 Карты RUB (Platega)",    callback_data="topup:platega_card")],
        [InlineKeyboardButton(text="🌍 Межд. карты (Platega)",  callback_data="topup:platega_intl")],
        [InlineKeyboardButton(text="🪙 Криптовалюта (Platega)", callback_data="topup:platega_crypto")],
        [InlineKeyboardButton(text="◀️ Назад",                  callback_data="main")],
    ])

def topup_amount_kb(method: str) -> InlineKeyboardMarkup:
    amounts = [100, 200, 300, 500, 1000]
    rows = [
        [InlineKeyboardButton(text=f"{a}₽", callback_data=f"topup_amount:{method}:{a}")]
        for a in amounts
    ]
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="balance")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def stars_amount_kb() -> InlineKeyboardMarkup:
    # stars : rub (курс ~2₽/star)
    options = [(50, 100), (100, 200), (175, 350), (250, 500), (500, 1000)]
    rows = [
        [InlineKeyboardButton(
            text=f"⭐ {s} Stars  ({r}₽)",
            callback_data=f"stars:{s}:{r}"
        )]
        for s, r in options
    ]
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="balance")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def pay_url_kb(url: str, back: str = "balance") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Перейти к оплате", url=url)],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=back)],
    ])

# ── Утилиты ───────────────────────────────────────────────────────────────────

def back_kb(target: str = "main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data=target)]
    ])

def my_subs_kb(active_subs: list[dict]) -> InlineKeyboardMarkup:
    """Список активных подписок с кнопками повторной выдачи .conf.

    active_subs: [{"id": int, "emoji": str, "name": str}, ...]
    """
    rows = [
        [InlineKeyboardButton(
            text=f"⬇️ {s['emoji']} {s['name']}",
            callback_data=f"getcfg:{s['id']}"
        )]
        for s in active_subs
    ]
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ── Админ ─────────────────────────────────────────────────────────────────────

def admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Тарифы WG",        callback_data="adm:plans:wg")],
        [InlineKeyboardButton(text="🛡 Тарифы AmneziaWG", callback_data="adm:plans:awg")],
        [InlineKeyboardButton(text="🎟 Промокоды",         callback_data="adm:promos")],
        [InlineKeyboardButton(text="📊 Статистика",        callback_data="adm:stats")],
    ])

def admin_plans_kb(plans: list[dict], protocol: str) -> InlineKeyboardMarkup:
    rows = []
    for p in plans:
        status = "✅" if p["active"] else "❌"
        rows.append([InlineKeyboardButton(
            text=f"{status} {p['name']}  —  {p['price']}₽",
            callback_data=f"adm:plan_edit:{p['id']}"
        )])
    rows.append([InlineKeyboardButton(text="➕ Добавить тариф", callback_data=f"adm:plan_add:{protocol}")])
    rows.append([InlineKeyboardButton(text="◀️ Назад",           callback_data="adm:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admin_plan_edit_kb(plan_id: int, active: int, protocol: str) -> InlineKeyboardMarkup:
    toggle = "❌ Отключить" if active else "✅ Включить"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить цену", callback_data=f"adm:plan_price:{plan_id}")],
        [InlineKeyboardButton(text=toggle,             callback_data=f"adm:plan_toggle:{plan_id}")],
        [InlineKeyboardButton(text="◀️ Назад",          callback_data=f"adm:plans:{protocol}")],
    ])

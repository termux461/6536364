from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import CallbackQuery
from keyboards.inline import (
    protocol_kb, plans_kb, confirm_buy_kb, main_menu, back_kb, my_subs_kb
)
from services.database import Database
from services.activation import activate_subscription, renew_subscription, resend_config
from config import Config

router = Router()

PROTO_INFO = {
    "wg": {
        "emoji": "⚡",
        "name": "WireGuard",
        "desc": (
            "⚡ <b>WireGuard</b>\n\n"
            "Классический быстрый VPN-протокол.\n\n"
            "✅ Высокая скорость\n"
            "✅ Низкий пинг\n"
            "✅ Работает на всех платформах\n"
            "⚠️ Может блокироваться провайдером\n\n"
            "📱 Клиент: <b>WireGuard</b> (App Store / Google Play)\n\n"
            "Выберите срок подписки:"
        ),
    },
    "awg": {
        "emoji": "🛡",
        "name": "AmneziaWG 2.0",
        "desc": (
            "🛡 <b>AmneziaWG 2.0</b>\n\n"
            "Обфусцированный WireGuard — трафик выглядит как обычный HTTPS.\n\n"
            "✅ Не блокируется ТСПУ / DPI\n"
            "✅ Работает там, где обычный WG заблокирован\n"
            "✅ Та же скорость, что и WireGuard\n"
            "✅ Все платформы\n\n"
            "📱 Клиент: <b>AmneziaVPN</b> (amnezia.org/download)\n\n"
            "Выберите срок подписки:"
        ),
    },
}


# ── Шаг 1: выбор протокола ───────────────────────────────────────────────────

@router.callback_query(F.data == "buy")
async def show_protocols(call: CallbackQuery):
    await call.message.edit_text(
        "🛒 <b>Купить подписку</b>\n\n"
        "Выберите протокол:\n\n"
        "⚡ <b>WireGuard</b> — быстрый, стандартный VPN\n"
        "🛡 <b>AmneziaWG 2.0</b> — обфускация, обходит блокировки ТСПУ",
        parse_mode="HTML",
        reply_markup=protocol_kb()
    )
    await call.answer()


# ── Шаг 2: выбор тарифа ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("proto:"))
async def show_plans(call: CallbackQuery, db: Database):
    protocol = call.data.split(":")[1]  # wg / awg
    info = PROTO_INFO.get(protocol)
    if not info:
        await call.answer("Неизвестный протокол", show_alert=True)
        return

    plans = await db.get_plans_by_protocol(protocol)
    if not plans:
        await call.answer("Тарифы временно недоступны", show_alert=True)
        return

    await call.message.edit_text(
        info["desc"],
        parse_mode="HTML",
        reply_markup=plans_kb(plans, protocol)
    )
    await call.answer()


# ── Шаг 3: подтверждение ─────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("plan:"))
async def select_plan(call: CallbackQuery, db: Database):
    plan_id = int(call.data.split(":")[1])
    plan = await db.get_plan(plan_id)
    if not plan:
        await call.answer("Тариф не найден", show_alert=True)
        return

    # Активная подписка на этот же протокол? → это продление, а не блок.
    sub = await db.get_active_subscription_by_proto(call.from_user.id, plan["protocol"])
    is_renewal = sub is not None

    user = await db.get_user(call.from_user.id)
    balance = user["balance"] if user else 0
    has_balance = balance >= plan["price"]
    proto = PROTO_INFO[plan["protocol"]]

    status_line = (
        f"✅ Достаточно (баланс: {balance}₽)"
        if has_balance
        else f"❌ Не хватает {plan['price'] - balance}₽ (баланс: {balance}₽)"
    )

    if is_renewal:
        exp = datetime.fromisoformat(sub["expires_at"])
        new_exp = exp + timedelta(days=plan["duration_days"])
        header = (
            f"🔄 <b>Продление {proto['name']}</b>  ·  {plan['name']}\n\n"
            f"📅 Сейчас действует до: <b>{exp.strftime('%d.%m.%Y')}</b>\n"
            f"📅 После продления: <b>{new_exp.strftime('%d.%m.%Y')}</b>\n"
        )
    else:
        header = (
            f"{proto['emoji']} <b>{proto['name']}</b>  ·  {plan['name']}\n\n"
            f"📅 Срок: <b>{plan['duration_days']} дней</b>\n"
        )

    await call.message.edit_text(
        header +
        f"💰 Стоимость: <b>{plan['price']}₽</b>\n"
        f"💳 Баланс: {status_line}",
        parse_mode="HTML",
        reply_markup=confirm_buy_kb(plan_id, has_balance, renew=is_renewal)
    )
    await call.answer()


# ── Шаг 4: оплата с баланса → активация ──────────────────────────────────────

@router.callback_query(F.data.startswith("confirm_buy:"))
async def confirm_buy(call: CallbackQuery, db: Database, config: Config):
    plan_id = int(call.data.split(":")[1])
    plan = await db.get_plan(plan_id)
    user = await db.get_user(call.from_user.id)

    if not plan or not user:
        await call.answer("Ошибка", show_alert=True)
        return

    user_id = call.from_user.id
    # Продление, если на этом протоколе уже есть активная подписка.
    sub = await db.get_active_subscription_by_proto(user_id, plan["protocol"])
    action = "продление" if sub else "покупка"

    # Атомарное списание: единственный источник правды о достаточности средств.
    # Защищает от двойного списания при повторном нажатии кнопки.
    debited = await db.try_debit_balance(
        user_id, plan["price"], f"{action} {plan['protocol']} {plan['name']}"
    )
    if not debited:
        await call.answer("❌ Недостаточно средств на балансе", show_alert=True)
        return

    await call.message.edit_text(
        "⏳ Продлеваем подписку..." if sub else "⏳ Создаём конфигурацию..."
    )
    await call.answer()

    if sub:
        success = await renew_subscription(call.bot, db, config, user_id, sub, plan)
    else:
        success = await activate_subscription(call.bot, db, config, user_id, plan_id)

    # Провал создания/продления пира — возвращаем деньги на баланс.
    if not success:
        await db.change_balance(
            user_id, plan["price"], f"возврат: сбой ({action}) {plan['name']}"
        )
        await call.bot.send_message(
            user_id,
            "⚠️ Не удалось выдать конфигурацию — <b>деньги возвращены на баланс</b>.\n"
            "Попробуйте ещё раз позже или напишите в поддержку.",
            parse_mode="HTML"
        )

    # Возвращаем на главную с обновлённым балансом
    from handlers.start import build_main_text
    text, balance = await build_main_text(user_id, db)
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=main_menu(balance))


# ── Мои подписки ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "my_subs")
async def my_subscriptions(call: CallbackQuery, db: Database):
    subs = await db.get_user_subscriptions(call.from_user.id)
    if not subs:
        await call.message.edit_text(
            "📋 <b>Мои подписки</b>\n\nПодписок пока нет.",
            parse_mode="HTML",
            reply_markup=back_kb("main")
        )
        await call.answer()
        return

    lines = ["📋 <b>Мои подписки:</b>\n"]
    active_subs = []
    for s in subs:
        expires = datetime.fromisoformat(s["expires_at"])
        is_active = s["active"] and expires > datetime.utcnow()
        status = "🟢" if is_active else "🔴"
        proto = PROTO_INFO.get(s.get("protocol", "wg"), PROTO_INFO["wg"])
        days_left = max((expires - datetime.utcnow()).days, 0)
        lines.append(
            f"{status} {proto['emoji']} <b>{proto['name']}</b>  ·  {s['plan_name']}\n"
            f"   до {expires.strftime('%d.%m.%Y')}"
            + (f"  ({days_left} дн.)" if is_active else "")
        )
        if is_active and s.get("wg_peer_id"):
            active_subs.append({"id": s["id"], "emoji": proto["emoji"], "name": proto["name"]})

    if active_subs:
        lines.append("\n⬇️ Потеряли файл? Скачайте конфиг заново:")

    await call.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=my_subs_kb(active_subs)
    )
    await call.answer()


# ── Перевыдача конфига ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("getcfg:"))
async def get_config(call: CallbackQuery, db: Database, config: Config):
    sub_id = int(call.data.split(":")[1])
    sub = await db.get_subscription(sub_id, call.from_user.id)
    if not sub:
        await call.answer("Подписка не найдена", show_alert=True)
        return

    expires = datetime.fromisoformat(sub["expires_at"])
    if not (sub["active"] and expires > datetime.utcnow()):
        await call.answer("Подписка неактивна — оформите новую", show_alert=True)
        return

    await call.answer("Отправляю конфиг…")
    ok = await resend_config(call.bot, db, config, call.from_user.id, sub)
    if not ok:
        await call.bot.send_message(
            call.from_user.id,
            "⚠️ Не удалось получить конфигурацию. Попробуйте позже или напишите в поддержку."
        )

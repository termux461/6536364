import time
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, LabeledPrice, PreCheckoutQuery
from keyboards.inline import topup_kb, topup_amount_kb, stars_amount_kb, back_kb, main_menu
from services.database import Database
from services.platega import PlategaService
from config import Config

router = Router()


@router.callback_query(F.data == "balance")
async def show_balance(call: CallbackQuery, db: Database):
    user = await db.get_user(call.from_user.id)
    balance = user["balance"] if user else 0

    await call.message.edit_text(
        f"💰 <b>Ваш баланс: {balance}₽</b>\n\n"
        "💳 <b>Способы пополнения баланса</b>\n\n"
        "Выберите удобный способ оплаты:\n\n"
        "⭐ <b>Telegram Stars</b> — быстро и удобно\n"
        "🏦 <b>СБП (QR)</b> — через Platega\n"
        "💳 <b>Карты (RUB)</b> — через Platega\n"
        "🌍 <b>Международные карты</b> — через Platega\n"
        "🪙 <b>Криптовалюта</b> — через Platega",
        parse_mode="HTML",
        reply_markup=topup_kb()
    )
    await call.answer()


# ── Platega topup ────────────────────────────────────────

@router.callback_query(F.data.startswith("topup:platega_"))
async def topup_platega_select_amount(call: CallbackQuery):
    method = call.data.split(":")[1]  # platega_sbp / platega_card / etc
    method_names = {
        "platega_sbp":   "СБП (QR)",
        "platega_card":  "Карта RUB",
        "platega_intl":  "Межд. карта",
        "platega_crypto": "Криптовалюта",
    }
    name = method_names.get(method, method)
    await call.message.edit_text(
        f"💳 <b>Пополнение через {name}</b>\n\nВыберите сумму:",
        parse_mode="HTML",
        reply_markup=topup_amount_kb(method)
    )
    await call.answer()


@router.callback_query(F.data.startswith("topup_amount:"))
async def topup_platega_pay(call: CallbackQuery, db: Database, config: Config):
    _, method, amount_str = call.data.split(":")
    amount = int(amount_str)
    user_id = call.from_user.id

    order_id = f"bal_{user_id}_{int(time.time())}"
    platega = PlategaService(config.PLATEGA_SHOP_ID, config.PLATEGA_SECRET)
    url = platega.create_url(
        order_id=order_id,
        amount=amount,
        description=f"Пополнение баланса AmneziaVPN на {amount}₽",
        user_id=user_id
    )

    await db.create_payment(user_id, order_id, method, amount)

    from keyboards.inline import pay_url_kb
    await call.message.edit_text(
        f"💳 Пополнение на <b>{amount}₽</b>\n\n"
        "После оплаты баланс пополнится автоматически.",
        parse_mode="HTML",
        reply_markup=pay_url_kb(url, back="balance")
    )
    await call.answer()


# ── Telegram Stars ───────────────────────────────────────

@router.callback_query(F.data == "topup:stars")
async def topup_stars_menu(call: CallbackQuery):
    await call.message.edit_text(
        "⭐ <b>Пополнение через Telegram Stars</b>\n\n"
        "Выберите количество Stars для пополнения:",
        parse_mode="HTML",
        reply_markup=stars_amount_kb()
    )
    await call.answer()


@router.callback_query(F.data.startswith("stars:"))
async def topup_stars_invoice(call: CallbackQuery):
    _, stars_str, rub_str = call.data.split(":")
    stars = int(stars_str)
    rub = int(rub_str)

    await call.bot.send_invoice(
        chat_id=call.from_user.id,
        title=f"Пополнение баланса на {rub}₽",
        description=f"Зачисление {rub}₽ на баланс AmneziaVPN",
        payload=f"stars_topup:{call.from_user.id}:{rub}",
        currency="XTR",
        prices=[LabeledPrice(label=f"{rub}₽ на баланс", amount=stars)],
    )
    await call.answer()


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_stars_payment(message: Message, db: Database):
    payload = message.successful_payment.invoice_payload
    if not payload.startswith("stars_topup:"):
        return

    _, user_id_str, rub_str = payload.split(":")
    user_id = int(user_id_str)
    rub = int(rub_str)

    await db.change_balance(user_id, rub, "пополнение Telegram Stars")

    order_id = f"stars_{user_id}_{int(time.time())}"
    await db.create_payment(user_id, order_id, "stars", rub)
    await db.confirm_payment(order_id)

    user = await db.get_user(user_id)
    await message.answer(
        f"✅ Баланс пополнен на <b>{rub}₽</b>\n"
        f"💰 Текущий баланс: <b>{user['balance']}₽</b>",
        parse_mode="HTML",
        reply_markup=main_menu(user["balance"])
    )

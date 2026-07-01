import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters import MenuAction
from bot.i18n import t
from bot.keyboards.buy import check_payment_keyboard, payment_methods_keyboard, tariffs_keyboard
from bot.services.fulfillment import fulfil_payment
from bot.services.payments.registry import build_provider, ensure_payment_methods_seeded, get_enabled_methods
from bot.states import BuyFlow
from database.models import Payment, PaymentStatus, PromoCode, Tariff, User

router = Router(name="buy")


async def _go_to_payment_methods(
    message: Message,
    session: AsyncSession,
    locale: str,
    state: FSMContext,
    tariff: Tariff,
    final_price: float,
) -> None:
    await ensure_payment_methods_seeded(session)
    methods = await get_enabled_methods(session)
    if not methods:
        await message.answer(t(locale, "buy.no_methods"))
        return
    await state.set_state(BuyFlow.choosing_payment)
    await message.answer(
        t(locale, "buy.choose_payment", tariff=tariff.name, price=final_price, currency="RUB"),
        reply_markup=payment_methods_keyboard(methods, tariff.id),
    )


@router.message(MenuAction("buy"))
@router.message(MenuAction("renew"))
async def handle_buy_entry(message: Message, session: AsyncSession, locale: str, state: FSMContext) -> None:
    tariffs = (await session.execute(select(Tariff).where(Tariff.is_active.is_(True)).order_by(Tariff.sort_order))).scalars().all()
    if not tariffs:
        await message.answer(t(locale, "buy.no_methods"))
        return
    await state.set_state(BuyFlow.choosing_tariff)
    await message.answer(t(locale, "buy.choose_tariff"), reply_markup=tariffs_keyboard(tariffs))


@router.callback_query(BuyFlow.choosing_tariff, F.data.startswith("tariff:"))
async def choose_tariff(callback: CallbackQuery, session: AsyncSession, locale: str, state: FSMContext) -> None:
    tariff_id = int(callback.data.split(":")[1])
    tariff = (await session.execute(select(Tariff).where(Tariff.id == tariff_id))).scalar_one_or_none()
    if not tariff:
        await callback.answer()
        return

    await state.update_data(tariff_id=tariff_id, promo_id=None, discount_amount=0, final_price=tariff.price)
    await state.set_state(BuyFlow.entering_promo)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t(locale, "buy.promo_skip"), callback_data="promo_skip")]]
    )
    await callback.message.answer(t(locale, "buy.promo_prompt"), reply_markup=kb)
    await callback.answer()


@router.callback_query(BuyFlow.entering_promo, F.data == "promo_skip")
async def skip_promo(callback: CallbackQuery, session: AsyncSession, locale: str, state: FSMContext) -> None:
    data = await state.get_data()
    tariff = (await session.execute(select(Tariff).where(Tariff.id == data["tariff_id"]))).scalar_one_or_none()
    if not tariff:
        await callback.answer()
        return
    await _go_to_payment_methods(callback.message, session, locale, state, tariff, tariff.price)
    await callback.answer()


@router.message(BuyFlow.entering_promo)
async def apply_promo(message: Message, session: AsyncSession, locale: str, state: FSMContext) -> None:
    code = message.text.strip().upper()
    now = datetime.datetime.now(datetime.timezone.utc)
    promo = (
        await session.execute(select(PromoCode).where(PromoCode.code == code, PromoCode.is_active.is_(True)))
    ).scalar_one_or_none()

    if (
        not promo
        or (promo.expires_at and promo.expires_at < now)
        or (promo.max_uses is not None and promo.uses_count >= promo.max_uses)
    ):
        await message.answer(t(locale, "buy.promo_invalid"))
        return

    data = await state.get_data()
    tariff = (await session.execute(select(Tariff).where(Tariff.id == data["tariff_id"]))).scalar_one_or_none()
    if not tariff:
        return
    discount = round(tariff.price * promo.discount_percent / 100, 2)
    final_price = max(0.0, round(tariff.price - discount, 2))
    await state.update_data(promo_id=promo.id, discount_amount=discount, final_price=final_price)
    await message.answer(t(locale, "buy.promo_applied", discount=int(promo.discount_percent), price=final_price))
    await _go_to_payment_methods(message, session, locale, state, tariff, final_price)


@router.callback_query(BuyFlow.choosing_payment, F.data.startswith("pay:"))
async def choose_payment(callback: CallbackQuery, session: AsyncSession, locale: str, user: User, state: FSMContext) -> None:
    _, tariff_id_str, code = callback.data.split(":")
    tariff_id = int(tariff_id_str)
    tariff = (await session.execute(select(Tariff).where(Tariff.id == tariff_id))).scalar_one_or_none()
    if not tariff:
        await callback.answer()
        return

    data = await state.get_data()
    final_price = data.get("final_price", tariff.price)
    promo_id = data.get("promo_id")
    discount_amount = data.get("discount_amount", 0)

    payment = Payment(
        user_id=user.id, tariff_id=tariff.id, provider=code,
        amount=final_price, currency="RUB",
        promo_code_id=promo_id, discount_amount=discount_amount,
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)

    # Increment promo usage
    if promo_id:
        promo = (await session.execute(select(PromoCode).where(PromoCode.id == promo_id))).scalar_one_or_none()
        if promo:
            promo.uses_count += 1
            await session.commit()

    provider = build_provider(code, callback.bot)
    if provider is None:
        await callback.message.answer(t(locale, "buy.no_methods"))
        return

    result = await provider.create_payment(
        amount=final_price, currency="RUB", description=tariff.name, payload={"payment_id": payment.id},
    )
    payment.external_id = result.external_id
    await session.commit()

    await state.update_data(payment_id=payment.id)
    await state.set_state(BuyFlow.waiting_payment)

    if result.pay_url:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💳 Оплатить", url=result.pay_url)]])
        await callback.message.answer(t(locale, "buy.invoice_created"), reply_markup=kb)
    await callback.message.answer(t(locale, "buy.check_payment"), reply_markup=check_payment_keyboard(payment.id, locale))
    await callback.answer()


@router.callback_query(F.data.startswith("check_pay:"))
async def check_pay(callback: CallbackQuery, session: AsyncSession, locale: str, state: FSMContext) -> None:
    payment_id = int(callback.data.split(":")[1])
    payment = (await session.execute(select(Payment).where(Payment.id == payment_id))).scalar_one_or_none()
    if not payment:
        await callback.answer()
        return

    if payment.status == PaymentStatus.PAID:
        await callback.answer()
        return

    is_paid = False
    if payment.provider != "stars":
        provider = build_provider(payment.provider, callback.bot)
        if provider and payment.external_id:
            is_paid = await provider.check_payment(payment.external_id)

    if not is_paid:
        await callback.answer(t(locale, "buy.payment_pending"), show_alert=True)
        return

    sub = await fulfil_payment(session, payment)
    await state.clear()
    await callback.message.answer(t(locale, "buy.payment_success"))
    await callback.message.answer(
        t(locale, "buy.config_caption", expires=sub.expires_at.strftime("%Y-%m-%d %H:%M UTC"), url=sub.subscription_url or "—")
    )
    await callback.answer()

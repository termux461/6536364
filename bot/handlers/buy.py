from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters import MenuAction
from bot.i18n import t
from bot.keyboards.buy import check_payment_keyboard, payment_methods_keyboard, tariffs_keyboard
from bot.services.payments.registry import build_provider, ensure_payment_methods_seeded, get_enabled_methods
from bot.services.referral import accrue_referral_bonus
from bot.services.remnawave import RemnawaveClient
from bot.states import BuyFlow
from database.models import Host, Payment, PaymentStatus, Subscription, SubscriptionStatus, Tariff, User

router = Router(name="buy")


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

    await ensure_payment_methods_seeded(session)
    methods = await get_enabled_methods(session)
    if not methods:
        await callback.message.answer(t(locale, "buy.no_methods"))
        return

    await state.update_data(tariff_id=tariff_id)
    await state.set_state(BuyFlow.choosing_payment)
    await callback.message.answer(
        t(locale, "buy.choose_payment", tariff=tariff.name, price=tariff.price, currency="RUB"),
        reply_markup=payment_methods_keyboard(methods, tariff_id),
    )
    await callback.answer()


@router.callback_query(BuyFlow.choosing_payment, F.data.startswith("pay:"))
async def choose_payment(callback: CallbackQuery, session: AsyncSession, locale: str, user: User, state: FSMContext) -> None:
    _, tariff_id_str, code = callback.data.split(":")
    tariff_id = int(tariff_id_str)
    tariff = (await session.execute(select(Tariff).where(Tariff.id == tariff_id))).scalar_one_or_none()
    if not tariff:
        await callback.answer()
        return

    payment = Payment(user_id=user.id, tariff_id=tariff.id, provider=code, amount=tariff.price, currency="RUB")
    session.add(payment)
    await session.commit()
    await session.refresh(payment)

    provider = build_provider(code, callback.bot)
    if provider is None:
        await callback.message.answer(t(locale, "buy.no_methods"))
        return

    result = await provider.create_payment(
        amount=tariff.price, currency="RUB", description=f"{tariff.name}", payload={"payment_id": payment.id},
    )
    payment.external_id = result.external_id
    await session.commit()

    await state.update_data(payment_id=payment.id)
    await state.set_state(BuyFlow.waiting_payment)

    if result.pay_url:
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💳 Оплатить", url=result.pay_url)]])
        await callback.message.answer(t(locale, "buy.invoice_created"), reply_markup=kb)
    await callback.message.answer(t(locale, "buy.check_payment"), reply_markup=check_payment_keyboard(payment.id, locale))
    await callback.answer()


async def fulfil_payment(session: AsyncSession, payment: Payment) -> Subscription:
    import datetime

    tariff = (await session.execute(select(Tariff).where(Tariff.id == payment.tariff_id))).scalar_one()
    host = (await session.execute(select(Host).where(Host.id == tariff.host_id))).scalar_one()
    user = (await session.execute(select(User).where(User.id == payment.user_id))).scalar_one()

    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=tariff.duration_days)
    client = RemnawaveClient(host.api_url, host.api_token)
    try:
        data = await client.create_user(
            telegram_id=user.tg_id,
            username=user.username or "",
            expire_at_iso=expires_at.isoformat(),
            traffic_limit_bytes=tariff.traffic_limit_gb * 1024 ** 3,
        )
    finally:
        await client.close()

    sub = Subscription(
        user_id=user.id, tariff_id=tariff.id, host_id=host.id,
        remnawave_uuid=data.get("uuid") or data.get("id"),
        subscription_url=data.get("subscriptionUrl") or data.get("subscription_url"),
        status=SubscriptionStatus.ACTIVE, expires_at=expires_at,
    )
    session.add(sub)
    payment.status = PaymentStatus.PAID
    import datetime as dt
    payment.paid_at = dt.datetime.now(dt.timezone.utc)
    await session.commit()
    await session.refresh(sub)

    await accrue_referral_bonus(session, payment)
    return sub


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

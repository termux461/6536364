from datetime import timedelta
from decimal import Decimal

from aiogram import F, Router
from aiogram.types import CallbackQuery

from sqlalchemy import select

from bot.config import PLANS
from bot.db.base import async_session
from bot.keyboards.user import (
    config_delivery_menu,
    main_menu,
    pay_link_menu,
    payment_methods_menu,
    subscriptions_menu,
    to_menu_keyboard,
)
from bot.models.payment import Payment
from bot.models.server import Server
from bot.models.subscription import Subscription
from bot.services.payment import PaymentError, get_provider
from bot.services.referral import accrue_referral_bonus
from bot.services.users import get_or_create_user
from bot.utils.config_gen import build_config_file, build_config_qr
from bot.utils.helpers import is_admin_async

router = Router(name="user_subscriptions")


@router.callback_query(F.data == "subs:list")
async def cb_subs_list(callback: CallbackQuery) -> None:
    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user)
        result = await session.execute(
            select(Subscription).where(Subscription.user_id == user.id).order_by(Subscription.created_at.desc())
        )
        subs = list(result.scalars().all())

    if not subs:
        await callback.message.edit_text("У вас пока нет подписок.", reply_markup=to_menu_keyboard())
        await callback.answer()
        return

    await callback.message.edit_text("Ваши подписки:", reply_markup=subscriptions_menu(subs))
    await callback.answer()


@router.callback_query(F.data.startswith("subs:show:"))
async def cb_subs_show(callback: CallbackQuery) -> None:
    sub_id = int(callback.data.split(":")[2])
    async with async_session() as session:
        subscription = await session.get(Subscription, sub_id)
        if subscription is None:
            await callback.answer("Подписка не найдена", show_alert=True)
            return
        server = await session.get(Server, subscription.server_id)

    plan = PLANS.get(subscription.plan, {"title": subscription.plan})
    text = (
        f"Подписка #{subscription.id}\n\n"
        f"Тариф: {plan['title']}\n"
        f"Сервер: {server.flag} {server.name} [{server.protocol.upper()}]\n"
        f"Статус: {'активна' if subscription.active else 'истекла'}\n"
        f"Истекает: {subscription.expires_at.strftime('%d.%m.%Y')}"
    )
    await callback.message.edit_text(text, reply_markup=config_delivery_menu(subscription.id))
    await callback.answer()


@router.callback_query(F.data.startswith("subs:config:"))
async def cb_subs_config(callback: CallbackQuery) -> None:
    sub_id = int(callback.data.split(":")[2])
    async with async_session() as session:
        subscription = await session.get(Subscription, sub_id)
        if subscription is None:
            await callback.answer("Подписка не найдена", show_alert=True)
            return
        server = await session.get(Server, subscription.server_id)

    await callback.message.answer_document(build_config_file(subscription, server))
    await callback.answer()


@router.callback_query(F.data.startswith("subs:qr:"))
async def cb_subs_qr(callback: CallbackQuery) -> None:
    sub_id = int(callback.data.split(":")[2])
    async with async_session() as session:
        subscription = await session.get(Subscription, sub_id)
        if subscription is None:
            await callback.answer("Подписка не найдена", show_alert=True)
            return
        server = await session.get(Server, subscription.server_id)

    await callback.message.answer_photo(build_config_qr(subscription, server))
    await callback.answer()


@router.callback_query(F.data.startswith("subs:extend:"))
async def cb_subs_extend(callback: CallbackQuery) -> None:
    sub_id = int(callback.data.split(":")[2])
    async with async_session() as session:
        subscription = await session.get(Subscription, sub_id)
        if subscription is None:
            await callback.answer("Подписка не найдена", show_alert=True)
            return
        user = await get_or_create_user(session, callback.from_user)
        plan = PLANS.get(subscription.plan, {"title": subscription.plan, "price": 0})
        balance_enough = Decimal(str(user.balance)) >= Decimal(str(plan["price"]))

    await callback.message.edit_text(
        f"Продление тарифа «{plan['title']}» — {plan['price']}₽.\nВыберите способ оплаты:",
        reply_markup=payment_methods_menu(f"subs:extendpay:{sub_id}", balance_enough),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("subs:extendpay:"))
async def cb_subs_extend_pay(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    sub_id, method = int(parts[2]), parts[3]

    async with async_session() as session:
        subscription = await session.get(Subscription, sub_id)
        if subscription is None:
            await callback.answer("Подписка не найдена", show_alert=True)
            return
        user = await get_or_create_user(session, callback.from_user)
        plan = PLANS.get(subscription.plan, {"title": subscription.plan, "price": 0, "days": 30})
        price = Decimal(str(plan["price"]))

        if method == "balance":
            if Decimal(str(user.balance)) < price:
                await callback.answer("Недостаточно средств", show_alert=True)
                return
            user.balance = Decimal(str(user.balance)) - price
            subscription.expires_at = subscription.expires_at + timedelta(days=plan["days"])
            subscription.active = True
            await session.commit()
            await accrue_referral_bonus(session, user, price)

            is_admin = await is_admin_async(callback.from_user.id)
            await callback.message.edit_text(
                f"Подписка #{subscription.id} продлена до {subscription.expires_at.strftime('%d.%m.%Y')}.",
                reply_markup=main_menu(is_admin),
            )
            await callback.answer()
            return

        provider = get_provider(method)
        try:
            invoice = await provider.create_invoice(float(price), f"Продление подписки #{sub_id}", f"extend:{sub_id}")
        except PaymentError as exc:
            await callback.message.edit_text(f"Ошибка создания платежа: {exc}", reply_markup=to_menu_keyboard())
            await callback.answer()
            return

        session.add(
            Payment(
                user_id=user.id,
                amount=price,
                method=method,
                status="pending",
                external_id=invoice.external_id,
                purpose="extend",
                payload=str(sub_id),
            )
        )
        await session.commit()

    await callback.message.edit_text(
        f"Счёт на {plan['price']}₽ создан. Оплатите по кнопке ниже — подписка продлится автоматически.",
        reply_markup=pay_link_menu(invoice.pay_url, "menu:main"),
    )
    await callback.answer()

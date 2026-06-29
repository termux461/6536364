from decimal import Decimal

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy import select

from bot.config import PAYMENT_METHODS, PLANS
from bot.db.base import async_session
from bot.keyboards.user import (
    main_menu,
    pay_link_menu,
    payment_methods_menu,
    plans_menu,
    servers_menu,
    to_menu_keyboard,
)
from bot.models.payment import Payment
from bot.models.server import Server
from bot.services.fulfillment import FulfillmentError, fulfill_purchase
from bot.services.payment import PaymentError, get_provider
from bot.services.users import get_or_create_user
from bot.utils.helpers import is_admin_async
from bot.utils.states import BuyVPN

router = Router(name="user_buy")


@router.callback_query(F.data == "buy:start")
async def cb_buy_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BuyVPN.choosing_plan)
    await callback.message.edit_text("Выберите тариф:", reply_markup=plans_menu())
    await callback.answer()


@router.callback_query(F.data.startswith("buy:plan:"))
async def cb_choose_plan(callback: CallbackQuery, state: FSMContext) -> None:
    plan_key = callback.data.split(":")[2]
    if plan_key not in PLANS:
        await callback.answer("Неизвестный тариф", show_alert=True)
        return
    await state.update_data(plan=plan_key)

    async with async_session() as session:
        result = await session.execute(select(Server).where(Server.active.is_(True)))
        servers = list(result.scalars().all())

    if not servers:
        await callback.message.edit_text(
            "Сейчас нет доступных серверов. Попробуйте позже.", reply_markup=to_menu_keyboard()
        )
        await callback.answer()
        return

    await state.set_state(BuyVPN.choosing_server)
    await callback.message.edit_text("Выберите сервер:", reply_markup=servers_menu(servers))
    await callback.answer()


@router.callback_query(F.data.startswith("buy:server:"))
async def cb_choose_server(callback: CallbackQuery, state: FSMContext) -> None:
    server_id = int(callback.data.split(":")[2])
    await state.update_data(server_id=server_id)
    data = await state.get_data()
    plan = PLANS[data["plan"]]

    async with async_session() as session:
        server = await session.get(Server, server_id)
        user = await get_or_create_user(session, callback.from_user)
        balance_enough = Decimal(str(user.balance)) >= Decimal(str(plan["price"]))

    if server is None:
        await callback.answer("Сервер не найден", show_alert=True)
        return

    text = (
        "Подтвердите покупку:\n\n"
        f"Тариф: {plan['title']}\n"
        f"Сервер: {server.flag} {server.name} [{server.protocol.upper()}]\n"
        f"Стоимость: {plan['price']}₽\n\n"
        "Выберите способ оплаты:"
    )
    await state.set_state(BuyVPN.confirm)
    await callback.message.edit_text(text, reply_markup=payment_methods_menu("buy:pay", balance_enough))
    await callback.answer()


@router.callback_query(F.data.startswith("buy:pay:"))
async def cb_pay(callback: CallbackQuery, state: FSMContext) -> None:
    method = callback.data.split(":")[2]
    data = await state.get_data()
    plan_key = data.get("plan")
    server_id = data.get("server_id")
    if not plan_key or not server_id or method not in PAYMENT_METHODS:
        await callback.answer("Сессия покупки истекла, начните заново", show_alert=True)
        await state.clear()
        return

    plan = PLANS[plan_key]
    price = Decimal(str(plan["price"]))

    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user)
        server = await session.get(Server, server_id)
        if server is None:
            await callback.answer("Сервер не найден", show_alert=True)
            return

        if method == "balance":
            if Decimal(str(user.balance)) < price:
                await callback.answer("Недостаточно средств", show_alert=True)
                return
            user.balance = Decimal(str(user.balance)) - price
            await session.commit()
            try:
                subscription = await fulfill_purchase(session, user, plan_key, server)
            except FulfillmentError as exc:
                user.balance = Decimal(str(user.balance)) + price
                await session.commit()
                await callback.message.edit_text(str(exc), reply_markup=to_menu_keyboard())
                await callback.answer()
                await state.clear()
                return

            await state.clear()
            is_admin = await is_admin_async(callback.from_user.id)
            await callback.message.edit_text(
                f"Подписка «{plan['title']}» оформлена! Конфигурация доступна в «Мои подписки».",
                reply_markup=main_menu(is_admin),
            )
            await callback.answer()
            return

        provider = get_provider(method)
        try:
            invoice = await provider.create_invoice(
                float(price), f"МАМОНТ ВПН: {plan['title']}", f"buy:{plan_key}:{server_id}"
            )
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
                purpose="buy",
                payload=f"{plan_key}:{server_id}",
            )
        )
        await session.commit()

    await state.clear()
    await callback.message.edit_text(
        f"Счёт на {plan['price']}₽ создан. Оплатите по кнопке ниже — подписка активируется автоматически.",
        reply_markup=pay_link_menu(invoice.pay_url, "menu:main"),
    )
    await callback.answer()

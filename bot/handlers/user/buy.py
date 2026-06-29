from datetime import datetime, timedelta
from decimal import Decimal

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy import select

from bot.config import PLANS
from bot.db.base import async_session
from bot.keyboards.user import (
    confirm_purchase_menu,
    main_menu,
    plans_menu,
    servers_menu,
    to_menu_keyboard,
)
from bot.models.server import Server
from bot.models.subscription import Subscription
from bot.services.users import get_or_create_user
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

    if server is None:
        await callback.answer("Сервер не найден", show_alert=True)
        return

    text = (
        "Подтвердите покупку:\n\n"
        f"Тариф: {plan['title']}\n"
        f"Сервер: {server.flag} {server.name} [{server.protocol.upper()}]\n"
        f"Стоимость: {plan['price']}₽ (списывается с баланса)"
    )
    await state.set_state(BuyVPN.confirm)
    await callback.message.edit_text(text, reply_markup=confirm_purchase_menu())
    await callback.answer()


@router.callback_query(F.data == "buy:confirm")
async def cb_confirm_purchase(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    plan_key = data.get("plan")
    server_id = data.get("server_id")
    if not plan_key or not server_id:
        await callback.answer("Сессия покупки истекла, начните заново", show_alert=True)
        await state.clear()
        return

    plan = PLANS[plan_key]

    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user)
        server = await session.get(Server, server_id)
        if server is None:
            await callback.answer("Сервер не найден", show_alert=True)
            return

        price = Decimal(str(plan["price"]))
        if Decimal(str(user.balance)) < price:
            await callback.message.edit_text(
                f"Недостаточно средств на балансе. Нужно {plan['price']}₽, "
                f"на балансе {user.balance}₽.\nПополните баланс и попробуйте снова.",
                reply_markup=to_menu_keyboard(),
            )
            await callback.answer()
            await state.clear()
            return

        user.balance = Decimal(str(user.balance)) - price
        subscription = Subscription(
            user_id=user.id,
            plan=plan_key,
            server_id=server.id,
            expires_at=datetime.utcnow() + timedelta(days=plan["days"]),
            active=True,
        )
        session.add(subscription)
        await session.commit()

    await state.clear()
    await callback.message.edit_text(
        f"Подписка «{plan['title']}» на сервере {server.flag} {server.name} оформлена!\n"
        "Конфигурация будет отправлена в раздел «Мои подписки».",
        reply_markup=main_menu(callback.from_user.id),
    )
    await callback.answer()

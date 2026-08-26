"""Tariff selection and order creation."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.keyboards import confirm_order_keyboard, payment_methods_keyboard
from app.models import User
from app.repositories import AuditRepository, OrderRepository, SettingRepository, TariffRepository
from app.services.payments import PaymentService

router = Router(name="purchase")


async def _maintenance_guard(message: Message, session: AsyncSession, is_admin: bool) -> bool:
    settings_repo = SettingRepository(session)
    if await settings_repo.maintenance_enabled() and not is_admin:
        await message.answer(await settings_repo.maintenance_text())
        return True
    return False


@router.message(F.text == "💰 Купить настройку")
async def buy(message: Message, session: AsyncSession, user: User, is_admin: bool) -> None:
    if await _maintenance_guard(message, session, is_admin):
        return
    if await OrderRepository(session).has_active(user.id):
        await message.answer(texts.ORDER_ACTIVE)
        return

    tariffs = await TariffRepository(session).list_enabled()
    if not tariffs:
        await message.answer("Тарифы временно недоступны. Загляните позже.")
        return

    for tariff in tariffs:
        await message.answer(
            f"<b>{tariff.name}</b>\n\n{tariff.description}\n\n💰 Стоимость: <b>{tariff.price_display}</b>",
            reply_markup=confirm_order_keyboard(tariff.id),
        )


@router.callback_query(F.data == "order:new")
async def order_new(callback: CallbackQuery, session: AsyncSession, user: User, is_admin: bool) -> None:
    await buy(callback.message, session, user, is_admin)
    await callback.answer()


@router.callback_query(F.data.startswith("order:confirm:"))
async def order_confirm(
    callback: CallbackQuery, session: AsyncSession, user: User, is_admin: bool
) -> None:
    if await _maintenance_guard(callback.message, session, is_admin):
        await callback.answer()
        return

    tariff_id = int(callback.data.split(":")[2])
    tariff = await TariffRepository(session).get(tariff_id)
    if tariff is None or not tariff.enabled:
        await callback.answer("Тариф недоступен", show_alert=True)
        return

    orders = OrderRepository(session)
    if await orders.has_active(user.id):
        await callback.answer(texts.ORDER_ACTIVE, show_alert=True)
        return

    order = await orders.create(
        user_id=user.id, tariff_id=tariff.id, amount=tariff.price, currency=tariff.currency
    )
    await AuditRepository(session).log(
        "order.created", user_id=user.telegram_id, order_id=order.id, message=tariff.code
    )

    gateways = PaymentService(session).available()
    if not gateways:
        await callback.message.answer("Приём платежей временно недоступен.")
        await callback.answer()
        return

    await callback.message.answer(
        f"Заказ <b>#{order.id}</b> на сумму <b>{order.amount_display}</b>\n\n{texts.CHOOSE_PAYMENT}",
        reply_markup=payment_methods_keyboard(order.id, gateways),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("order:cancel"))
async def order_cancel(callback: CallbackQuery, session: AsyncSession) -> None:
    parts = callback.data.split(":")
    if len(parts) == 3:
        from app.models.enums import OrderStatus

        orders = OrderRepository(session)
        order = await orders.get(int(parts[2]))
        if order and order.status in (OrderStatus.CREATED, OrderStatus.WAITING_PAYMENT):
            await orders.set_status(order, OrderStatus.CANCELLED)
    await callback.message.edit_text("Заказ отменён.")
    await callback.answer()

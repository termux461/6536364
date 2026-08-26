"""Payment creation and the (advisory) manual status check."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.keyboards import payment_keyboard
from app.config import get_settings
from app.core.exceptions import PaymentError
from app.models import User
from app.models.enums import OrderStatus
from app.repositories import OrderRepository, TariffRepository
from app.services.payments import PaymentService

logger = logging.getLogger(__name__)
router = Router(name="payment")


@router.callback_query(F.data.startswith("pay:check:"))
async def check_payment(callback: CallbackQuery, session: AsyncSession) -> None:
    """A convenience button only. Money is credited by the webhook, never by this press."""
    order_id = int(callback.data.split(":")[2])
    order = await OrderRepository(session).get(order_id)
    if order is None:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    if order.status in (OrderStatus.CREATED, OrderStatus.WAITING_PAYMENT):
        await callback.answer(
            "Платёж ещё не подтверждён платёжной системой. Настройка стартует автоматически.",
            show_alert=True,
        )
    else:
        await callback.answer("Платёж получен — настройка уже идёт.", show_alert=True)


@router.callback_query(F.data.startswith("pay:"))
async def create_payment(callback: CallbackQuery, session: AsyncSession, user: User) -> None:
    parts = callback.data.split(":")
    if len(parts) != 3 or parts[1] == "check":
        return
    provider, order_id = parts[1], int(parts[2])

    order = await OrderRepository(session).get(order_id)
    if order is None or order.user_id != user.id:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    if order.status not in (OrderStatus.CREATED, OrderStatus.WAITING_PAYMENT):
        await callback.answer("Этот заказ уже оплачен", show_alert=True)
        return

    tariff = await TariffRepository(session).get(order.tariff_id)
    description = f"Заказ #{order.id}: {tariff.name if tariff else 'Автонастройка'}"
    settings = get_settings()

    try:
        payment = await PaymentService(session).create(
            order=order,
            user=user,
            provider=provider,
            description=description,
            return_url=f"https://t.me/{(await callback.bot.me()).username}",
        )
    except PaymentError as exc:
        logger.error("Payment creation failed for order %s: %s", order_id, exc)
        await callback.answer("Не удалось создать платёж. Попробуйте другой способ.", show_alert=True)
        return

    await callback.message.edit_text(
        texts.PAYMENT_CREATED.format(amount=order.amount_display),
        reply_markup=payment_keyboard(payment.payment_url or settings.webhook_base_url, order.id),
    )
    await callback.answer()

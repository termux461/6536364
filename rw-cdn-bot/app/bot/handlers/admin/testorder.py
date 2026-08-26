"""Admin-only test order: run the whole setup without going through a payment.

This exists so the deployment pipeline can be exercised end to end — SSH, Remnawave, Yandex,
DNS — without a merchant account and without spending money on a real transaction.

It deliberately does NOT touch the payment path: no fake webhook, no synthetic Payment row,
no bypass of signature or amount checks. The order is simply created already marked paid, at
a zero amount, and flagged as a test in the audit log. Everything a customer's order does
after payment happens identically.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.handlers.admin.filters import IsAdmin
from app.bot.states import CollectData
from app.models import User
from app.models.enums import OrderStatus
from app.repositories import AuditRepository, OrderRepository, TariffRepository

router = Router(name="admin_testorder")
router.message.filter(IsAdmin())

TEST_TARIFF_CODE = "auto_setup"


@router.message(F.text.regexp(r"^/testorder$"))
async def test_order(message: Message, session: AsyncSession, user: User, state: FSMContext) -> None:
    orders = OrderRepository(session)
    if await orders.has_active(user.id):
        await message.answer(
            "У вас уже есть активный заказ. Завершите или остановите его: /admin → 📦 Заказы."
        )
        return

    tariff = await TariffRepository(session).get_by_code(TEST_TARIFF_CODE)
    if tariff is None:
        await message.answer("Тариф auto_setup не найден — перезапустите бота.")
        return

    # Zero amount: nothing was paid, and the order card should say so honestly.
    order = await orders.create(user_id=user.id, tariff_id=tariff.id, amount=0, currency=tariff.currency)
    await orders.set_status(order, OrderStatus.COLLECTING_DATA)
    await AuditRepository(session).log(
        "order.test_created",
        admin_id=message.from_user.id,
        order_id=order.id,
        message="тестовый заказ без оплаты",
    )
    await session.commit()

    await state.clear()
    await state.update_data(order_id=order.id)
    await state.set_state(CollectData.panel_url)

    await message.answer(
        f"🧪 Тестовый заказ <b>#{order.id}</b> создан без оплаты.\n\n"
        "Дальше всё как у обычного клиента: сбор данных, затем автоматическая настройка. "
        "Остановить в любой момент: /admin → 📦 Заказы → 🛑 Stop."
    )
    await message.answer(texts.ASK_PANEL_URL)

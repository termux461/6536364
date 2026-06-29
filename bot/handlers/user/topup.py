from decimal import Decimal

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.db.base import async_session
from bot.keyboards.user import pay_link_menu, payment_methods_menu, to_menu_keyboard, topup_amounts_menu
from bot.models.payment import Payment
from bot.services.payment import PaymentError, get_provider
from bot.services.users import get_or_create_user

router = Router(name="user_topup")


@router.callback_query(F.data == "topup:start")
async def cb_topup_start(callback: CallbackQuery) -> None:
    await callback.message.edit_text("Выберите сумму пополнения:", reply_markup=topup_amounts_menu())
    await callback.answer()


@router.callback_query(F.data.startswith("topup:amount:"))
async def cb_topup_amount(callback: CallbackQuery) -> None:
    amount = int(callback.data.split(":")[2])
    await callback.message.edit_text(
        f"Пополнение на {amount}₽. Выберите способ оплаты:",
        reply_markup=payment_methods_menu(f"topup:pay:{amount}", balance_enough=False),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("topup:pay:"))
async def cb_topup_pay(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    amount, method = Decimal(parts[2]), parts[3]

    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user)
        provider = get_provider(method)
        try:
            invoice = await provider.create_invoice(float(amount), "МАМОНТ ВПН: пополнение баланса", "topup")
        except PaymentError as exc:
            await callback.message.edit_text(f"Ошибка создания платежа: {exc}", reply_markup=to_menu_keyboard())
            await callback.answer()
            return

        session.add(
            Payment(
                user_id=user.id,
                amount=amount,
                method=method,
                status="pending",
                external_id=invoice.external_id,
                purpose="topup",
                payload="",
            )
        )
        await session.commit()

    await callback.message.edit_text(
        f"Счёт на {amount}₽ создан. Оплатите по кнопке ниже — баланс пополнится автоматически.",
        reply_markup=pay_link_menu(invoice.pay_url, "menu:main"),
    )
    await callback.answer()

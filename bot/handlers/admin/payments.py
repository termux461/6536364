from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.admin import payment_methods_admin_keyboard
from bot.services.payments.registry import ensure_payment_methods_seeded
from database.models import PaymentMethod

router = Router(name="admin_payments")


@router.message(lambda m: m.text == "💳 Платёжки")
async def list_payment_methods(message: Message, session: AsyncSession, is_admin: bool) -> None:
    if not is_admin:
        return
    await ensure_payment_methods_seeded(session)
    methods = (await session.execute(select(PaymentMethod).order_by(PaymentMethod.sort_order))).scalars().all()
    await message.answer(
        "Способы оплаты (нажмите, чтобы включить/выключить для пользователей):",
        reply_markup=payment_methods_admin_keyboard(methods),
    )


@router.callback_query(F.data.startswith("admin_pm_toggle:"))
async def toggle_payment_method(callback: CallbackQuery, session: AsyncSession) -> None:
    code = callback.data.split(":")[1]
    method = (await session.execute(select(PaymentMethod).where(PaymentMethod.code == code))).scalar_one_or_none()
    if method:
        method.is_enabled = not method.is_enabled
        await session.commit()
        methods = (await session.execute(select(PaymentMethod).order_by(PaymentMethod.sort_order))).scalars().all()
        await callback.message.edit_reply_markup(reply_markup=payment_methods_admin_keyboard(methods))
    await callback.answer()

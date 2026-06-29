from aiogram import F, Router
from aiogram.types import Message, PreCheckoutQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.buy import fulfil_payment
from bot.i18n import t
from database.models import Payment, PaymentStatus

router = Router(name="payments")


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message, session: AsyncSession, locale: str) -> None:
    payload = message.successful_payment.invoice_payload
    payment = (await session.execute(select(Payment).where(Payment.id == int(payload)))).scalar_one_or_none()
    if not payment or payment.status == PaymentStatus.PAID:
        return
    sub = await fulfil_payment(session, payment)
    await message.answer(t(locale, "buy.payment_success"))
    await message.answer(
        t(locale, "buy.config_caption", expires=sub.expires_at.strftime("%Y-%m-%d %H:%M UTC"), url=sub.subscription_url or "—")
    )

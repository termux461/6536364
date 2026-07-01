from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters import MenuAction
from bot.i18n import t
from bot.keyboards.referral import referral_keyboard
from bot.services.referral import referral_stats, request_withdraw
from bot.states import WithdrawFlow
from config import settings
from database.models import User

router = Router(name="referral")


@router.message(MenuAction("referral"))
async def show_referral(message: Message, session: AsyncSession, locale: str, user: User) -> None:
    stats = await referral_stats(session, user)
    link = f"https://t.me/{(await message.bot.get_me()).username}?start=ref_{user.tg_id}"
    await message.answer(
        t(locale, "referral.title", link=link, count=stats["count"], earned=stats["earned"], balance=stats["balance"]),
        reply_markup=referral_keyboard(locale),
    )


@router.callback_query(F.data == "withdraw_request")
async def start_withdraw(callback: CallbackQuery, session: AsyncSession, locale: str, user: User, state: FSMContext) -> None:
    if user.balance < settings.REFERRAL_MIN_WITHDRAW:
        await callback.answer(t(locale, "referral.withdraw_min", min=settings.REFERRAL_MIN_WITHDRAW), show_alert=True)
        return
    await state.set_state(WithdrawFlow.entering_amount)
    await callback.message.answer(t(locale, "referral.withdraw_min", min=settings.REFERRAL_MIN_WITHDRAW))
    await callback.answer()


@router.message(WithdrawFlow.entering_amount)
async def process_withdraw_amount(message: Message, session: AsyncSession, locale: str, user: User, state: FSMContext) -> None:
    try:
        amount = float(message.text.replace(",", "."))
    except ValueError:
        return
    if amount <= 0 or amount > user.balance or amount < settings.REFERRAL_MIN_WITHDRAW:
        await message.answer(t(locale, "referral.withdraw_min", min=settings.REFERRAL_MIN_WITHDRAW))
        return
    await request_withdraw(session, user, amount)
    await state.clear()
    await message.answer(t(locale, "referral.withdraw_requested", amount=amount))

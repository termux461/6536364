from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.i18n import t
from bot.keyboards.common import ensure_menu_seeded, main_menu_keyboard
from bot.services.referral import parse_referrer_id
from database.models import User

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession, user: User, locale: str) -> None:
    if user.is_banned:
        await message.answer(t(locale, "start.banned"))
        return

    if user.referrer_id is None:
        args = message.text.split(maxsplit=1)
        if len(args) > 1:
            ref_tg_id = parse_referrer_id(args[1].strip())
            if ref_tg_id and ref_tg_id != user.tg_id:
                from sqlalchemy import select
                referrer = (await session.execute(select(User).where(User.tg_id == ref_tg_id))).scalar_one_or_none()
                if referrer:
                    user.referrer_id = referrer.id
                    await session.commit()

    await ensure_menu_seeded(session)
    kb = await main_menu_keyboard(session, locale)
    await message.answer(t(locale, "start.greeting", name=message.from_user.full_name), reply_markup=kb)


@router.callback_query(F.data == "check_sub")
async def cb_check_sub(callback: CallbackQuery, session: AsyncSession, user: User, locale: str) -> None:
    from aiogram.exceptions import TelegramBadRequest

    from config import settings

    try:
        member = await callback.bot.get_chat_member(settings.SUBSCRIBE_CHANNEL_ID, user.tg_id)
        is_subscribed = member.status not in ("left", "kicked")
    except TelegramBadRequest:
        is_subscribed = True

    if is_subscribed:
        kb = await main_menu_keyboard(session, locale)
        await callback.message.answer(t(locale, "subscribe.ok"), reply_markup=kb)
    else:
        await callback.answer(t(locale, "subscribe.fail"), show_alert=True)

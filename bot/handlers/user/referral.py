from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select

from bot.db.base import async_session
from bot.keyboards.user import to_menu_keyboard
from bot.models.user import User
from bot.services.users import get_or_create_user

router = Router(name="user_referral")


@router.callback_query(F.data == "ref:show")
async def cb_referral(callback: CallbackQuery) -> None:
    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user)
        result = await session.execute(select(User).where(User.ref_by == user.id))
        invited = list(result.scalars().all())

    bot_username = (await callback.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start=ref_{user.tg_id}"

    text = (
        "Реферальная программа\n\n"
        f"Ваша ссылка:\n{link}\n\n"
        f"Приглашено друзей: {len(invited)}\n"
        f"Заработано: {user.referral_earned}₽\n\n"
        "Вы получаете процент от пополнений и покупок приглашённых друзей."
    )
    await callback.message.edit_text(text, reply_markup=to_menu_keyboard())
    await callback.answer()

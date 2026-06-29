from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import func, select

from bot.db.base import async_session
from bot.keyboards.user import to_menu_keyboard
from bot.models.subscription import Subscription
from bot.services.users import get_or_create_user

router = Router(name="user_profile")


@router.callback_query(F.data == "profile:show")
async def cb_profile(callback: CallbackQuery) -> None:
    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user)
        result = await session.execute(
            select(func.count()).select_from(Subscription).where(Subscription.user_id == user.id)
        )
        subs_count = result.scalar_one()

    text = (
        f"Профиль\n\n"
        f"ID: {user.tg_id}\n"
        f"Имя: {user.first_name or '-'}\n"
        f"Юзернейм: {'@' + user.username if user.username else '-'}\n"
        f"Баланс: {user.balance}₽\n"
        f"Подписок оформлено: {subs_count}\n"
        f"Дата регистрации: {user.created_at.strftime('%d.%m.%Y')}"
    )
    await callback.message.edit_text(text, reply_markup=to_menu_keyboard())
    await callback.answer()

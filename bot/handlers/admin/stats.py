from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import func, select

from bot.db.base import async_session
from bot.keyboards.admin import admin_back_menu
from bot.models.server import Server
from bot.models.subscription import Subscription
from bot.models.user import User
from bot.utils.helpers import admin_filter

router = Router(name="admin_stats")
router.callback_query.filter(admin_filter)


@router.callback_query(F.data == "admin:stats")
async def cb_admin_stats(callback: CallbackQuery) -> None:
    async with async_session() as session:
        users_count = (await session.execute(select(func.count()).select_from(User))).scalar_one()
        active_subs = (
            await session.execute(select(func.count()).select_from(Subscription).where(Subscription.active.is_(True)))
        ).scalar_one()
        servers_count = (await session.execute(select(func.count()).select_from(Server))).scalar_one()

    text = (
        "Статистика\n\n"
        f"Пользователей: {users_count}\n"
        f"Активных подписок: {active_subs}\n"
        f"Серверов: {servers_count}"
    )
    await callback.message.edit_text(text, reply_markup=admin_back_menu())
    await callback.answer()

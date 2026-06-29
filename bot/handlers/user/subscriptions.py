from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select

from bot.config import PLANS
from bot.db.base import async_session
from bot.keyboards.user import subscriptions_menu, to_menu_keyboard
from bot.models.server import Server
from bot.models.subscription import Subscription
from bot.services.users import get_or_create_user

router = Router(name="user_subscriptions")


@router.callback_query(F.data == "subs:list")
async def cb_subs_list(callback: CallbackQuery) -> None:
    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user)
        result = await session.execute(
            select(Subscription).where(Subscription.user_id == user.id).order_by(Subscription.created_at.desc())
        )
        subs = list(result.scalars().all())

    if not subs:
        await callback.message.edit_text("У вас пока нет подписок.", reply_markup=to_menu_keyboard())
        await callback.answer()
        return

    await callback.message.edit_text("Ваши подписки:", reply_markup=subscriptions_menu(subs))
    await callback.answer()


@router.callback_query(F.data.startswith("subs:show:"))
async def cb_subs_show(callback: CallbackQuery) -> None:
    sub_id = int(callback.data.split(":")[2])
    async with async_session() as session:
        subscription = await session.get(Subscription, sub_id)
        if subscription is None:
            await callback.answer("Подписка не найдена", show_alert=True)
            return
        server = await session.get(Server, subscription.server_id)

    plan = PLANS.get(subscription.plan, {"title": subscription.plan})
    text = (
        f"Подписка #{subscription.id}\n\n"
        f"Тариф: {plan['title']}\n"
        f"Сервер: {server.flag} {server.name} [{server.protocol.upper()}]\n"
        f"Статус: {'активна' if subscription.active else 'истекла'}\n"
        f"Истекает: {subscription.expires_at.strftime('%d.%m.%Y')}"
    )
    await callback.message.edit_text(text, reply_markup=to_menu_keyboard("subs:list"))
    await callback.answer()

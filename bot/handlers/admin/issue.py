from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from bot.config import PLANS
from bot.db.base import async_session
from bot.keyboards.admin import admin_back_menu
from bot.keyboards.user import plans_menu, servers_menu
from bot.models.server import Server
from bot.services.fulfillment import FulfillmentError, fulfill_purchase
from bot.services.users import get_user_by_tg_id
from bot.utils.helpers import admin_filter
from bot.utils.states import AdminIssueKey

router = Router(name="admin_issue")
router.message.filter(admin_filter)
router.callback_query.filter(admin_filter)


@router.callback_query(F.data == "admin:issue")
async def cb_admin_issue_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminIssueKey.waiting_tg_id)
    await callback.message.edit_text("Введите TG ID пользователя, которому нужно выдать ключ:", reply_markup=admin_back_menu())
    await callback.answer()


@router.message(AdminIssueKey.waiting_tg_id)
async def msg_admin_issue_tg_id(message: Message, state: FSMContext) -> None:
    if not message.text or not message.text.strip().isdigit():
        await message.answer("Некорректный TG ID. Попробуйте снова:")
        return
    tg_id = int(message.text.strip())
    async with async_session() as session:
        user = await get_user_by_tg_id(session, tg_id)
    if user is None:
        await message.answer("Пользователь не найден в базе (он должен хотя бы раз запустить /start).")
        return
    await state.update_data(tg_id=tg_id)
    await state.set_state(AdminIssueKey.choosing_plan)
    await message.answer("Выберите тариф:", reply_markup=plans_menu())


@router.callback_query(AdminIssueKey.choosing_plan, F.data.startswith("buy:plan:"))
async def cb_admin_issue_plan(callback: CallbackQuery, state: FSMContext) -> None:
    plan_key = callback.data.split(":")[2]
    await state.update_data(plan=plan_key)

    async with async_session() as session:
        result = await session.execute(select(Server).where(Server.active.is_(True)))
        servers = list(result.scalars().all())

    if not servers:
        await callback.message.edit_text("Нет доступных серверов.", reply_markup=admin_back_menu())
        await callback.answer()
        return

    await state.set_state(AdminIssueKey.choosing_server)
    await callback.message.edit_text("Выберите сервер:", reply_markup=servers_menu(servers))
    await callback.answer()


@router.callback_query(AdminIssueKey.choosing_server, F.data.startswith("buy:server:"))
async def cb_admin_issue_server(callback: CallbackQuery, state: FSMContext) -> None:
    server_id = int(callback.data.split(":")[2])
    data = await state.get_data()
    tg_id, plan_key = data["tg_id"], data["plan"]
    plan = PLANS[plan_key]

    async with async_session() as session:
        user = await get_user_by_tg_id(session, tg_id)
        server = await session.get(Server, server_id)
        if user is None or server is None:
            await callback.answer("Пользователь или сервер не найден", show_alert=True)
            await state.clear()
            return
        try:
            subscription = await fulfill_purchase(session, user, plan_key, server)
        except FulfillmentError as exc:
            await callback.message.edit_text(str(exc), reply_markup=admin_back_menu())
            await callback.answer()
            await state.clear()
            return

    await state.clear()
    await callback.message.edit_text(
        f"Ключ выдан пользователю {tg_id}: подписка #{subscription.id} «{plan['title']}» "
        f"на сервере {server.flag} {server.name}.",
        reply_markup=admin_back_menu(),
    )
    await callback.answer()

    try:
        await callback.bot.send_message(
            tg_id, f"Вам выдана подписка «{plan['title']}» администратором. Загляните в «Мои подписки»."
        )
    except Exception:
        pass

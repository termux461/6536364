from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from bot.db.base import async_session
from bot.keyboards.admin import admin_admins_menu, admin_back_menu
from bot.models.admin import Admin
from bot.utils.helpers import admin_filter
from bot.utils.states import AdminAdmins

router = Router(name="admin_admins")
router.message.filter(admin_filter)
router.callback_query.filter(admin_filter)


@router.callback_query(F.data == "admin:admins")
async def cb_admin_admins(callback: CallbackQuery) -> None:
    async with async_session() as session:
        result = await session.execute(select(Admin))
        admins = list(result.scalars().all())
    await callback.message.edit_text("Администраторы (из БД, помимо ADMIN_IDS в .env):", reply_markup=admin_admins_menu(admins))
    await callback.answer()


@router.callback_query(F.data == "admin:admins:add")
async def cb_admin_admins_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminAdmins.waiting_tg_id)
    await callback.message.edit_text("Введите TG ID нового администратора:", reply_markup=admin_back_menu("admin:admins"))
    await callback.answer()


@router.message(AdminAdmins.waiting_tg_id)
async def msg_admin_admins_add(message: Message, state: FSMContext) -> None:
    await state.clear()
    if not message.text or not message.text.strip().isdigit():
        await message.answer("Некорректный TG ID.", reply_markup=admin_back_menu("admin:admins"))
        return
    tg_id = int(message.text.strip())

    async with async_session() as session:
        existing = await session.execute(select(Admin).where(Admin.tg_id == tg_id))
        if existing.scalar_one_or_none() is None:
            session.add(Admin(tg_id=tg_id))
            await session.commit()

    await message.answer(f"Пользователь {tg_id} добавлен в администраторы.", reply_markup=admin_back_menu("admin:admins"))


@router.callback_query(F.data.startswith("admin:admins:remove:"))
async def cb_admin_admins_remove(callback: CallbackQuery) -> None:
    tg_id = int(callback.data.split(":")[3])
    async with async_session() as session:
        result = await session.execute(select(Admin).where(Admin.tg_id == tg_id))
        admin = result.scalar_one_or_none()
        if admin is not None:
            await session.delete(admin)
            await session.commit()
    await callback.answer("Администратор удалён")
    async with async_session() as session:
        result = await session.execute(select(Admin))
        admins = list(result.scalars().all())
    await callback.message.edit_text("Администраторы (из БД, помимо ADMIN_IDS в .env):", reply_markup=admin_admins_menu(admins))

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.admin import host_detail_keyboard, hosts_list_keyboard
from bot.states import AdminHostFlow
from database.models import Host

router = Router(name="admin_hosts")


@router.message(lambda m: m.text == "🖥 Хосты")
async def list_hosts(message: Message, session: AsyncSession, is_admin: bool) -> None:
    if not is_admin:
        return
    hosts = (await session.execute(select(Host))).scalars().all()
    await message.answer("Хосты Remnawave:", reply_markup=hosts_list_keyboard(hosts))


@router.callback_query(F.data == "admin_host_add")
async def add_host_start(callback: CallbackQuery, is_admin: bool, state: FSMContext) -> None:
    if not is_admin:
        return
    await state.set_state(AdminHostFlow.entering_name)
    await callback.message.answer("Введите название хоста:")
    await callback.answer()


@router.message(AdminHostFlow.entering_name)
async def add_host_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text)
    await state.set_state(AdminHostFlow.entering_url)
    await message.answer("Введите API URL панели Remnawave:")


@router.message(AdminHostFlow.entering_url)
async def add_host_url(message: Message, state: FSMContext) -> None:
    await state.update_data(api_url=message.text)
    await state.set_state(AdminHostFlow.entering_token)
    await message.answer("Введите API токен:")


@router.message(AdminHostFlow.entering_token)
async def add_host_token(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    host = Host(name=data["name"], api_url=data["api_url"], api_token=message.text)
    session.add(host)
    await session.commit()
    await state.clear()
    await message.answer(f"Хост «{host.name}» добавлен.")


@router.callback_query(F.data.startswith("admin_host:"))
async def host_detail(callback: CallbackQuery, session: AsyncSession) -> None:
    host_id = int(callback.data.split(":")[1])
    host = (await session.execute(select(Host).where(Host.id == host_id))).scalar_one_or_none()
    if not host:
        await callback.answer()
        return
    await callback.message.answer(
        f"Хост: {host.name}\nURL: {host.api_url}\nАктивен: {host.is_active}",
        reply_markup=host_detail_keyboard(host),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_host_toggle:"))
async def host_toggle(callback: CallbackQuery, session: AsyncSession) -> None:
    host_id = int(callback.data.split(":")[1])
    host = (await session.execute(select(Host).where(Host.id == host_id))).scalar_one_or_none()
    if host:
        host.is_active = not host.is_active
        await session.commit()
        await callback.message.answer(f"Хост «{host.name}»: активен = {host.is_active}")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_host_delete:"))
async def host_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    host_id = int(callback.data.split(":")[1])
    host = (await session.execute(select(Host).where(Host.id == host_id))).scalar_one_or_none()
    if host:
        await session.delete(host)
        await session.commit()
        await callback.message.answer("Хост удалён.")
    await callback.answer()

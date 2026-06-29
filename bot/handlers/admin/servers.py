from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from bot.db.base import async_session
from bot.keyboards.admin import admin_back_menu, admin_servers_menu
from bot.models.server import Server
from bot.utils.helpers import is_admin
from bot.utils.states import AdminAddServer

router = Router(name="admin_servers")
router.message.filter(lambda message: is_admin(message.from_user.id))
router.callback_query.filter(lambda callback: is_admin(callback.from_user.id))


@router.callback_query(F.data == "admin:servers")
async def cb_admin_servers(callback: CallbackQuery) -> None:
    async with async_session() as session:
        result = await session.execute(select(Server).order_by(Server.priority))
        servers = list(result.scalars().all())
    await callback.message.edit_text("Список серверов:", reply_markup=admin_servers_menu(servers))
    await callback.answer()


@router.callback_query(F.data.startswith("admin:server:"))
async def cb_admin_server_card(callback: CallbackQuery) -> None:
    server_id = int(callback.data.split(":")[2])
    async with async_session() as session:
        server = await session.get(Server, server_id)
    if server is None:
        await callback.answer("Сервер не найден", show_alert=True)
        return
    text = (
        f"{server.flag} {server.name}\n"
        f"Страна: {server.country}\n"
        f"Протокол: {server.protocol.upper()}\n"
        f"Endpoint: {server.endpoint or '-'}\n"
        f"Активен: {'да' if server.active else 'нет'}"
    )
    await callback.message.edit_text(text, reply_markup=admin_back_menu("admin:servers"))
    await callback.answer()


@router.callback_query(F.data == "admin:servers:add")
async def cb_admin_server_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminAddServer.name)
    await callback.message.edit_text("Введите название сервера (например, Latvia #1):", reply_markup=admin_back_menu("admin:servers"))
    await callback.answer()


@router.message(AdminAddServer.name)
async def msg_server_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip())
    await state.set_state(AdminAddServer.country)
    await message.answer("Введите страну:")


@router.message(AdminAddServer.country)
async def msg_server_country(message: Message, state: FSMContext) -> None:
    await state.update_data(country=message.text.strip())
    await state.set_state(AdminAddServer.flag)
    await message.answer("Введите эмодзи-флаг страны (например, 🇱🇻):")


@router.message(AdminAddServer.flag)
async def msg_server_flag(message: Message, state: FSMContext) -> None:
    await state.update_data(flag=message.text.strip())
    await state.set_state(AdminAddServer.protocol)
    await message.answer("Введите протокол (awg или wg):")


@router.message(AdminAddServer.protocol)
async def msg_server_protocol(message: Message, state: FSMContext) -> None:
    protocol = message.text.strip().lower()
    if protocol not in ("awg", "wg"):
        await message.answer("Протокол должен быть «awg» или «wg». Попробуйте снова:")
        return
    await state.update_data(protocol=protocol)
    await state.set_state(AdminAddServer.endpoint)
    await message.answer("Введите endpoint сервера (ip:port):")


@router.message(AdminAddServer.endpoint)
async def msg_server_endpoint(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    server = Server(
        name=data["name"],
        country=data["country"],
        flag=data["flag"],
        protocol=data["protocol"],
        endpoint=message.text.strip(),
        active=True,
    )
    async with async_session() as session:
        session.add(server)
        await session.commit()

    await state.clear()
    await message.answer(f"Сервер {server.flag} {server.name} добавлен.", reply_markup=admin_back_menu("admin:servers"))

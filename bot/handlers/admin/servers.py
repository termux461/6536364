from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from bot.db.base import async_session
from bot.keyboards.admin import admin_back_menu, admin_server_card_menu, admin_servers_menu
from bot.models.server import Server
from bot.services.node_installer import STEPS as _STEP_NAMES
from bot.services.node_installer import NodeInstallParams, node_installer
from bot.utils.crypto import encrypt
from bot.utils.helpers import admin_filter
from bot.utils.states import AdminAddServer

router = Router(name="admin_servers")
router.message.filter(admin_filter)
router.callback_query.filter(admin_filter)


@router.callback_query(F.data == "admin:servers")
async def cb_admin_servers(callback: CallbackQuery) -> None:
    async with async_session() as session:
        result = await session.execute(select(Server).order_by(Server.priority))
        servers = list(result.scalars().all())
    await callback.message.edit_text("Список серверов:", reply_markup=admin_servers_menu(servers))
    await callback.answer()


@router.callback_query(F.data.startswith("admin:server:delete:"))
async def cb_admin_server_delete(callback: CallbackQuery) -> None:
    server_id = int(callback.data.split(":")[3])
    async with async_session() as session:
        server = await session.get(Server, server_id)
        if server is not None:
            await session.delete(server)
            await session.commit()
    await callback.answer("Сервер удалён")
    async with async_session() as session:
        result = await session.execute(select(Server).order_by(Server.priority))
        servers = list(result.scalars().all())
    await callback.message.edit_text("Список серверов:", reply_markup=admin_servers_menu(servers))


@router.callback_query(F.data.startswith("admin:server:"))
async def cb_admin_server_card(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    if not parts[2].isdigit():
        return
    server_id = int(parts[2])
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
        f"Публичный ключ: {server.public_key or '-'}\n"
        f"Активен: {'да' if server.active else 'нет'}"
    )
    await callback.message.edit_text(text, reply_markup=admin_server_card_menu(server.id))
    await callback.answer()


@router.callback_query(F.data == "admin:servers:add")
async def cb_admin_server_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminAddServer.name)
    await callback.message.edit_text(
        "Автоустановка ноды.\n\nВведите название сервера (например, Latvia #1):",
        reply_markup=admin_back_menu("admin:servers"),
    )
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
    await state.set_state(AdminAddServer.ssh_host)
    await message.answer("Введите SSH host (IP сервера):")


@router.message(AdminAddServer.ssh_host)
async def msg_server_ssh_host(message: Message, state: FSMContext) -> None:
    await state.update_data(ssh_host=message.text.strip())
    await state.set_state(AdminAddServer.ssh_port)
    await message.answer("Введите SSH порт (по умолчанию 22):")


@router.message(AdminAddServer.ssh_port)
async def msg_server_ssh_port(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    port = int(text) if text.isdigit() else 22
    await state.update_data(ssh_port=port)
    await state.set_state(AdminAddServer.ssh_user)
    await message.answer("Введите SSH пользователя (например, root):")


@router.message(AdminAddServer.ssh_user)
async def msg_server_ssh_user(message: Message, state: FSMContext) -> None:
    await state.update_data(ssh_user=message.text.strip())
    await state.set_state(AdminAddServer.ssh_password)
    await message.answer("Введите SSH пароль:")


@router.message(AdminAddServer.ssh_password)
async def msg_server_ssh_password(message: Message, state: FSMContext) -> None:
    await state.update_data(ssh_password=message.text.strip())
    await state.set_state(AdminAddServer.wg_port)
    await message.answer("Введите WireGuard порт (например, 51820):")


@router.message(AdminAddServer.wg_port)
async def msg_server_wg_port(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("Порт должен быть числом. Попробуйте снова:")
        return
    await state.update_data(wg_port=int(text))
    await state.set_state(AdminAddServer.api_password)
    await message.answer("Введите пароль для веб-панели управления нодой (будет использоваться API ботом):")


@router.message(AdminAddServer.api_password)
async def msg_server_api_password(message: Message, state: FSMContext) -> None:
    await state.update_data(api_password=message.text.strip())
    data = await state.get_data()
    await state.set_state(AdminAddServer.installing)

    progress_message = await message.answer("Начинаю автоустановку ноды...\n\n" + "\n".join(["⬜ " + s for s in _STEP_NAMES]))

    params = NodeInstallParams(
        ssh_host=data["ssh_host"],
        ssh_port=data["ssh_port"],
        ssh_user=data["ssh_user"],
        ssh_password=data["ssh_password"],
        protocol=data["protocol"],
        wg_port=data["wg_port"],
        api_password=data["api_password"],
    )

    completed_steps: list[str] = []

    async def on_progress(step: int, total: int, text: str) -> None:
        completed_steps.append(text)
        lines = [f"✅ {s}" for s in completed_steps]
        lines += [f"⬜ {s}" for s in _STEP_NAMES[len(completed_steps):]]
        try:
            await progress_message.edit_text("Автоустановка ноды:\n\n" + "\n".join(lines))
        except Exception:
            pass

    try:
        public_key = await node_installer.install(params, on_progress)
    except Exception as exc:
        await progress_message.answer(f"Ошибка автоустановки: {exc}")
        await state.clear()
        return

    server = Server(
        name=data["name"],
        country=data["country"],
        flag=data["flag"],
        protocol=data["protocol"],
        endpoint=f"{data['ssh_host']}:{data['wg_port']}",
        api_url=f"http://{data['ssh_host']}:51821",
        api_token=data["api_password"],
        public_key=public_key,
        ssh_host=data["ssh_host"],
        ssh_port=data["ssh_port"],
        ssh_user=data["ssh_user"],
        ssh_password_enc=encrypt(data["ssh_password"]),
        wg_port=data["wg_port"],
        active=True,
    )
    async with async_session() as session:
        session.add(server)
        await session.commit()

    await state.clear()
    await progress_message.answer(
        f"Нода {server.flag} {server.name} успешно установлена и добавлена в систему.",
        reply_markup=admin_back_menu("admin:servers"),
    )


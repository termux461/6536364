from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select

from bot.db.base import async_session
from bot.keyboards.admin import admin_back_menu, admin_keys_list_menu, admin_keys_menu
from bot.models.server import Server
from bot.services.node_manager import node_manager
from bot.utils.helpers import admin_filter

router = Router(name="admin_keys")
router.callback_query.filter(admin_filter)


@router.callback_query(F.data == "admin:keys")
async def cb_admin_keys(callback: CallbackQuery) -> None:
    async with async_session() as session:
        result = await session.execute(select(Server).where(Server.active.is_(True)))
        servers = list(result.scalars().all())
    if not servers:
        await callback.message.edit_text("Нет добавленных серверов.", reply_markup=admin_back_menu())
        await callback.answer()
        return
    await callback.message.edit_text("Выберите сервер:", reply_markup=admin_keys_menu(servers))
    await callback.answer()


@router.callback_query(F.data.startswith("admin:keys:cleanup:"))
async def cb_admin_keys_cleanup(callback: CallbackQuery) -> None:
    server_id = int(callback.data.split(":")[3])
    async with async_session() as session:
        server = await session.get(Server, server_id)
    if server is None:
        await callback.answer("Сервер не найден", show_alert=True)
        return
    try:
        peers = await node_manager.list_peers(server)
    except Exception as exc:
        await callback.answer(f"Ошибка: {exc}", show_alert=True)
        return

    removed = 0
    for peer in peers:
        if not peer.get("enabled", True) or peer.get("expired"):
            try:
                await node_manager.delete_peer(server, str(peer.get("id")))
                removed += 1
            except Exception:
                pass
    await callback.answer(f"Удалено истекших ключей: {removed}", show_alert=True)


@router.callback_query(F.data.startswith("admin:keys:"))
async def cb_admin_keys_list(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    server_id, offset = int(parts[2]), int(parts[3])

    async with async_session() as session:
        server = await session.get(Server, server_id)
    if server is None:
        await callback.answer("Сервер не найден", show_alert=True)
        return

    try:
        peers = await node_manager.list_peers(server)
    except Exception as exc:
        await callback.message.edit_text(f"Не удалось получить список ключей: {exc}", reply_markup=admin_back_menu())
        await callback.answer()
        return

    text = f"Ключи на ноде {server.flag} {server.name}: {len(peers)}"
    await callback.message.edit_text(text, reply_markup=admin_keys_list_menu(server_id, peers, offset))
    await callback.answer()

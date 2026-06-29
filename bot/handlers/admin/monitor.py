from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select

from bot.db.base import async_session
from bot.keyboards.admin import admin_back_menu
from bot.models.server import Server
from bot.services.monitoring import fetch_metrics
from bot.utils.helpers import admin_filter

router = Router(name="admin_monitor")
router.callback_query.filter(admin_filter)


@router.callback_query(F.data == "admin:monitor")
async def cb_admin_monitor(callback: CallbackQuery) -> None:
    async with async_session() as session:
        result = await session.execute(select(Server).where(Server.active.is_(True)))
        servers = list(result.scalars().all())

    if not servers:
        await callback.message.edit_text("Нет добавленных серверов.", reply_markup=admin_back_menu())
        await callback.answer()
        return

    await callback.message.edit_text("Собираю метрики с нод...")

    lines = ["Мониторинг нод:\n"]
    for server in servers:
        try:
            metrics = await fetch_metrics(server)
            lines.append(
                f"{server.flag} {server.name}: CPU load {metrics['load1']:.2f}, "
                f"RAM {metrics['mem_used_percent']:.0f}%, Uptime {metrics['uptime_days']:.1f} дн."
            )
        except Exception:
            lines.append(f"{server.flag} {server.name}: недоступен (node-exporter не отвечает)")

    await callback.message.edit_text("\n".join(lines), reply_markup=admin_back_menu())
    await callback.answer()

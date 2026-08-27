from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.admin.filters import IsAdmin
from app.bot.states import AdminStates
from app.core.crypto import mask, secret_box
from app.models.enums import DeploymentStatus, OrderStatus
from app.repositories import (
    AuditRepository,
    DeploymentRepository,
    InfraRepository,
    OrderRepository,
    UserRepository,
)
from app.services.deployment.context import ssh_credentials_for
from app.services.deployment.node_installer import NodeInstaller
from app.services.deployment.steps import INSTALL_REMNANODE
from app.services.queue import JobQueue
from app.services.ssh import SSHClient

router = Router(name="admin_orders")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

FILTERS: dict[str, list[str] | None] = {
    "all": None,
    "waiting": [OrderStatus.WAITING_PAYMENT],
    "paid": [OrderStatus.PAID],
    "deploying": [
        OrderStatus.DEPLOYING,
        OrderStatus.CONFIGURING_ORIGIN,
        OrderStatus.CONFIGURING_REMNAWAVE,
        OrderStatus.CONFIGURING_YANDEX,
        OrderStatus.CONFIGURING_DNS,
        OrderStatus.CHECKING,
    ],
    "completed": [OrderStatus.COMPLETED],
    "waiting_data": [OrderStatus.COLLECTING_DATA],
    "failed": [OrderStatus.FAILED],
    "cancelled": [OrderStatus.CANCELLED],
}
PAGE = 8


def _filter_keyboard(current: str, page: int) -> InlineKeyboardMarkup:
    labels = {
        "all": "Все", "waiting": "Ожидают оплаты", "paid": "Оплачены",
        "deploying": "Деплой", "waiting_data": "Ждут данных",
        "completed": "Готовы", "failed": "Ошибки", "cancelled": "Отменены",
    }
    rows = [
        [
            InlineKeyboardButton(
                text=("• " if key == current else "") + label, callback_data=f"adm:orders:{key}:0"
            )
        ]
        for key, label in labels.items()
    ]
    rows.append(
        [
            InlineKeyboardButton(text="⬅️", callback_data=f"adm:orders:{current}:{max(page - 1, 0)}"),
            InlineKeyboardButton(text="➡️", callback_data=f"adm:orders:{current}:{page + 1}"),
        ]
    )
    rows.append([InlineKeyboardButton(text="⬅️ Меню", callback_data="adm:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("adm:orders:"))
async def list_orders(callback: CallbackQuery, session: AsyncSession) -> None:
    _, _, key, page_raw = callback.data.split(":")
    page = int(page_raw)
    orders = await OrderRepository(session).list_by_status(
        FILTERS.get(key), offset=page * PAGE, limit=PAGE
    )
    users = UserRepository(session)

    if not orders:
        await callback.message.edit_text(
            "📦 Заказов в этой выборке нет.", reply_markup=_filter_keyboard(key, page)
        )
        await callback.answer()
        return

    lines = []
    for order in orders:
        user = await users.get(order.user_id)
        lines.append(
            f"<b>#{order.id}</b> · {order.status} · {order.amount_display} · "
            f"{user.display_name if user else '—'} · {order.created_at:%d.%m %H:%M}"
        )
    await callback.message.edit_text(
        "📦 <b>Заказы</b>\n\n" + "\n".join(lines) + "\n\nОткрыть: /order &lt;id&gt;",
        reply_markup=_filter_keyboard(key, page),
    )
    await callback.answer()


@router.message(F.text.regexp(r"^/order\s+(\d+)$").as_("match"))
async def order_card(message, session: AsyncSession, match) -> None:
    order_id = int(match.group(1))
    order = await OrderRepository(session).get(order_id)
    if order is None:
        await message.answer("Заказ не найден.")
        return

    user = await UserRepository(session).get(order.user_id)
    infra = InfraRepository(session)
    origin = await infra.origin(order_id)
    yandex = await infra.yandex(order_id)
    remnawave = await infra.remnawave(order_id)
    resources = await infra.resources(order_id)
    deployment = await DeploymentRepository(session).get_by_order(order_id)

    lines = [
        f"<b>Заказ #{order.id}</b>",
        f"User: {user.display_name if user else '—'} (<code>{user.telegram_id if user else '—'}</code>)",
        f"Статус: <code>{order.status}</code>",
        f"Сумма: {order.amount_display}" + (" 🧪 тестовый, без оплаты" if not order.amount else ""),
        f"Создан: {order.created_at:%d.%m.%Y %H:%M}",
    ]
    if origin:
        lines += [
            "",
            f"Origin IP: <code>{origin.origin_ip or '—'}</code>",
            f"Origin Domain: <code>{origin.origin_domain or '—'}</code>",
            f"CDN Domain: <code>{origin.cdn_domain or '—'}</code>",
            f"Origin Status: {origin.origin_status}",
        ]
    if remnawave:
        lines += [
            "",
            f"Панель: <code>{remnawave.panel_url or '—'}</code>",
            f"API панели: <code>{remnawave.api_version}</code>",
        ]
    if resources:
        lines += [
            "",
            f"Profile: <code>{resources.profile_uuid or '—'}</code>",
            f"Node: <code>{resources.node_uuid or '—'}</code>",
            f"Host: <code>{resources.host_uuid or '—'}</code>",
            f"SECRET_KEY: {mask(secret_box().decrypt(resources.node_secret_enc))}",
        ]
    if yandex:
        lines += [
            "",
            f"Yandex auth: <code>{yandex.auth_type}</code>",
            f"Certificate: <code>{yandex.certificate_id or '—'}</code> ({yandex.certificate_status or '—'})",
            f"CDN resource: <code>{yandex.cdn_resource_id or '—'}</code>",
            f"CDN CNAME: <code>{yandex.cdn_cname or '—'}</code>",
        ]
    if deployment:
        lines += [
            "",
            f"Deployment: <code>{deployment.status}</code> · "
            f"шаг <code>{deployment.current_step or '—'}</code>",
        ]
        if deployment.last_error:
            lines.append(f"Ошибка: <code>{deployment.last_error[:600]}</code>")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="▶️ Continue", callback_data=f"adm:ord:continue:{order_id}"),
                InlineKeyboardButton(text="🔄 Retry", callback_data=f"adm:ord:retry:{order_id}"),
            ],
            [InlineKeyboardButton(text="🛑 Stop", callback_data=f"adm:ord:stop:{order_id}")],
            [
                InlineKeyboardButton(text="🔑 SECRET_KEY", callback_data=f"adm:node:secret:{order_id}"),
                InlineKeyboardButton(text="🩺 Нода", callback_data=f"adm:node:diag:{order_id}"),
            ],
            [
                InlineKeyboardButton(
                    text="♻️ Переустановить ноду", callback_data=f"adm:node:reinstall:{order_id}"
                )
            ],
        ]
    )
    await message.answer("\n".join(lines), reply_markup=keyboard)


@router.callback_query(F.data.startswith("adm:ord:"))
async def order_action(callback: CallbackQuery, session: AsyncSession) -> None:
    _, _, action, raw_id = callback.data.split(":")
    order_id = int(raw_id)
    orders = OrderRepository(session)
    deployments = DeploymentRepository(session)
    order = await orders.get(order_id)
    deployment = await deployments.get_by_order(order_id)
    if order is None:
        await callback.answer("Заказ не найден", show_alert=True)
        return

    if action == "stop":
        if deployment:
            await deployments.set_status(deployment, DeploymentStatus.STOPPED)
        await orders.set_status(order, OrderStatus.FAILED, error="Остановлено администратором")
        await AuditRepository(session).log(
            "deployment.stopped", admin_id=callback.from_user.id, order_id=order_id
        )
        await session.commit()
        await callback.answer("Остановлено", show_alert=True)
        return

    if action == "retry" and deployment:
        # Retry re-runs the failed step; completed steps stay completed.
        failed = [step for step in await deployments.steps(deployment.id) if step.status == "failed"]
        for step in failed:
            step.status = "pending"
            step.error = None
        await session.flush()

    await orders.set_status(order, OrderStatus.DEPLOYING, error="")
    await AuditRepository(session).log(
        f"deployment.{action}", admin_id=callback.from_user.id, order_id=order_id
    )
    await session.commit()

    queue = JobQueue.from_settings()
    try:
        await queue.enqueue_deployment(order_id, reason=f"admin_{action}")
    finally:
        await queue.close()
    await callback.answer("Поставлено в очередь", show_alert=True)


# --------------------------------------------------------------- node actions


@router.callback_query(F.data.startswith("adm:node:"))
async def node_action(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    _, _, action, raw_id = callback.data.split(":")
    order_id = int(raw_id)
    infra = InfraRepository(session)

    if action == "secret":
        await state.set_state(AdminStates.node_secret)
        await state.update_data(node_secret_order=order_id)
        await callback.message.answer(
            f"Пришлите SECRET_KEY для Remnawave Node заказа #{order_id}.\n"
            "Скопируйте его из карточки ноды в панели. Сообщение будет удалено."
        )
        await callback.answer()
        return

    origin = await infra.origin(order_id)
    if origin is None or not origin.origin_ip:
        await callback.answer("Нет данных Origin Server", show_alert=True)
        return

    if action == "reinstall":
        # The worker owns the SSH session, so a reinstall is a queued job, not an inline command.
        deployments = DeploymentRepository(session)
        deployment = await deployments.get_by_order(order_id)
        if deployment is None:
            await callback.answer("Деплой ещё не создан", show_alert=True)
            return
        step = await deployments.get_step(deployment.id, INSTALL_REMNANODE)
        if step is not None:
            step.status = "pending"
            step.error = None
        await deployments.set_status(deployment, DeploymentStatus.QUEUED)
        await AuditRepository(session).log(
            "node.reinstall", admin_id=callback.from_user.id, order_id=order_id
        )
        await session.commit()

        queue = JobQueue.from_settings()
        try:
            await queue.enqueue_deployment(order_id, reason="admin_node_reinstall")
        finally:
            await queue.close()
        await callback.answer("Переустановка поставлена в очередь", show_alert=True)
        return

    if action == "diag":
        resources = await infra.resources(order_id)
        secret = secret_box().decrypt(resources.node_secret_enc if resources else None) or "—"
        await callback.answer("Подключаюсь к Origin Server…")
        try:
            async with SSHClient(ssh_credentials_for(origin)) as ssh:
                data = await NodeInstaller(ssh, secret=secret).diagnostics()
        except Exception as exc:  # noqa: BLE001 — shown to an admin, full trace stays in the logs
            await callback.message.answer(f"Диагностика не удалась: <code>{exc}</code>")
            return

        logs = (data.pop("logs_tail", "") or "").strip()[-1200:]
        lines = [f"🩺 <b>Нода заказа #{order_id}</b>"]
        lines += [f"{key}: <code>{value}</code>" for key, value in data.items()]
        if logs:
            lines += ["", "<b>Последние строки лога:</b>", f"<pre>{logs}</pre>"]
        await callback.message.answer("\n".join(lines))
        return

    await callback.answer()


@router.message(AdminStates.node_secret)
async def save_node_secret(message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    order_id = int(data.get("node_secret_order") or 0)
    secret = (message.text or "").strip()
    await state.clear()

    try:
        await message.delete()
    except Exception:  # noqa: BLE001 — a message we cannot delete is not worth failing on
        pass

    if not order_id or not secret:
        await message.answer("Пустое значение, ничего не сохранено.")
        return

    resources = await InfraRepository(session).resources_or_create(order_id)
    resources.node_secret_enc = secret_box().encrypt(secret)
    await AuditRepository(session).log(
        "node.secret_set", admin_id=message.from_user.id, order_id=order_id
    )
    await session.commit()
    await message.answer(
        f"SECRET_KEY для заказа #{order_id} сохранён ({mask(secret)}).\n"
        "Нажмите «♻️ Переустановить ноду», чтобы применить."
    )

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.keyboards import order_actions_keyboard
from app.config import get_settings
from app.models import User
from app.models.enums import OrderStatus
from app.repositories import DeploymentRepository, InfraRepository, OrderRepository
from app.services.queue import JobQueue

router = Router(name="orders")

STATUS_LABELS = {
    OrderStatus.CREATED: "🆕 создан",
    OrderStatus.WAITING_PAYMENT: "⏳ ожидает оплаты",
    OrderStatus.PAID: "💰 оплачен",
    OrderStatus.COLLECTING_DATA: "📝 сбор данных",
    OrderStatus.DEPLOYING: "🚀 настройка",
    OrderStatus.CONFIGURING_ORIGIN: "🖥 настройка Origin Server",
    OrderStatus.CONFIGURING_REMNAWAVE: "📡 настройка Remnawave",
    OrderStatus.CONFIGURING_YANDEX: "☁️ настройка Yandex",
    OrderStatus.CONFIGURING_DNS: "🌐 настройка DNS",
    OrderStatus.CHECKING: "🧪 проверка",
    OrderStatus.COMPLETED: "✅ завершён",
    OrderStatus.FAILED: "❌ ошибка",
    OrderStatus.CANCELLED: "✖️ отменён",
    OrderStatus.REFUNDED: "↩️ возврат",
}


@router.message(F.text == "📋 Мои заказы")
async def my_orders(message: Message, session: AsyncSession, user: User) -> None:
    orders = await OrderRepository(session).list_for_user(user.id)
    if not orders:
        await message.answer(texts.NO_ORDERS)
        return

    infra = InfraRepository(session)
    settings = get_settings()
    for order in orders:
        origin = await infra.origin(order.id)
        lines = [
            f"<b>Заказ #{order.id}</b>",
            f"Статус: {STATUS_LABELS.get(OrderStatus(order.status), order.status)}",
            f"Сумма: {order.amount_display}",
        ]
        if origin and origin.cdn_domain:
            lines.append(f"CDN: <code>{origin.cdn_domain}</code>")
        if origin and origin.origin_domain:
            lines.append(f"Origin: <code>{origin.origin_domain}</code>")
        await message.answer(
            "\n".join(lines),
            reply_markup=order_actions_keyboard(
                order.id,
                failed=order.status == OrderStatus.FAILED,
                support=settings.support_username,
            ),
        )


@router.callback_query(F.data.startswith("order:retry:"))
async def retry_order(callback: CallbackQuery, session: AsyncSession, user: User) -> None:
    order_id = int(callback.data.split(":")[2])
    order = await OrderRepository(session).get(order_id)
    if order is None or order.user_id != user.id:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    if order.status not in (OrderStatus.FAILED, OrderStatus.DEPLOYING):
        await callback.answer("Этот заказ нельзя продолжить", show_alert=True)
        return

    deployment = await DeploymentRepository(session).get_by_order(order_id)
    if deployment is None:
        await callback.answer("Нет данных о развёртывании", show_alert=True)
        return

    await OrderRepository(session).set_status(order, OrderStatus.DEPLOYING, error="")
    await session.commit()

    queue = JobQueue.from_settings()
    try:
        await queue.enqueue_deployment(order_id, reason="user_retry")
    finally:
        await queue.close()
    await callback.answer("Продолжаю с последнего успешного шага", show_alert=True)

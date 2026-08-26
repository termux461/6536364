from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.admin.filters import IsAdmin
from app.bot.handlers.admin.keyboards import admin_menu, back_button
from app.models.enums import DeploymentStatus, OrderStatus
from app.repositories import (
    AuditRepository,
    DeploymentRepository,
    OrderRepository,
    PaymentRepository,
    UserRepository,
)

router = Router(name="admin_stats")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

PERIODS = {0: ("Сегодня", 1), 1: ("7 дней", 7), 2: ("30 дней", 30), 3: ("За всё время", None)}


@router.message(Command("admin"))
async def admin_entry(message: Message) -> None:
    await message.answer("⚙️ <b>Админ-панель</b>", reply_markup=admin_menu())


@router.callback_query(F.data == "adm:menu")
async def menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text("⚙️ <b>Админ-панель</b>", reply_markup=admin_menu())
    await callback.answer()


def _money(value: int) -> str:
    return f"{value // 100:,}".replace(",", " ") + " ₽"


@router.callback_query(F.data.startswith("adm:stats:"))
async def stats(callback: CallbackQuery, session: AsyncSession) -> None:
    index = int(callback.data.split(":")[2]) % len(PERIODS)
    label, days = PERIODS[index]
    since = OrderRepository.period_start(days)

    users = await UserRepository(session).count()
    orders = await OrderRepository(session).counters(since)
    payments = await PaymentRepository(session).stats(since)
    deployments = await DeploymentRepository(session).counters(since)

    text = (
        f"📊 <b>Статистика — {label}</b>\n\n"
        f"👥 Пользователи: {users}\n"
        f"📦 Заказы: {orders.get('total', 0)}\n"
        f"💰 Выручка: {_money(payments.get('revenue', 0))}\n"
        f"💳 Успешные платежи: {payments.get('paid', 0)}\n"
        f"❌ Ошибочные платежи: {payments.get('failed', 0)}\n"
        f"🚀 Успешные deployment: {deployments.get(DeploymentStatus.COMPLETED, 0)}\n"
        f"⚠️ Failed deployment: {deployments.get(DeploymentStatus.FAILED, 0)}\n"
        f"✅ Завершённых заказов: {orders.get(OrderStatus.COMPLETED, 0)}"
    )
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔁 Период", callback_data=f"adm:stats:{index + 1}")],
            [InlineKeyboardButton(text="⬅️ Меню", callback_data="adm:menu")],
        ]
    )
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "adm:logs")
async def logs(callback: CallbackQuery, session: AsyncSession) -> None:
    entries = await AuditRepository(session).recent(20)
    if not entries:
        await callback.message.edit_text("Логи пусты.", reply_markup=back_button())
        await callback.answer()
        return
    lines = [
        f"<code>{entry.created_at:%d.%m %H:%M}</code> {entry.action} "
        f"[{entry.status}]{f' #{entry.order_id}' if entry.order_id else ''}"
        for entry in entries
    ]
    await callback.message.edit_text(
        "📋 <b>Последние события</b>\n\n" + "\n".join(lines), reply_markup=back_button()
    )
    await callback.answer()

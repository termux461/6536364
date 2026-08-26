"""Progress and result messages, edited in place instead of spamming the chat."""
from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from app.config import get_settings
from app.database import session_scope
from app.repositories import DeploymentRepository, InfraRepository, OrderRepository, UserRepository
from app.services.deployment import progress
from app.services.remnawave.templates import XHTTP_PATH

logger = logging.getLogger(__name__)


async def _edit(bot: Bot, chat_id: int | None, message_id: int | None, text: str, markup=None) -> None:
    if not chat_id or not message_id:
        return
    try:
        await bot.edit_message_text(
            chat_id=chat_id, message_id=message_id, text=text, reply_markup=markup
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            logger.warning("Could not edit progress message: %s", exc)


async def ensure_progress_message(bot: Bot, order_id: int, chat_id: int) -> None:
    async with session_scope() as session:
        orders = OrderRepository(session)
        order = await orders.get(order_id)
        if order is None or order.progress_message_id:
            return
        message = await bot.send_message(chat_id, progress.render(order_id, {}))
        order.progress_chat_id = chat_id
        order.progress_message_id = message.message_id


async def refresh_progress_message(bot: Bot, order_id: int) -> None:
    async with session_scope() as session:
        order = await OrderRepository(session).get(order_id)
        if order is None:
            return
        deployment = await DeploymentRepository(session).get_by_order(order_id)
        statuses = {}
        if deployment is not None:
            statuses = {
                step.step: step.status for step in await DeploymentRepository(session).steps(deployment.id)
            }
        text = progress.render(order_id, statuses)
    await _edit(bot, order.progress_chat_id, order.progress_message_id, text)


async def notify_success(bot: Bot, order_id: int) -> None:
    async with session_scope() as session:
        order = await OrderRepository(session).get(order_id)
        if order is None:
            return
        infra = InfraRepository(session)
        origin = await infra.origin(order_id)
        deployment = await DeploymentRepository(session).get_by_order(order_id)
        user = await UserRepository(session).get(order.user_id)

    health = (deployment.context or {}).get("health", {}) if deployment else {}
    cdn_domain = (origin.cdn_domain if origin else "") or ""
    text = progress.render_success(
        order_id=order_id,
        origin_domain=(origin.origin_domain if origin else "") or "",
        cdn_domain=cdn_domain,
        xhttp_url=f"https://{cdn_domain}{XHTTP_PATH}",
        health_passed=str(health.get("cdn")) == "200",
    )
    if user:
        await bot.send_message(user.telegram_id, text)


async def notify_failure(bot: Bot, order_id: int) -> None:
    from app.bot.keyboards import order_actions_keyboard

    settings = get_settings()
    async with session_scope() as session:
        order = await OrderRepository(session).get(order_id)
        if order is None:
            return
        deployment = await DeploymentRepository(session).get_by_order(order_id)
        user = await UserRepository(session).get(order.user_id)

    step = deployment.current_step if deployment else "—"
    # The user sees a short reason; the full traceback stays in the logs and audit table.
    reason = (deployment.last_error or "неизвестная ошибка") if deployment else "неизвестная ошибка"
    text = progress.render_failure(order_id=order_id, step=step or "—", message=reason[:400])
    if user:
        await bot.send_message(
            user.telegram_id,
            text,
            reply_markup=order_actions_keyboard(
                order_id, failed=True, support=settings.support_username
            ),
        )


async def notify_waiting_dns(bot: Bot, order_id: int, *, record_type: str, name: str, value: str) -> None:
    from app.bot import texts
    from app.bot.keyboards import dns_check_keyboard

    async with session_scope() as session:
        order = await OrderRepository(session).get(order_id)
        if order is None:
            return
        user = await UserRepository(session).get(order.user_id)
    if user:
        await bot.send_message(
            user.telegram_id,
            texts.MANUAL_DNS.format(record_type=record_type, name=name, value=value),
            reply_markup=dns_check_keyboard(order_id),
        )


async def notify_reauth_needed(bot: Bot, order_id: int) -> None:
    """Ask the customer for fresh Yandex credentials without failing the order."""
    from app.bot import texts

    async with session_scope() as session:
        order = await OrderRepository(session).get(order_id)
        if order is None:
            return
        user = await UserRepository(session).get(order.user_id)
    if user is None:
        return
    try:
        await bot.send_message(
            user.telegram_id, texts.YANDEX_REAUTH_NEEDED.format(order_id=order_id)
        )
    except Exception:  # noqa: BLE001
        logger.warning("Could not notify user about reauth for order %s", order_id)

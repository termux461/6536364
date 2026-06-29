from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.i18n import t
from config import settings

ALLOWED_CALLBACK_PREFIX = "check_sub"


class ForceSubscriptionMiddleware(BaseMiddleware):
    """Blocks bot usage until the user joins the configured channel."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not settings.SUBSCRIBE_CHANNEL_ID or data.get("is_admin"):
            return await handler(event, data)

        if isinstance(event, CallbackQuery) and event.data and event.data.startswith(ALLOWED_CALLBACK_PREFIX):
            return await handler(event, data)

        tg_user = data.get("event_from_user")
        bot = data.get("bot")
        locale = data.get("locale", "ru")
        if tg_user is None or bot is None:
            return await handler(event, data)

        try:
            member = await bot.get_chat_member(settings.SUBSCRIBE_CHANNEL_ID, tg_user.id)
            is_subscribed = member.status not in ("left", "kicked")
        except TelegramBadRequest:
            is_subscribed = True  # fail-open if channel misconfigured

        if is_subscribed:
            return await handler(event, data)

        from bot.keyboards.common import subscribe_keyboard

        text = t(locale, "subscribe.required")
        if isinstance(event, Message):
            await event.answer(text, reply_markup=subscribe_keyboard(locale))
        elif isinstance(event, CallbackQuery) and event.message:
            await event.message.answer(text, reply_markup=subscribe_keyboard(locale))
        return None

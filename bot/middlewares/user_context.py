from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.services.referral import get_or_create_user
from config import settings


class UserContextMiddleware(BaseMiddleware):
    """Loads/creates the User row and exposes it (+ locale) to handlers."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        session = data.get("session")
        if tg_user is None or session is None:
            return await handler(event, data)

        user = await get_or_create_user(
            session,
            tg_id=tg_user.id,
            username=tg_user.username,
            full_name=tg_user.full_name,
            locale=tg_user.language_code if tg_user.language_code in ("ru", "en") else settings.DEFAULT_LOCALE,
        )
        data["user"] = user
        data["locale"] = user.locale
        data["is_admin"] = tg_user.id in settings.admin_ids
        return await handler(event, data)

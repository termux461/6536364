from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from aiogram.types import User as TgUser

from app.bot import texts
from app.config import get_settings
from app.repositories import UserRepository


class UserMiddleware(BaseMiddleware):
    """Upserts the Telegram user, injects `user` and `is_admin`, and stops blocked users."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)

        session = data["session"]
        repo = UserRepository(session)
        user = await repo.upsert(
            tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
            language_code=tg_user.language_code,
        )
        data["user"] = user
        data["is_admin"] = get_settings().is_admin(tg_user.id)

        if user.is_blocked and not data["is_admin"]:
            update = event if isinstance(event, Update) else None
            target = None
            if update is not None:
                target = update.message or (
                    update.callback_query.message if update.callback_query else None
                )
            if target is not None:
                await target.answer(texts.BLOCKED)
            return None

        return await handler(event, data)

import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update


class AntiFloodMiddleware(BaseMiddleware):
    def __init__(self, min_interval: float = 0.6):
        self.min_interval = min_interval
        self._last_seen: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is not None:
            now = time.monotonic()
            last = self._last_seen.get(user.id, 0)
            if now - last < self.min_interval:
                if isinstance(event, Update) and event.message:
                    return
            self._last_seen[user.id] = now
        return await handler(event, data)

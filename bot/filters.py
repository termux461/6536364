from aiogram.filters import BaseFilter
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.menu_router import resolve_action


class MenuAction(BaseFilter):
    """True when the pressed reply-keyboard button resolves to the given action."""

    def __init__(self, action: str):
        self.action = action

    async def __call__(self, message: Message, session: AsyncSession) -> bool:
        if not message.text:
            return False
        return await resolve_action(session, message.text) == self.action

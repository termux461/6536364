from aiogram import Dispatcher

from app.bot.middlewares.database import DatabaseMiddleware
from app.bot.middlewares.user import UserMiddleware


def register_middlewares(dp: Dispatcher) -> None:
    dp.update.middleware(DatabaseMiddleware())
    dp.update.middleware(UserMiddleware())


__all__ = ["DatabaseMiddleware", "UserMiddleware", "register_middlewares"]

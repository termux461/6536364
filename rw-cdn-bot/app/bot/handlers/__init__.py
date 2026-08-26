from aiogram import Dispatcher

from app.bot.handlers import collect, orders, payment, purchase, start, support
from app.bot.handlers.admin import router as admin_router


def register_handlers(dp: Dispatcher) -> None:
    dp.include_router(admin_router)
    dp.include_router(collect.commands_router)
    dp.include_router(start.router)
    dp.include_router(purchase.router)
    dp.include_router(payment.router)
    dp.include_router(collect.router)
    dp.include_router(orders.router)
    dp.include_router(support.router)

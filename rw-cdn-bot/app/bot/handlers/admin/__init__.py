from aiogram import Router

from app.bot.handlers.admin import broadcast, maintenance, orders, prices, stats, testorder, users

router = Router(name="admin")
# Registered first: a bare command must not be swallowed by a running FSM state.
router.include_router(testorder.router)
router.include_router(stats.router)
router.include_router(prices.router)
router.include_router(maintenance.router)
router.include_router(orders.router)
router.include_router(users.router)
router.include_router(broadcast.router)

__all__ = ["router"]

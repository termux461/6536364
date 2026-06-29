from aiogram import Router

from bot.handlers.admin.broadcast import router as broadcast_router
from bot.handlers.admin.entry import router as entry_router
from bot.handlers.admin.hosts import router as hosts_router
from bot.handlers.admin.menu_builder import router as menu_router
from bot.handlers.admin.payments import router as payments_router
from bot.handlers.admin.stats import router as stats_router
from bot.handlers.admin.tariffs import router as tariffs_router
from bot.handlers.admin.tickets import router as tickets_router

router = Router(name="admin")
router.include_router(entry_router)
router.include_router(hosts_router)
router.include_router(tariffs_router)
router.include_router(payments_router)
router.include_router(tickets_router)
router.include_router(broadcast_router)
router.include_router(stats_router)
router.include_router(menu_router)

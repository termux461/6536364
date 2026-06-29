from bot.config import settings


def is_admin(tg_id: int) -> bool:
    return tg_id in settings.admin_ids

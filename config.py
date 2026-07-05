import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class Config:
    BOT_TOKEN: str    = field(default_factory=lambda: os.environ["BOT_TOKEN"])
    ADMIN_IDS: List[int] = field(default_factory=lambda: [
        int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()
    ])

    # Platega
    PLATEGA_SHOP_ID: str = field(default_factory=lambda: os.environ["PLATEGA_SHOP_ID"])
    PLATEGA_SECRET: str  = field(default_factory=lambda: os.environ["PLATEGA_SECRET"])

    # wg-easy — WireGuard (основной)
    WG_EASY_URL: str      = field(default_factory=lambda: os.environ["WG_EASY_URL"])
    WG_EASY_PASSWORD: str = field(default_factory=lambda: os.environ["WG_EASY_PASSWORD"])

    # wg-easy — AmneziaWG (опционально, отдельный инстанс)
    # Если не задан — используется тот же WG_EASY_URL
    WG_EASY_URL_AWG: str  = field(default_factory=lambda: os.getenv("WG_EASY_URL_AWG", ""))
    WG_EASY_PASS_AWG: str = field(default_factory=lambda: os.getenv("WG_EASY_PASS_AWG", ""))

    REFERRAL_BONUS: int   = field(default_factory=lambda: int(os.getenv("REFERRAL_BONUS", "30")))
    DB_PATH: str          = field(default_factory=lambda: os.getenv("DB_PATH", "bot.db"))
    WEBHOOK_PORT: int     = field(default_factory=lambda: int(os.getenv("WEBHOOK_PORT", "8080")))
    BOT_USERNAME: str     = field(default_factory=lambda: os.getenv("BOT_USERNAME", "your_bot"))

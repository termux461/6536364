from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    BOT_TOKEN: str = ""
    BOT_NAME: str = "МАМОНТ ВПН"

    ADMIN_IDS: str = ""

    DATABASE_URL: str = "sqlite+aiosqlite:///mammot_vpn.db"

    SUPPORT_USERNAME: str = "support"

    PRICE_1M: int = 149
    PRICE_3M: int = 399
    PRICE_6M: int = 699
    PRICE_1Y: int = 1199

    REFERRAL_PERCENT: int = 20

    @property
    def admin_ids(self) -> set[int]:
        return {int(x) for x in self.ADMIN_IDS.split(",") if x.strip()}


settings = Settings()

PLANS = {
    "1m": {"title": "1 месяц", "price": settings.PRICE_1M, "days": 30},
    "3m": {"title": "3 месяца", "price": settings.PRICE_3M, "days": 90},
    "6m": {"title": "6 месяцев", "price": settings.PRICE_6M, "days": 180},
    "1y": {"title": "1 год", "price": settings.PRICE_1Y, "days": 365},
}

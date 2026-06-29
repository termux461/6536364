from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    BOT_TOKEN: str = ""
    BOT_NAME: str = "МАМОНТ ВПН"

    ADMIN_IDS: str = ""

    # === БД И REDIS ===
    DB_HOST: str = "db"
    DB_PORT: int = 5432
    DB_NAME: str = "mammot_vpn"
    DB_USER: str = "mammot"
    DB_PASSWORD: str = "secret"
    REDIS_URL: str = "redis://redis:6379/0"

    SUPPORT_USERNAME: str = "support"

    # === ВЕБХУКИ ===
    WEBHOOK_BASE_URL: str = ""
    WEBHOOK_SECRET: str = "secret_string_for_webhook_security"
    WEBHOOK_HOST: str = "0.0.0.0"
    WEBHOOK_PORT: int = 8080

    # === ПЛАТЕЖИ ===
    PAYMENT_PLATEGA_ENABLED: bool = False
    PAYMENT_YOOKASSA_ENABLED: bool = False
    PAYMENT_CRYPTOBOT_ENABLED: bool = False

    PLATEGA_API_KEY: str = ""
    PLATEGA_SHOP_ID: str = ""
    YOOKASSA_SHOP_ID: str = ""
    YOOKASSA_SECRET_KEY: str = ""
    CRYPTOBOT_TOKEN: str = ""

    # === ЦЕНЫ (RUB) ===
    PRICE_1M: int = 149
    PRICE_3M: int = 399
    PRICE_6M: int = 699
    PRICE_1Y: int = 1199
    PRICE_FAMILY_3: int = 299
    PRICE_FAMILY_5: int = 449

    # === РЕФЕРАЛЬНАЯ СИСТЕМА ===
    REFERRAL_PERCENT: int = 20

    # === БЕЗОПАСНОСТЬ ===
    FERNET_KEY: str = ""

    # === БЭКАПЫ ===
    BACKUP_DIR: str = "/app/backups"
    BACKUP_KEEP_DAYS: int = 7
    BACKUP_CHAT_ID: str = ""

    @property
    def admin_ids(self) -> set[int]:
        return {int(x) for x in self.ADMIN_IDS.split(",") if x.strip()}

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def sync_database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


settings = Settings()

PLANS = {
    "1m": {"title": "1 месяц", "price": settings.PRICE_1M, "days": 30},
    "3m": {"title": "3 месяца", "price": settings.PRICE_3M, "days": 90},
    "6m": {"title": "6 месяцев", "price": settings.PRICE_6M, "days": 180},
    "1y": {"title": "1 год", "price": settings.PRICE_1Y, "days": 365},
    "fam3": {"title": "Семейный 3 устройства / мес", "price": settings.PRICE_FAMILY_3, "days": 30},
    "fam5": {"title": "Семейный 5 устройств / мес", "price": settings.PRICE_FAMILY_5, "days": 30},
}

PAYMENT_METHODS = {
    "platega": {"title": "Банковская карта", "enabled": settings.PAYMENT_PLATEGA_ENABLED},
    "yookassa": {"title": "ЮKassa", "enabled": settings.PAYMENT_YOOKASSA_ENABLED},
    "cryptobot": {"title": "Криптовалюта (CryptoBot)", "enabled": settings.PAYMENT_CRYPTOBOT_ENABLED},
    "balance": {"title": "Баланс", "enabled": True},
}

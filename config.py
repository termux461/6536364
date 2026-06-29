from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    BOT_TOKEN: str
    ADMIN_IDS: str = ""
    SUPPORT_CHAT_ID: str = ""

    WEBAPP_URL: str = "http://localhost:8001/webapp"
    PANEL_URL: str = "http://localhost:8002/panel"
    PUBLIC_BASE_URL: str = "http://localhost:8001"

    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"

    PANEL_SECRET_KEY: str = "dev-secret"
    PANEL_ADMIN_LOGIN: str = "admin"
    PANEL_ADMIN_PASSWORD: str = "admin"

    REMNAWAVE_API_URL: str = ""
    REMNAWAVE_API_TOKEN: str = ""

    YOOKASSA_SHOP_ID: str = ""
    YOOKASSA_SECRET_KEY: str = ""
    CRYPTOBOT_API_TOKEN: str = ""
    CRYPTOBOT_API_URL: str = "https://pay.crypt.bot/api"

    DEFAULT_LOCALE: str = "ru"
    REFERRAL_BONUS_PERCENT: float = 10
    REFERRAL_SIGNUP_BONUS: float = 0
    REFERRAL_MIN_WITHDRAW: float = 100
    SUBSCRIBE_CHANNEL_ID: str = ""
    LOG_LEVEL: str = "INFO"

    @property
    def admin_ids(self) -> set[int]:
        return {int(x) for x in self.ADMIN_IDS.split(",") if x.strip()}


settings = Settings()

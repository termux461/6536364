"""Application configuration. Everything comes from the environment, nothing is hardcoded."""
from __future__ import annotations

import logging
from functools import lru_cache
from urllib.parse import urlparse

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    # Telegram
    bot_token: str
    # Comma-separated in the environment. Declared as `str` on purpose: pydantic-settings
    # JSON-decodes list-typed fields inside the env source, before any validator runs, so a
    # plain `1,2` value would fail there and never reach a `mode="before"` splitter.
    admin_ids_raw: str = Field(default="", validation_alias="admin_ids")
    support_username: str = "support"

    # Infrastructure
    database_url: str
    redis_url: str

    # Webhook HTTP server
    # Public HTTPS base where /webhooks/* are reachable. This is what you paste into the
    # merchant dashboards; the app never sends it to the provider itself.
    webhook_base_url: str = ""
    # Domain Caddy issues a certificate for (docker-compose.caddy.yml). Must be the same host
    # as webhook_base_url, otherwise callbacks arrive at a name nothing is listening on.
    bot_public_domain: str = ""
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8080

    # Platega
    platega_api_key: str = ""
    platega_merchant_id: str = ""
    platega_webhook_secret: str = ""
    platega_api_url: str = "https://app.platega.io"

    # YooKassa
    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""
    yookassa_receipt_email: str = ""
    yookassa_allowed_ips_raw: str = Field(default="", validation_alias="yookassa_allowed_ips")

    # Remnawave defaults (per-order values always win)
    remnawave_default_url: str = ""
    remnawave_api_token: str = ""

    # Yandex Cloud defaults (per-order values always win)
    yandex_cloud_id: str = ""
    yandex_folder_id: str = ""
    yandex_service_account_key: str = ""
    # Cookie auth is not part of the published Yandex API — the exchange endpoint and the
    # JSON field holding the token are configuration, never hardcoded.
    yandex_cookie_exchange_url: str = ""
    yandex_cookie_token_field: str = "iamToken"
    # The exchange endpoint is discovered automatically; setting the URL above only pins it.
    yandex_cookie_auth_enabled: bool = True

    # Security
    secret_encryption_key: str

    # Deployment tuning
    deploy_max_attempts: int = 3
    deploy_retry_delays_raw: str = Field(default="5,15,30", validation_alias="deploy_retry_delays")
    ssh_timeout: int = 30
    ssh_command_timeout: int = 900
    dns_propagation_timeout: int = 1800
    certificate_wait_timeout: int = 3600
    log_level: str = "INFO"

    @staticmethod
    def _split(value: str) -> list[str]:
        """Accept `a,b,c`, `a, b, c`, a JSON array, or an empty value."""
        text = (value or "").strip()
        if not text:
            return []
        if text.startswith("[") and text.endswith("]"):
            text = text[1:-1]
        return [part.strip().strip("\"'") for part in text.split(",") if part.strip().strip("\"'")]

    @property
    def admin_ids(self) -> list[int]:
        ids: list[int] = []
        for part in self._split(self.admin_ids_raw):
            try:
                ids.append(int(part))
            except ValueError:
                logger.warning("ADMIN_IDS contains a non-numeric entry, ignoring: %r", part)
        return ids

    @property
    def yookassa_allowed_ips(self) -> list[str]:
        return self._split(self.yookassa_allowed_ips_raw)

    @property
    def deploy_retry_delays(self) -> list[int]:
        delays: list[int] = []
        for part in self._split(self.deploy_retry_delays_raw):
            try:
                delays.append(int(part))
            except ValueError:
                logger.warning("DEPLOY_RETRY_DELAYS contains a non-numeric entry: %r", part)
        return delays or [5, 15, 30]

    @property
    def platega_webhook_url(self) -> str:
        return f"{self.webhook_base_url.rstrip('/')}/webhooks/platega"

    @property
    def yookassa_webhook_url(self) -> str:
        return f"{self.webhook_base_url.rstrip('/')}/webhooks/yookassa"

    def webhook_domain_mismatch(self) -> str | None:
        """Return a description when the public domain and the webhook URL disagree.

        A silent mismatch here is nasty: everything starts fine, payments look normal, and
        callbacks simply never arrive — the order sits unpaid with no error anywhere.
        """
        if not self.webhook_base_url or not self.bot_public_domain:
            return None
        host = urlparse(self.webhook_base_url).hostname or ""
        expected = self.bot_public_domain.strip().lower()
        if host and expected and host.lower() != expected:
            return (
                f"WEBHOOK_BASE_URL указывает на {host}, а сертификат выпускается для "
                f"{expected} — колбэки платёжек не дойдут"
            )
        return None

    def is_admin(self, telegram_id: int) -> bool:
        return telegram_id in self.admin_ids


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

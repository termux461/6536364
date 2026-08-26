"""Everything one deployment run needs, assembled once and passed between steps."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.config import get_settings
from app.core.crypto import secret_box
from app.models import Deployment, Order, OriginServer, RemnawaveInstance, RemnawaveResource, YandexProject
from app.models.enums import SSHAuthType
from app.services.ssh import SSHCredentials
from app.services.yandex.auth import AUTH_SERVICE_ACCOUNT, YandexAuth, build_auth


def ssh_credentials_for(origin: OriginServer) -> SSHCredentials:
    """Build SSH credentials from a stored Origin Server row (secrets decrypted here only)."""
    box = secret_box()
    return SSHCredentials(
        host=(origin.origin_ip or "").strip(),
        port=origin.ssh_port,
        username=origin.ssh_username,
        private_key=box.decrypt(origin.ssh_private_key_enc)
        if origin.ssh_auth_type == SSHAuthType.KEY
        else None,
        passphrase=box.decrypt(origin.ssh_passphrase_enc),
        password=box.decrypt(origin.ssh_password_enc),
    )


@dataclass(slots=True)
class DeployContext:
    order: Order
    deployment: Deployment
    origin: OriginServer
    remnawave: RemnawaveInstance
    resources: RemnawaveResource
    yandex: YandexProject
    facts: dict = field(default_factory=dict)
    health: dict = field(default_factory=dict)
    # Session cookies are held in memory for this run only — they are never persisted.
    cookies: str | None = None

    # ------------------------------------------------------------- accessors

    @property
    def origin_domain(self) -> str:
        return (self.origin.origin_domain or "").strip().lower()

    @property
    def cdn_domain(self) -> str:
        return (self.origin.cdn_domain or "").strip().lower()

    @property
    def origin_ip(self) -> str:
        return (self.origin.origin_ip or "").strip()

    @property
    def node_name(self) -> str:
        return f"CDN {self.origin_domain or self.origin_ip}"[:64]

    def ssh_credentials(self) -> SSHCredentials:
        return ssh_credentials_for(self.origin)

    def remnawave_credentials(self) -> tuple[str, str]:
        box = secret_box()
        token = box.decrypt(self.remnawave.api_token_enc) or ""
        return self.remnawave.panel_url or "", token

    def yandex_credentials(self) -> tuple[str, str]:
        """Legacy accessor: service account key + folder."""
        box = secret_box()
        key = box.decrypt(self.yandex.service_account_key_enc) or ""
        return key, self.yandex.folder_id or ""

    def yandex_auth(self) -> YandexAuth:
        """Build the auth provider this order was configured with."""
        settings = get_settings()
        box = secret_box()
        return build_auth(
            auth_type=self.yandex.auth_type or AUTH_SERVICE_ACCOUNT,
            service_account_key=box.decrypt(self.yandex.service_account_key_enc),
            oauth_token=box.decrypt(self.yandex.oauth_token_enc),
            cookies=self.cookies,
            cookie_exchange_url=settings.yandex_cookie_exchange_url,
            cookie_token_field=settings.yandex_cookie_token_field,
        )

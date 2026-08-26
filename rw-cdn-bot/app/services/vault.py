"""Short-lived secret storage for credentials that must never reach the database.

Yandex session cookies live here and nowhere else. They cross exactly one process boundary —
bot (collects them) → worker (uses them) — so they need a place to sit for the length of one
deployment, encrypted, with a TTL that expires them even if nothing ever calls `purge`.

Rules this module enforces:
  * value is Fernet-encrypted before it touches Redis, with the key that only lives in .env;
  * every entry carries a TTL, so a crashed worker cannot leave a session behind;
  * `purge` is called the moment the last step that needs the credential succeeds.

Anything that should survive a restart belongs in Postgres instead. Nothing here does.
"""
from __future__ import annotations

import logging

from redis.asyncio import Redis

from app.config import get_settings
from app.core.crypto import secret_box
from app.services.yandex.cookies import CookieJar

logger = logging.getLogger(__name__)

KEY = "vault:{scope}:{ref}"
DEFAULT_TTL = 3600  # one hour: long enough for a deployment, short enough to not linger

SCOPE_YANDEX_COOKIES = "yandex_cookies"


class SecretVault:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    @classmethod
    def from_settings(cls) -> SecretVault:
        return cls(Redis.from_url(get_settings().redis_url, decode_responses=True))

    async def close(self) -> None:
        await self.redis.aclose()

    async def __aenter__(self) -> SecretVault:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    @staticmethod
    def _key(scope: str, ref: int | str) -> str:
        return KEY.format(scope=scope, ref=ref)

    async def put(self, scope: str, ref: int | str, value: str, *, ttl: int = DEFAULT_TTL) -> None:
        await self.redis.set(self._key(scope, ref), secret_box().encrypt(value), ex=ttl)

    async def get(self, scope: str, ref: int | str) -> str | None:
        raw = await self.redis.get(self._key(scope, ref))
        if raw is None:
            return None
        try:
            return secret_box().decrypt(raw)
        except ValueError:
            # Encryption key changed under us; treat as absent rather than crash a deployment.
            logger.warning("Vault entry %s:%s could not be decrypted, dropping", scope, ref)
            await self.purge(scope, ref)
            return None

    async def purge(self, scope: str, ref: int | str) -> None:
        await self.redis.delete(self._key(scope, ref))

    async def ttl(self, scope: str, ref: int | str) -> int:
        """Seconds left, -2 when the entry is gone."""
        return int(await self.redis.ttl(self._key(scope, ref)))


# Never hold a session for less than this even if it dies sooner: the entry still has to
# outlive the bot→worker handover so the failure is reported as "cookie expired" rather than
# as a credential that silently vanished.
MIN_TTL = 60


def cookie_ttl(jar: CookieJar, *, default: int = DEFAULT_TTL) -> int:
    """Keep a session only as long as it can still be used.

    A jar that dies in ten minutes has no business sitting in Redis for an hour, and one that
    outlives the deployment is still capped at the default.
    """
    hours_left = jar.expires_in_hours
    if hours_left is None:
        return default
    return max(MIN_TTL, min(default, int(hours_left * 3600)))


async def store_yandex_cookies(order_id: int, payload: str | CookieJar, *, ttl: int | None = None) -> None:
    """Park a session for one deployment.

    A `CookieJar` is stored in its serialised form, not as a `Cookie:` header: the header
    drops the issuing domain and the expiry, and the worker needs both — the domain decides
    which host the jar may authenticate against, the expiry decides whether it is worth
    trying at all.
    """
    if isinstance(payload, CookieJar):
        ttl = cookie_ttl(payload) if ttl is None else ttl
        payload = payload.dumps()
    async with SecretVault.from_settings() as vault:
        await vault.put(SCOPE_YANDEX_COOKIES, order_id, payload, ttl=ttl or DEFAULT_TTL)


async def read_yandex_cookies(order_id: int) -> str | None:
    async with SecretVault.from_settings() as vault:
        return await vault.get(SCOPE_YANDEX_COOKIES, order_id)


async def purge_yandex_cookies(order_id: int) -> None:
    async with SecretVault.from_settings() as vault:
        await vault.purge(SCOPE_YANDEX_COOKIES, order_id)

from __future__ import annotations

from app.services.vault import DEFAULT_TTL, SCOPE_YANDEX_COOKIES, SecretVault


class FakeRedis:
    """Enough of redis.asyncio to exercise the vault, with TTLs recorded."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.closed = False

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.data[key] = value
        self.ttls[key] = ex if ex is not None else -1

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def delete(self, key: str) -> int:
        self.ttls.pop(key, None)
        return 1 if self.data.pop(key, None) is not None else 0

    async def ttl(self, key: str) -> int:
        return self.ttls.get(key, -2)

    async def aclose(self) -> None:
        self.closed = True


COOKIES = "Session_id=3:abc.def; yandexuid=42"


async def test_value_is_encrypted_at_rest():
    redis = FakeRedis()
    vault = SecretVault(redis)
    await vault.put(SCOPE_YANDEX_COOKIES, 7, COOKIES)

    stored = next(iter(redis.data.values()))
    assert COOKIES not in stored
    assert "Session_id" not in stored
    assert await vault.get(SCOPE_YANDEX_COOKIES, 7) == COOKIES


async def test_every_entry_gets_a_ttl():
    redis = FakeRedis()
    await SecretVault(redis).put(SCOPE_YANDEX_COOKIES, 7, COOKIES)
    assert redis.ttls[f"vault:{SCOPE_YANDEX_COOKIES}:7"] == DEFAULT_TTL


async def test_purge_removes_the_entry():
    redis = FakeRedis()
    vault = SecretVault(redis)
    await vault.put(SCOPE_YANDEX_COOKIES, 7, COOKIES)
    await vault.purge(SCOPE_YANDEX_COOKIES, 7)

    assert redis.data == {}
    assert await vault.get(SCOPE_YANDEX_COOKIES, 7) is None


async def test_missing_entry_reads_as_none():
    assert await SecretVault(FakeRedis()).get(SCOPE_YANDEX_COOKIES, 999) is None


async def test_undecryptable_entry_is_dropped_not_raised():
    redis = FakeRedis()
    redis.data[f"vault:{SCOPE_YANDEX_COOKIES}:7"] = "not-a-fernet-token"
    vault = SecretVault(redis)

    assert await vault.get(SCOPE_YANDEX_COOKIES, 7) is None
    assert redis.data == {}  # and it does not linger


async def test_orders_do_not_share_entries():
    redis = FakeRedis()
    vault = SecretVault(redis)
    await vault.put(SCOPE_YANDEX_COOKIES, 1, "Session_id=a")
    await vault.put(SCOPE_YANDEX_COOKIES, 2, "Session_id=b")

    await vault.purge(SCOPE_YANDEX_COOKIES, 1)
    assert await vault.get(SCOPE_YANDEX_COOKIES, 1) is None
    assert await vault.get(SCOPE_YANDEX_COOKIES, 2) == "Session_id=b"


async def test_context_manager_closes_the_connection():
    redis = FakeRedis()
    async with SecretVault(redis):
        pass
    assert redis.closed is True


def test_cookies_are_not_a_database_column():
    """The model must not grow a place to persist sessions again."""
    from app.models import YandexProject

    assert not hasattr(YandexProject, "session_cookies_enc")


# ------------------------------------------------------------------ cookie TTL


def test_cookie_ttl_follows_the_session_lifetime():
    """A jar that dies in ten minutes has no business sitting in Redis for an hour."""
    from datetime import UTC, datetime, timedelta

    from app.services.vault import DEFAULT_TTL, cookie_ttl
    from app.services.yandex.cookies import parse_cookies

    soon = (datetime.now(UTC) + timedelta(minutes=10)).timestamp()
    jar = parse_cookies(f".yandex.cloud\tTRUE\t/\tTRUE\t{int(soon)}\tyc_session\tc1.abc")
    assert 500 < cookie_ttl(jar) <= 600
    assert cookie_ttl(jar) < DEFAULT_TTL


def test_cookie_ttl_is_capped_at_the_default():
    from datetime import UTC, datetime, timedelta

    from app.services.vault import DEFAULT_TTL, cookie_ttl
    from app.services.yandex.cookies import parse_cookies

    far = (datetime.now(UTC) + timedelta(days=30)).timestamp()
    jar = parse_cookies(f".yandex.cloud\tTRUE\t/\tTRUE\t{int(far)}\tyc_session\tc1.abc")
    assert cookie_ttl(jar) == DEFAULT_TTL


def test_cookie_ttl_without_an_expiry_uses_the_default():
    from app.services.vault import DEFAULT_TTL, cookie_ttl
    from app.services.yandex.cookies import parse_cookies

    assert cookie_ttl(parse_cookies("yc_session=c1.abc")) == DEFAULT_TTL

"""Authentication strategies for the Yandex Cloud API.

Three ways to obtain the `Authorization: Bearer <IAM token>` that every Yandex Cloud REST
call needs:

    service_account  JWT PS256 -> POST /iam/v1/tokens {"jwt": ...}          (documented)
    oauth            POST /iam/v1/tokens {"yandexPassportOauthToken": ...}  (documented)
    cookie           yc_session -> exchange endpoint -> token                (NOT documented)

Cookie input is parsed by `cookies.py`, which accepts a pasted header, a Netscape
`cookies.txt` / `.cookie` file and the JSON exports produced by the common extensions.

Yandex Cloud web interfaces authenticate with `yc_session`. One logical session is started by
auth.yandex.cloud, but the cookie is issued separately for every service domain (console,
Cloud Center, DataLens, ...) — so the export has to come from the same domain the exchange
endpoint lives on, and that is checked before any request is made.

The first two hit the published IAM API. The third does not: Yandex publishes no
cookie-to-IAM exchange, so the exchange URL and the JSON field holding the token are
configuration (`YANDEX_COOKIE_EXCHANGE_URL`, `YANDEX_COOKIE_TOKEN_FIELD`), never hardcoded
here. If Yandex changes the console, you change one env var instead of patching code.

Cookie sessions expire on Yandex's schedule and cannot be renewed programmatically. Every
provider therefore reports `needs_reauth` so the deployment can park in a waiting state and
ask the operator for a fresh session, rather than failing the order outright.
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from urllib.parse import urlparse

import httpx

from app.core.exceptions import PermanentError, TransientError, YandexAPIError
from app.services.yandex.cookies import (
    SESSION_COOKIE_NAME,  # noqa: F401 — re-exported for callers importing from auth
    SESSION_COOKIE_NAMES,  # noqa: F401 — re-exported for callers importing from auth
    Cookie,
    CookieJar,
    parse_cookie_header,  # noqa: F401 — re-exported for callers importing from auth
    parse_cookies,
)
from app.services.yandex.iam import IAM_TOKEN_URL, TOKEN_TTL, IAMTokenProvider, ServiceAccountKey

logger = logging.getLogger(__name__)

AUTH_SERVICE_ACCOUNT = "service_account"
AUTH_OAUTH = "oauth"
AUTH_COOKIE = "cookie"

class ReauthRequired(PermanentError):
    """The stored credential is dead and only a human can replace it.

    Raised instead of a generic auth error so the deployment parks and asks for a refresh
    rather than burning retries against a session that will never come back.
    """


class YandexAuth(ABC):
    """Anything that can produce an IAM token for the REST client."""

    kind: str = "unknown"

    @abstractmethod
    async def token(self) -> str: ...

    async def check(self) -> bool:
        """True when the credential currently works."""
        try:
            await self.token()
            return True
        except (ReauthRequired, YandexAPIError):
            return False

    @property
    def renewable(self) -> bool:
        """False when expiry needs a human, not a retry."""
        return True

    def describe(self) -> str:
        return self.kind


class ServiceAccountAuth(YandexAuth):
    kind = AUTH_SERVICE_ACCOUNT

    def __init__(self, key: str | dict) -> None:
        self._provider = IAMTokenProvider(ServiceAccountKey.parse(key))

    async def token(self) -> str:
        return await self._provider.token()

    def describe(self) -> str:
        return f"service account {self._provider.key.service_account_id}"


class OAuthAuth(YandexAuth):
    """Yandex account OAuth token — documented, valid for a year."""

    kind = AUTH_OAUTH

    def __init__(self, oauth_token: str, *, timeout: int = 30) -> None:
        token = (oauth_token or "").strip()
        if not token:
            raise PermanentError("Пустой OAuth-токен Yandex")
        self._oauth = token
        self._timeout = timeout
        self._token: str | None = None
        self._expires_at: float = 0.0

    async def token(self) -> str:
        if self._token and time.time() < self._expires_at - 120:
            return self._token
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                IAM_TOKEN_URL, json={"yandexPassportOauthToken": self._oauth}
            )
        if response.status_code >= 500:
            raise TransientError(f"Yandex IAM HTTP {response.status_code}")
        if response.status_code in (401, 403):
            raise ReauthRequired(
                "OAuth-токен Yandex отозван или истёк — нужен новый токен"
            )
        if response.status_code >= 400:
            raise YandexAPIError(response.status_code, response.text, "iam/v1/tokens")
        self._token = response.json()["iamToken"]
        self._expires_at = time.time() + TOKEN_TTL
        return self._token

    @property
    def renewable(self) -> bool:
        return False  # a year, but still a human-issued credential

    def describe(self) -> str:
        return "OAuth-токен аккаунта Yandex"


# Candidate paths tried when no exchange URL is configured. None of these is documented by
# Yandex — they are probed, and a candidate only counts if it answers with JSON containing
# something token-shaped. A wrong guess therefore fails closed instead of silently "working".
DISCOVERY_PATHS: tuple[str, ...] = (
    "/api/iam/token",
    "/api/token",
    "/iam/token",
    "/api/auth/token",
    "/auth/token",
)

# Token field names seen in practice, tried in order when the configured one is absent.
TOKEN_FIELDS: tuple[str, ...] = ("iamToken", "token", "accessToken", "access_token")

BROWSER_HEADERS = {
    "Accept": "application/json",
    # The console rejects requests without a browser-shaped UA.
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}


# A blind probe has to tell a token apart from any other string the endpoint happens to
# return, so discovery insists on something long enough to be one. A configured field name is
# an explicit instruction and is taken at its word, whatever the length.
DISCOVERY_MIN_TOKEN_LENGTH = 20


def _token_from(payload: object, preferred: str = "", *, min_length: int = 1) -> tuple[str, str] | None:
    """Pull a token out of a JSON body. Returns (value, field) or None.

    `preferred` is a field name, optionally dotted (`data.token`); it wins over the fallback
    list. `min_length` guards blind discovery only — see DISCOVERY_MIN_TOKEN_LENGTH.
    """
    if preferred:
        value = _dig(payload, preferred)
        if isinstance(value, str) and value.strip():
            return value, preferred
    for field_name in TOKEN_FIELDS:
        if field_name == preferred:
            continue
        value = _dig(payload, field_name)
        if isinstance(value, str) and len(value.strip()) >= min_length:
            return value, field_name
    return None


# Discovery costs one HTTPS round-trip per candidate path and the answer is the same for
# every order on this deployment, so the winning endpoint is remembered for the process.
_discovered: dict[str, tuple[str, str]] = {}


def _discovery_cache_key(domains: set[str]) -> str:
    return ",".join(sorted(domains)) or "-"


def forget_discovered_endpoint() -> None:
    """Drop the cached endpoint — used when a discovered URL stops working."""
    _discovered.clear()


async def discover_exchange_url(
    cookies: dict[str, str], domains: set[str], *, timeout: int = 15
) -> tuple[str, str] | None:
    """Find an endpoint that swaps this session for a token. Returns (url, token_field).

    Tries the hosts the cookies were actually issued for — a `yc_session` for
    `console.yandex.cloud` is not sent anywhere else, so probing other domains is pointless.
    Only a JSON response carrying a token-shaped value counts as a hit; HTML, a redirect to
    the login page or a 404 are all misses.
    """
    cache_key = _discovery_cache_key(domains)
    cached = _discovered.get(cache_key)
    if cached:
        return cached

    hosts = _candidate_hosts(domains)
    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=False, cookies=cookies, headers=BROWSER_HEADERS
    ) as client:
        for host in hosts:
            for path in DISCOVERY_PATHS:
                url = f"https://{host}{path}"
                try:
                    response = await client.get(url)
                except httpx.HTTPError:
                    continue
                if response.status_code != 200:
                    continue
                try:
                    payload = response.json()
                except ValueError:
                    continue
                found = _token_from(payload, min_length=DISCOVERY_MIN_TOKEN_LENGTH)
                if found:
                    logger.info("Discovered Yandex cookie exchange endpoint at %s", url)
                    _discovered[cache_key] = (url, found[1])
                    return url, found[1]
    return None


def _candidate_hosts(domains: set[str]) -> list[str]:
    """Hosts worth probing, most specific first."""
    hosts: list[str] = []
    for domain in sorted(domains):
        scope = domain.lstrip(".").lower()
        if not scope:
            continue
        if scope.count(".") >= 2:  # already a concrete host like console.yandex.cloud
            hosts.append(scope)
        else:  # a parent scope such as yandex.cloud — try the services that live under it
            hosts.extend([f"console.{scope}", f"auth.{scope}"])
    if not hosts:
        hosts = ["console.yandex.cloud", "auth.yandex.cloud"]
    # de-duplicate, keep order
    return list(dict.fromkeys(hosts))


class CookieSessionAuth(YandexAuth):
    """Browser session cookies exchanged for an IAM token.

    Unsupported by Yandex: there is no published endpoint for this, so `exchange_url` and
    `token_field` come from configuration. When no URL is configured the endpoint is probed
    once from the domains the cookies were issued for (`discover=True`, the default); with
    discovery switched off the provider refuses to start rather than guessing a console path.
    """

    kind = AUTH_COOKIE

    def __init__(
        self,
        cookies: str | dict[str, str] | CookieJar,
        *,
        exchange_url: str,
        token_field: str = "iamToken",
        timeout: int = 30,
        ttl: int = TOKEN_TTL,
        discover: bool = True,
    ) -> None:
        if isinstance(cookies, CookieJar):
            jar = cookies
        elif isinstance(cookies, str):
            if not cookies.strip():
                # The vault entry expired, or the session was already wiped after the last
                # Yandex step. Ask for a fresh one instead of failing the order outright.
                raise ReauthRequired(
                    "Сессия Yandex не сохранилась — пришлите свежие cookie"
                )
            jar = parse_cookies(cookies)
        else:
            jar = CookieJar(entries=[Cookie(name=k, value=v) for k, v in dict(cookies).items()])
        if not jar.entries:
            raise ReauthRequired("В сессии Yandex не осталось действующих cookie")
        if not jar.alive:
            raise ReauthRequired("Cookie Yandex просрочены — пришлите свежую сессию")

        self.jar = jar
        self.cookies = jar.cookies
        self.expires_at = jar.expires_at

        self._discover = discover
        if not exchange_url and not discover:
            raise PermanentError(
                "Не задан YANDEX_COOKIE_EXCHANGE_URL и автоопределение выключено"
            )

        # Yandex Cloud issues yc_session separately per service domain, so cookies exported on
        # one domain are simply not sent to another. Catch the mismatch here rather than
        # letting it surface as an unexplained redirect to the login page.
        host = urlparse(exchange_url).hostname or ""
        if host and not jar.covers_host(host):
            raise PermanentError(
                f"Cookie выданы для {', '.join(sorted(jar.domains))}, "
                f"а обмен идёт на {host} — экспортируйте cookie на этом домене"
            )
        self._exchange_url = exchange_url
        self._token_field = token_field
        self._timeout = timeout
        self._ttl = ttl
        self._token: str | None = None
        self._expires_at: float = 0.0

    def _cookies_for(self, url: str) -> dict[str, str]:
        """Exactly what a browser would send to this URL, and nothing else."""
        host = urlparse(url).hostname or ""
        return self.jar.for_host(host) if host else self.jar.cookies

    async def token(self) -> str:
        if self._token and time.time() < self._expires_at - 120:
            return self._token

        # A session that died while the deployment was running is a reauth, not a retry.
        if not self.jar.alive:
            raise ReauthRequired("Cookie Yandex просрочены — пришлите свежую сессию")

        if not self._exchange_url:
            found = await discover_exchange_url(self.cookies, self.jar.domains)
            if not found:
                raise PermanentError(
                    "Не удалось определить эндпоинт обмена cookie автоматически.\n\n"
                    "Проще всего переключиться на OAuth-токен — он документирован, "
                    "работает от того же аккаунта и живёт год.\n\n"
                    "Либо найдите эндпоинт вручную: DevTools → Network → Fetch/XHR, "
                    "запрос, который отдаёт JSON с токеном, — и укажите его URL "
                    "в YANDEX_COOKIE_EXCHANGE_URL."
                )
            self._exchange_url, self._token_field = found

        url = self._exchange_url
        # Cookies go on the client, not on the request: per-request cookies are deprecated in
        # httpx and leave it ambiguous whether the jar is merged with or replaces the client's.
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                follow_redirects=False,
                headers=BROWSER_HEADERS,
                cookies=self._cookies_for(url),
            ) as client:
                response = await client.get(url)
        except httpx.TimeoutException as exc:
            raise TransientError(f"Таймаут обмена cookie Yandex: {url}") from exc
        except httpx.HTTPError as exc:
            raise TransientError(f"Сеть недоступна при обмене cookie Yandex: {exc}") from exc

        # A dead session is a redirect to the login page, not a clean 401.
        if response.status_code in (301, 302, 303, 307, 308):
            self._forget_discovered()
            raise ReauthRequired("Сессия Yandex истекла — cookie больше не действительны")
        if response.status_code in (401, 403):
            self._forget_discovered()
            raise ReauthRequired("Yandex отклонил cookie — нужна свежая сессия")
        if response.status_code >= 500:
            raise TransientError(f"Yandex cookie exchange HTTP {response.status_code}")
        if response.status_code >= 400:
            self._forget_discovered()
            raise YandexAPIError(response.status_code, response.text, url)

        try:
            payload = response.json()
        except ValueError as exc:
            # HTML back means the login page was served with a 200.
            self._forget_discovered()
            raise ReauthRequired(
                "Ответ на обмен cookie не JSON — вероятно, сессия истекла"
            ) from exc

        found = _token_from(payload, self._token_field)
        if not found:
            raise PermanentError(
                f"В ответе обмена cookie нет поля '{self._token_field}' — "
                "проверьте YANDEX_COOKIE_TOKEN_FIELD"
            )
        self._token, self._token_field = found
        self._expires_at = time.time() + self._ttl
        return self._token

    def _forget_discovered(self) -> None:
        """A probed endpoint that starts refusing us was the wrong guess — probe again."""
        if self._discover:
            forget_discovered_endpoint()

    @property
    def renewable(self) -> bool:
        return False

    @property
    def exchange_url(self) -> str:
        """Empty until the first successful discovery."""
        return self._exchange_url

    def describe(self) -> str:
        detail = f", истекает {self.expires_at:%d.%m.%Y %H:%M UTC}" if self.expires_at else ""
        return f"cookie-сессия Yandex (неофициальный способ){detail}"


def _dig(payload: object, path: str) -> object:
    """Read a dotted path out of a JSON body: 'data.iamToken'."""
    current = payload
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def build_auth(
    *,
    auth_type: str,
    service_account_key: str | None = None,
    oauth_token: str | None = None,
    cookies: str | None = None,
    cookie_exchange_url: str = "",
    cookie_token_field: str = "iamToken",
) -> YandexAuth:
    if auth_type == AUTH_SERVICE_ACCOUNT:
        if not service_account_key:
            raise PermanentError("Не задан ключ сервисного аккаунта Yandex")
        return ServiceAccountAuth(service_account_key)
    if auth_type == AUTH_OAUTH:
        return OAuthAuth(oauth_token or "")
    if auth_type == AUTH_COOKIE:
        return CookieSessionAuth(
            cookies or "",
            exchange_url=cookie_exchange_url,
            token_field=cookie_token_field or "iamToken",
        )
    raise PermanentError(f"Неизвестный способ авторизации Yandex: {auth_type}")

"""Cookie parsing for the Yandex session auth method.

Operators export cookies in whatever their extension produces, so five shapes are accepted
and auto-detected from the content (the filename is only a hint):

  header      Session_id=3:abc; yandexuid=1     — pasted `Cookie:` header or document.cookie
  netscape    cookies.txt / *.cookie             — tab-separated, `# Netscape HTTP Cookie File`
  json_list   [{"name": ..., "value": ...}, ...] — EditThisCookie, Cookie-Editor
  json_state  {"cookies": [...]}                 — Playwright/Puppeteer storage state
  json_map    {"Session_id": "3:abc", ...}       — a plain name→value object

Expired entries are dropped rather than sent, and the earliest remaining expiry is reported
so the operator can be told when the session will die instead of finding out mid-deployment.

A jar keeps one `Cookie` per entry — name, value, issuing domain and expiry — instead of a
flat name→value map, because the domain decides which host the jar may authenticate against
and the expiry decides how long it is worth storing. `dumps()` writes that back out in the
`json_list` shape, which `parse_cookies` reads again, so a jar survives the hop from the bot
process to the deployment worker without losing either.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.core.exceptions import PermanentError

logger = logging.getLogger(__name__)

# Yandex Cloud web interfaces authenticate with `yc_session`. The single logical session is
# started by auth.yandex.cloud, but the cookie itself is issued separately for every service
# domain (console, Cloud Center, DataLens, ...), so an export taken on the wrong domain will
# not authenticate the one we call.
SESSION_COOKIE_NAME = "yc_session"

# Yandex ID (passport) cookies. They are a different session entirely — a `Session_id` from
# yandex.ru does not authenticate a Cloud service, so an export holding only these is a
# recognisable mistake worth naming precisely.
PASSPORT_COOKIE_NAMES = ("Session_id", "sessionid2")

# Kept for callers that still import the old name.
SESSION_COOKIE_NAMES = (SESSION_COOKIE_NAME, *PASSPORT_COOKIE_NAMES)

# Only cookies for these domains are taken from file exports — a full browser dump holds
# hundreds of unrelated cookies and sending them all is both pointless and leaky.
YANDEX_DOMAIN_HINTS = ("yandex.cloud", "yandexcloud.", "cloud.yandex", "yandex.")

FORMAT_HEADER = "header"
FORMAT_NETSCAPE = "netscape"
FORMAT_JSON_LIST = "json_list"
FORMAT_JSON_STATE = "json_state"
FORMAT_JSON_MAP = "json_map"

# Attribute names that appear in a `Cookie:`/`Set-Cookie:` string but are not cookies.
_COOKIE_ATTRIBUTES = frozenset(
    {
        "expires", "path", "domain", "max-age", "secure", "httponly",
        "samesite", "version", "comment", "priority", "partitioned",
    }
)


@dataclass(slots=True, frozen=True)
class Cookie:
    name: str
    value: str
    domain: str | None = None
    expires: datetime | None = None

    def as_export(self) -> dict:
        """The `json_list` shape, so `parse_cookies` can read it straight back."""
        data: dict = {"name": self.name, "value": self.value}
        if self.domain:
            data["domain"] = self.domain
        if self.expires is not None:
            data["expirationDate"] = self.expires.timestamp()
        else:
            data["session"] = True
        return data


@dataclass(slots=True)
class CookieJar:
    entries: list[Cookie] = field(default_factory=list)
    source_format: str = FORMAT_HEADER
    dropped_expired: int = 0
    skipped_foreign: int = 0

    @property
    def cookies(self) -> dict[str, str]:
        """Flat name→value view. Later entries win, as they do in a browser."""
        return {cookie.name: cookie.value for cookie in self.entries}

    @property
    def domains(self) -> set[str]:
        """Domains the surviving cookies were issued for.

        Empty for header-style input, which carries no domain at all.
        """
        return {cookie.domain for cookie in self.entries if cookie.domain}

    @property
    def expires_at(self) -> datetime | None:
        """The earliest expiry among the cookies — when the session starts falling apart."""
        stamps = [cookie.expires for cookie in self.entries if cookie.expires is not None]
        return min(stamps) if stamps else None

    def covers_host(self, host: str) -> bool:
        """True when a cookie in this jar would be sent to `host`.

        A cookie for `.yandex.cloud` is sent to `console.yandex.cloud`; one for
        `console.yandex.cloud` is not sent to `datalens.yandex.cloud`.
        """
        domains = self.domains
        if not domains:
            return True  # nothing to check against
        target = host.strip().lower().rstrip(".")
        for domain in domains:
            scope = domain.lstrip(".").lower()
            if target == scope or target.endswith("." + scope):
                return True
        return False

    def for_host(self, host: str) -> dict[str, str]:
        """Only the cookies a browser would actually send to `host`.

        Cookies with no domain (a pasted header) are sent everywhere, exactly as the browser
        that produced them would have done.
        """
        target = host.strip().lower().rstrip(".")
        selected: dict[str, str] = {}
        for cookie in self.entries:
            if not cookie.domain:
                selected[cookie.name] = cookie.value
                continue
            scope = cookie.domain.lstrip(".").lower()
            if target == scope or target.endswith("." + scope):
                selected[cookie.name] = cookie.value
        return selected

    def header(self) -> str:
        return "; ".join(f"{name}={value}" for name, value in self.cookies.items())

    def dumps(self) -> str:
        """Serialise losslessly, including domains and per-cookie expiry."""
        return json.dumps([cookie.as_export() for cookie in self.entries], ensure_ascii=False)

    @property
    def expires_in_hours(self) -> float | None:
        expires_at = self.expires_at
        if expires_at is None:
            return None
        return (expires_at - datetime.now(UTC)).total_seconds() / 3600

    @property
    def alive(self) -> bool:
        """False once the earliest expiry has passed — the session is no longer usable."""
        expires_at = self.expires_at
        return expires_at is None or expires_at > datetime.now(UTC)

    def describe(self) -> str:
        parts = [f"формат: {self.source_format}", f"cookie: {len(self.entries)}"]
        expires_at = self.expires_at
        if expires_at:
            parts.append(f"истекает: {expires_at:%d.%m.%Y %H:%M UTC}")
        if self.dropped_expired:
            parts.append(f"просроченных отброшено: {self.dropped_expired}")
        domains = self.domains
        if domains:
            parts.append("домены: " + ", ".join(sorted(domains)))
        if self.skipped_foreign:
            parts.append(f"чужих доменов пропущено: {self.skipped_foreign}")
        return ", ".join(parts)


def _to_datetime(value: object) -> datetime | None:
    """Expiry comes as a unix timestamp (int, float or numeric string) or an ISO string.

    Always returns an aware datetime: an ISO string without an offset would otherwise be
    compared against an aware `now` and raise TypeError instead of expiring the cookie.
    """
    if value in (None, "", 0, "0", -1, "-1"):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        try:
            return datetime.fromtimestamp(float(text), UTC)
        except (ValueError, OverflowError, OSError):
            pass
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _is_yandex_domain(domain: str | None) -> bool:
    if not domain:
        return True  # header-style input carries no domain; assume it is the right one
    lowered = domain.lstrip(".").lower()
    return any(hint in lowered for hint in YANDEX_DOMAIN_HINTS)


def _collect(entries: Iterable[tuple[str, str, str | None, datetime | None]]) -> CookieJar:
    """Fold parsed (name, value, domain, expiry) rows into a jar."""
    jar = CookieJar()
    now = datetime.now(UTC)
    seen: dict[str, int] = {}

    for name, value, domain, expiry in entries:
        if not name or value in (None, ""):
            continue
        if not _is_yandex_domain(domain):
            jar.skipped_foreign += 1
            continue
        if expiry is not None and expiry <= now:
            jar.dropped_expired += 1
            continue
        cookie = Cookie(name=name, value=value, domain=domain or None, expires=expiry)
        if name in seen:
            jar.entries[seen[name]] = cookie
        else:
            seen[name] = len(jar.entries)
            jar.entries.append(cookie)

    return jar


def _split_header(text: str) -> list[tuple[str, str]]:
    """Split a `Cookie:` string into pairs.

    Written by hand rather than with `http.cookies.SimpleCookie` because that parser also
    treats a comma as a separator, and several Yandex cookies (`L`, `ys`, `yp`) carry commas
    inside their value — SimpleCookie chops them into fragments and silently drops the rest.
    It also swallows any name it recognises as a Set-Cookie attribute.
    """
    pairs: list[tuple[str, str]] = []
    for chunk in text.split(";"):
        part = chunk.strip()
        if not part or "=" not in part:
            continue
        name, _, value = part.partition("=")
        name = name.strip()
        if not name or name.lower() in _COOKIE_ATTRIBUTES:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
            value = value[1:-1]
        pairs.append((name, value))
    return pairs


def _parse_header(text: str) -> CookieJar:
    if text.lower().startswith("cookie:"):
        text = text.split(":", 1)[1].strip()
    pairs = _split_header(text)
    if not pairs:
        raise PermanentError("Не удалось разобрать cookie: не найдено ни одной пары name=value")
    jar = _collect([(name, value, None, None) for name, value in pairs])
    jar.source_format = FORMAT_HEADER
    return jar


def _parse_netscape(text: str) -> CookieJar:
    """cookies.txt: domain, include_subdomains, path, secure, expiry, name, value."""
    entries: list[tuple[str, str, str | None, datetime | None]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            # `#HttpOnly_.yandex.ru` rows are real cookies wearing a comment prefix.
            if not stripped.startswith("#HttpOnly_"):
                continue
            stripped = stripped[len("#HttpOnly_"):]
        parts = stripped.split("\t") if "\t" in stripped else stripped.split()
        if len(parts) < 7:
            continue
        domain, _subdomains, _path, _secure, expiry, name, value = parts[:7]
        entries.append((name, value, domain, _to_datetime(expiry)))

    if not entries:
        raise PermanentError("В файле не найдено ни одной строки cookie в формате Netscape")
    jar = _collect(entries)
    jar.source_format = FORMAT_NETSCAPE
    return jar


def _parse_json(payload: object) -> CookieJar:
    if isinstance(payload, dict) and isinstance(payload.get("cookies"), list):
        jar = _parse_cookie_objects(payload["cookies"])
        jar.source_format = FORMAT_JSON_STATE
        return jar

    if isinstance(payload, list):
        jar = _parse_cookie_objects(payload)
        jar.source_format = FORMAT_JSON_LIST
        return jar

    if isinstance(payload, dict):
        # A flat name -> value object. Values must be scalars, otherwise this is some other
        # export we should not silently mangle.
        flat = {
            key: str(value)
            for key, value in payload.items()
            if isinstance(value, (str, int, float)) and not isinstance(value, bool) and str(value)
        }
        if not flat:
            raise PermanentError("JSON не похож на экспорт cookie")
        jar = _collect([(name, value, None, None) for name, value in flat.items()])
        jar.source_format = FORMAT_JSON_MAP
        return jar

    raise PermanentError("JSON не похож на экспорт cookie")


def _parse_cookie_objects(items: list) -> CookieJar:
    entries: list[tuple[str, str, str | None, datetime | None]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("Name")
        value = item.get("value") or item.get("Value")
        if not name or value is None:
            continue
        expiry = _to_datetime(
            item.get("expirationDate")
            if item.get("expirationDate") is not None
            else item.get("expires")
        )
        # Session cookies are exported with session: true and no expiry — keep them.
        entries.append((str(name), str(value), item.get("domain"), expiry))

    if not entries:
        raise PermanentError("В JSON нет объектов cookie с полями name/value")
    return _collect(entries)


def parse_cookies(raw: str, *, filename: str | None = None) -> CookieJar:
    """Parse any supported export into a jar, detecting the format from the content."""
    text = (raw or "").strip()
    if not text:
        raise PermanentError("Пустой файл или строка cookie")

    if text.startswith(("{", "[")):
        try:
            payload = json.loads(text)
        except ValueError as exc:
            raise PermanentError(f"Некорректный JSON: {exc}") from exc
        jar = _parse_json(payload)
    elif text.lstrip().startswith("# Netscape") or "\t" in text or (filename or "").endswith(
        (".cookie", ".cookies", ".txt")
    ):
        jar = _parse_netscape(text)
    else:
        jar = _parse_header(text)

    if not jar.entries:
        if jar.dropped_expired:
            raise PermanentError(
                f"Все cookie в файле просрочены ({jar.dropped_expired} шт.) — "
                "экспортируйте свежие"
            )
        raise PermanentError("Не найдено ни одного действующего cookie")

    names = jar.cookies
    if SESSION_COOKIE_NAME not in names:
        if any(name in names for name in PASSPORT_COOKIE_NAMES):
            raise PermanentError(
                f"Это cookie Яндекс ID, а не Yandex Cloud: нет {SESSION_COOKIE_NAME}. "
                "Экспортируйте cookie на вкладке с консолью Yandex Cloud."
            )
        raise PermanentError(
            f"Нет cookie {SESSION_COOKIE_NAME} — экспорт снят не с того домена или не с той вкладки"
        )
    return jar


def parse_cookie_header(raw: str) -> dict[str, str]:
    """Back-compatible helper: any supported format in, plain name→value map out."""
    return parse_cookies(raw).cookies

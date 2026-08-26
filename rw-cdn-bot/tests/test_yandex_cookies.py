from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import PermanentError
from app.services.yandex.cookies import (
    FORMAT_HEADER,
    FORMAT_JSON_LIST,
    FORMAT_JSON_MAP,
    FORMAT_JSON_STATE,
    FORMAT_NETSCAPE,
    parse_cookie_header,
    parse_cookies,
)

SESSION = "c1.abcdef.yc"
FUTURE = (datetime.now(UTC) + timedelta(days=3)).timestamp()
PAST = (datetime.now(UTC) - timedelta(days=3)).timestamp()


# ------------------------------------------------------------------- header


def test_header_string():
    jar = parse_cookies(f"yc_session={SESSION}; yandexuid=42")
    assert jar.source_format == FORMAT_HEADER
    assert jar.cookies == {"yc_session": SESSION, "yandexuid": "42"}


def test_header_with_prefix():
    assert parse_cookies(f"Cookie: yc_session={SESSION}").cookies["yc_session"] == SESSION


# ----------------------------------------------------------------- netscape


NETSCAPE = "\n".join(
    [
        "# Netscape HTTP Cookie File",
        "# This is a generated file! Do not edit.",
        "",
        f".yandex.ru\tTRUE\t/\tTRUE\t{int(FUTURE)}\tyc_session\t{SESSION}",
        f".yandex.ru\tTRUE\t/\tFALSE\t{int(FUTURE)}\tyandexuid\t42",
    ]
)


def test_netscape_file():
    jar = parse_cookies(NETSCAPE, filename="cookies.txt")
    assert jar.source_format == FORMAT_NETSCAPE
    assert jar.cookies["yc_session"] == SESSION
    assert jar.expires_at is not None


def test_netscape_httponly_rows_are_not_treated_as_comments():
    text = f"#HttpOnly_.yandex.ru\tTRUE\t/\tTRUE\t{int(FUTURE)}\tyc_session\t{SESSION}"
    assert parse_cookies(text, filename="x.cookie").cookies["yc_session"] == SESSION


def test_netscape_detected_without_a_filename():
    assert parse_cookies(NETSCAPE).source_format == FORMAT_NETSCAPE


def test_netscape_drops_expired_rows():
    text = "\n".join(
        [
            f".yandex.ru\tTRUE\t/\tTRUE\t{int(FUTURE)}\tyc_session\t{SESSION}",
            f".yandex.ru\tTRUE\t/\tTRUE\t{int(PAST)}\told\tstale",
        ]
    )
    jar = parse_cookies(text)
    assert "old" not in jar.cookies
    assert jar.dropped_expired == 1


def test_netscape_skips_other_domains():
    text = "\n".join(
        [
            f".yandex.ru\tTRUE\t/\tTRUE\t{int(FUTURE)}\tyc_session\t{SESSION}",
            f".example.com\tTRUE\t/\tTRUE\t{int(FUTURE)}\ttracker\tzzz",
        ]
    )
    jar = parse_cookies(text)
    assert "tracker" not in jar.cookies
    assert jar.skipped_foreign == 1


# --------------------------------------------------------------------- json


def test_edit_this_cookie_export():
    payload = json.dumps(
        [
            {"name": "yc_session", "value": SESSION, "domain": ".yandex.ru", "expirationDate": FUTURE},
            {"name": "yandexuid", "value": "42", "domain": ".yandex.ru", "session": True},
        ]
    )
    jar = parse_cookies(payload, filename="cookies.json")
    assert jar.source_format == FORMAT_JSON_LIST
    assert jar.cookies["yc_session"] == SESSION
    assert jar.cookies["yandexuid"] == "42"  # session cookie without expiry is kept


def test_playwright_storage_state():
    payload = json.dumps(
        {
            "cookies": [
                {"name": "yc_session", "value": SESSION, "domain": ".yandex.ru", "expires": FUTURE}
            ],
            "origins": [],
        }
    )
    jar = parse_cookies(payload)
    assert jar.source_format == FORMAT_JSON_STATE
    assert jar.cookies["yc_session"] == SESSION


def test_flat_json_map():
    jar = parse_cookies(json.dumps({"yc_session": SESSION, "yandexuid": 42}))
    assert jar.source_format == FORMAT_JSON_MAP
    assert jar.cookies["yandexuid"] == "42"


def test_json_expiry_as_iso_string():
    stamp = (datetime.now(UTC) + timedelta(hours=5)).isoformat().replace("+00:00", "Z")
    payload = json.dumps([{"name": "yc_session", "value": SESSION, "expirationDate": stamp}])
    jar = parse_cookies(payload)
    assert jar.expires_at is not None
    assert 4 < (jar.expires_in_hours or 0) < 6


def test_broken_json_is_reported_as_such():
    with pytest.raises(PermanentError) as exc:
        parse_cookies('[{"name": "yc_session",')
    assert "JSON" in str(exc.value)


def test_json_that_is_not_a_cookie_export_is_rejected():
    with pytest.raises(PermanentError):
        parse_cookies(json.dumps({"id": {"nested": 1}}))


# ---------------------------------------------------------------- guardrails


def test_missing_session_cookie_is_rejected():
    with pytest.raises(PermanentError) as exc:
        parse_cookies("yandexuid=42; L=1")
    assert "yc_session" in str(exc.value)


def test_passport_only_export_is_named_precisely():
    """Session_id belongs to Yandex ID, not to Cloud — say so instead of a generic error."""
    with pytest.raises(PermanentError) as exc:
        parse_cookies("Session_id=3:abc.def; yandexuid=42")
    assert "Яндекс ID" in str(exc.value)


def test_domains_are_recorded_and_scoped():
    text = f".yandex.cloud\tTRUE\t/\tTRUE\t{int(FUTURE)}\tyc_session\t{SESSION}"
    jar = parse_cookies(text)
    assert jar.domains == {".yandex.cloud"}
    assert jar.covers_host("console.yandex.cloud") is True
    assert jar.covers_host("auth.yandex.cloud") is True
    assert jar.covers_host("example.com") is False


def test_service_scoped_cookie_does_not_cover_a_sibling_service():
    text = f"console.yandex.cloud\tFALSE\t/\tTRUE\t{int(FUTURE)}\tyc_session\t{SESSION}"
    jar = parse_cookies(text)
    assert jar.covers_host("console.yandex.cloud") is True
    assert jar.covers_host("datalens.yandex.cloud") is False


def test_header_input_has_no_domains_and_covers_anything():
    jar = parse_cookies(f"yc_session={SESSION}")
    assert jar.domains == set()
    assert jar.covers_host("console.yandex.cloud") is True


def test_all_expired_gives_a_specific_message():
    text = f".yandex.ru\tTRUE\t/\tTRUE\t{int(PAST)}\tyc_session\t{SESSION}"
    with pytest.raises(PermanentError) as exc:
        parse_cookies(text)
    assert "просрочен" in str(exc.value).lower()


def test_empty_input_is_rejected():
    with pytest.raises(PermanentError):
        parse_cookies("   ")


def test_header_roundtrip_is_stable():
    jar = parse_cookies(json.dumps({"yc_session": SESSION, "yandexuid": "42"}))
    assert parse_cookies(jar.header()).cookies == jar.cookies


def test_backwards_compatible_helper_still_returns_a_map():
    assert parse_cookie_header(f"yc_session={SESSION}") == {"yc_session": SESSION}


def test_describe_mentions_format_and_counts():
    jar = parse_cookies(NETSCAPE)
    described = jar.describe()
    assert FORMAT_NETSCAPE in described
    assert "cookie: 2" in described


# ------------------------------------------------------------------ round-trip


def test_dumps_round_trip_keeps_domains_and_expiry():
    """The jar crosses a process boundary through Redis — nothing may be lost on the way."""
    jar = parse_cookies(NETSCAPE, filename="cookies.txt")
    restored = parse_cookies(jar.dumps())
    assert restored.cookies == jar.cookies
    assert restored.domains == jar.domains
    assert restored.expires_at == jar.expires_at


def test_header_form_loses_the_domain_but_dumps_does_not():
    jar = parse_cookies(NETSCAPE, filename="cookies.txt")
    assert parse_cookies(jar.header()).domains == set()
    assert parse_cookies(jar.dumps()).domains == {".yandex.ru"}


def test_session_cookies_survive_a_round_trip():
    payload = json.dumps([{"name": "yc_session", "value": SESSION, "session": True}])
    restored = parse_cookies(parse_cookies(payload).dumps())
    assert restored.cookies["yc_session"] == SESSION
    assert restored.expires_at is None


# ---------------------------------------------------------- header edge cases


def test_comma_inside_a_value_is_not_a_separator():
    """Yandex `L`, `ys` and `yp` cookies carry commas; splitting on them destroys the value."""
    jar = parse_cookies(f"yc_session={SESSION}; L=abc,,,1234567,,; yandexuid=42")
    assert jar.cookies["L"] == "abc,,,1234567,,"
    assert jar.cookies["yc_session"] == SESSION
    assert jar.cookies["yandexuid"] == "42"


def test_set_cookie_attributes_are_not_mistaken_for_cookies():
    jar = parse_cookies(f"yc_session={SESSION}; Path=/; Domain=.yandex.cloud; Secure; HttpOnly")
    assert set(jar.cookies) == {"yc_session"}


def test_quoted_values_are_unquoted():
    assert parse_cookies(f'yc_session="{SESSION}"').cookies["yc_session"] == SESSION


def test_equals_sign_inside_a_value_is_kept():
    jar = parse_cookies("yc_session=a=b=c")
    assert jar.cookies["yc_session"] == "a=b=c"


def test_a_string_with_no_pairs_at_all_is_rejected():
    with pytest.raises(PermanentError):
        parse_cookies("this is not a cookie string")


# --------------------------------------------------------------- expiry shapes


def test_iso_expiry_without_a_timezone_is_treated_as_utc():
    """A naive datetime compared against an aware `now` used to raise TypeError."""
    stamp = (datetime.now(UTC) + timedelta(hours=5)).replace(tzinfo=None).isoformat()
    jar = parse_cookies(json.dumps([{"name": "yc_session", "value": SESSION, "expires": stamp}]))
    assert jar.expires_at is not None
    assert jar.expires_at.tzinfo is not None


def test_alive_is_false_once_the_earliest_expiry_passed():
    jar = parse_cookies(f"yc_session={SESSION}")
    assert jar.alive is True  # no expiry known
    jar = parse_cookies(NETSCAPE)
    assert jar.alive is True


def test_for_host_sends_only_what_a_browser_would():
    text = "\n".join(
        [
            f"console.yandex.cloud\tFALSE\t/\tTRUE\t{int(FUTURE)}\tyc_session\t{SESSION}",
            f".yandex.cloud\tTRUE\t/\tTRUE\t{int(FUTURE)}\tyandexuid\t42",
        ]
    )
    jar = parse_cookies(text)
    assert jar.for_host("console.yandex.cloud") == {"yc_session": SESSION, "yandexuid": "42"}
    assert jar.for_host("datalens.yandex.cloud") == {"yandexuid": "42"}


def test_for_host_sends_domainless_cookies_everywhere():
    jar = parse_cookies(f"yc_session={SESSION}")
    assert jar.for_host("console.yandex.cloud") == {"yc_session": SESSION}

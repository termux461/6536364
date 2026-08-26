import httpx
import pytest
import respx

from app.core.exceptions import PermanentError
from app.services.yandex.auth import (
    AUTH_COOKIE,
    AUTH_OAUTH,
    AUTH_SERVICE_ACCOUNT,
    CookieSessionAuth,
    OAuthAuth,
    ReauthRequired,
    _candidate_hosts,
    build_auth,
    discover_exchange_url,
    parse_cookie_header,
)

IAM_URL = "https://iam.api.cloud.yandex.net/iam/v1/tokens"
EXCHANGE = "https://console.yandex.cloud/api/token"
COOKIES = "yc_session=c1.abcdef.yc; yandexuid=99887766; L=xyz"


# ------------------------------------------------------------------- parsing


def test_parses_a_plain_cookie_string():
    jar = parse_cookie_header(COOKIES)
    assert jar["yc_session"] == "c1.abcdef.yc"
    assert jar["yandexuid"] == "99887766"


def test_parses_a_pasted_header_line():
    assert parse_cookie_header(f"Cookie: {COOKIES}")["yc_session"] == "c1.abcdef.yc"


def test_rejects_a_string_without_a_session_cookie():
    with pytest.raises(PermanentError):
        parse_cookie_header("yandexuid=1; L=2")


def test_rejects_empty_input():
    with pytest.raises(PermanentError):
        parse_cookie_header("   ")


# ----------------------------------------------------------------- providers


@respx.mock
async def test_oauth_exchanges_for_an_iam_token():
    route = respx.post(IAM_URL).mock(
        return_value=httpx.Response(200, json={"iamToken": "t1", "expiresAt": "2030-01-01T00:00:00Z"})
    )
    auth = OAuthAuth("y0_TESTTOKENTESTTOKEN")
    assert await auth.token() == "t1"
    assert route.calls[0].request.read().decode().startswith('{"yandexPassportOauthToken"')


@respx.mock
async def test_oauth_token_is_cached():
    route = respx.post(IAM_URL).mock(return_value=httpx.Response(200, json={"iamToken": "t1"}))
    auth = OAuthAuth("y0_TESTTOKENTESTTOKEN")
    await auth.token()
    await auth.token()
    assert route.call_count == 1


@respx.mock
async def test_revoked_oauth_asks_for_reauth_not_retries():
    respx.post(IAM_URL).mock(return_value=httpx.Response(401, text="unauthorized"))
    with pytest.raises(ReauthRequired):
        await OAuthAuth("y0_DEAD").token()


def test_cookie_auth_refuses_without_a_configured_endpoint():
    # No endpoint is invented when configuration is missing and probing is switched off.
    with pytest.raises(PermanentError):
        CookieSessionAuth(COOKIES, exchange_url="", discover=False)


def test_cookie_auth_without_cookies_asks_for_a_fresh_session():
    """An expired vault entry must park the deployment, not read as a malformed file."""
    with pytest.raises(ReauthRequired):
        CookieSessionAuth("", exchange_url=EXCHANGE)


@respx.mock
async def test_cookie_exchange_sends_the_jar_and_reads_the_token():
    route = respx.get(EXCHANGE).mock(return_value=httpx.Response(200, json={"iamToken": "t9"}))
    auth = CookieSessionAuth(COOKIES, exchange_url=EXCHANGE)
    assert await auth.token() == "t9"
    sent = route.calls[0].request.headers.get("cookie", "")
    assert "yc_session=c1.abcdef.yc" in sent


@respx.mock
async def test_cookie_exchange_supports_a_nested_token_field():
    respx.get(EXCHANGE).mock(return_value=httpx.Response(200, json={"data": {"token": "deep"}}))
    auth = CookieSessionAuth(COOKIES, exchange_url=EXCHANGE, token_field="data.token")
    assert await auth.token() == "deep"


@respx.mock
async def test_redirect_to_login_means_the_session_died():
    respx.get(EXCHANGE).mock(return_value=httpx.Response(302, headers={"Location": "https://passport"}))
    with pytest.raises(ReauthRequired):
        await CookieSessionAuth(COOKIES, exchange_url=EXCHANGE).token()


@respx.mock
async def test_html_login_page_with_200_also_means_the_session_died():
    respx.get(EXCHANGE).mock(return_value=httpx.Response(200, text="<html>Войдите</html>"))
    with pytest.raises(ReauthRequired):
        await CookieSessionAuth(COOKIES, exchange_url=EXCHANGE).token()


@respx.mock
async def test_wrong_token_field_is_a_config_error_not_a_reauth():
    respx.get(EXCHANGE).mock(return_value=httpx.Response(200, json={"somethingElse": "x"}))
    with pytest.raises(PermanentError) as exc:
        await CookieSessionAuth(COOKIES, exchange_url=EXCHANGE).token()
    assert "YANDEX_COOKIE_TOKEN_FIELD" in str(exc.value)


@respx.mock
async def test_check_returns_false_instead_of_raising():
    respx.get(EXCHANGE).mock(return_value=httpx.Response(403))
    assert await CookieSessionAuth(COOKIES, exchange_url=EXCHANGE).check() is False


async def test_auth_accepts_cookies_passed_in_memory():
    """Cookies reach the provider as a value, never from a stored column."""
    auth = build_auth(
        auth_type=AUTH_COOKIE, cookies=COOKIES, cookie_exchange_url=EXCHANGE
    )
    assert auth.cookies["yc_session"] == "c1.abcdef.yc"


def test_exchange_on_a_domain_the_cookies_do_not_cover_is_rejected():
    """yc_session is issued per service domain — a mismatch cannot work, so fail early."""
    from app.services.yandex.cookies import parse_cookies

    jar = parse_cookies(
        "console.yandex.cloud\tFALSE\t/\tTRUE\t0\tyc_session\tc1.abcdef.yc"
    )
    with pytest.raises(PermanentError) as exc:
        CookieSessionAuth(jar, exchange_url="https://datalens.yandex.cloud/api/token")
    assert "datalens.yandex.cloud" in str(exc.value)


def test_cookie_and_oauth_are_marked_non_renewable():
    assert CookieSessionAuth(COOKIES, exchange_url=EXCHANGE).renewable is False
    assert OAuthAuth("y0_TESTTOKENTESTTOKEN").renewable is False


# ------------------------------------------------------------------ factory

SA_KEY = {
    "id": "key-id",
    "service_account_id": "sa-id",
    "private_key": "-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----\n",
}


def test_factory_builds_each_kind():
    import json

    assert build_auth(
        auth_type=AUTH_SERVICE_ACCOUNT, service_account_key=json.dumps(SA_KEY)
    ).kind == AUTH_SERVICE_ACCOUNT
    assert build_auth(auth_type=AUTH_OAUTH, oauth_token="y0_x" * 8).kind == AUTH_OAUTH
    assert (
        build_auth(auth_type=AUTH_COOKIE, cookies=COOKIES, cookie_exchange_url=EXCHANGE).kind
        == AUTH_COOKIE
    )


def test_factory_rejects_an_unknown_kind():
    with pytest.raises(PermanentError):
        build_auth(auth_type="magic")


# --------------------------------------------------- exchange auto-discovery


def test_candidate_hosts_prefer_the_exact_domain():
    assert _candidate_hosts({"console.yandex.cloud"}) == ["console.yandex.cloud"]


def test_candidate_hosts_expand_a_parent_scope():
    hosts = _candidate_hosts({".yandex.cloud"})
    assert hosts == ["console.yandex.cloud", "auth.yandex.cloud"]


def test_candidate_hosts_fall_back_when_nothing_is_known():
    assert "console.yandex.cloud" in _candidate_hosts(set())


@respx.mock
async def test_discovery_finds_a_json_token_endpoint():
    respx.get("https://console.yandex.cloud/api/iam/token").mock(
        return_value=httpx.Response(200, json={"iamToken": "t" * 40})
    )
    found = await discover_exchange_url({"yc_session": "c1"}, {"console.yandex.cloud"})
    assert found == ("https://console.yandex.cloud/api/iam/token", "iamToken")


@respx.mock
async def test_discovery_skips_html_and_keeps_looking():
    respx.get("https://console.yandex.cloud/api/iam/token").mock(
        return_value=httpx.Response(200, text="<html>login</html>")
    )
    respx.get("https://console.yandex.cloud/api/token").mock(
        return_value=httpx.Response(200, json={"accessToken": "a" * 40})
    )
    found = await discover_exchange_url({"yc_session": "c1"}, {"console.yandex.cloud"})
    assert found == ("https://console.yandex.cloud/api/token", "accessToken")


@respx.mock
async def test_discovery_ignores_a_json_body_without_a_token():
    """A 200 with unrelated JSON is not an exchange endpoint — fail closed, do not guess."""
    for path in ("/api/iam/token", "/api/token", "/iam/token", "/api/auth/token", "/auth/token"):
        respx.get(f"https://console.yandex.cloud{path}").mock(
            return_value=httpx.Response(200, json={"folders": []})
        )
    assert await discover_exchange_url({"yc_session": "c1"}, {"console.yandex.cloud"}) is None


@respx.mock
async def test_cookie_auth_discovers_on_first_use():
    respx.get("https://console.yandex.cloud/api/iam/token").mock(
        return_value=httpx.Response(200, json={"iamToken": "t" * 40})
    )
    auth = CookieSessionAuth("yc_session=c1.abcdef.yc", exchange_url="")
    assert auth.exchange_url == ""
    token = await auth.token()
    assert token == "t" * 40
    assert auth.exchange_url.endswith("/api/iam/token")


@respx.mock
async def test_failed_discovery_asks_for_a_configured_url():
    for path in ("/api/iam/token", "/api/token", "/iam/token", "/api/auth/token", "/auth/token"):
        respx.get(f"https://console.yandex.cloud{path}").mock(return_value=httpx.Response(404))
        respx.get(f"https://auth.yandex.cloud{path}").mock(return_value=httpx.Response(404))
    auth = CookieSessionAuth("yc_session=c1.abcdef.yc", exchange_url="")
    with pytest.raises(PermanentError) as exc:
        await auth.token()
    assert "YANDEX_COOKIE_EXCHANGE_URL" in str(exc.value)


# ------------------------------------------------------- cookie scoping & life


@respx.mock
async def test_exchange_only_sends_cookies_scoped_to_that_host():
    """A cookie issued for one console domain is not leaked to another."""
    import json

    route = respx.get(EXCHANGE).mock(return_value=httpx.Response(200, json={"iamToken": "t9"}))
    jar = json.dumps(
        [
            {"name": "yc_session", "value": "c1.abc", "domain": "console.yandex.cloud"},
            {"name": "yandexuid", "value": "42", "domain": "datalens.yandex.cloud"},
        ]
    )
    await CookieSessionAuth(jar, exchange_url=EXCHANGE).token()
    sent = route.calls[0].request.headers.get("cookie", "")
    assert "yc_session=c1.abc" in sent
    assert "yandexuid" not in sent


def test_cookies_scoped_to_another_domain_are_refused_up_front():
    import json

    jar = json.dumps([{"name": "yc_session", "value": "c1.abc", "domain": "datalens.yandex.cloud"}])
    with pytest.raises(PermanentError) as exc:
        CookieSessionAuth(jar, exchange_url=EXCHANGE)
    assert "datalens.yandex.cloud" in str(exc.value)


@respx.mock
async def test_a_dead_session_clears_the_discovered_endpoint():
    """A probed endpoint that starts refusing us was the wrong guess — do not keep it."""
    from app.services.yandex.auth import _discovered

    respx.get("https://console.yandex.cloud/api/iam/token").mock(
        return_value=httpx.Response(200, json={"iamToken": "t" * 40})
    )
    auth = CookieSessionAuth("yc_session=c1.abcdef.yc", exchange_url="")
    await auth.token()
    assert _discovered

    respx.get("https://console.yandex.cloud/api/iam/token").mock(
        return_value=httpx.Response(401)
    )
    fresh = CookieSessionAuth("yc_session=c1.abcdef.yc", exchange_url="")
    with pytest.raises(ReauthRequired):
        await fresh.token()
    assert not _discovered


@respx.mock
async def test_a_short_token_is_accepted_from_a_configured_field():
    """The configured field name is an instruction; its value is not second-guessed."""
    respx.get(EXCHANGE).mock(return_value=httpx.Response(200, json={"iamToken": "t9"}))
    assert await CookieSessionAuth(COOKIES, exchange_url=EXCHANGE).token() == "t9"


@respx.mock
async def test_a_network_failure_during_exchange_is_transient_not_fatal():
    from app.core.exceptions import TransientError

    respx.get(EXCHANGE).mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(TransientError):
        await CookieSessionAuth(COOKIES, exchange_url=EXCHANGE).token()

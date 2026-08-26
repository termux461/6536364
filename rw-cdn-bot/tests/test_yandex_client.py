import httpx
import pytest
import respx

from app.services.yandex.client import YandexCloudClient, bool_option

KEY = {
    "id": "key-id",
    "service_account_id": "sa-id",
    "private_key": "-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----\n",
}


def test_dns_challenge_extraction():
    certificate = {
        "id": "cert-1",
        "domains": ["cdn.example.com"],
        "challenges": [
            {
                "domain": "cdn.example.com",
                "type": "DNS",
                "dnsChallenge": {
                    "name": "_acme-challenge.cdn.example.com.",
                    "type": "CNAME",
                    "value": "cert-1.cm.yandexcloud.net.",
                },
            }
        ],
    }
    challenge = YandexCloudClient.dns_challenge(certificate, "cdn.example.com")
    assert challenge == {
        "name": "_acme-challenge.cdn.example.com",
        "type": "CNAME",
        "value": "cert-1.cm.yandexcloud.net",
    }


def test_cdn_options_disable_everything_that_would_break_xhttp():
    client = YandexCloudClient(KEY, "folder-1")
    options = client._vpn_resource_options("origin.example.com")
    assert options["disableCache"] == bool_option(True)
    assert options["gzipOn"]["value"] is False
    assert options["slice"]["value"] is False
    assert options["browserCacheSettings"]["value"] == "0"
    # Host header must be pinned to the origin domain
    assert options["hostOptions"]["host"]["value"] == "origin.example.com"
    assert options["allowedHttpMethods"]["value"] == ["GET", "HEAD", "OPTIONS"]


def test_malformed_service_account_key_is_permanent_error():
    from app.core.exceptions import PermanentError

    with pytest.raises(PermanentError):
        YandexCloudClient({"nope": True}, "folder-1")


# ------------------------------------------------------------- access preflight

CM = "https://certificate-manager.api.cloud.yandex.net/certificate-manager/v1"
CDN = "https://cdn.api.cloud.yandex.net/cdn/v1"
DNS = "https://dns.api.cloud.yandex.net/dns/v1"


class StubAuth:
    kind = "stub"

    async def token(self) -> str:
        return "iam-token"


def _client():
    from app.services.yandex.client import YandexCloudClient

    return YandexCloudClient(folder_id="folder-1", auth=StubAuth())


@respx.mock
async def test_access_ok_when_both_services_answer():
    respx.get(f"{CM}/certificates").mock(return_value=httpx.Response(200, json={"certificates": []}))
    respx.get(f"{CDN}/resources").mock(return_value=httpx.Response(200, json={"resources": []}))

    report = await _client().check_access()
    assert report.ok
    assert report.missing_roles() == []


@respx.mock
async def test_missing_certificate_role_is_named():
    respx.get(f"{CM}/certificates").mock(return_value=httpx.Response(403, text="permission denied"))
    respx.get(f"{CDN}/resources").mock(return_value=httpx.Response(200, json={"resources": []}))

    report = await _client().check_access()
    assert report.ok is False
    assert report.missing_roles() == ["certificate-manager.editor"]
    assert "certificate-manager.editor" in report.describe()


@respx.mock
async def test_missing_cdn_role_is_named():
    respx.get(f"{CM}/certificates").mock(return_value=httpx.Response(200, json={"certificates": []}))
    respx.get(f"{CDN}/resources").mock(return_value=httpx.Response(403, text="permission denied"))

    report = await _client().check_access()
    assert report.missing_roles() == ["cdn.editor"]


@respx.mock
async def test_dns_role_is_only_checked_when_yandex_dns_is_used():
    respx.get(f"{CM}/certificates").mock(return_value=httpx.Response(200, json={"certificates": []}))
    respx.get(f"{CDN}/resources").mock(return_value=httpx.Response(200, json={"resources": []}))
    zones = respx.get(f"{DNS}/zones").mock(return_value=httpx.Response(403))

    assert (await _client().check_access(need_dns=False)).ok
    assert not zones.called

    report = await _client().check_access(need_dns=True)
    assert report.missing_roles() == ["dns.editor"]


@respx.mock
async def test_outage_is_reported_separately_from_a_permission_problem():
    respx.get(f"{CM}/certificates").mock(return_value=httpx.Response(500, text="boom"))
    respx.get(f"{CDN}/resources").mock(return_value=httpx.Response(200, json={"resources": []}))

    report = await _client().check_access()
    assert report.denied == []          # not a role problem
    assert report.failed                # but not healthy either
    assert report.ok is False


@respx.mock
async def test_timeout_reason_is_never_blank():
    """Timeouts stringify to '', which used to render as a message ending in a bare colon."""
    respx.get(f"{CM}/certificates").mock(side_effect=httpx.ConnectTimeout(""))
    respx.get(f"{CDN}/resources").mock(return_value=httpx.Response(200, json={"resources": []}))

    report = await _client().check_access()
    assert report.denied == []
    reason = report.describe_failed()
    assert reason.strip()
    assert "таймаут" in reason


@respx.mock
async def test_one_shared_cause_is_reported_once():
    """All probes failing for the same reason is one problem, not one per service."""
    respx.get(f"{CM}/certificates").mock(side_effect=httpx.ConnectError(""))
    respx.get(f"{CDN}/resources").mock(side_effect=httpx.ConnectError(""))

    report = await _client().check_access()
    assert report.describe_failed().count("\n") == 0


@respx.mock
async def test_denied_and_failed_are_described_separately():
    respx.get(f"{CM}/certificates").mock(return_value=httpx.Response(403))
    respx.get(f"{CDN}/resources").mock(side_effect=httpx.ConnectTimeout(""))

    report = await _client().check_access()
    assert "certificate-manager.editor" in report.describe_denied()
    assert "certificate-manager.editor" not in report.describe_failed()


# --------------------------------------------------- discovery & role granting

RM = "https://resource-manager.api.cloud.yandex.net/resource-manager/v1"
IAM_API = "https://iam.api.cloud.yandex.net/iam/v1"


@respx.mock
async def test_discover_scope_lists_clouds_and_their_folders():
    respx.get(f"{RM}/clouds").mock(
        return_value=httpx.Response(200, json={"clouds": [{"id": "cl1", "name": "my-cloud"}]})
    )
    respx.get(f"{RM}/folders").mock(
        return_value=httpx.Response(200, json={"folders": [{"id": "fl1", "name": "default"}]})
    )
    scope = await _client().discover_scope()
    assert scope["clouds"][0]["id"] == "cl1"
    assert scope["folders"]["cl1"][0]["id"] == "fl1"


@respx.mock
async def test_user_id_resolved_from_login():
    respx.get(f"{IAM_API}/yandexPassportUserAccounts:byLogin").mock(
        return_value=httpx.Response(200, json={"id": "aje123", "yandexPassportUserAccount": {}})
    )
    assert await _client().user_id_by_login("@test-user") == "aje123"


@respx.mock
async def test_unknown_login_returns_none_instead_of_raising():
    respx.get(f"{IAM_API}/yandexPassportUserAccounts:byLogin").mock(
        return_value=httpx.Response(404)
    )
    assert await _client().user_id_by_login("nobody") is None


@respx.mock
async def test_grant_uses_add_deltas_never_a_full_rewrite():
    """setAccessBindings would wipe the customer's existing roles — only ADD deltas allowed."""
    route = respx.post(f"{RM}/folders/fl1:updateAccessBindings").mock(
        return_value=httpx.Response(200, json={"done": True, "response": {}})
    )
    await _client().grant_roles(
        "fl1", subject_id="aje123", subject_type="userAccount", roles=["cdn.editor"]
    )
    body = route.calls[0].request.read().decode()
    assert '"action": "ADD"' in body or '"action":"ADD"' in body
    assert "setAccessBindings" not in str(route.calls[0].request.url)


@respx.mock
async def test_ensure_roles_returns_false_when_not_allowed_to_grant():
    """A locked-down credential cannot grant to itself — that is expected, not an error."""
    respx.get(f"{CM}/certificates").mock(return_value=httpx.Response(403))
    respx.get(f"{CDN}/resources").mock(return_value=httpx.Response(200, json={"resources": []}))
    respx.post(f"{RM}/folders/fl1:updateAccessBindings").mock(return_value=httpx.Response(403))

    client = _client()
    report = await client.check_access()
    granted = await client.ensure_roles(
        "fl1", report, subject={"id": "aje123", "type": "userAccount"}
    )
    assert granted is False


@respx.mock
async def test_ensure_roles_is_a_noop_without_a_subject():
    respx.get(f"{CM}/certificates").mock(return_value=httpx.Response(403))
    respx.get(f"{CDN}/resources").mock(return_value=httpx.Response(200, json={"resources": []}))

    client = _client()
    report = await client.check_access()
    assert await client.ensure_roles("fl1", report, subject={}) is False


# --------------------------------------------------------------- pagination


@respx.mock
async def test_list_endpoints_read_every_page():
    """Yandex caps a page at 100 items. Reading only the first one made `find_*` miss
    resources that already exist, so a re-run created a duplicate instead of reusing them."""
    pages = {
        None: httpx.Response(200, json={"resources": [{"cname": "a"}], "nextPageToken": "p2"}),
        "p2": httpx.Response(200, json={"resources": [{"cname": "b"}], "nextPageToken": "p3"}),
        "p3": httpx.Response(200, json={"resources": [{"cname": "c"}]}),
    }

    def _respond(request):
        return pages[request.url.params.get("pageToken")]

    respx.get(f"{CDN}/resources").mock(side_effect=_respond)

    resources = await _client().list_cdn_resources()
    assert [r["cname"] for r in resources] == ["a", "b", "c"]


@respx.mock
async def test_find_cdn_resource_looks_past_the_first_page():
    pages = {
        None: httpx.Response(200, json={"resources": [{"cname": "other"}], "nextPageToken": "p2"}),
        "p2": httpx.Response(200, json={"resources": [{"cname": "cdn.example.com", "id": "r1"}]}),
    }
    respx.get(f"{CDN}/resources").mock(
        side_effect=lambda request: pages[request.url.params.get("pageToken")]
    )
    found = await _client().find_cdn_resource("cdn.example.com")
    assert found is not None
    assert found["id"] == "r1"


@respx.mock
async def test_pagination_stops_on_a_repeated_token():
    """A server that keeps handing back the same token must not spin forever."""
    route = respx.get(f"{DNS}/zones").mock(
        return_value=httpx.Response(
            200, json={"dnsZones": [{"zone": "example.com."}], "nextPageToken": "same"}
        )
    )
    zones = await _client().list_dns_zones()
    assert route.call_count == 2  # the page after the repeat is not requested again
    assert all(zone["zone"] == "example.com." for zone in zones)


@respx.mock
async def test_a_network_failure_is_retried_not_raised_as_httpx():
    """httpx errors are not OSError, so without translation retry_async never sees them."""
    from unittest.mock import AsyncMock, patch

    route = respx.get(f"{CDN}/resources").mock(
        side_effect=[
            httpx.ConnectError("boom"),
            httpx.Response(200, json={"resources": [{"cname": "a"}]}),
        ]
    )
    with patch("app.core.retry.asyncio.sleep", new=AsyncMock()):
        resources = await _client().list_cdn_resources(attempts=2)
    assert [r["cname"] for r in resources] == ["a"]
    assert route.call_count == 2


@respx.mock
async def test_wait_operation_tolerates_an_empty_body():
    """A 204 leaves the operation as None — a completed call with nothing to poll."""
    assert await _client().wait_operation(None) == {}

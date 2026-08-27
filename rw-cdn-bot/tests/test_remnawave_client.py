import httpx
import pytest
import respx

from app.services.remnawave import RemnawaveClient
from app.services.remnawave.dialects import V2, V3, ApiVersion, dialect_for, version_from_metadata
from app.services.remnawave.templates import (
    HOST_ALPN,
    HOST_FINGERPRINT,
    INBOUND_TAG,
    PROFILE_NAME,
    XHTTP_EXTRA,
    XHTTP_MODE,
    XHTTP_PATH,
    XRAY_PORT,
    build_host_payload,
    build_profile_config,
)

BASE = "https://panel.example.com/api"


def test_profile_config_matches_the_guide():
    config = build_profile_config()
    inbound = config["inbounds"][0]
    assert inbound["tag"] == INBOUND_TAG == "XHTTP_LTE_YANDEX"
    assert inbound["listen"] == "127.0.0.1"
    assert inbound["port"] == XRAY_PORT == 2090
    assert inbound["protocol"] == "vless"
    stream = inbound["streamSettings"]
    assert stream["network"] == "xhttp"
    assert stream["security"] == "none"
    assert stream["xhttpSettings"]["mode"] == XHTTP_MODE == "packet-up"
    assert stream["xhttpSettings"]["path"] == XHTTP_PATH == "/api/v1/sync"
    assert stream["xhttpSettings"]["extra"] == XHTTP_EXTRA


def test_padding_and_pacing_match_the_guide():
    extra = build_profile_config()["inbounds"][0]["streamSettings"]["xhttpSettings"]["extra"]
    assert extra["xPaddingKey"] == "_dc"
    assert extra["xPaddingHeader"] == "X-Cache"
    assert extra["xPaddingMethod"] == "tokenish"
    assert extra["xPaddingPlacement"] == "queryInHeader"
    assert extra["xPaddingObfsMode"] is True
    assert extra["uplinkHTTPMethod"] == "GET"
    assert extra["scMaxEachPostBytes"] == 524288
    assert extra["scMaxConcurrentPosts"] == 1
    assert extra["scMinPostsIntervalMs"] == 150


def test_routing_sends_the_inbound_straight_out_with_no_cascade():
    config = build_profile_config()
    assert {o["tag"] for o in config["outbounds"]} == {"DIRECT", "BLOCK"}
    rules = config["routing"]["rules"]
    assert rules == [{"type": "field", "inboundTag": [INBOUND_TAG], "outboundTag": "DIRECT"}]
    # nothing foreign, nothing geo-based
    assert "geoip" not in str(config)
    assert "geosite" not in str(config)


def test_host_extra_matches_the_inbound_exactly():
    """A mismatch between the two ends is a silent failure, so pin them together."""
    inbound_extra = build_profile_config()["inbounds"][0]["streamSettings"]["xhttpSettings"]["extra"]
    host = build_host_payload(
        profile_uuid="p", inbound_uuid="i", cdn_domain="cdn.example.com", node_uuid="n"
    )
    assert host["xHttpExtraParams"] == inbound_extra


def test_host_points_at_cdn_domain_not_yandex_cname():
    payload = build_host_payload(
        profile_uuid="p", inbound_uuid="i", cdn_domain="cdn.example.com", node_uuid="n"
    )
    assert payload["address"] == "cdn.example.com"
    assert payload["sni"] == "cdn.example.com"
    assert payload["host"] == "cdn.example.com"
    assert payload["port"] == 443
    assert payload["alpn"] == HOST_ALPN == "h2,http/1.1"
    assert payload["fingerprint"] == HOST_FINGERPRINT == "chrome"
    assert payload["path"] == XHTTP_PATH



# ------------------------------------------------------ v2 / v3 test scaffolding

METADATA = f"{BASE}/system/metadata"


def mock_panel(version: str) -> None:
    """Stub the version probe the client runs when it connects.

    v3 answers /system/metadata with its version; v2 has no such route and answers 404.
    """
    if version == "v3":
        respx.get(METADATA).mock(
            return_value=httpx.Response(200, json={"response": {"version": "3.1.2"}})
        )
    else:
        respx.get(METADATA).mock(return_value=httpx.Response(404))


def panel(version: str = "v3", token: str = "token") -> RemnawaveClient:
    mock_panel(version)
    return RemnawaveClient("https://panel.example.com", token)


BOTH = pytest.mark.parametrize("version", ["v2", "v3"])


# --------------------------------------------------------- version detection


def test_api_version_parses_whatever_the_panel_or_an_admin_writes():
    assert ApiVersion.parse("v3") is ApiVersion.V3
    assert ApiVersion.parse("3") is ApiVersion.V3
    assert ApiVersion.parse("3.1.2") is ApiVersion.V3
    assert ApiVersion.parse(" V2 ") is ApiVersion.V2
    assert ApiVersion.parse("") is ApiVersion.AUTO
    assert ApiVersion.parse(None) is ApiVersion.AUTO
    assert ApiVersion.parse("auto") is ApiVersion.AUTO
    assert ApiVersion.parse("4.0.0") is ApiVersion.AUTO  # unknown major, not silently v3


def test_version_is_read_from_the_metadata_body():
    assert version_from_metadata({"version": "3.0.0"}) is ApiVersion.V3
    assert version_from_metadata({"version": "2.9.9"}) is ApiVersion.V2
    assert version_from_metadata({"nothing": "here"}) is None
    assert version_from_metadata("not a dict") is None


def test_auto_falls_back_to_a_dialect_not_to_auto():
    assert dialect_for(ApiVersion.AUTO).version is not ApiVersion.AUTO
    assert dialect_for(None).version is not ApiVersion.AUTO


@respx.mock
async def test_v3_is_detected_from_system_metadata():
    async with panel("v3") as client:
        assert client.version is ApiVersion.V3
        assert client.panel_version == "3.1.2"
        assert "3.1.2" in client.describe()


@respx.mock
async def test_a_panel_without_metadata_is_v2():
    """The endpoint was added in v3, so its absence is an answer, not a failure."""
    async with panel("v2") as client:
        assert client.version is ApiVersion.V2
        assert client.panel_version is None


@respx.mock
async def test_a_pinned_version_skips_the_probe():
    probe = respx.get(METADATA)
    async with RemnawaveClient("https://panel.example.com", "token", api_version="v2") as client:
        assert client.version is ApiVersion.V2
    assert not probe.called


@respx.mock
async def test_a_refused_token_is_not_mistaken_for_a_version():
    from app.core.exceptions import RemnawaveAPIError

    respx.get(METADATA).mock(return_value=httpx.Response(401, text="unauthorized"))
    with pytest.raises(RemnawaveAPIError):
        async with RemnawaveClient("https://panel.example.com", "bad"):
            pass


@respx.mock
async def test_an_unreachable_panel_leaves_the_default_dialect():
    from app.services.remnawave.dialects import DEFAULT_VERSION

    respx.get(METADATA).mock(side_effect=httpx.ConnectError("boom"))
    async with RemnawaveClient("https://panel.example.com", "token") as client:
        assert client.version is DEFAULT_VERSION


# ------------------------------------------------------------ dialect payloads


def test_the_xhttp_field_is_renamed_in_v3():
    """v2 spells it xHttpExtraParams, v3 xhttpExtraParams. Same block, different key."""
    args = {"profile_uuid": "p", "inbound_uuid": "i", "cdn_domain": "cdn.example.com"}
    assert "xHttpExtraParams" in V2.host_payload(**args)
    assert "xhttpExtraParams" not in V2.host_payload(**args)
    assert "xhttpExtraParams" in V3.host_payload(**args)
    assert "xHttpExtraParams" not in V3.host_payload(**args)


def test_host_to_node_binding_is_v3_only():
    """CreateHostRequestDto has no `nodes` field on v2 — sending it risks a 400."""
    args = {"profile_uuid": "p", "inbound_uuid": "i", "cdn_domain": "cdn.example.com"}
    assert "nodes" not in V2.host_payload(**args, node_uuid="n")
    assert V3.host_payload(**args, node_uuid="n")["nodes"] == ["n"]


def test_host_hidden_flag_uses_the_documented_name():
    """`isHostHidden` is in neither contract; a strict panel rejects unknown properties."""
    payload = build_host_payload(profile_uuid="p", inbound_uuid="i", cdn_domain="cdn.example.com")
    assert payload["isHidden"] is False
    assert "isHostHidden" not in payload


@BOTH
def test_both_dialects_carry_the_same_scheme_values(version):
    dialect = dialect_for(version)
    payload = dialect.host_payload(
        profile_uuid="p", inbound_uuid="i", cdn_domain="cdn.example.com"
    )
    assert payload["address"] == payload["sni"] == payload["host"] == "cdn.example.com"
    assert payload["port"] == 443
    assert payload["path"] == XHTTP_PATH
    assert payload[dialect.host_xhttp_field] == XHTTP_EXTRA


@respx.mock
async def test_created_host_uses_the_dialect_of_the_connected_panel():
    mock_panel("v2")
    route = respx.post(f"{BASE}/hosts").mock(
        return_value=httpx.Response(201, json={"response": {"uuid": "h1"}})
    )
    async with RemnawaveClient("https://panel.example.com", "token") as client:
        await client.create_host(profile_uuid="p", inbound_uuid="i", cdn_domain="cdn.example.com")
    import json as _json

    body = _json.loads(route.calls[0].request.read())
    assert "xHttpExtraParams" in body  # the panel said v2, so the v2 spelling went out


# ------------------------------------------------------------------- requests


@BOTH
@respx.mock
async def test_ensure_profile_reuses_existing(version):
    respx.get(f"{BASE}/config-profiles").mock(
        return_value=httpx.Response(200, json={"response": {"configProfiles": [
            {"uuid": "existing", "name": PROFILE_NAME}
        ]}})
    )
    create = respx.post(f"{BASE}/config-profiles")
    async with panel(version) as client:
        profile = await client.ensure_profile()
    assert profile["uuid"] == "existing"
    assert not create.called


@BOTH
@respx.mock
async def test_ensure_node_reuses_by_address(version):
    respx.get(f"{BASE}/nodes").mock(
        return_value=httpx.Response(200, json={"response": {"nodes": [
            {"uuid": "node-1", "address": "203.0.113.10"}
        ]}})
    )
    create = respx.post(f"{BASE}/nodes")
    async with panel(version) as client:
        node = await client.ensure_node(
            name="CDN", address="203.0.113.10", profile_uuid="p", inbound_uuid="i"
        )
    assert node["uuid"] == "node-1"
    assert not create.called


@respx.mock
async def test_api_error_is_raised_with_context():
    from app.core.exceptions import RemnawaveAPIError

    respx.get(f"{BASE}/config-profiles").mock(return_value=httpx.Response(401, text="unauthorized"))
    async with panel("v3", token="bad") as client:
        with pytest.raises(RemnawaveAPIError) as exc:
            await client.list_profiles()
    assert exc.value.status == 401


@respx.mock
async def test_node_secret_falls_back_to_keygen_on_v2():
    """v2 answers GET /keygen with {"pubKey": ...}."""
    respx.get(f"{BASE}/nodes/node-1").mock(
        return_value=httpx.Response(200, json={"response": {"uuid": "node-1", "address": "203.0.113.10"}})
    )
    respx.get(f"{BASE}/keygen").mock(
        return_value=httpx.Response(200, json={"response": {"pubKey": "CERT-FROM-PANEL"}})
    )
    async with panel("v2") as client:
        assert await client.node_install_secret("node-1") == "CERT-FROM-PANEL"


@respx.mock
async def test_node_secret_reads_the_renamed_field_on_v3():
    """v3 renamed the same field to secretKey. Same endpoint, same meaning."""
    respx.get(f"{BASE}/nodes/node-1").mock(
        return_value=httpx.Response(200, json={"response": {"uuid": "node-1"}})
    )
    respx.get(f"{BASE}/keygen").mock(
        return_value=httpx.Response(200, json={"response": {"secretKey": "CERT-V3"}})
    )
    async with panel("v3") as client:
        assert await client.node_install_secret("node-1") == "CERT-V3"


@BOTH
@respx.mock
async def test_keygen_reads_either_field_whatever_the_dialect(version):
    """A panel caught mid-upgrade may answer with the other name — take it either way."""
    respx.get(f"{BASE}/keygen").mock(
        return_value=httpx.Response(200, json={"response": {"pubKey": "EITHER"}})
    )
    async with panel(version) as client:
        assert await client.keygen_secret() == "EITHER"


@respx.mock
async def test_node_secret_override_wins_and_skips_the_api():
    nodes = respx.get(f"{BASE}/nodes/node-1")
    async with panel("v3") as client:
        assert await client.node_install_secret("node-1", override="  MANUAL  ") == "MANUAL"
    assert not nodes.called


@respx.mock
async def test_keygen_falls_back_to_the_pub_key_path():
    """`/keygen` is the documented route in both majors; some builds expose /keygen/pub-key."""
    respx.get(f"{BASE}/keygen").mock(return_value=httpx.Response(404))
    respx.get(f"{BASE}/keygen/pub-key").mock(
        return_value=httpx.Response(200, json={"response": {"secretKey": "ALT-PATH-CERT"}})
    )
    async with panel("v3") as client:
        assert await client.keygen_secret() == "ALT-PATH-CERT"


@respx.mock
async def test_missing_secret_raises_unsupported_operation():
    from app.core.exceptions import RemnawaveUnsupportedOperation

    respx.get(f"{BASE}/nodes/node-1").mock(
        return_value=httpx.Response(200, json={"response": {"uuid": "node-1"}})
    )
    respx.get(f"{BASE}/keygen/pub-key").mock(return_value=httpx.Response(404))
    respx.get(f"{BASE}/keygen").mock(return_value=httpx.Response(404))
    async with panel("v3") as client:
        with pytest.raises(RemnawaveUnsupportedOperation):
            await client.node_install_secret("node-1")


# ------------------------------------------------------------ update routing


@BOTH
@respx.mock
async def test_updates_patch_the_collection_with_the_uuid_in_the_body(version):
    """There is no `PATCH /nodes/{uuid}` in either major — it answers 404.

    Every update DTO (UpdateNodeRequestDto, UpdateHostRequestDto, ...) carries the uuid in
    the body and the route is the collection itself.
    """
    import json as _json

    collection = respx.patch(f"{BASE}/nodes").mock(
        return_value=httpx.Response(200, json={"response": {"uuid": "node-1"}})
    )
    per_uuid = respx.patch(f"{BASE}/nodes/node-1")

    async with panel(version) as client:
        await client.update_node("node-1", name="renamed")

    assert not per_uuid.called
    body = _json.loads(collection.calls[0].request.read())
    assert body == {"uuid": "node-1", "name": "renamed"}


@BOTH
@respx.mock
async def test_host_update_patches_the_collection(version):
    collection = respx.patch(f"{BASE}/hosts").mock(
        return_value=httpx.Response(200, json={"response": {"uuid": "h1"}})
    )
    async with panel(version) as client:
        await client.update_host("h1", address="cdn.example.com")
    assert collection.called


@BOTH
@respx.mock
async def test_profile_update_patches_the_collection(version):
    collection = respx.patch(f"{BASE}/config-profiles").mock(
        return_value=httpx.Response(200, json={"response": {"uuid": "p1"}})
    )
    async with panel(version) as client:
        await client.update_profile("p1", {"inbounds": []})
    assert collection.called


@BOTH
@respx.mock
async def test_squads_get_the_new_inbound_through_the_collection_route(version):
    """This is what actually hands the inbound out to users — a 404 here is silent breakage."""
    import json as _json

    respx.get(f"{BASE}/internal-squads").mock(
        return_value=httpx.Response(200, json={"response": {"internalSquads": [
            {"uuid": "squad-1", "inbounds": [{"uuid": "old"}]},
            {"uuid": "squad-2", "inbounds": [{"uuid": "i-new"}]},  # already has it
        ]}})
    )
    collection = respx.patch(f"{BASE}/internal-squads").mock(
        return_value=httpx.Response(200, json={"response": {}})
    )
    per_uuid = respx.patch(f"{BASE}/internal-squads/squad-1")

    async with panel(version) as client:
        assert await client.add_inbound_to_squads("i-new") == 1

    assert not per_uuid.called
    body = _json.loads(collection.calls[0].request.read())
    assert body == {"uuid": "squad-1", "inbounds": ["old", "i-new"]}


@respx.mock
async def test_v3_creation_status_201_is_not_an_error():
    """v3 answers POST with 201 where v2 answered 200."""
    respx.post(f"{BASE}/config-profiles").mock(
        return_value=httpx.Response(201, json={"response": {"uuid": "p1"}})
    )
    async with panel("v3") as client:
        assert (await client.create_profile())["uuid"] == "p1"


@respx.mock
async def test_v3_delete_returns_204_with_no_body():
    """v3 returns 204 and an empty body where v2 returned 200 with JSON."""
    respx.delete(f"{BASE}/hosts/h1").mock(return_value=httpx.Response(204))
    async with panel("v3") as client:
        assert await client.delete_host("h1") is None


@BOTH
@respx.mock
async def test_error_bodies_are_reported_by_their_message_not_as_raw_json(version):
    """Both majors answer errors with {message, errorCode}; v3 only types the envelope."""
    from app.core.exceptions import RemnawaveAPIError

    respx.post(f"{BASE}/hosts").mock(
        return_value=httpx.Response(
            400,
            json={
                "timestamp": "2026-01-01T00:00:00Z",
                "path": "/api/hosts",
                "message": "port must be an integer",
                "errorCode": "A032",
            },
        )
    )
    async with panel(version) as client:
        with pytest.raises(RemnawaveAPIError) as exc:
            await client.create_host(profile_uuid="p", inbound_uuid="i", cdn_domain="c")
    assert "port must be an integer" in str(exc.value)
    assert "A032" in str(exc.value)
    assert "timestamp" not in str(exc.value)


@respx.mock
async def test_a_validation_error_list_is_joined_into_one_line():
    from app.core.exceptions import RemnawaveAPIError

    respx.post(f"{BASE}/hosts").mock(
        return_value=httpx.Response(400, json={"message": ["address required", "port required"]})
    )
    async with panel("v3") as client:
        with pytest.raises(RemnawaveAPIError) as exc:
            await client.create_host(profile_uuid="p", inbound_uuid="i", cdn_domain="c")
    assert "address required; port required" in str(exc.value)


@respx.mock
async def test_a_non_json_error_body_still_reaches_the_admin():
    from app.core.exceptions import RemnawaveAPIError

    respx.post(f"{BASE}/hosts").mock(return_value=httpx.Response(400, text="<html>bad</html>"))
    async with panel("v3") as client:
        with pytest.raises(RemnawaveAPIError) as exc:
            await client.create_host(profile_uuid="p", inbound_uuid="i", cdn_domain="c")
    assert "bad" in str(exc.value)


@respx.mock
async def test_a_failed_probe_does_not_leak_the_transport():
    """__aexit__ never runs when __aenter__ raises, so the client closes itself."""
    from app.core.exceptions import RemnawaveAPIError

    respx.get(METADATA).mock(return_value=httpx.Response(403, text="forbidden"))
    client = RemnawaveClient("https://panel.example.com", "bad")
    with pytest.raises(RemnawaveAPIError):
        await client.__aenter__()
    assert client._client is None

import httpx
import pytest
import respx

from app.services.remnawave import RemnawaveClient
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


@respx.mock
async def test_ensure_profile_reuses_existing():
    respx.get(f"{BASE}/config-profiles").mock(
        return_value=httpx.Response(200, json={"response": {"configProfiles": [
            {"uuid": "existing", "name": PROFILE_NAME}
        ]}})
    )
    create = respx.post(f"{BASE}/config-profiles")
    async with RemnawaveClient("https://panel.example.com", "token") as client:
        profile = await client.ensure_profile()
    assert profile["uuid"] == "existing"
    assert not create.called


@respx.mock
async def test_ensure_node_reuses_by_address():
    respx.get(f"{BASE}/nodes").mock(
        return_value=httpx.Response(200, json={"response": {"nodes": [
            {"uuid": "node-1", "address": "203.0.113.10"}
        ]}})
    )
    create = respx.post(f"{BASE}/nodes")
    async with RemnawaveClient("https://panel.example.com", "token") as client:
        node = await client.ensure_node(
            name="CDN", address="203.0.113.10", profile_uuid="p", inbound_uuid="i"
        )
    assert node["uuid"] == "node-1"
    assert not create.called


@respx.mock
async def test_api_error_is_raised_with_context():
    from app.core.exceptions import RemnawaveAPIError

    respx.get(f"{BASE}/config-profiles").mock(return_value=httpx.Response(401, text="unauthorized"))
    async with RemnawaveClient("https://panel.example.com", "bad") as client:
        with pytest.raises(RemnawaveAPIError) as exc:
            await client.list_profiles()
    assert exc.value.status == 401


@respx.mock
async def test_node_secret_falls_back_to_keygen():
    respx.get(f"{BASE}/nodes/node-1").mock(
        return_value=httpx.Response(200, json={"response": {"uuid": "node-1", "address": "203.0.113.10"}})
    )
    respx.get(f"{BASE}/keygen/pub-key").mock(
        return_value=httpx.Response(200, json={"response": {"pubKey": "CERT-FROM-PANEL"}})
    )
    async with RemnawaveClient("https://panel.example.com", "token") as client:
        assert await client.node_install_secret("node-1") == "CERT-FROM-PANEL"


@respx.mock
async def test_node_secret_override_wins_and_skips_the_api():
    nodes = respx.get(f"{BASE}/nodes/node-1")
    async with RemnawaveClient("https://panel.example.com", "token") as client:
        assert await client.node_install_secret("node-1", override="  MANUAL  ") == "MANUAL"
    assert not nodes.called


@respx.mock
async def test_keygen_legacy_path_is_tried_when_new_one_is_absent():
    respx.get(f"{BASE}/keygen/pub-key").mock(return_value=httpx.Response(404))
    respx.get(f"{BASE}/keygen").mock(
        return_value=httpx.Response(200, json={"response": {"secretKey": "LEGACY-CERT"}})
    )
    async with RemnawaveClient("https://panel.example.com", "token") as client:
        assert await client.keygen_secret() == "LEGACY-CERT"


@respx.mock
async def test_missing_secret_raises_unsupported_operation():
    from app.core.exceptions import RemnawaveUnsupportedOperation

    respx.get(f"{BASE}/nodes/node-1").mock(
        return_value=httpx.Response(200, json={"response": {"uuid": "node-1"}})
    )
    respx.get(f"{BASE}/keygen/pub-key").mock(return_value=httpx.Response(404))
    respx.get(f"{BASE}/keygen").mock(return_value=httpx.Response(404))
    async with RemnawaveClient("https://panel.example.com", "token") as client:
        with pytest.raises(RemnawaveUnsupportedOperation):
            await client.node_install_secret("node-1")

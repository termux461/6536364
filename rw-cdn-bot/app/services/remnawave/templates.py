"""Fixed technical parameters of the scheme.

Everything here has to agree across three places at once — the Xray inbound, the nginx
location and the Remnawave host. Change one without the others and the tunnel stops working,
so they all read from this module and nothing hardcodes them anywhere else.

    Client -> CDN Domain -> Yandex Cloud CDN -> Origin Domain -> Origin Server
           -> Nginx :443 -> 127.0.0.1:2090 -> Remnawave Node / Xray

There is no cascade, no foreign outbound and no geo-based routing anywhere in this project.

The current values follow the VLESS + XHTTP + Yandex CDN guide (`packet-up` transport on
`/api/v1/sync`). An earlier revision used `auto` on `/video/download` with a different
padding set; if you ever need to go back, this file is the only place to edit — see
PROFILE_ALTERNATIVES at the bottom.
"""
from __future__ import annotations

PROFILE_NAME = "cdn"
INBOUND_TAG = "XHTTP_LTE_YANDEX"
XHTTP_PATH = "/api/v1/sync"
XHTTP_MODE = "packet-up"
XRAY_LISTEN = "127.0.0.1"
XRAY_PORT = 2090
NODE_PORT = 2222
HOST_PORT = 443

HOST_ALPN = "h2,http/1.1"
HOST_FINGERPRINT = "chrome"

# HTTP methods the CDN is allowed to forward. packet-up carries uplink data on GET, and HEAD
# comes along with it; OPTIONS is allowed as well because a CORS preflight from a browser-based
# client is answered by Xray, and a 405 from the edge would kill the connection before the
# tunnel ever opens. Anything else stays blocked.
CDN_HTTP_METHODS = ["GET", "HEAD", "OPTIONS"]

# The xHTTP "extra" block, shared verbatim by the inbound and the host raw config. Any
# mismatch between the two ends shows up as a silent connection failure, which is exactly why
# both sides read this one dict.
XHTTP_EXTRA: dict = {
    "mode": XHTTP_MODE,
    "path": XHTTP_PATH,
    "xPaddingKey": "_dc",
    "xPaddingHeader": "X-Cache",
    "xPaddingMethod": "tokenish",
    "xPaddingPlacement": "queryInHeader",
    "xPaddingObfsMode": True,
    "uplinkHTTPMethod": "GET",
    "scMaxEachPostBytes": 524288,
    "scMaxConcurrentPosts": 1,
    "scMinPostsIntervalMs": 150,
}

# Tuning knobs from the guide's troubleshooting table: raise concurrency and lower the
# interval if throughput is poor. Named here rather than left as magic numbers.
XHTTP_THROUGHPUT_TUNING: dict = {
    "scMaxConcurrentPosts": 2,
    "scMinPostsIntervalMs": 80,
}


def build_profile_config() -> dict:
    """Full Xray config for the profile — one XHTTP inbound bound to loopback."""
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "tag": INBOUND_TAG,
                "listen": XRAY_LISTEN,
                "port": XRAY_PORT,
                "protocol": "vless",
                "settings": {"clients": [], "fallbacks": [], "decryption": "none"},
                "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"]},
                "streamSettings": {
                    "network": "xhttp",
                    "security": "none",
                    "xhttpSettings": {
                        "mode": XHTTP_MODE,
                        "path": XHTTP_PATH,
                        "extra": dict(XHTTP_EXTRA),
                    },
                },
            }
        ],
        "outbounds": [
            {"tag": "DIRECT", "protocol": "freedom"},
            {"tag": "BLOCK", "protocol": "blackhole"},
        ],
        "routing": {
            "domainStrategy": "IPIfNonMatch",
            # Everything from this inbound leaves the Origin Server directly. No geo rules,
            # no foreign exit — that is the whole point of the scheme.
            "rules": [
                {"type": "field", "inboundTag": [INBOUND_TAG], "outboundTag": "DIRECT"},
            ],
        },
    }


def build_host_payload(
    *,
    profile_uuid: str,
    inbound_uuid: str,
    cdn_domain: str,
    node_uuid: str | None = None,
    remark: str = PROFILE_NAME,
) -> dict:
    """Host clients actually connect to — points at the CDN domain, not the Yandex CNAME."""
    payload: dict = {
        "inbound": {"configProfileUuid": profile_uuid, "configProfileInboundUuid": inbound_uuid},
        "remark": remark,
        "address": cdn_domain,
        "port": HOST_PORT,
        "path": XHTTP_PATH,
        "sni": cdn_domain,
        "host": cdn_domain,
        "alpn": HOST_ALPN,
        "fingerprint": HOST_FINGERPRINT,
        "securityLayer": "TLS",
        "isDisabled": False,
        "overrideSniFromAddress": False,
        "isHostHidden": False,
        "xHttpExtraParams": dict(XHTTP_EXTRA),
    }
    if node_uuid:
        payload["nodes"] = [node_uuid]
    return payload


# Kept for reference: the parameter set this project shipped with before the LTE/Yandex
# guide. Not wired to anything — swapping back means editing the constants above.
PROFILE_ALTERNATIVES: dict = {
    "video-download-auto": {
        "inbound_tag": "XHTTP-cdn",
        "path": "/video/download",
        "mode": "auto",
        "port": 9001,
        "alpn": "h2",
        "fingerprint": "firefox",
    }
}

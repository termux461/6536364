"""What differs between Remnawave panel API v2 and v3.

The paths this project calls are identical in both majors — `/config-profiles`, `/nodes`,
`/hosts`, `/internal-squads`, `/keygen`, `/system/*` all live where they always did. What
changed is smaller and easier to miss, which is exactly why it is written down here instead
of being guessed at each call site:

    keygen response      v2: {"response": {"pubKey": ...}}
                         v3: {"response": {"secretKey": ...}}   (renamed, same endpoint)

    host xHTTP params    v2: "xHttpExtraParams"                 (capital H)
                         v3: "xhttpExtraParams"                 (lowercase h)

    host -> node link    v2: not part of CreateHostRequestDto
                         v3: "nodes": [uuid, ...]

    host tags            v2: "tag": "STRING"
                         v3: "tags": ["STRING", ...]

    creation status      v2: 200                                v3: 201
    delete status        v2: 200 + body                         v3: 204, empty
    background actions   v2: 200 + affected counts              v3: 202, empty

    version endpoint     v2: absent                             v3: GET /system/metadata

Sources: the v2.1.13 OpenAPI document published by the panel and the v3 request contracts in
remnawave/backend (`libs/contract`). Nothing here is inferred from behaviour.

The success envelope `{"response": ...}` is unchanged, and so are the endpoints for everything
this project touches — so a single client speaks both dialects and only the pieces above are
selected per version.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import StrEnum

from app.services.remnawave.templates import build_host_payload

logger = logging.getLogger(__name__)


class ApiVersion(StrEnum):
    """Panel major version. `AUTO` asks the client to detect it on connect."""

    AUTO = "auto"
    V2 = "v2"
    V3 = "v3"

    @classmethod
    def parse(cls, value: str | None) -> ApiVersion:
        """Accept `v3`, `3`, `3.1.2`, `V3 ` and anything else as AUTO."""
        text = (value or "").strip().lower().lstrip("v")
        if not text:
            return cls.AUTO
        if text == "auto":
            return cls.AUTO
        major = text.split(".", 1)[0]
        if major == "2":
            return cls.V2
        if major == "3":
            return cls.V3
        return cls.AUTO


# The panel reports something like "3.1.2"; only the major decides the dialect.
_VERSION_RE = re.compile(r"^\s*v?(\d+)")


def version_from_metadata(payload: object) -> ApiVersion | None:
    """Read the dialect out of a `GET /system/metadata` body.

    The endpoint exists only from v3 on, so reaching it at all is already the answer; the
    version string is still read so a future v4 is reported as unknown rather than silently
    treated as v3.
    """
    if not isinstance(payload, dict):
        return None
    raw = payload.get("version")
    if not isinstance(raw, str):
        return None
    match = _VERSION_RE.match(raw)
    if not match:
        return None
    return ApiVersion.parse(match.group(1))


@dataclass(frozen=True, slots=True)
class Dialect:
    """The version-specific half of the API surface."""

    version: ApiVersion
    # Field names holding the panel-wide node certificate, most likely first. Both are tried
    # in either dialect: the cost is one dict lookup, and a panel mid-upgrade may answer with
    # the other one.
    keygen_fields: tuple[str, ...]
    # Name of the xHTTP parameter block in a host payload. The casing changed in v3.
    host_xhttp_field: str
    # v3 accepts a host->node binding in the create payload; v2 has no such field and
    # rejects it when the panel validates unknown properties.
    supports_host_nodes: bool
    # v3 exposes GET /system/metadata. Used for detection, and worth reporting to an admin.
    supports_metadata: bool

    def host_payload(
        self,
        *,
        profile_uuid: str,
        inbound_uuid: str,
        cdn_domain: str,
        node_uuid: str | None = None,
    ) -> dict:
        """A create-host body this panel version will accept.

        The values all come from `templates.py` — this only decides what the fields are
        called and which of them exist in this major.
        """
        return build_host_payload(
            profile_uuid=profile_uuid,
            inbound_uuid=inbound_uuid,
            cdn_domain=cdn_domain,
            node_uuid=node_uuid if self.supports_host_nodes else None,
            xhttp_field=self.host_xhttp_field,
        )

    def describe(self) -> str:
        return {
            ApiVersion.V2: "Remnawave API v2",
            ApiVersion.V3: "Remnawave API v3",
        }.get(self.version, f"Remnawave API {self.version}")


V2 = Dialect(
    version=ApiVersion.V2,
    keygen_fields=("pubKey", "secretKey"),
    host_xhttp_field="xHttpExtraParams",
    supports_host_nodes=False,
    supports_metadata=False,
)

V3 = Dialect(
    version=ApiVersion.V3,
    keygen_fields=("secretKey", "pubKey"),
    host_xhttp_field="xhttpExtraParams",
    supports_host_nodes=True,
    supports_metadata=True,
)

DIALECTS: dict[ApiVersion, Dialect] = {ApiVersion.V2: V2, ApiVersion.V3: V3}

# What an undetected panel is treated as. v3 is the current major, and a v2 panel is
# identified positively (no /system/metadata), so the fallback only applies when detection
# itself failed — a network blip, or a proxy swallowing the 404.
DEFAULT_VERSION = ApiVersion.V3


def dialect_for(version: ApiVersion | str | None) -> Dialect:
    parsed = version if isinstance(version, ApiVersion) else ApiVersion.parse(version)
    if parsed is ApiVersion.AUTO:
        parsed = DEFAULT_VERSION
    return DIALECTS[parsed]

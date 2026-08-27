"""Async Remnawave panel client, speaking both panel API v2 and v3.

Only documented endpoints are called (see endpoints.py). Every create operation is
idempotent: it looks for an existing object by its natural key first, so a restarted worker
reuses what is already there instead of duplicating profiles, nodes or hosts.

**Two majors, one client.** The paths are the same in v2 and v3; the payload and response
details that are not live in `dialects.py`. The version is detected once on connect from
`GET /system/metadata` — an endpoint v3 has and v2 does not, so its absence is a positive
answer rather than a guess — and can be pinned with `api_version="v2"` / `"v3"` when a panel
sits behind something that mangles the probe.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.exceptions import (
    RemnawaveAPIError,
    RemnawaveUnsupportedOperation,
    TransientError,
)
from app.core.retry import retry_async
from app.services.remnawave import endpoints as ep
from app.services.remnawave.dialects import (
    DEFAULT_VERSION,
    ApiVersion,
    Dialect,
    dialect_for,
    version_from_metadata,
)
from app.services.remnawave.templates import (
    INBOUND_TAG,
    NODE_PORT,
    PROFILE_NAME,
    build_profile_config,
)

logger = logging.getLogger(__name__)


def _unwrap(payload: Any) -> Any:
    """Remnawave wraps successful bodies in {"response": ...}. Unchanged between v2 and v3."""
    if isinstance(payload, dict) and "response" in payload:
        return payload["response"]
    return payload


def _error_detail(response: httpx.Response) -> str:
    """The readable half of an error body.

    Both majors answer with `{"message": ..., "errorCode": ..., "timestamp": ..., "path": ...}`
    — v3 types those bodies per status but keeps the fields. Pulling the message out beats
    showing an admin a wall of JSON; anything unrecognised falls back to the raw text.
    """
    try:
        body = response.json()
    except ValueError:
        return response.text[:1000]
    if not isinstance(body, dict):
        return response.text[:1000]
    message = body.get("message") or body.get("error") or body.get("detail")
    code = body.get("errorCode")
    if isinstance(message, list):  # validation errors arrive as a list of strings
        message = "; ".join(str(item) for item in message)
    if not message:
        return response.text[:1000]
    return f"{message} [{code}]" if code else str(message)[:1000]


class RemnawaveClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        caddy_token: str | None = None,
        timeout: int = 45,
        verify_ssl: bool = True,
        api_version: ApiVersion | str | None = ApiVersion.AUTO,
    ) -> None:
        base = base_url.rstrip("/")
        self.base_url = base if base.endswith("/api") else f"{base}/api"
        self._token = token if token.lower().startswith("bearer ") else f"Bearer {token}"
        self._caddy_token = caddy_token
        self._timeout = timeout
        self._verify = verify_ssl
        self._client: httpx.AsyncClient | None = None

        self._pinned = (
            api_version if isinstance(api_version, ApiVersion) else ApiVersion.parse(api_version)
        )
        self._version = self._pinned
        self.panel_version: str | None = None  # the exact string the panel reported, if any

    @property
    def version(self) -> ApiVersion:
        """The dialect in use. AUTO until the connection is opened and detection has run."""
        return self._version

    @property
    def dialect(self) -> Dialect:
        return dialect_for(self._version)

    async def __aenter__(self) -> RemnawaveClient:
        headers = {"Authorization": self._token, "Content-Type": "application/json"}
        if self._caddy_token:
            headers["X-Api-Key"] = self._caddy_token
        self._client = httpx.AsyncClient(
            base_url=self.base_url, headers=headers, timeout=self._timeout, verify=self._verify
        )
        if self._pinned is ApiVersion.AUTO:
            try:
                self._version = await self.detect_version()
            except BaseException:
                # __aexit__ never runs when __aenter__ raises, so the transport would be left
                # open — a refused token would leak a connection per attempt.
                await self.__aexit__(None, None, None)
                raise
        return self

    async def detect_version(self) -> ApiVersion:
        """Ask the panel which major it is.

        `GET /system/metadata` was added in v3 and returns the exact version string. A 404 is
        the v2 answer — the endpoint is simply not there. Anything else (the panel is down, a
        proxy in the way) leaves the dialect at the default rather than reading a version out
        of an error, and the first real call reports the actual problem.
        """
        try:
            data = await self._request("GET", ep.SYSTEM_METADATA, attempts=1)
        except RemnawaveAPIError as exc:
            if exc.status in (401, 403):
                raise  # a refused token is not a version answer
            logger.info("Remnawave version probe answered HTTP %s, assuming v2", exc.status)
            return ApiVersion.V2
        except TransientError:
            logger.warning("Remnawave version probe failed, falling back to %s", DEFAULT_VERSION)
            return DEFAULT_VERSION

        if data is None:  # a 404 on a GET is normalised to None by _request
            logger.info("Remnawave panel has no /system/metadata — treating it as v2")
            return ApiVersion.V2

        if isinstance(data, dict) and isinstance(data.get("version"), str):
            self.panel_version = data["version"]
        detected = version_from_metadata(data)
        if detected is None or detected is ApiVersion.AUTO:
            logger.warning(
                "Remnawave reported an unrecognised version %r, using %s",
                self.panel_version,
                DEFAULT_VERSION,
            )
            return DEFAULT_VERSION
        logger.info("Remnawave panel %s detected as %s", self.panel_version, detected)
        return detected

    def describe(self) -> str:
        detail = f" {self.panel_version}" if self.panel_version else ""
        return f"{self.dialect.describe()}{detail}"

    async def __aexit__(self, *exc_info: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(self, method: str, path: str, *, attempts: int = 3, **kwargs) -> Any:
        if self._client is None:
            raise RuntimeError("RemnawaveClient must be used as an async context manager")

        async def _call() -> Any:
            try:
                response = await self._client.request(method, path, **kwargs)  # type: ignore[union-attr]
            except httpx.TimeoutException as exc:
                # httpx errors are not OSError, so without this retry_async never sees them
                # and a momentary blip fails the whole deployment step.
                raise TransientError(f"Таймаут запроса к Remnawave: {method} {path}") from exc
            except httpx.HTTPError as exc:
                raise TransientError(
                    f"Панель Remnawave недоступна: {exc!s} ({type(exc).__name__})"
                ) from exc
            if response.status_code in (502, 503, 504) or response.status_code == 429:
                raise TransientError(f"Remnawave {path} -> HTTP {response.status_code}")
            if response.status_code == 404 and method.upper() == "GET":
                return None
            if response.status_code >= 400:
                raise RemnawaveAPIError(response.status_code, _error_detail(response), path)
            if not response.content:
                return None
            return _unwrap(response.json())

        return await retry_async(_call, attempts=attempts, label=f"remnawave {method} {path}")

    # ------------------------------------------------------------------ health

    async def health_check(self) -> bool:
        """True when the panel answers and the token is accepted."""
        try:
            await self._request("GET", ep.SYSTEM_STATS)
            return True
        except RemnawaveAPIError as exc:
            if exc.status in (401, 403):
                raise
            return False

    # ---------------------------------------------------------------- profiles

    async def list_profiles(self) -> list[dict]:
        data = await self._request("GET", ep.CONFIG_PROFILES)
        if isinstance(data, dict):
            return list(data.get("configProfiles") or data.get("data") or [])
        return list(data or [])

    async def get_profile(self, uuid: str) -> dict | None:
        return await self._request("GET", ep.CONFIG_PROFILE.format(uuid=uuid))

    async def find_profile_by_name(self, name: str) -> dict | None:
        for profile in await self.list_profiles():
            if profile.get("name") == name:
                return profile
        return None

    async def create_profile(self, name: str = PROFILE_NAME, config: dict | None = None) -> dict:
        payload = {"name": name, "config": config or build_profile_config()}
        return await self._request("POST", ep.CONFIG_PROFILES, json=payload)

    async def update_profile(self, uuid: str, config: dict) -> dict:
        # PATCH targets the collection in both majors; the uuid travels in the body.
        return await self._request(
            "PATCH", ep.CONFIG_PROFILE_UPDATE, json={"uuid": uuid, "config": config}
        )

    async def delete_profile(self, uuid: str) -> None:
        await self._request("DELETE", ep.CONFIG_PROFILE.format(uuid=uuid))

    async def ensure_profile(self, name: str = PROFILE_NAME) -> dict:
        """Create the `cdn` profile, or reuse an existing one with the same name."""
        existing = await self.find_profile_by_name(name)
        if existing:
            logger.info("Reusing existing Remnawave profile %s", name)
            return existing
        return await self.create_profile(name)

    async def profile_inbounds(self, uuid: str) -> list[dict]:
        data = await self._request("GET", ep.CONFIG_PROFILE_INBOUNDS.format(uuid=uuid))
        if isinstance(data, dict):
            return list(data.get("inbounds") or data.get("data") or [])
        return list(data or [])

    async def find_inbound(self, profile_uuid: str, tag: str = INBOUND_TAG) -> dict | None:
        for inbound in await self.profile_inbounds(profile_uuid):
            if inbound.get("tag") == tag:
                return inbound
        return None

    # ------------------------------------------------------------------- nodes

    async def list_nodes(self) -> list[dict]:
        data = await self._request("GET", ep.NODES)
        if isinstance(data, dict):
            return list(data.get("nodes") or data.get("data") or [])
        return list(data or [])

    async def get_node(self, uuid: str) -> dict | None:
        return await self._request("GET", ep.NODE.format(uuid=uuid))

    async def find_node_by_address(self, address: str) -> dict | None:
        for node in await self.list_nodes():
            if node.get("address") == address:
                return node
        return None

    async def create_node(
        self,
        *,
        name: str,
        address: str,
        profile_uuid: str,
        inbound_uuid: str,
        port: int = NODE_PORT,
    ) -> dict:
        """Create the Remnawave Node object. The node is installed on the Origin Server later."""
        payload = {
            "name": name,
            "address": address,
            "port": port,
            "isTrafficTrackingActive": False,
            "configProfile": {
                "activeConfigProfileUuid": profile_uuid,
                "activeInbounds": [inbound_uuid],
            },
        }
        return await self._request("POST", ep.NODES, json=payload)

    async def update_node(self, uuid: str, **fields) -> dict:
        return await self._request("PATCH", ep.NODE_UPDATE, json={"uuid": uuid, **fields})

    async def delete_node(self, uuid: str) -> None:
        await self._request("DELETE", ep.NODE.format(uuid=uuid))

    async def enable_node(self, uuid: str) -> None:
        await self._request("POST", ep.NODE_ENABLE.format(uuid=uuid))

    async def ensure_node(
        self, *, name: str, address: str, profile_uuid: str, inbound_uuid: str, port: int = NODE_PORT
    ) -> dict:
        existing = await self.find_node_by_address(address)
        if existing:
            logger.info("Reusing existing Remnawave Node for %s", address)
            return existing
        return await self.create_node(
            name=name, address=address, profile_uuid=profile_uuid, inbound_uuid=inbound_uuid, port=port
        )

    async def node_is_connected(self, uuid: str) -> bool:
        node = await self.get_node(uuid)
        if not node:
            return False
        return bool(node.get("isConnected") or node.get("isNodeOnline"))

    async def keygen_secret(self) -> str | None:
        """The panel-wide node certificate handed out in the node card.

        This is the value that goes into the node's SECRET_KEY (older builds: SSL_CERT).
        It belongs to the panel, not to an individual node.
        """
        # v2 calls the field pubKey, v3 renamed it to secretKey — same endpoint, so both
        # names are tried in the order this dialect expects them.
        fields = (*self.dialect.keygen_fields, "publicKey", "certificate", "key")
        for path in (ep.KEYGEN, ep.KEYGEN_PUB_KEY):
            try:
                data = await self._request("GET", path)
            except RemnawaveAPIError as exc:
                if exc.status in (404, 405, 501):
                    continue
                raise
            if isinstance(data, dict):
                for key in fields:
                    value = data.get(key)
                    if value:
                        return str(value).strip()
            elif isinstance(data, str) and data.strip():
                return data.strip()
        return None

    async def node_install_secret(self, uuid: str, *, override: str | None = None) -> str:
        """The SECRET_KEY that the Remnanode container needs.

        Resolution order, all of it documented behaviour — nothing is generated locally:
          1. an operator-supplied value (admin pasted it from the node card);
          2. the node object itself, on builds that return it;
          3. GET /keygen/pub-key (or /keygen on older builds) — the panel-wide certificate.
        """
        if override and override.strip():
            return override.strip()

        node = await self.get_node(uuid)
        if not node:
            raise RemnawaveUnsupportedOperation(f"Node {uuid} not found")
        for key in ("nodeSecret", "secretKey", "apiKey", "sslCert", "token"):
            value = node.get(key)
            if value:
                return str(value).strip()

        keygen = await self.keygen_secret()
        if keygen:
            return keygen

        raise RemnawaveUnsupportedOperation(
            "Панель не отдаёт сертификат ноды через API. Откройте карточку ноды в Remnawave, "
            "скопируйте SECRET_KEY и отправьте его в админ-панели для этого заказа."
        )

    # ------------------------------------------------------------------- hosts

    async def list_hosts(self) -> list[dict]:
        data = await self._request("GET", ep.HOSTS)
        if isinstance(data, dict):
            return list(data.get("hosts") or data.get("data") or [])
        return list(data or [])

    async def get_host(self, uuid: str) -> dict | None:
        return await self._request("GET", ep.HOST.format(uuid=uuid))

    async def find_host_by_address(self, address: str) -> dict | None:
        for host in await self.list_hosts():
            if host.get("address") == address:
                return host
        return None

    async def create_host(
        self, *, profile_uuid: str, inbound_uuid: str, cdn_domain: str, node_uuid: str | None = None
    ) -> dict:
        payload = self.dialect.host_payload(
            profile_uuid=profile_uuid,
            inbound_uuid=inbound_uuid,
            cdn_domain=cdn_domain,
            node_uuid=node_uuid,
        )
        return await self._request("POST", ep.HOSTS, json=payload)

    async def update_host(self, uuid: str, **fields) -> dict:
        return await self._request("PATCH", ep.HOST_UPDATE, json={"uuid": uuid, **fields})

    async def delete_host(self, uuid: str) -> None:
        await self._request("DELETE", ep.HOST.format(uuid=uuid))

    async def ensure_host(
        self, *, profile_uuid: str, inbound_uuid: str, cdn_domain: str, node_uuid: str | None = None
    ) -> dict:
        existing = await self.find_host_by_address(cdn_domain)
        if existing:
            logger.info("Reusing existing Remnawave Host for %s", cdn_domain)
            return existing
        return await self.create_host(
            profile_uuid=profile_uuid,
            inbound_uuid=inbound_uuid,
            cdn_domain=cdn_domain,
            node_uuid=node_uuid,
        )

    # ---------------------------------------------------------------- squads

    async def list_internal_squads(self) -> list[dict]:
        data = await self._request("GET", ep.INTERNAL_SQUADS)
        if isinstance(data, dict):
            return list(data.get("internalSquads") or data.get("data") or [])
        return list(data or [])

    async def add_inbound_to_squads(self, inbound_uuid: str) -> int:
        """Attach the new inbound to every existing internal squad, so users receive it."""
        updated = 0
        for squad in await self.list_internal_squads():
            uuid = squad.get("uuid")
            current = [
                item.get("uuid") if isinstance(item, dict) else item
                for item in (squad.get("inbounds") or [])
            ]
            current = [item for item in current if item]
            if not uuid or inbound_uuid in current:
                continue
            await self._request(
                "PATCH",
                ep.INTERNAL_SQUAD_UPDATE,
                json={"uuid": uuid, "inbounds": [*current, inbound_uuid]},
            )
            updated += 1
        return updated

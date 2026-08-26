"""Async Remnawave panel client.

Only documented endpoints are called (see endpoints.py). Every create operation is
idempotent: it looks for an existing object by its natural key first, so a restarted worker
reuses what is already there instead of duplicating profiles, nodes or hosts.
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
from app.services.remnawave.templates import (
    INBOUND_TAG,
    NODE_PORT,
    PROFILE_NAME,
    build_host_payload,
    build_profile_config,
)

logger = logging.getLogger(__name__)


def _unwrap(payload: Any) -> Any:
    """Remnawave wraps successful bodies in {"response": ...}."""
    if isinstance(payload, dict) and "response" in payload:
        return payload["response"]
    return payload


class RemnawaveClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        caddy_token: str | None = None,
        timeout: int = 45,
        verify_ssl: bool = True,
    ) -> None:
        base = base_url.rstrip("/")
        self.base_url = base if base.endswith("/api") else f"{base}/api"
        self._token = token if token.lower().startswith("bearer ") else f"Bearer {token}"
        self._caddy_token = caddy_token
        self._timeout = timeout
        self._verify = verify_ssl
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> RemnawaveClient:
        headers = {"Authorization": self._token, "Content-Type": "application/json"}
        if self._caddy_token:
            headers["X-Api-Key"] = self._caddy_token
        self._client = httpx.AsyncClient(
            base_url=self.base_url, headers=headers, timeout=self._timeout, verify=self._verify
        )
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(self, method: str, path: str, **kwargs) -> Any:
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
                raise RemnawaveAPIError(response.status_code, response.text, path)
            if not response.content:
                return None
            return _unwrap(response.json())

        return await retry_async(_call, attempts=3, label=f"remnawave {method} {path}")

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
        return await self._request(
            "PATCH", ep.CONFIG_PROFILE.format(uuid=uuid), json={"uuid": uuid, "config": config}
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
        return await self._request("PATCH", ep.NODE.format(uuid=uuid), json={"uuid": uuid, **fields})

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
        for path in (ep.KEYGEN_PUB_KEY, ep.KEYGEN):
            try:
                data = await self._request("GET", path)
            except RemnawaveAPIError as exc:
                if exc.status in (404, 405, 501):
                    continue
                raise
            if isinstance(data, dict):
                for key in ("secretKey", "pubKey", "publicKey", "certificate", "key"):
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
        payload = build_host_payload(
            profile_uuid=profile_uuid,
            inbound_uuid=inbound_uuid,
            cdn_domain=cdn_domain,
            node_uuid=node_uuid,
        )
        return await self._request("POST", ep.HOSTS, json=payload)

    async def update_host(self, uuid: str, **fields) -> dict:
        return await self._request("PATCH", ep.HOST.format(uuid=uuid), json={"uuid": uuid, **fields})

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
                ep.INTERNAL_SQUAD.format(uuid=uuid),
                json={"uuid": uuid, "inbounds": [*current, inbound_uuid]},
            )
            updated += 1
        return updated

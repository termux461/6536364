"""Thin async client for the Remnawave VPN panel REST API.

Remnawave exposes a REST API for managing panel users (VPN clients), inbounds
and nodes. Endpoints below follow the documented `/api/users` resource shape;
adjust paths if your Remnawave version differs.
"""
import logging
import time
import uuid

import httpx

logger = logging.getLogger(__name__)


class RemnawaveError(Exception):
    pass


class RemnawaveClient:
    def __init__(self, api_url: str, api_token: str, timeout: float = 15.0):
        self.api_url = api_url.rstrip("/")
        self.api_token = api_token
        self._client = httpx.AsyncClient(
            base_url=self.api_url,
            headers={"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"},
            timeout=timeout,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        try:
            resp = await self._client.request(method, path, **kwargs)
            resp.raise_for_status()
            return resp.json() if resp.content else {}
        except httpx.HTTPStatusError as e:
            logger.error("Remnawave API error %s %s -> %s", method, path, e.response.text)
            raise RemnawaveError(str(e)) from e
        except httpx.HTTPError as e:
            logger.error("Remnawave API connection error: %s", e)
            raise RemnawaveError(str(e)) from e

    async def create_user(self, telegram_id: int, username: str, expire_at_iso: str, traffic_limit_bytes: int = 0) -> dict:
        payload = {
            "username": f"tg{telegram_id}_{uuid.uuid4().hex[:6]}",
            "telegramId": telegram_id,
            "expireAt": expire_at_iso,
            "trafficLimitBytes": traffic_limit_bytes,
            "status": "ACTIVE",
            "description": username or "",
        }
        return await self._request("POST", "/api/users", json=payload)

    async def extend_user(self, remnawave_uuid: str, expire_at_iso: str) -> dict:
        payload = {"expireAt": expire_at_iso, "status": "ACTIVE"}
        return await self._request("PATCH", f"/api/users/{remnawave_uuid}", json=payload)

    async def delete_user(self, remnawave_uuid: str) -> dict:
        return await self._request("DELETE", f"/api/users/{remnawave_uuid}")

    async def get_user(self, remnawave_uuid: str) -> dict:
        return await self._request("GET", f"/api/users/{remnawave_uuid}")

    async def get_subscription_url(self, remnawave_uuid: str) -> str:
        data = await self.get_user(remnawave_uuid)
        return data.get("subscriptionUrl") or data.get("subscription_url", "")


async def http_ping(url: str) -> int | None:
    """Simple HTTP(s) ping used for node status display. Returns ms or None on failure."""
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.get(url)
        return int((time.monotonic() - started) * 1000)
    except httpx.HTTPError:
        return None

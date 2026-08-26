"""Cloudflare DNS provider (api.cloudflare.com/client/v4).

Records are always created with proxying disabled — an orange cloud in front of the CDN
domain would break the xHTTP transport.
"""
from __future__ import annotations

import logging

import httpx

from app.core.exceptions import PermanentError, TransientError
from app.core.retry import retry_async
from app.services.dns.base import DNSProvider, DNSRecordSpec

logger = logging.getLogger(__name__)

API = "https://api.cloudflare.com/client/v4"


class CloudflareDNSProvider(DNSProvider):
    name = "cloudflare"
    automatic = True

    def __init__(self, api_token: str, zone_name: str | None = None) -> None:
        self._token = api_token
        self._zone_name = zone_name
        self._zone_id: str | None = None

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        async def _call() -> dict:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.request(method, f"{API}{path}", headers=self._headers(), **kwargs)
            if response.status_code in (429, 500, 502, 503, 504):
                raise TransientError(f"Cloudflare HTTP {response.status_code}")
            data = response.json()
            if not data.get("success"):
                raise PermanentError(f"Cloudflare error: {data.get('errors')}")
            return data

        return await retry_async(_call, attempts=3, label=f"cloudflare {method} {path}")

    async def zone_id_for(self, fqdn: str) -> str:
        if self._zone_id:
            return self._zone_id
        candidates = []
        parts = (self._zone_name or fqdn).split(".")
        for index in range(len(parts) - 1):
            candidates.append(".".join(parts[index:]))
        for candidate in candidates:
            data = await self._request("GET", "/zones", params={"name": candidate})
            results = data.get("result") or []
            if results:
                self._zone_id = results[0]["id"]
                return self._zone_id
        raise PermanentError(f"No Cloudflare zone found for {fqdn}")

    async def create_record(self, spec: DNSRecordSpec) -> str | None:
        zone_id = await self.zone_id_for(spec.name)
        existing = await self._find(zone_id, spec.name, spec.record_type)
        body = {
            "type": spec.record_type,
            "name": spec.name,
            "content": spec.value,
            "ttl": spec.ttl,
            "proxied": False,
        }
        if existing:
            data = await self._request(
                "PUT", f"/zones/{zone_id}/dns_records/{existing['id']}", json=body
            )
        else:
            data = await self._request("POST", f"/zones/{zone_id}/dns_records", json=body)
        return (data.get("result") or {}).get("id")

    async def _find(self, zone_id: str, name: str, record_type: str) -> dict | None:
        data = await self._request(
            "GET", f"/zones/{zone_id}/dns_records", params={"name": name, "type": record_type}
        )
        results = data.get("result") or []
        return results[0] if results else None

    async def get_record(self, name: str, record_type: str) -> DNSRecordSpec | None:
        zone_id = await self.zone_id_for(name)
        record = await self._find(zone_id, name, record_type)
        if not record:
            return None
        return DNSRecordSpec(
            name=record["name"], record_type=record["type"], value=record["content"],
            ttl=int(record.get("ttl") or 300),
        )

    async def delete_record(self, name: str, record_type: str) -> None:
        zone_id = await self.zone_id_for(name)
        record = await self._find(zone_id, name, record_type)
        if record:
            await self._request("DELETE", f"/zones/{zone_id}/dns_records/{record['id']}")

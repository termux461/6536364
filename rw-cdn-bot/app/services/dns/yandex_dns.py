"""Cloud DNS provider — used when the customer keeps the zone inside the same Yandex folder."""
from __future__ import annotations

import logging

from app.core.exceptions import PermanentError
from app.services.dns.base import DNSProvider, DNSRecordSpec
from app.services.yandex.client import YandexCloudClient

logger = logging.getLogger(__name__)


class YandexDNSProvider(DNSProvider):
    name = "yandex"
    automatic = True

    def __init__(self, client: YandexCloudClient) -> None:
        self.client = client

    async def _zone_id(self, fqdn: str) -> str:
        zone = await self.client.find_dns_zone(fqdn)
        if not zone:
            raise PermanentError(f"No Cloud DNS zone in this folder covers {fqdn}")
        return str(zone["id"])

    async def create_record(self, spec: DNSRecordSpec) -> str | None:
        zone_id = await self._zone_id(spec.name)
        value = spec.value if spec.record_type != "CNAME" else spec.value.rstrip(".") + "."
        await self.client.upsert_dns_record(
            zone_id=zone_id, name=spec.name, record_type=spec.record_type, value=value, ttl=spec.ttl
        )
        return zone_id

    async def get_record(self, name: str, record_type: str) -> DNSRecordSpec | None:
        return None  # verification goes through the public resolver, not the zone API

    async def delete_record(self, name: str, record_type: str) -> None:
        return None

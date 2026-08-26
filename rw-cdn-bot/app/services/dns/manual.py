from __future__ import annotations

from app.services.dns.base import DNSProvider, DNSRecordSpec


class ManualDNSProvider(DNSProvider):
    """No API available. The bot shows the record and waits for the user to press «Проверить DNS»."""

    name = "manual"
    automatic = False

    async def create_record(self, spec: DNSRecordSpec) -> str | None:
        return None

    async def get_record(self, name: str, record_type: str) -> DNSRecordSpec | None:
        return None

    async def delete_record(self, name: str, record_type: str) -> None:
        return None

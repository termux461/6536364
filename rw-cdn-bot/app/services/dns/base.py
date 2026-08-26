from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(slots=True)
class DNSRecordSpec:
    name: str          # full FQDN, e.g. cdn.example.com
    record_type: str   # A | CNAME
    value: str
    ttl: int = 300


class DNSProvider(ABC):
    """Abstraction over a DNS zone. `manual` is always available as a fallback."""

    name: str
    automatic: bool

    @abstractmethod
    async def create_record(self, spec: DNSRecordSpec) -> str | None:
        """Create or update the record. Returns the provider-side record id when there is one."""

    @abstractmethod
    async def get_record(self, name: str, record_type: str) -> DNSRecordSpec | None: ...

    @abstractmethod
    async def delete_record(self, name: str, record_type: str) -> None: ...

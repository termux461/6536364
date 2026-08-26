from app.services.dns.base import DNSProvider, DNSRecordSpec
from app.services.dns.cloudflare import CloudflareDNSProvider
from app.services.dns.manual import ManualDNSProvider
from app.services.dns.resolver import (
    resolve_a,
    resolve_cname_chain,
    verify_a_record,
    verify_cname_record,
)
from app.services.dns.yandex_dns import YandexDNSProvider

__all__ = [
    "CloudflareDNSProvider",
    "DNSProvider",
    "DNSRecordSpec",
    "ManualDNSProvider",
    "YandexDNSProvider",
    "resolve_a",
    "resolve_cname_chain",
    "verify_a_record",
    "verify_cname_record",
]

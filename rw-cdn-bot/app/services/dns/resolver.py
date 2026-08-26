"""Live DNS verification. Deployment does not advance until records actually resolve."""
from __future__ import annotations

import logging

import dns.asyncresolver
import dns.exception

logger = logging.getLogger(__name__)

PUBLIC_RESOLVERS = ["1.1.1.1", "8.8.8.8", "77.88.8.8"]


def _resolver() -> dns.asyncresolver.Resolver:
    resolver = dns.asyncresolver.Resolver(configure=False)
    resolver.nameservers = PUBLIC_RESOLVERS
    resolver.lifetime = 10
    resolver.timeout = 5
    return resolver


async def resolve_a(name: str) -> list[str]:
    try:
        answer = await _resolver().resolve(name, "A")
        return sorted(record.address for record in answer)
    except (TimeoutError, dns.exception.DNSException):
        return []


async def resolve_cname_chain(name: str) -> list[str]:
    """Return every CNAME target in the chain, lower-cased and dot-stripped."""
    chain: list[str] = []
    current = name
    for _ in range(8):
        try:
            answer = await _resolver().resolve(current, "CNAME")
        except (TimeoutError, dns.exception.DNSException):
            break
        targets = [str(record.target).rstrip(".").lower() for record in answer]
        if not targets:
            break
        chain.extend(targets)
        current = targets[0]
    return chain


async def verify_a_record(name: str, expected_ip: str) -> bool:
    addresses = await resolve_a(name)
    ok = expected_ip in addresses
    logger.info("DNS A %s -> %s (expected %s): %s", name, addresses, expected_ip, ok)
    return ok


async def verify_cname_record(name: str, expected_target: str) -> bool:
    expected = expected_target.rstrip(".").lower()
    chain = await resolve_cname_chain(name)
    ok = any(expected == target or target.endswith("." + expected) or expected in target
             for target in chain)
    logger.info("DNS CNAME %s -> %s (expected %s): %s", name, chain, expected, ok)
    return ok

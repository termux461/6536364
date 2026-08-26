
from app.services.dns import resolver


async def test_verify_a_record_true(monkeypatch):
    async def fake_resolve(name):
        return ["203.0.113.10"]

    monkeypatch.setattr(resolver, "resolve_a", fake_resolve)
    assert await resolver.verify_a_record("origin.example.com", "203.0.113.10") is True


async def test_verify_a_record_false(monkeypatch):
    async def fake_resolve(name):
        return ["198.51.100.1"]

    monkeypatch.setattr(resolver, "resolve_a", fake_resolve)
    assert await resolver.verify_a_record("origin.example.com", "203.0.113.10") is False


async def test_verify_cname_follows_chain(monkeypatch):
    async def fake_chain(name):
        return ["cl-abc123.edgecdn.ru", "edge-7.edgecdn.ru"]

    monkeypatch.setattr(resolver, "resolve_cname_chain", fake_chain)
    assert await resolver.verify_cname_record("cdn.example.com", "cl-abc123.edgecdn.ru") is True
    assert await resolver.verify_cname_record("cdn.example.com", "other.example.net") is False

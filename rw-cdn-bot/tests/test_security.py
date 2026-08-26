import pytest

from app.config import get_settings
from app.core.crypto import mask, secret_box
from app.core.logging import redact


def test_secrets_roundtrip_and_are_not_plaintext():
    box = secret_box()
    secret = "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----"
    encrypted = box.encrypt(secret)
    assert encrypted != secret
    assert "PRIVATE KEY" not in encrypted
    assert box.decrypt(encrypted) == secret


def test_wrong_key_cannot_decrypt():
    from cryptography.fernet import Fernet

    from app.core.crypto import SecretBox

    a, b = SecretBox(Fernet.generate_key().decode()), SecretBox(Fernet.generate_key().decode())
    with pytest.raises(ValueError):
        b.decrypt(a.encrypt("hello"))


def test_log_redaction_removes_credentials():
    text = "curl -H 'Authorization: Bearer abcdef123' https://panel"
    assert "abcdef123" not in redact(text)
    key = "-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----"
    assert "secret" not in redact(key)


def test_mask_keeps_only_edges():
    assert mask("supersecrettoken") == "supe…oken"
    assert mask(None) == "—"


def test_admin_permissions_come_from_env():
    settings = get_settings()
    assert settings.is_admin(111) is True
    assert settings.is_admin(999) is False

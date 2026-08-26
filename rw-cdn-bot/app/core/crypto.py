"""Symmetric encryption of stored credentials.

The key never leaves the environment (SECRET_ENCRYPTION_KEY in .env).
Nothing sensitive is written to the database in plaintext.
"""
from __future__ import annotations

import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class SecretBox:
    def __init__(self, key: str) -> None:
        try:
            self._fernet = Fernet(key.encode() if isinstance(key, str) else key)
        except Exception as exc:
            raise ValueError(
                "SECRET_ENCRYPTION_KEY is invalid. Generate one with "
                "python -c \"from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())\""
            ) from exc

    def encrypt(self, value: str | None) -> str | None:
        if value is None:
            return None
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except InvalidToken as exc:
            raise ValueError("Stored secret cannot be decrypted with the current key") from exc

    def encrypt_json(self, value: Any) -> str | None:
        if value is None:
            return None
        return self.encrypt(json.dumps(value, ensure_ascii=False))

    def decrypt_json(self, value: str | None) -> Any:
        raw = self.decrypt(value)
        return json.loads(raw) if raw is not None else None


_box: SecretBox | None = None


def secret_box() -> SecretBox:
    global _box
    if _box is None:
        _box = SecretBox(get_settings().secret_encryption_key)
    return _box


def mask(value: str | None, keep: int = 4) -> str:
    """Human-readable masked representation for admin screens."""
    if not value:
        return "—"
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}…{value[-keep:]}"

from functools import lru_cache

from cryptography.fernet import Fernet

from bot.config import settings


@lru_cache
def _fernet() -> Fernet:
    if not settings.FERNET_KEY:
        raise RuntimeError("FERNET_KEY is not set. Generate one with Fernet.generate_key()")
    return Fernet(settings.FERNET_KEY.encode())


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    return _fernet().decrypt(value.encode()).decode()

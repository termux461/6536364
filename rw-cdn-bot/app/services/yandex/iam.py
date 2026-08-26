"""IAM token exchange for a service account authorized key.

POST https://iam.api.cloud.yandex.net/iam/v1/tokens  {"jwt": "<PS256 JWT>"}
The key JSON is the one produced by `yc iam key create --output key.json`.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass

import httpx
import jwt

from app.core.exceptions import PermanentError, TransientError, YandexAPIError

IAM_TOKEN_URL = "https://iam.api.cloud.yandex.net/iam/v1/tokens"
JWT_AUDIENCE = IAM_TOKEN_URL
TOKEN_TTL = 3600


@dataclass(slots=True)
class ServiceAccountKey:
    key_id: str
    service_account_id: str
    private_key: str

    @classmethod
    def parse(cls, raw: str | dict) -> ServiceAccountKey:
        data = json.loads(raw) if isinstance(raw, str) else raw
        try:
            return cls(
                key_id=data["id"],
                service_account_id=data["service_account_id"],
                private_key=data["private_key"],
            )
        except (KeyError, TypeError) as exc:
            raise PermanentError(
                "Yandex service account key is malformed: expected id / service_account_id / private_key"
            ) from exc


class IAMTokenProvider:
    def __init__(self, key: ServiceAccountKey) -> None:
        self.key = key
        self._token: str | None = None
        self._expires_at: float = 0.0

    def _build_jwt(self) -> str:
        now = int(time.time())
        payload = {
            "aud": JWT_AUDIENCE,
            "iss": self.key.service_account_id,
            "iat": now,
            "exp": now + 360,
        }
        return jwt.encode(
            payload,
            self.key.private_key,
            algorithm="PS256",
            headers={"kid": self.key.key_id},
        )

    async def token(self) -> str:
        if self._token and time.time() < self._expires_at - 120:
            return self._token
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(IAM_TOKEN_URL, json={"jwt": self._build_jwt()})
        if response.status_code >= 500:
            raise TransientError(f"Yandex IAM HTTP {response.status_code}")
        if response.status_code >= 400:
            raise YandexAPIError(response.status_code, response.text, "iam/v1/tokens")
        data = response.json()
        self._token = data["iamToken"]
        self._expires_at = time.time() + TOKEN_TTL
        return self._token

"""Structured logging with secret redaction."""
from __future__ import annotations

import logging
import re
import sys

_SECRET_PATTERNS = [
    re.compile(r"(-----BEGIN [A-Z ]*PRIVATE KEY-----)(.|\n)*?(-----END [A-Z ]*PRIVATE KEY-----)"),
    # `Authorization: Bearer <token>` — the scheme word is part of the value, so it has to be
    # consumed too. Matching only up to the first token left the credential itself in the log.
    re.compile(
        r"(?i)\b(authorization|proxy-authorization|x-api-key|x-auth-token)\s*[:=]\s*"
        r"(?:\"|')?(?:bearer|basic|token)?\s*\S+"
    ),
    # A bare `Bearer <token>` with no header name in front of it.
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/=]+"),
    re.compile(r"(?i)(password|secret|token|api_key|apikey|private_key)\"?\s*[:=]\s*\"?[^\s\",}]+"),
    # Cookie headers and jars: the whole value is credential material.
    re.compile(r"(?i)\b(set-cookie|cookie)\s*[:=]\s*\S.*"),
    re.compile(r"(?i)\b(yc_session|session_id|sessionid2)=[^\s;\"',]+"),
    re.compile(r"sshpass -p \S+"),
]


def redact(text: str) -> str:
    """Remove anything that looks like a credential before it reaches a log sink."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("***REDACTED***", text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            record.args = tuple(
                redact(arg) if isinstance(arg, str) else arg for arg in record.args
            )  # type: ignore[assignment]
        return True


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-8s %(name)s | %(message)s")
    )
    handler.addFilter(RedactingFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    for noisy in ("aiogram.event", "asyncssh", "httpx", "aiosqlite"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

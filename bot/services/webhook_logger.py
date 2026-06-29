import json
import logging
from pathlib import Path

from aiohttp import web

webhook_logger = logging.getLogger("webhooks")
webhook_logger.setLevel(logging.INFO)

_log_path = Path("logs")
_log_path.mkdir(exist_ok=True)
_handler = logging.FileHandler(_log_path / "webhooks.log", encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
webhook_logger.addHandler(_handler)
webhook_logger.propagate = False


async def log_incoming_webhook(provider: str, request: web.Request, body: bytes) -> None:
    entry = {
        "provider": provider,
        "ip": request.remote,
        "headers": dict(request.headers),
        "body": body.decode("utf-8", errors="replace"),
    }
    webhook_logger.info(json.dumps(entry, ensure_ascii=False))

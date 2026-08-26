"""Retry helper with configurable backoff, used by every network-facing operation."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import TypeVar

from app.core.exceptions import TransientError

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_DELAYS: Sequence[int] = (5, 15, 30)


async def retry_async(
    func: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    delays: Sequence[int] = DEFAULT_DELAYS,
    retry_on: tuple[type[BaseException], ...] = (TransientError, asyncio.TimeoutError, OSError),
    label: str = "operation",
) -> T:
    last_error: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await func()
        except retry_on as exc:
            last_error = exc
            if attempt >= attempts:
                break
            delay = delays[min(attempt - 1, len(delays) - 1)]
            logger.warning(
                "%s failed (attempt %s/%s): %s — retrying in %ss", label, attempt, attempts, exc, delay
            )
            await asyncio.sleep(delay)
    assert last_error is not None
    raise last_error


async def poll_until(
    check: Callable[[], Awaitable[bool]],
    *,
    timeout: int,
    interval: int = 15,
    label: str = "condition",
) -> bool:
    """Poll ``check`` until it returns True or the timeout expires."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if await check():
            return True
        await asyncio.sleep(interval)
    logger.info("%s was not satisfied within %ss", label, timeout)
    return False

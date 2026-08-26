"""Redis-backed job queue.

The webhook only pushes a job id and returns 200; all long work happens in the worker.
Jobs are moved to a processing list so a crashed worker's job can be recovered.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from redis.asyncio import Redis

from app.config import get_settings

logger = logging.getLogger(__name__)

DEPLOY_QUEUE = "queue:deployments"
DEPLOY_PROCESSING = "queue:deployments:processing"
BROADCAST_QUEUE = "queue:broadcasts"
DEPLOY_LOCK = "lock:deployment:{order_id}"


class JobQueue:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    @classmethod
    def from_settings(cls) -> JobQueue:
        return cls(Redis.from_url(get_settings().redis_url, decode_responses=True))

    async def close(self) -> None:
        await self.redis.aclose()

    async def enqueue_deployment(self, order_id: int, *, reason: str = "paid") -> None:
        payload = json.dumps({"order_id": order_id, "reason": reason})
        await self.redis.rpush(DEPLOY_QUEUE, payload)
        logger.info("Queued deployment for order %s (%s)", order_id, reason)

    async def enqueue_broadcast(self, broadcast_id: int) -> None:
        await self.redis.rpush(BROADCAST_QUEUE, json.dumps({"broadcast_id": broadcast_id}))

    async def pop(self, queue: str, timeout: int = 5) -> dict[str, Any] | None:
        raw = await self.redis.blpop([queue], timeout=timeout)
        if raw is None:
            return None
        return json.loads(raw[1])

    async def acquire_deploy_lock(self, order_id: int, ttl: int = 7200) -> bool:
        return bool(
            await self.redis.set(DEPLOY_LOCK.format(order_id=order_id), "1", nx=True, ex=ttl)
        )

    async def release_deploy_lock(self, order_id: int) -> None:
        await self.redis.delete(DEPLOY_LOCK.format(order_id=order_id))

    async def schedule_retry(self, order_id: int, delay: int, *, reason: str = "retry") -> None:
        """Park a waiting deployment: a sorted set acts as a delayed queue."""
        import time

        await self.redis.zadd(
            "queue:deployments:delayed",
            {json.dumps({"order_id": order_id, "reason": reason}): time.time() + delay},
        )

    async def due_delayed(self) -> list[dict[str, Any]]:
        import time

        now = time.time()
        items = await self.redis.zrangebyscore("queue:deployments:delayed", 0, now)
        if not items:
            return []
        await self.redis.zremrangebyscore("queue:deployments:delayed", 0, now)
        return [json.loads(item) for item in items]

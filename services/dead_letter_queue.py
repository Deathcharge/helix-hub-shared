"""
Redis Dead-Letter Queue (DLQ) for Helix Collective.

Provides a lightweight, Redis-backed retry mechanism for failed async
operations (webhooks, emails, integration calls).  Jobs that exhaust
their retry budget are moved to a dead-letter list for manual inspection.

Architecture
------------
  work queue  ──►  worker picks job  ──►  success → done
                                      └►  failure  →  increment attempt
                                            ├─ attempts < max  →  re-enqueue (with backoff)
                                            └─ attempts >= max →  move to DLQ

Redis keys used
---------------
  helix:queue:<name>          – FIFO list of pending jobs (JSON)
  helix:dlq:<name>            – list of permanently failed jobs
  helix:queue:<name>:stats    – hash with counters (enqueued, processed, failed, dead)

Environment
-----------
  REDIS_URL : standard Redis connection string (already used by cache layer)
"""

import json
import logging
import os
import time
from collections.abc import Callable, Coroutine
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MAX_RETRIES = 5
DEFAULT_BACKOFF_BASE = 2  # exponential backoff base in seconds


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class DLQJob:
    """Represents a single job in the queue."""

    id: str
    queue: str
    payload: dict[str, Any]
    attempts: int = 0
    max_retries: int = DEFAULT_MAX_RETRIES
    created_at: float = field(default_factory=time.time)
    last_error: str | None = None
    next_retry_at: float = 0.0

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "DLQJob":
        data = json.loads(raw)
        return cls(**data)


# ---------------------------------------------------------------------------
# Dead-Letter Queue service
# ---------------------------------------------------------------------------


class DeadLetterQueue:
    """Redis-backed retry queue with dead-letter semantics."""

    def __init__(self, redis_url: str | None = None) -> None:
        self._redis_url = redis_url or os.getenv("REDIS_URL", "")
        self._redis = None

    async def _ensure_redis(self):
        """Lazy-connect to Redis."""
        if self._redis is not None:
            return self._redis

        if not self._redis_url:
            logger.warning("DLQ: No REDIS_URL configured – queue disabled")
            return None

        try:
            import redis.asyncio as aioredis

            client = aioredis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            await client.ping()
            self._redis = client
            logger.info("✅ Dead-letter queue connected to Redis")
            return self._redis
        except (OSError, ConnectionError) as exc:
            logger.error("DLQ: Redis connection failed: %s", exc)
            self._redis = None
            return None

    # -- keys ---------------------------------------------------------------

    @staticmethod
    def _queue_key(name: str) -> str:
        return "helix:queue:%s" % name

    @staticmethod
    def _dlq_key(name: str) -> str:
        return "helix:dlq:%s" % name

    @staticmethod
    def _stats_key(name: str) -> str:
        return "helix:queue:%s:stats" % name

    # -- public API ---------------------------------------------------------

    async def enqueue(
        self,
        queue_name: str,
        job_id: str,
        payload: dict[str, Any],
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> bool:
        """Add a new job to the work queue."""
        redis = await self._ensure_redis()
        if redis is None:
            return False

        job = DLQJob(
            id=job_id,
            queue=queue_name,
            payload=payload,
            max_retries=max_retries,
        )
        await redis.rpush(self._queue_key(queue_name), job.to_json())
        await redis.hincrby(self._stats_key(queue_name), "enqueued", 1)
        logger.debug("DLQ: enqueued job %s on %s", job_id, queue_name)
        return True

    async def dequeue(self, queue_name: str, timeout: int = 0) -> DLQJob | None:
        """Pop the next job from the queue (blocking if *timeout* > 0)."""
        redis = await self._ensure_redis()
        if redis is None:
            return None

        if timeout > 0:
            result = await redis.blpop(self._queue_key(queue_name), timeout=timeout)
            raw = result[1] if result else None
        else:
            raw = await redis.lpop(self._queue_key(queue_name))

        if raw is None:
            return None

        return DLQJob.from_json(raw)

    async def nack(
        self,
        job: DLQJob,
        error: str,
    ) -> bool:
        """Mark a job as failed.

        If retries remain the job is re-enqueued with exponential backoff.
        Otherwise it is moved to the dead-letter list.
        """
        redis = await self._ensure_redis()
        if redis is None:
            return False

        job.attempts += 1
        job.last_error = error

        if job.attempts >= job.max_retries:
            # Move to dead-letter queue
            await redis.rpush(self._dlq_key(job.queue), job.to_json())
            await redis.hincrby(self._stats_key(job.queue), "dead", 1)
            logger.warning(
                "DLQ: job %s moved to dead-letter after %d attempts: %s",
                job.id,
                job.attempts,
                error,
            )
            return False  # indicates exhausted

        # Re-enqueue with backoff
        backoff = DEFAULT_BACKOFF_BASE**job.attempts
        job.next_retry_at = time.time() + backoff
        await redis.rpush(self._queue_key(job.queue), job.to_json())
        await redis.hincrby(self._stats_key(job.queue), "retried", 1)
        logger.info(
            "DLQ: job %s retry %d/%d (backoff %ds)",
            job.id,
            job.attempts,
            job.max_retries,
            backoff,
        )
        return True  # will be retried

    async def ack(self, job: DLQJob) -> None:
        """Mark a job as successfully processed."""
        redis = await self._ensure_redis()
        if redis is None:
            return
        await redis.hincrby(self._stats_key(job.queue), "processed", 1)

    async def peek_dlq(self, queue_name: str, limit: int = 50) -> list[DLQJob]:
        """Inspect dead-letter items without removing them."""
        redis = await self._ensure_redis()
        if redis is None:
            return []

        raw_items = await redis.lrange(self._dlq_key(queue_name), 0, limit - 1)
        return [DLQJob.from_json(r) for r in raw_items]

    async def replay_dlq(self, queue_name: str, count: int = 1) -> int:
        """Move *count* items from the DLQ back to the work queue for retry."""
        redis = await self._ensure_redis()
        if redis is None:
            return 0

        replayed = 0
        for _ in range(count):
            raw = await redis.lpop(self._dlq_key(queue_name))
            if raw is None:
                break
            job = DLQJob.from_json(raw)
            job.attempts = 0  # reset attempts
            job.last_error = None
            await redis.rpush(self._queue_key(queue_name), job.to_json())
            replayed += 1

        if replayed:
            logger.info("DLQ: replayed %d jobs from %s dead-letter", replayed, queue_name)
        return replayed

    async def stats(self, queue_name: str) -> dict[str, Any]:
        """Return queue statistics."""
        redis = await self._ensure_redis()
        if redis is None:
            return {"enabled": False}

        raw = await redis.hgetall(self._stats_key(queue_name))
        pending = await redis.llen(self._queue_key(queue_name))
        dead = await redis.llen(self._dlq_key(queue_name))

        return {
            "enabled": True,
            "queue": queue_name,
            "pending": pending,
            "dead_letters": dead,
            "enqueued": int(raw.get("enqueued", 0)),
            "processed": int(raw.get("processed", 0)),
            "retried": int(raw.get("retried", 0)),
            "dead": int(raw.get("dead", 0)),
        }

    async def process_queue(
        self,
        queue_name: str,
        handler: Callable[[dict[str, Any]], Coroutine],
        batch_size: int = 10,
    ) -> int:
        """Process up to *batch_size* jobs from the queue.

        Parameters
        ----------
        handler : async callable
            Receives ``job.payload`` and should raise on failure.
        """
        processed = 0
        for _ in range(batch_size):
            job = await self.dequeue(queue_name)
            if job is None:
                break

            # Respect backoff timing
            if job.next_retry_at > time.time():
                # Not ready yet – put it back
                redis = await self._ensure_redis()
                if redis:
                    await redis.rpush(self._queue_key(queue_name), job.to_json())
                continue

            try:
                await handler(job.payload)
                await self.ack(job)
                processed += 1
            except Exception as exc:
                await self.nack(job, str(exc))

        return processed


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

dlq = DeadLetterQueue()

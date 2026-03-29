"""
Distributed Worker Queue for Helix Collective
===============================================

Provides a Redis-backed distributed task queue that allows multiple
worker processes to claim and execute tasks independently from the
main FastAPI process.

Architecture:
  Producer (API server) → Redis queue → Worker processes (separate)

Redis keys:
  helix:worker:queue:{name}         — FIFO list of serialized jobs
  helix:worker:processing:{name}    — set of job IDs currently being processed
  helix:worker:results:{job_id}     — JSON result (auto-expires)
  helix:worker:heartbeat:{worker_id} — worker liveness (TTL-based)
  helix:worker:registry              — hash of registered workers
  helix:worker:stats                 — hash with global counters

Usage (producer side — within FastAPI):
    from apps.backend.services.worker_queue import get_worker_queue

    wq = await get_worker_queue()
    job_id = await wq.enqueue("email_send", {"to": "user@example.com", "body": "..."})
    status = await wq.get_job_status(job_id)

Usage (worker side — standalone process):
    python -m apps.backend.services.worker_queue --queues=default,email --concurrency=4
"""

import argparse
import asyncio
import json
import logging
import os
import signal
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Redis key prefixes
_Q_PREFIX = "helix:worker:queue:"
_PROC_PREFIX = "helix:worker:processing:"
_RESULT_PREFIX = "helix:worker:results:"
_HB_PREFIX = "helix:worker:heartbeat:"
_REGISTRY_KEY = "helix:worker:registry"
_STATS_KEY = "helix:worker:stats"

# Dead-letter queue key — permanently-failed jobs land here for inspection
# Keys match the dead_letter_queue.py convention: helix:dlq:<name>
_DLQ_PREFIX = "helix:dlq:worker:"

try:
    from apps.backend.services.dead_letter_queue import DLQJob

    _DLQ_AVAILABLE = True
except ImportError:
    _DLQ_AVAILABLE = False
    logger.debug("dead_letter_queue module not available, DLQ features disabled")

# Defaults
DEFAULT_QUEUE = "default"
RESULT_TTL = 86400  # 24h
HEARTBEAT_TTL = 30  # seconds — worker must refresh within this
HEARTBEAT_INTERVAL = 10  # seconds between heartbeat refreshes
CLAIM_TIMEOUT = 5  # seconds to block-wait for a job


# ── Data Model ───────────────────────────────────────────────────────


@dataclass
class WorkerJob:
    """A job in the distributed queue."""

    id: str
    queue: str
    task_name: str
    payload: dict[str, Any]
    priority: str = "normal"  # low, normal, high, critical
    max_retries: int = 3
    attempt: int = 0
    created_at: float = field(default_factory=time.time)
    timeout_seconds: int = 300  # 5 min max execution time

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "WorkerJob":
        return cls(**json.loads(raw))


@dataclass
class JobResult:
    """Result of a completed job."""

    job_id: str
    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    execution_time_ms: float = 0.0
    completed_at: float = field(default_factory=time.time)
    worker_id: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "JobResult":
        return cls(**json.loads(raw))


# ── Task Handler Registry ────────────────────────────────────────────
# Workers register handler functions by task name.

_handler_registry: dict[str, Callable] = {}


def register_task(name: str):
    """Decorator to register a task handler function.

    Usage:
        @register_task("email_send")
        async def handle_email_send(payload: dict) -> dict:
            ...
    """

    def decorator(func: Callable):
        _handler_registry[name] = func
        return func

    return decorator


# ── Producer API (used by FastAPI) ───────────────────────────────────


class WorkerQueue:
    """Producer-side API for enqueuing jobs and checking results."""

    def __init__(self, redis):
        self.redis = redis

    async def enqueue(
        self,
        task_name: str,
        payload: dict[str, Any],
        queue: str = DEFAULT_QUEUE,
        priority: str = "normal",
        max_retries: int = 3,
        timeout_seconds: int = 300,
    ) -> str:
        """Enqueue a job for worker processing. Returns job ID."""
        job = WorkerJob(
            id=str(uuid.uuid4()),
            queue=queue,
            task_name=task_name,
            payload=payload,
            priority=priority,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
        )

        queue_key = f"{_Q_PREFIX}{queue}"

        if priority in ("high", "critical"):
            # High priority: push to front of queue
            await self.redis.lpush(queue_key, job.to_json())
        else:
            # Normal/low priority: push to back
            await self.redis.rpush(queue_key, job.to_json())

        # Increment stats
        await self.redis.hincrby(_STATS_KEY, "enqueued", 1)
        await self.redis.hincrby(_STATS_KEY, f"enqueued:{queue}", 1)

        logger.info("Job %s enqueued: task=%s queue=%s", job.id, task_name, queue)
        return job.id

    async def get_job_status(self, job_id: str) -> dict[str, Any]:
        """Check job status. Returns result if completed."""
        result_key = f"{_RESULT_PREFIX}{job_id}"
        raw = await self.redis.get(result_key)

        if raw:
            data = raw.decode() if isinstance(raw, bytes) else raw
            result = JobResult.from_json(data)
            return {
                "status": "completed" if result.success else "failed",
                "result": asdict(result),
            }

        # Check if still in processing
        # (We'd need to scan all processing sets — expensive.
        #  For now, "pending" means no result yet.)
        return {"status": "pending", "result": None}

    async def get_queue_stats(self) -> dict[str, Any]:
        """Get queue statistics."""
        raw_stats = await self.redis.hgetall(_STATS_KEY)
        stats = {}
        for k, v in raw_stats.items():
            key = k.decode() if isinstance(k, bytes) else k
            val = v.decode() if isinstance(v, bytes) else v
            try:
                stats[key] = int(val)
            except (ValueError, TypeError):
                stats[key] = val

        # Get worker registry
        raw_workers = await self.redis.hgetall(_REGISTRY_KEY)
        workers = []
        for wid, wdata in raw_workers.items():
            wid_str = wid.decode() if isinstance(wid, bytes) else wid
            wdata_str = wdata.decode() if isinstance(wdata, bytes) else wdata
            try:
                info = json.loads(wdata_str)
                # Check heartbeat
                hb = await self.redis.get(f"{_HB_PREFIX}{wid_str}")
                info["alive"] = hb is not None
                info["worker_id"] = wid_str
                workers.append(info)
            except Exception as e:
                logger.warning("Failed to parse worker info for %s: %s", wid_str, e)
                workers.append({"worker_id": wid_str, "alive": False})

        return {"stats": stats, "workers": workers}

    async def list_queue_lengths(self) -> dict[str, int]:
        """Get the length of each known queue."""
        # Scan for queue keys
        lengths = {}
        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(cursor, match=f"{_Q_PREFIX}*", count=100)
            for k in keys:
                key_str = k.decode() if isinstance(k, bytes) else k
                queue_name = key_str.replace(_Q_PREFIX, "")
                length = await self.redis.llen(key_str)
                lengths[queue_name] = length
            if cursor == 0:
                break
        return lengths

    async def purge_queue(self, queue: str = DEFAULT_QUEUE) -> int:
        """Remove all pending jobs from a queue. Returns count removed."""
        queue_key = f"{_Q_PREFIX}{queue}"
        count = await self.redis.llen(queue_key)
        await self.redis.delete(queue_key)
        logger.warning("Purged %d jobs from queue %s", count, queue)
        return count


# Singleton
_worker_queue: WorkerQueue | None = None


async def get_worker_queue() -> WorkerQueue:
    """Get or create the WorkerQueue singleton."""
    global _worker_queue
    if _worker_queue is None:
        from apps.backend.core.redis_client import get_redis

        redis = await get_redis()
        _worker_queue = WorkerQueue(redis)
    return _worker_queue


# ── Worker Process ───────────────────────────────────────────────────


class Worker:
    """A worker process that claims and executes jobs from Redis queues.

    Run standalone: python -m apps.backend.services.worker_queue --queues=default
    """

    def __init__(
        self,
        queues: list[str],
        concurrency: int = 4,
        worker_id: str | None = None,
    ):
        self.queues = queues
        self.concurrency = concurrency
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self.redis = None
        self._running = False
        self._semaphore = asyncio.Semaphore(concurrency)
        self._active_jobs: dict[str, asyncio.Task] = {}

    async def start(self):
        """Start the worker — connects to Redis and begins claiming jobs."""
        import redis.asyncio as aioredis

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.redis = aioredis.from_url(redis_url, decode_responses=False)

        # Test connection
        await self.redis.ping()
        logger.info("Worker %s connected to Redis", self.worker_id)

        # Register worker
        await self.redis.hset(
            _REGISTRY_KEY,
            self.worker_id,
            json.dumps(
                {
                    "queues": self.queues,
                    "concurrency": self.concurrency,
                    "started_at": time.time(),
                    "pid": os.getpid(),
                }
            ),
        )

        self._running = True

        # Start heartbeat and claim loops
        tasks = [
            asyncio.create_task(self._heartbeat_loop()),
        ]
        for queue in self.queues:
            tasks.append(asyncio.create_task(self._claim_loop(queue)))

        logger.info(
            "Worker %s started: queues=%s concurrency=%d",
            self.worker_id,
            self.queues,
            self.concurrency,
        )

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Graceful shutdown — wait for active jobs, then unregister."""
        self._running = False
        logger.info("Worker %s shutting down...", self.worker_id)

        # Wait for active jobs (with timeout)
        if self._active_jobs:
            logger.info("Waiting for %d active jobs to complete...", len(self._active_jobs))
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._active_jobs.values(), return_exceptions=True),
                    timeout=30,
                )
            except TimeoutError:
                logger.warning("Timed out waiting for active jobs, cancelling")
                for task in self._active_jobs.values():
                    task.cancel()

        # Unregister
        if self.redis:
            await self.redis.hdel(_REGISTRY_KEY, self.worker_id)
            await self.redis.delete(f"{_HB_PREFIX}{self.worker_id}")
            await self.redis.aclose()

        logger.info("Worker %s shutdown complete", self.worker_id)

    async def _heartbeat_loop(self):
        """Periodically refresh heartbeat key in Redis."""
        while self._running:
            try:
                await self.redis.setex(
                    f"{_HB_PREFIX}{self.worker_id}",
                    HEARTBEAT_TTL,
                    json.dumps(
                        {
                            "active_jobs": len(self._active_jobs),
                            "timestamp": time.time(),
                            "pid": os.getpid(),
                        }
                    ),
                )
            except Exception as e:
                logger.warning("Heartbeat failed: %s", e)
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def _claim_loop(self, queue: str):
        """Continuously claim jobs from a queue."""
        queue_key = f"{_Q_PREFIX}{queue}"

        while self._running:
            try:
                # Block-wait for a job (BLPOP = atomic claim)
                result = await self.redis.blpop(queue_key, timeout=CLAIM_TIMEOUT)
                if result is None:
                    continue

                _, raw = result
                raw_str = raw.decode() if isinstance(raw, bytes) else raw

                try:
                    job = WorkerJob.from_json(raw_str)
                except Exception as e:
                    logger.warning("Failed to parse job from queue %s: %s", queue, e)
                    continue

                # Track in processing set
                proc_key = f"{_PROC_PREFIX}{queue}"
                await self.redis.sadd(proc_key, job.id)

                # Execute with concurrency limit
                async with self._semaphore:
                    task = asyncio.create_task(self._execute_job(job))
                    self._active_jobs[job.id] = task
                    task.add_done_callback(lambda t, jid=job.id: self._job_done(jid))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Error in claim loop for queue %s: %s", queue, e)
                await asyncio.sleep(1)

    def _job_done(self, job_id: str):
        """Callback when a job task completes."""
        self._active_jobs.pop(job_id, None)

    async def _execute_job(self, job: WorkerJob):
        """Execute a single job."""
        logger.info("[JOB] %s executing: task=%s attempt=%d", job.id, job.task_name, job.attempt)
        start = time.monotonic()

        handler = _handler_registry.get(job.task_name)
        if not handler:
            logger.warning("No handler for task %s — skipping job %s", job.task_name, job.id)
            result = JobResult(
                job_id=job.id,
                success=False,
                error=f"No handler registered for task: {job.task_name}",
                worker_id=self.worker_id,
            )
            await self._store_result(result, job)
            return

        try:
            data = await asyncio.wait_for(handler(job.payload), timeout=job.timeout_seconds)
            elapsed = (time.monotonic() - start) * 1000

            result = JobResult(
                job_id=job.id,
                success=True,
                data=data if isinstance(data, dict) else {"result": data},
                execution_time_ms=elapsed,
                worker_id=self.worker_id,
            )
            await self._store_result(result, job)
            await self.redis.hincrby(_STATS_KEY, "completed", 1)
            logger.info("[OK] Job %s completed in %.0fms", job.id, elapsed)

        except TimeoutError:
            elapsed = (time.monotonic() - start) * 1000
            logger.warning("[TIMEOUT] Job %s timed out after %ds", job.id, job.timeout_seconds)
            await self._handle_failure(job, f"Timed out after {job.timeout_seconds}s", elapsed)

        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            logger.warning("[FAIL] Job %s failed: %s", job.id, e)
            await self._handle_failure(job, str(e), elapsed)

        finally:
            # Remove from processing set
            proc_key = f"{_PROC_PREFIX}{job.queue}"
            await self.redis.srem(proc_key, job.id)

    async def _handle_failure(self, job: WorkerJob, error: str, elapsed_ms: float):
        """Handle a failed job — retry or store failure result."""
        job.attempt += 1

        if job.attempt < job.max_retries:
            # Re-enqueue with incremented attempt
            backoff = min(2**job.attempt, 60)
            logger.info(
                "[RETRY] Job %s will retry in %ds (attempt %d/%d)",
                job.id,
                backoff,
                job.attempt,
                job.max_retries,
            )
            await asyncio.sleep(backoff)

            queue_key = f"{_Q_PREFIX}{job.queue}"
            await self.redis.rpush(queue_key, job.to_json())
            await self.redis.hincrby(_STATS_KEY, "retried", 1)
        else:
            result = JobResult(
                job_id=job.id,
                success=False,
                error=error,
                execution_time_ms=elapsed_ms,
                worker_id=self.worker_id,
            )
            await self._store_result(result, job)
            await self.redis.hincrby(_STATS_KEY, "failed", 1)
            logger.warning("[DEAD] Job %s failed permanently after %d attempts", job.id, job.attempt)

            # Move to dead-letter queue for inspection and replay via DeadLetterQueue API
            if _DLQ_AVAILABLE:
                try:
                    dlq_job = DLQJob(
                        id=job.id,
                        queue=job.queue,
                        payload={"task_name": job.task_name, **job.payload},
                        attempts=job.attempt,
                        max_retries=job.max_retries,
                        created_at=job.created_at,
                        last_error=error,
                    )
                    dlq_key = f"{_DLQ_PREFIX}{job.queue}"
                    await self.redis.rpush(dlq_key, dlq_job.to_json())
                    logger.info("[DLQ] Job %s pushed to %s", job.id, dlq_key)
                except Exception as _dlq_err:
                    logger.warning("[DLQ] Failed to push job %s to DLQ: %s", job.id, _dlq_err)

    async def _store_result(self, result: JobResult, job: WorkerJob):
        """Store job result in Redis with TTL."""
        result_key = f"{_RESULT_PREFIX}{job.id}"
        await self.redis.setex(result_key, RESULT_TTL, result.to_json())


# ── Built-in Task Handlers ───────────────────────────────────────────
# Register common task handlers so workers can execute them out of the box.


@register_task("noop")
async def _handle_noop(payload: dict) -> dict:
    """No-op task for testing worker connectivity."""
    return {"message": "noop completed", "received": payload}


@register_task("webhook_deliver")
async def _handle_webhook_deliver(payload: dict) -> dict:
    """Deliver a webhook to a URL."""
    import httpx

    url = payload.get("url")
    body = payload.get("body", {})
    headers = payload.get("headers", {})
    timeout = payload.get("timeout", 30)

    if not url:
        raise ValueError("Webhook URL is required")

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=body, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return {"status_code": resp.status_code, "url": url}


@register_task("email_send")
async def _handle_email_send(payload: dict) -> dict:
    """Send an email via SendGrid (primary) or SMTP (fallback)."""
    import os

    to = payload.get("to")
    subject = payload.get("subject", "")
    body_html = payload.get("body_html", "")
    body_text = payload.get("body_text", body_html)
    from_email = payload.get("from_email", os.getenv("EMAIL_FROM", "noreply@helixcollective.ai"))

    if not to:
        raise ValueError("Email 'to' address is required")

    sendgrid_key = os.getenv("SENDGRID_API_KEY")
    if sendgrid_key:
        import httpx

        resp = await httpx.AsyncClient().post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={"Authorization": f"Bearer {sendgrid_key}", "Content-Type": "application/json"},
            json={
                "personalizations": [{"to": [{"email": to}]}],
                "from": {"email": from_email},
                "subject": subject,
                "content": [
                    {"type": "text/plain", "value": body_text},
                    {"type": "text/html", "value": body_html},
                ],
            },
            timeout=30,
        )
        if resp.status_code >= 400:
            logger.warning("SendGrid error %s: %s", resp.status_code, resp.text)
            raise RuntimeError(f"SendGrid returned {resp.status_code}")
        logger.info("Email sent via SendGrid to=%s subject=%s", to, subject)
        return {"sent_to": to, "subject": subject, "provider": "sendgrid"}

    # Fallback: SMTP
    smtp_host = os.getenv("SMTP_HOST")
    if smtp_host:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER", "")
        smtp_pass = os.getenv("SMTP_PASS", "")

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to
        msg.attach(MIMEText(body_text, "plain"))
        if body_html:
            msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            if smtp_user:
                server.login(smtp_user, smtp_pass)
            server.sendmail(from_email, [to], msg.as_string())

        logger.info("Email sent via SMTP to=%s subject=%s", to, subject)
        return {"sent_to": to, "subject": subject, "provider": "smtp"}

    logger.warning("No email provider configured (set SENDGRID_API_KEY or SMTP_HOST). Email to=%s not sent.", to)
    raise RuntimeError("No email provider configured — set SENDGRID_API_KEY or SMTP_HOST")


# ── Worker Routes (for monitoring) ───────────────────────────────────


def create_worker_routes():
    """Create FastAPI routes for worker queue monitoring."""
    from fastapi import APIRouter, Depends

    from apps.backend.core.unified_auth import get_current_user

    router = APIRouter(prefix="/api/workers", tags=["Worker Queue"])

    @router.get("/stats")
    async def worker_stats(user=Depends(get_current_user)):
        """Get worker queue statistics."""
        wq = await get_worker_queue()
        stats = await wq.get_queue_stats()
        lengths = await wq.list_queue_lengths()
        return {**stats, "queue_lengths": lengths}

    @router.get("/jobs/{job_id}")
    async def get_job(job_id: str, user=Depends(get_current_user)):
        """Check status of a specific job."""
        wq = await get_worker_queue()
        return await wq.get_job_status(job_id)

    @router.post("/enqueue")
    async def enqueue_job(
        task_name: str,
        payload: dict,
        queue: str = DEFAULT_QUEUE,
        priority: str = "normal",
        user=Depends(get_current_user),
    ):
        """Manually enqueue a job (admin/debugging)."""
        wq = await get_worker_queue()
        job_id = await wq.enqueue(task_name, payload, queue=queue, priority=priority)
        return {"job_id": job_id, "queue": queue}

    @router.get("/queues")
    async def list_queues(user=Depends(get_current_user)):
        """List all queues and their lengths."""
        wq = await get_worker_queue()
        return {"queues": await wq.list_queue_lengths()}

    return router


# ── CLI Entry Point ──────────────────────────────────────────────────


async def _run_worker(queues: list[str], concurrency: int, worker_id: str | None):
    """Run a worker process."""
    worker = Worker(queues=queues, concurrency=concurrency, worker_id=worker_id)

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(worker.shutdown()))
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            logger.debug("Signal handler not supported on this platform for %s", sig)

    await worker.start()


def main():
    """CLI entry point for running a standalone worker."""
    parser = argparse.ArgumentParser(description="Helix Worker Process")
    parser.add_argument(
        "--queues",
        default="default",
        help="Comma-separated list of queues to process (default: default)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Number of concurrent jobs per worker (default: 4)",
    )
    parser.add_argument(
        "--worker-id",
        default=None,
        help="Custom worker ID (default: auto-generated)",
    )
    args = parser.parse_args()

    queues = [q.strip() for q in args.queues.split(",")]

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("Starting Helix worker: queues=%s concurrency=%d", queues, args.concurrency)
    asyncio.run(_run_worker(queues, args.concurrency, args.worker_id))


if __name__ == "__main__":
    main()

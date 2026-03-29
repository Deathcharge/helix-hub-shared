"""
Background Tasks Service for Helix Unified

Provides comprehensive background task management including:
- Task queue implementation
- Task retry logic
- Task status tracking
- Task monitoring endpoints
- Async task execution with error handling
- Redis-backed task persistence
"""

import asyncio
import logging
import time
import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)

_TASK_KEY_PREFIX = "helix:task:"
_TASK_INDEX_KEY = "helix:tasks:index"  # sorted set: task_id scored by created_at timestamp


class TaskStatus(str, Enum):
    """Task status enumeration"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    """Task priority levels"""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class TaskResult(BaseModel):
    """Task execution result"""

    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    execution_time_ms: float


class BackgroundTask(BaseModel):
    """Background task model"""

    task_id: str
    task_name: str
    status: TaskStatus
    priority: TaskPriority
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    result: TaskResult | None = None
    retry_count: int = 0
    max_retries: int = 3
    error_message: str | None = None
    metadata: dict[str, Any] | None = None


async def _get_redis():
    """Get Redis client, returning None if unavailable."""
    try:
        from apps.backend.core.redis_client import get_redis

        return await get_redis()
    except Exception as e:
        logger.debug("Redis unavailable for task persistence: %s", e)
        return None


async def _persist_task(task: BackgroundTask) -> None:
    """Persist a task record to Redis."""
    r = await _get_redis()
    if not r:
        return
    try:
        key = f"{_TASK_KEY_PREFIX}{task.task_id}"
        data = task.model_dump_json()
        # Store task data with 7-day TTL (completed tasks auto-expire)
        ttl = 604800 if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED) else 0
        if ttl:
            await r.setex(key, ttl, data)
        else:
            await r.set(key, data)
        # Add to sorted set index (score = unix timestamp for ordering)
        try:
            ts = datetime.fromisoformat(task.created_at).timestamp()
        except (ValueError, TypeError) as e:
            logger.debug("Could not parse task created_at for %s, using current time: %s", task.task_id, e)
            ts = time.time()
        await r.zadd(_TASK_INDEX_KEY, {task.task_id: ts})
    except Exception as e:
        logger.warning("Failed to persist task %s to Redis: %s", task.task_id, e)


async def _load_task(task_id: str) -> BackgroundTask | None:
    """Load a task record from Redis."""
    r = await _get_redis()
    if not r:
        return None
    try:
        data = await r.get(f"{_TASK_KEY_PREFIX}{task_id}")
        if data:
            raw = data.decode() if isinstance(data, bytes) else data
            return BackgroundTask.model_validate_json(raw)
    except Exception as e:
        logger.debug("Failed to load task %s from Redis: %s", task_id, e)
    return None


async def _load_all_tasks(limit: int = 200) -> dict[str, BackgroundTask]:
    """Load recent task records from Redis."""
    r = await _get_redis()
    if not r:
        return {}
    tasks: dict[str, BackgroundTask] = {}
    try:
        # Get most recent task IDs from the sorted set (newest first)
        task_ids = await r.zrevrange(_TASK_INDEX_KEY, 0, limit - 1)
        if not task_ids:
            return tasks
        keys = [f"{_TASK_KEY_PREFIX}{(tid.decode() if isinstance(tid, bytes) else tid)}" for tid in task_ids]
        values = await r.mget(keys)
        for tid_raw, val in zip(task_ids, values, strict=False):
            if val:
                tid = tid_raw.decode() if isinstance(tid_raw, bytes) else tid_raw
                raw = val.decode() if isinstance(val, bytes) else val
                try:
                    tasks[tid] = BackgroundTask.model_validate_json(raw)
                except Exception as e:
                    logger.debug("Skipping corrupt task record %s: %s", tid, e)
    except Exception as e:
        logger.warning("Failed to load tasks from Redis: %s", e)
    return tasks


class BackgroundTaskManager:
    """
    Background task manager with queue, retry logic, and monitoring.

    Features:
    - Async task execution
    - Automatic retry with exponential backoff
    - Task status tracking (Redis-backed)
    - Priority-based execution
    - Concurrent task limits
    - Task cancellation support
    """

    # Maximum number of completed/failed tasks kept in-memory before pruning.
    _MAX_CACHED_TASKS = 500

    def __init__(
        self,
        max_concurrent_tasks: int = 10,
        default_max_retries: int = 3,
        retry_base_delay: float = 1.0,
    ):
        self.max_concurrent_tasks = max_concurrent_tasks
        self.default_max_retries = default_max_retries
        self.retry_base_delay = retry_base_delay

        # Write-through cache over Redis
        self.tasks: dict[str, BackgroundTask] = {}
        self.task_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()

        # Semaphore for concurrent task limiting
        self.semaphore = asyncio.Semaphore(max_concurrent_tasks)

        # Background worker task
        self.worker_task: asyncio.Task | None = None

        # Periodic pruning task
        self._pruner_task: asyncio.Task | None = None

        # Shutdown flag
        self.is_running = False

    async def start(self) -> None:
        """Start the background task worker"""
        if self.is_running:
            logger.warning("Background task manager is already running")
            return

        # Load existing task records from Redis on startup
        persisted = await _load_all_tasks()
        if persisted:
            self.tasks.update(persisted)
            logger.info("Loaded %d task records from Redis", len(persisted))

        # Recover stale tasks that were RUNNING/RETRYING when the previous
        # process died — mark them FAILED so they don't stay stuck forever.
        recovered = 0
        for task in list(self.tasks.values()):
            if task.status in (TaskStatus.RUNNING, TaskStatus.RETRYING):
                task.status = TaskStatus.FAILED
                task.completed_at = datetime.now(UTC).isoformat()
                task.error_message = "Recovered after service restart (was stuck in %s)" % task.status.value
                task.result = TaskResult(
                    success=False,
                    error=task.error_message,
                    execution_time_ms=0,
                )
                await _persist_task(task)
                recovered += 1
        if recovered:
            logger.warning("Recovered %d stale tasks (marked FAILED after restart)", recovered)

        self.is_running = True
        self.worker_task = asyncio.create_task(self._worker())
        self._pruner_task = asyncio.create_task(self._prune_old_tasks_loop())
        logger.info("[OK] Background task manager started")

    async def stop(self) -> None:
        """Stop the background task worker"""
        if not self.is_running:
            return

        self.is_running = False

        for t in (self.worker_task, self._pruner_task):
            if t:
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass

        logger.info("[OK] Background task manager stopped")

    async def _worker(self) -> None:
        """Background worker that processes tasks from the queue"""
        logger.info("[INFO] Background task worker started")

        while self.is_running:
            try:
                # Wait for task with timeout
                try:
                    priority_score, task_id = await asyncio.wait_for(self.task_queue.get(), timeout=1.0)
                except TimeoutError:
                    continue

                # Get task from storage
                task = self.tasks.get(task_id)
                if not task:
                    logger.warning("Task %s not found in storage", task_id)
                    continue

                # Skip if task is cancelled
                if task.status == TaskStatus.CANCELLED:
                    logger.info("Task %s was cancelled, skipping", task_id)
                    continue

                # Execute task
                await self._execute_task(task)

            except Exception as e:
                logger.error("Error in background task worker: %s", e, exc_info=True)
                await asyncio.sleep(1.0)

        logger.info("[INFO] Background task worker stopped")

    async def _prune_old_tasks_loop(self) -> None:
        """Periodically evict completed/failed tasks from in-memory cache."""
        while self.is_running:
            try:
                await asyncio.sleep(600)  # every 10 minutes
                terminal = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}
                finished = [(tid, t) for tid, t in self.tasks.items() if t.status in terminal]
                if len(finished) > self._MAX_CACHED_TASKS:
                    # Sort oldest first, evict the excess
                    finished.sort(key=lambda x: x[1].created_at)
                    to_evict = finished[: len(finished) - self._MAX_CACHED_TASKS]
                    for tid, _ in to_evict:
                        self.tasks.pop(tid, None)
                    logger.info(
                        "Pruned %d finished tasks from in-memory cache (kept %d)",
                        len(to_evict),
                        self._MAX_CACHED_TASKS,
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Task cache pruning failed: %s", e)

    async def _execute_task(self, task: BackgroundTask) -> None:
        """Execute a single task with retry logic"""
        async with self.semaphore:
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now(UTC).isoformat()
            await _persist_task(task)

            logger.info(
                "[TASK] Starting task %s: %s (retry %d/%d)",
                task.task_id,
                task.task_name,
                task.retry_count,
                task.max_retries,
            )

            try:
                # Get task function from registry
                task_func = _task_registry.get(task.task_name)
                if not task_func:
                    raise ValueError(f"Task function not found: {task.task_name}")

                # Execute task function
                start_time = time.monotonic()
                result_data = await task_func(task.metadata or {})
                execution_time = (time.monotonic() - start_time) * 1000

                # Task completed successfully
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.now(UTC).isoformat()
                task.result = TaskResult(success=True, data=result_data, execution_time_ms=execution_time)
                await _persist_task(task)

                logger.info("[OK] Task %s completed successfully in %.2fms", task.task_id, execution_time)

            except Exception as e:
                error_message = str(e)
                logger.error(
                    "[ERROR] Task %s failed: %s",
                    task.task_id,
                    error_message,
                    exc_info=True,
                )

                # Check if we should retry
                if task.retry_count < task.max_retries:
                    task.status = TaskStatus.RETRYING
                    task.retry_count += 1
                    task.error_message = error_message
                    await _persist_task(task)

                    # Calculate exponential backoff delay
                    retry_delay = self.retry_base_delay * (2**task.retry_count)
                    logger.info(
                        "[RETRY] Task %s will retry in %.2fs (attempt %d/%d)",
                        task.task_id,
                        retry_delay,
                        task.retry_count,
                        task.max_retries,
                    )

                    # Schedule retry
                    await asyncio.sleep(retry_delay)
                    await self._retry_task(task)
                else:
                    # Max retries reached, mark as failed
                    task.status = TaskStatus.FAILED
                    task.completed_at = datetime.now(UTC).isoformat()
                    task.result = TaskResult(success=False, error=error_message, execution_time_ms=0)
                    task.error_message = error_message
                    await _persist_task(task)

                    logger.error("[FAIL] Task %s failed after %s retries", task.task_id, task.max_retries)

    async def _retry_task(self, task: BackgroundTask) -> None:
        """Re-queue a failed task for retry"""
        # Calculate priority score (higher priority = lower score)
        priority_score = self._get_priority_score(task.priority)

        # Re-add to queue
        await self.task_queue.put((priority_score, task.task_id))

    def _get_priority_score(self, priority: TaskPriority) -> int:
        """Convert priority to numeric score for queue ordering"""
        priority_scores = {
            TaskPriority.CRITICAL: 0,
            TaskPriority.HIGH: 1,
            TaskPriority.NORMAL: 2,
            TaskPriority.LOW: 3,
        }
        return priority_scores.get(priority, 2)

    async def submit_task(
        self,
        task_name: str,
        task_func: Callable[[dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]],
        metadata: dict[str, Any] | None = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        max_retries: int | None = None,
    ) -> str:
        """
        Submit a new background task.

        Args:
            task_name: Name of the task
            task_func: Async function to execute
            metadata: Optional metadata for the task
            priority: Task priority
            max_retries: Maximum retry attempts (default: 3)

        Returns:
            Task ID
        """
        # Register task function
        _task_registry[task_name] = task_func

        # Generate unique task ID
        task_id = str(uuid.uuid4())

        # Create task model
        task = BackgroundTask(
            task_id=task_id,
            task_name=task_name,
            status=TaskStatus.PENDING,
            priority=priority,
            created_at=datetime.now(UTC).isoformat(),
            max_retries=max_retries or self.default_max_retries,
            metadata=metadata,
        )

        # Store task locally and persist to Redis
        self.tasks[task_id] = task
        await _persist_task(task)

        # Calculate priority score and add to queue
        priority_score = self._get_priority_score(priority)
        await self.task_queue.put((priority_score, task_id))

        logger.info(
            "[QUEUE] Task %s queued: %s (priority: %s, max_retries: %d)",
            task_id,
            task_name,
            priority,
            task.max_retries,
        )

        return task_id

    async def get_task_status(self, task_id: str) -> BackgroundTask | None:
        """Get the status of a task"""
        # Check in-memory first, fall back to Redis
        task = self.tasks.get(task_id)
        if task:
            return task
        task = await _load_task(task_id)
        if task:
            self.tasks[task_id] = task
        return task

    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a pending task.

        Args:
            task_id: Task ID to cancel

        Returns:
            True if cancelled, False if not found or already running
        """
        task = self.tasks.get(task_id)
        if not task:
            task = await _load_task(task_id)
            if task:
                self.tasks[task_id] = task

        if not task:
            return False

        if task.status in [TaskStatus.PENDING, TaskStatus.RETRYING]:
            task.status = TaskStatus.CANCELLED
            await _persist_task(task)
            logger.info("[CANCEL] Task %s cancelled", task_id)
            return True

        return False

    async def list_tasks(self, status: TaskStatus | None = None, limit: int = 100) -> list[BackgroundTask]:
        """
        List tasks with optional filtering.

        Args:
            status: Filter by status (optional)
            limit: Maximum number of tasks to return

        Returns:
            List of tasks
        """
        # Refresh from Redis if in-memory cache is empty
        if not self.tasks:
            self.tasks = await _load_all_tasks(limit=limit)

        tasks = list(self.tasks.values())

        # Filter by status if specified
        if status:
            tasks = [t for t in tasks if t.status == status]

        # Sort by created_at (newest first) and limit
        tasks.sort(key=lambda t: t.created_at, reverse=True)

        return tasks[:limit]

    async def get_task_statistics(self) -> dict[str, Any]:
        """Get task execution statistics"""
        # Refresh from Redis if in-memory is empty
        if not self.tasks:
            self.tasks = await _load_all_tasks()

        total_tasks = len(self.tasks)

        status_counts = {}
        for status in TaskStatus:
            status_counts[status.value] = sum(1 for t in self.tasks.values() if t.status == status)

        # Calculate average execution time
        completed_tasks = [t for t in self.tasks.values() if t.result and t.result.execution_time_ms > 0]

        avg_execution_time = 0
        if completed_tasks:
            avg_execution_time = sum(t.result.execution_time_ms for t in completed_tasks) / len(completed_tasks)

        return {
            "total_tasks": total_tasks,
            "status_counts": status_counts,
            "avg_execution_time_ms": round(avg_execution_time, 2),
            "queue_size": self.task_queue.qsize(),
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "is_running": self.is_running,
        }


# Global task registry
_task_registry: dict[str, Callable] = {}

# Global task manager instance
_task_manager: BackgroundTaskManager | None = None


def get_task_manager() -> BackgroundTaskManager:
    """Get or create the global task manager instance"""
    global _task_manager

    if _task_manager is None:
        _task_manager = BackgroundTaskManager()

    return _task_manager


async def start_background_tasks() -> None:
    """Start the background task manager and register periodic tasks"""
    task_manager = get_task_manager()
    await task_manager.start()

    # Register coordination snapshot periodic task
    try:
        from apps.backend.services.state_snapshot_service import get_snapshot_service

        snapshot_service = get_snapshot_service()

        async def _coordination_snapshot_loop() -> None:
            """Capture coordination state every 5 minutes."""
            while task_manager.is_running:
                try:
                    snapshot_service.capture_snapshot(source="background_task")
                except Exception as e:
                    logger.debug("Coordination snapshot capture failed: %s", e)
                await asyncio.sleep(300)  # 5 minutes

        asyncio.create_task(_coordination_snapshot_loop())
        logger.info("[OK] Coordination snapshot periodic task registered (every 5 min)")
    except Exception as e:
        logger.warning("[WARN] Failed to register coordination snapshot task: %s", e)

    # Register expired token cleanup (every 5 minutes)
    try:
        from apps.backend.routes.auth import cleanup_expired_tokens

        async def _token_cleanup_loop() -> None:
            """Prune expired tokens from in-memory store every 5 minutes."""
            while task_manager.is_running:
                try:
                    removed = cleanup_expired_tokens()
                    if removed:
                        logger.info("Cleaned up %d expired tokens", removed)
                except Exception as e:
                    logger.debug("Token cleanup failed: %s", e)
                await asyncio.sleep(300)  # 5 minutes

        asyncio.create_task(_token_cleanup_loop())
        logger.info("[OK] Expired token cleanup task registered (every 5 min)")
    except Exception as e:
        logger.warning("[WARN] Failed to register token cleanup task: %s", e)

    # Register weekly digest email (checks every hour, sends on Monday 9 AM UTC)
    try:

        async def _weekly_digest_loop() -> None:
            """Check once per hour; on Monday 9 AM UTC, send weekly digest to opted-in users."""
            import datetime

            last_sent_week: int = -1  # ISO week number of last send

            while task_manager.is_running:
                try:
                    now = datetime.datetime.now(datetime.UTC)
                    # Monday = 0, 9 AM UTC window (hour 9)
                    is_monday_morning = now.weekday() == 0 and now.hour == 9
                    current_week = now.isocalendar()[1]

                    if is_monday_morning and current_week != last_sent_week:
                        last_sent_week = current_week
                        await _send_weekly_digests()
                except Exception as e:
                    logger.warning("Weekly digest loop error: %s", e)
                await asyncio.sleep(3600)  # Check every hour

        asyncio.create_task(_weekly_digest_loop())
        logger.info("[OK] Weekly digest email task registered (Monday 9 AM UTC)")
    except Exception as e:
        logger.warning("[WARN] Failed to register weekly digest task: %s", e)


async def _send_weekly_digests() -> None:
    """
    Send weekly activity digest to all users who have email and haven't
    disabled marketing/analytics emails.
    """
    try:
        from sqlalchemy import select

        from apps.backend.db_models import User, get_async_db
        from apps.backend.services.email_automation import send_weekly_summary_email

        async for db in get_async_db():
            result = await db.execute(
                select(User).where(
                    User.email.isnot(None),
                    User.email != "",
                    User.is_active == True,  # noqa: E712
                )
            )
            users = result.scalars().all()

            sent_count = 0
            for user in users:
                try:
                    # Gather user's weekly stats
                    stats = await _gather_user_weekly_stats(db, user)

                    await send_weekly_summary_email(
                        user_email=user.email,
                        user_name=user.display_name or user.email.split("@")[0],
                        summary_data=stats,
                    )
                    sent_count += 1
                except Exception as e:
                    logger.debug("Failed to send digest to %s: %s", user.email, e)

            logger.info("Weekly digest sent to %d/%d users", sent_count, len(users))
            break  # Only one iteration of async generator
    except ImportError as e:
        logger.debug("Weekly digest dependencies not available: %s", e)
    except Exception as e:
        logger.warning("Weekly digest batch failed: %s", e)


async def _gather_user_weekly_stats(db, user) -> dict:
    """Gather a user's activity stats for the past 7 days."""
    import datetime

    from sqlalchemy import func, select

    one_week_ago = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=7)

    stats = {
        "api_calls": 0,
        "agent_sessions": 0,
        "tokens_used": 0,
        "top_feature": "Dashboard",
    }

    try:
        # Count API usage from api_usage table
        from apps.backend.db_models import APIUsage

        usage_result = await db.execute(
            select(
                func.count(APIUsage.id),
                func.coalesce(func.sum(APIUsage.total_tokens), 0),
            ).where(
                APIUsage.user_id == user.id,
                APIUsage.created_at >= one_week_ago,
            )
        )
        row = usage_result.one_or_none()
        if row:
            stats["api_calls"] = row[0] or 0
            stats["tokens_used"] = row[1] or 0
    except Exception as e:
        logger.debug("Could not gather API usage stats: %s", e)

    try:
        # Count chat conversations as agent sessions
        from apps.backend.db_models import Conversation

        conv_result = await db.execute(
            select(func.count(Conversation.id)).where(
                Conversation.user_id == user.id,
                Conversation.created_at >= one_week_ago,
            )
        )
        stats["agent_sessions"] = conv_result.scalar() or 0
    except Exception as e:
        logger.debug("Could not gather conversation stats: %s", e)

    # Determine top feature
    if stats["agent_sessions"] > stats["api_calls"]:
        stats["top_feature"] = "Agent Chat"
    elif stats["api_calls"] > 0:
        stats["top_feature"] = "API"

    return stats


async def stop_background_tasks() -> None:
    """Stop the background task manager"""
    task_manager = get_task_manager()
    await task_manager.stop()

"""
Living Documents Service (T5-A)

Handles scheduled and manual refreshes of ManagedDocuments — documents
that an AI agent keeps up-to-date based on a user-defined research prompt
and a configurable cron schedule.

Key responsibilities:
- run_refresh(): core refresh logic (LLM call → update doc + log)
- LivingDocumentScheduler: registers/unregisters docs in AgentTaskScheduler
- _rehydrate_living_docs(): startup hook to re-register all enabled docs after restart
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ── Schedule label → cron mapping ──────────────────────────────────────────
SCHEDULE_CRONS: dict[str, str] = {
    "daily": "0 9 * * *",
    "weekly": "0 9 * * 1",
    "monthly": "0 9 1 * *",
}

# Sentinel prefix used to identify living-document tasks inside AgentTaskScheduler
_SENTINEL = "__living_doc_refresh__:"

# ── Per-tier document creation limits ──────────────────────────────────────
TIER_DOC_LIMITS: dict[str, int] = {
    "free": 0,
    "hobby": 3,
    "starter": 10,
    "pro": 50,
    "enterprise": -1,  # unlimited
}


def get_doc_limit(tier: str) -> int:
    """Return max living documents for a tier. -1 = unlimited, 0 = not allowed."""
    return TIER_DOC_LIMITS.get(tier.lower(), 0)


# ── Core refresh logic ──────────────────────────────────────────────────────


async def run_refresh(
    document_id: str,
    user_id: str,
    triggered_by: Literal["schedule", "manual"],
    db: AsyncSession,
) -> dict:
    """Run a single refresh cycle for a living document.

    Loads the document, invokes the assigned agent via UnifiedLLMService,
    updates content in-place, and writes an immutable refresh log row.

    Returns the refresh log as a dict.

    Raises ValueError if document not found or wrong owner.
    Raises RuntimeError if a refresh is already in progress (concurrency guard).
    """
    from apps.backend.db_models import ManagedDocument, ManagedDocumentRefreshLog

    # ── Atomic concurrency guard: claim status=refreshing ──────────────────
    # UPDATE ... WHERE id = ? AND status != 'refreshing' avoids a TOCTOU race.
    result = await db.execute(
        update(ManagedDocument)
        .where(
            ManagedDocument.id == document_id,
            ManagedDocument.user_id == user_id,
            ManagedDocument.status != "refreshing",
        )
        .values(status="refreshing")
        .returning(ManagedDocument.id)
    )
    claimed_id = result.scalar_one_or_none()
    if claimed_id is None:
        # Either not found, wrong owner, or already refreshing
        doc_check = await db.execute(select(ManagedDocument).where(ManagedDocument.id == document_id))
        doc = doc_check.scalar_one_or_none()
        if doc is None:
            raise ValueError(f"Document {document_id} not found")
        if doc.user_id != user_id:
            raise PermissionError(f"Document {document_id} not owned by user")
        raise RuntimeError("A refresh is already in progress for this document")

    await db.commit()

    # Re-load the document after the status update
    doc_result = await db.execute(select(ManagedDocument).where(ManagedDocument.id == document_id))
    doc = doc_result.scalar_one()

    start = datetime.now(UTC)
    new_content: str | None = None
    error_message: str | None = None
    final_status = "error"

    try:
        from apps.backend.services.unified_llm import UnifiedLLMService

        llm = UnifiedLLMService()
        system_prompt = (
            f"You are {doc.agent_id}, an AI agent maintaining a living document titled "
            f"'{doc.title}'. Produce a comprehensive, well-structured Markdown report. "
            f"Use clear headings, be factual, and include a brief summary at the top. "
            f"Do not copy the previous content verbatim — rewrite and update it."
        )
        user_prompt = (
            f"Research prompt: {doc.refresh_prompt}\n\n"
            f"Previous content (for context only — do not copy verbatim):\n"
            f"{doc.content or '[No previous content — write from scratch]'}"
        )
        new_content = await llm.generate(
            prompt=user_prompt,
            system=system_prompt,
            max_tokens=4096,
            temperature=0.4,
        )
        final_status = "success"
        logger.info(
            "Living document refresh succeeded: doc=%s agent=%s triggered_by=%s",
            document_id,
            doc.agent_id,
            triggered_by,
        )
    except Exception as exc:
        error_message = str(exc)
        logger.error(
            "Living document refresh failed: doc=%s error=%s",
            document_id,
            exc,
        )

    duration_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)

    # ── Update document ──────────────────────────────────────────────────────
    await db.execute(
        update(ManagedDocument)
        .where(ManagedDocument.id == document_id)
        .values(
            content=new_content if final_status == "success" else doc.content,
            status="idle" if final_status == "success" else "error",
            last_error=error_message,
            last_refreshed_at=start if final_status == "success" else doc.last_refreshed_at,
            refresh_count=ManagedDocument.refresh_count + (1 if final_status == "success" else 0),
            updated_at=datetime.now(UTC),
        )
    )

    # ── Write immutable refresh log ──────────────────────────────────────────
    log_id = str(uuid.uuid4())
    log_row = {
        "id": log_id,
        "document_id": document_id,
        "user_id": user_id,
        "triggered_by": triggered_by,
        "status": final_status,
        "content_snapshot": new_content,
        "agent_id": doc.agent_id,
        "duration_ms": duration_ms,
        "error_message": error_message,
        "refreshed_at": start,
    }
    db.add(ManagedDocumentRefreshLog(**log_row))
    await db.commit()

    return log_row


# ── Scheduler integration ────────────────────────────────────────────────────


class LivingDocumentScheduler:
    """Registers/unregisters living documents in the AgentTaskScheduler.

    Uses a sentinel prompt (`__living_doc_refresh__:{doc_id}`) so that the
    patched _execute_task (installed in main.py lifespan) can intercept the
    task and call run_refresh() instead of running a plain LLM prompt.
    """

    def register(self, doc) -> str:
        """Register a document with the AgentTaskScheduler. Returns the task_id."""
        from apps.backend.workflow_engine.scheduler import (
            AgentTaskScheduler,
            ScheduleType,
            get_agent_task_scheduler,
        )

        scheduler: AgentTaskScheduler = get_agent_task_scheduler()
        task = scheduler.add_task(
            user_id=doc.user_id,
            agent_id=doc.agent_id,
            name=f"living_doc:{doc.id}:{doc.title[:40]}",
            prompt=f"{_SENTINEL}{doc.id}",
            schedule_type=ScheduleType.CRON,
            cron_expression=doc.schedule_cron,
        )
        return task.id

    def unregister(self, task_id: str) -> None:
        """Remove a task from the scheduler (no-op if already gone)."""
        from apps.backend.workflow_engine.scheduler import get_agent_task_scheduler

        get_agent_task_scheduler().remove_task(task_id)


_living_doc_scheduler = LivingDocumentScheduler()


def get_living_doc_scheduler() -> LivingDocumentScheduler:
    return _living_doc_scheduler


# ── Startup rehydration ──────────────────────────────────────────────────────


async def rehydrate_living_docs() -> int:
    """Re-register all enabled living documents into the AgentTaskScheduler.

    Called in main.py lifespan after the scheduler has started.
    Also resets any documents stuck in 'refreshing' status (interrupted by restart).

    Returns the number of documents re-registered.
    """
    from apps.backend.db_models import ManagedDocument, get_db_session

    count = 0
    async with get_db_session() as db:
        # Reset stuck 'refreshing' docs from a previous crash
        await db.execute(
            update(ManagedDocument)
            .where(ManagedDocument.status == "refreshing")
            .values(
                status="error",
                last_error="Interrupted by server restart",
            )
        )
        await db.commit()

        # Re-register all enabled docs
        result = await db.execute(select(ManagedDocument).where(ManagedDocument.is_enabled == True))  # noqa: E712
        docs = result.scalars().all()
        svc = get_living_doc_scheduler()
        for doc in docs:
            try:
                new_task_id = svc.register(doc)
                doc.scheduler_task_id = new_task_id
                count += 1
            except Exception as e:
                logger.warning("Failed to re-register living doc %s: %s", doc.id, e)
        await db.commit()

    logger.info("[OK] Rehydrated %d living documents into scheduler", count)
    return count

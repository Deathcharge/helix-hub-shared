"""
Engagement Event Hooks
=====================

Non-blocking helper functions that fire engagement tracking events.
These run in FastAPI background tasks so they never slow down request handling.

Usage in a route:
    from apps.backend.services.engagement_hooks import fire_login_event

    @router.post("/login")
    async def login(..., background_tasks: BackgroundTasks):
        ...
        background_tasks.add_task(fire_login_event, user_id, tier=tier)
        return response
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def _safe_track(event_type_str: str, user_id: str, metadata: dict[str, Any] | None = None) -> None:
    """Track an engagement event, swallowing any errors."""
    try:
        from apps.backend.services.engagement_service import EngagementEvent, track_engagement_event

        event_type = EngagementEvent(event_type_str)
        await track_engagement_event(user_id, event_type, metadata)
    except Exception as exc:
        # Never let engagement tracking break the caller
        logger.debug("Engagement tracking failed for %s/%s: %s", user_id, event_type_str, exc)


# ---------------------------------------------------------------------------
# Login / Authentication
# ---------------------------------------------------------------------------

async def fire_login_event(user_id: str, *, tier: str = "free", agent_id: str | None = None) -> None:
    """Fire after successful authentication."""
    await _safe_track("login", user_id, {"tier": tier, "agent_id": agent_id})
    # Also mark daily active
    await _safe_track("daily_active", user_id)


# ---------------------------------------------------------------------------
# Agent Execution
# ---------------------------------------------------------------------------

async def fire_agent_execution_event(
    user_id: str, *, agent_name: str, operation: str = "handshake"
) -> None:
    """Fire when a user triggers an agent operation (handshake, Z-88, chat)."""
    await _safe_track("agent_execution", user_id, {"agent": agent_name, "operation": operation})


# ---------------------------------------------------------------------------
# Workflow / Spiral Events
# ---------------------------------------------------------------------------

async def fire_workflow_created_event(user_id: str, *, workflow_id: str, name: str = "") -> None:
    """Fire when a user creates a new Spiral/workflow."""
    await _safe_track("workflow_created", user_id, {"workflow_id": workflow_id, "name": name})


async def fire_workflow_completed_event(user_id: str, *, workflow_id: str) -> None:
    """Fire when a workflow run finishes successfully."""
    await _safe_track("workflow_completed", user_id, {"workflow_id": workflow_id})


# ---------------------------------------------------------------------------
# Integration Events
# ---------------------------------------------------------------------------

async def fire_integration_connected_event(
    user_id: str, *, provider: str, integration_id: str = ""
) -> None:
    """Fire when a user connects an external integration (Discord, GitHub, etc.)."""
    await _safe_track("integration_connected", user_id, {"provider": provider, "integration_id": integration_id})


# ---------------------------------------------------------------------------
# Feature Discovery
# ---------------------------------------------------------------------------

async def fire_feature_first_use_event(user_id: str, *, feature_id: str) -> None:
    """Fire when a user uses a feature for the first time."""
    await _safe_track("feature_first_use", user_id, {"feature_id": feature_id})


# ---------------------------------------------------------------------------
# Content & Community
# ---------------------------------------------------------------------------

async def fire_feedback_event(user_id: str, *, feedback_type: str = "general", content: str = "") -> None:
    """Fire when a user submits feedback."""
    await _safe_track("feedback_submitted", user_id, {"type": feedback_type, "content": content[:200]})


async def fire_template_used_event(user_id: str, *, template_id: str, template_name: str = "") -> None:
    """Fire when a user uses a workflow template."""
    await _safe_track("template_used", user_id, {"template_id": template_id, "name": template_name})

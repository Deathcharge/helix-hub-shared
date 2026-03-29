"""
Agent Access Control
====================

Shared utilities for enforcing tier-based agent access, BYOK key resolution,
and ethics validation across all agent route endpoints.

Wires together existing systems:
- saas/guards.py (tier enforcement)
- middleware/rbac.py (TIER_FEATURES, can_use_agent)
- byok_management.py (get_effective_llm_key)
- ethics/ethics_validator.py (ethics validation)

Usage:
    from apps.backend.agents.agent_access import (
        get_authenticated_user,
        require_agent_access,
        validate_agent_ethics,
        resolve_llm_key,
    )

    @router.post("/agents/{agent_id}/execute")
    async def execute_agent(
        agent_id: str,
        user: User = Depends(get_authenticated_user),
    ):
        require_agent_access(user, agent_id)
        api_key = await resolve_llm_key(user, provider="anthropic")
        await validate_agent_ethics(agent_id, action_description)
        ...
"""

import logging
from typing import Any

from fastapi import HTTPException, status

from apps.backend.middleware.rbac import TIER_FEATURES, can_use_agent
from apps.backend.saas.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)

# Tier hierarchy for comparison
TIER_HIERARCHY = ["free", "hobby", "starter", "pro", "enterprise"]

# Agent-to-minimum-tier mapping (derived from TIER_FEATURES)
# Free tier: rishi, kael, oracle
# Pro+: all agents
FREE_TIER_AGENTS = {"rishi", "kael", "oracle"}


def get_user_tier(user) -> str:
    """Extract subscription tier from user object, defaulting to free."""
    tier = getattr(user, "subscription_tier", None) or "free"
    return tier.lower()


def get_user_id_str(user) -> str:
    """Extract user ID as string from user object."""
    user_id = getattr(user, "id", None)
    return str(user_id) if user_id else "anonymous"


def require_agent_access(user, agent_id: str) -> None:
    """
    Check if the user's subscription tier allows access to the specified agent.

    Uses the existing TIER_FEATURES from rbac.py and can_use_agent().
    Raises HTTP 402 if the user's tier is insufficient.

    Args:
        user: Authenticated User object (from get_current_user dependency)
        agent_id: The agent identifier (e.g., "kael", "lumina", "vega")

    Raises:
        HTTPException 402: If user's tier doesn't include this agent
    """
    tier = get_user_tier(user)
    agent_id_lower = agent_id.lower()

    if not can_use_agent(tier, agent_id_lower):
        allowed = TIER_FEATURES.get(tier, TIER_FEATURES["free"]).get("agents", [])
        allowed_display = allowed if isinstance(allowed, list) else "all"

        logger.warning(
            "Agent access denied: user=%s tier=%s agent=%s allowed=%s",
            get_user_id_str(user),
            tier,
            agent_id_lower,
            allowed_display,
        )

        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "agent_access_denied",
                "message": f"Your subscription tier ({tier.title()}) does not include access to the {agent_id} agent. "
                "Please upgrade to Pro or higher.",
                "agent": agent_id,
                "current_tier": tier,
                "allowed_agents": allowed_display,
                "upgrade_url": "/billing",
            },
        )

    logger.debug(
        "Agent access granted: user=%s tier=%s agent=%s",
        get_user_id_str(user),
        tier,
        agent_id_lower,
    )


async def resolve_llm_key(user, provider: str = "anthropic") -> str | None:
    """
    Resolve the effective LLM API key for a user, preferring BYOK keys.

    Wires the existing byok_management.get_effective_llm_key into agent execution.

    Args:
        user: Authenticated User object
        provider: LLM provider name (openai, anthropic, xai, etc.)

    Returns:
        API key string, or None if no key available (graceful fallback)
    """
    try:
        from apps.backend.byok_management import get_effective_llm_key

        user_id = get_user_id_str(user)
        key = await get_effective_llm_key(user_id, provider)
        logger.debug(
            "LLM key resolved for user=%s provider=%s source=%s",
            user_id,
            provider,
            "byok" if user_id != "anonymous" else "platform",
        )
        return key
    except ValueError:
        logger.debug(
            "No LLM key available for user=%s provider=%s",
            get_user_id_str(user),
            provider,
        )
        return None
    except ImportError:
        logger.warning("byok_management module not available")
        return None
    except Exception as e:
        logger.error("Error resolving LLM key: %s", e)
        return None


async def validate_agent_ethics(
    agent_id: str,
    action: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Validate an agent action against ethical guardrails before execution.

    Wires the existing EthicsValidator into enhanced agent endpoints.
    Non-blocking: logs violations but allows action to proceed with warnings
    unless the violation is critical.

    Args:
        agent_id: The agent performing the action
        action: Description of the proposed action
        context: Additional context (UCF metrics, user info, etc.)

    Returns:
        Dict with compliance result:
            - compliant (bool)
            - accords (list)
            - outcome (str)
            - violations (list, if any)

    Raises:
        HTTPException 403: Only for critical violations (nonmaleficence)
    """
    try:
        from apps.backend.ethics.ethics_validator import EthicsValidator

        validator = EthicsValidator()

        # Provide default UCF metrics if not in context
        ucf_metrics = (context or {}).get(
            "ucf_metrics",
            {
                "performance_score": 5.0,
                "harmony": 0.7,
                "resilience": 0.7,
                "friction": 0.3,
                "focus": 0.6,
                "throughput": 0.7,
                "velocity": 0.5,
            },
        )

        decision = validator.evaluate_action(
            agent_name=agent_id,
            proposed_action=action,
            context=context or {},
            ucf_metrics=ucf_metrics,
        )

        # Convert EthicalDecision dataclass to dict
        result = decision.to_dict()
        compliant = decision.outcome in ("APPROVED", "REQUIRES_REVIEW")
        violations = decision.violations

        if not compliant:
            logger.warning(
                "Ethics violation: agent=%s action=%s outcome=%s violations=%s",
                agent_id,
                action[:100],
                decision.outcome,
                violations,
            )

            # Only block for critical nonmaleficence violations
            if "nonmaleficence" in [v.lower() for v in violations]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "error": "ethics_validator_violation",
                        "message": "Action blocked: ethics nonmaleficence violation",
                        "agent": agent_id,
                        "violations": violations,
                    },
                )

        return result

    except HTTPException:
        raise
    except ImportError:
        logger.debug("Ethics Validator validator not available, skipping ethics check")
        return {
            "compliant": True,
            "accords": ["nonmaleficence", "autonomy", "compassion", "humility"],
            "outcome": "APPROVED",
            "note": "validator_unavailable",
        }
    except Exception as e:
        logger.error("Ethics Validator validation error: %s", e)
        # Fail open - don't block actions due to validator errors
        return {
            "compliant": True,
            "accords": [],
            "outcome": "ERROR_FALLBACK",
            "error": str(e),
        }


def log_agent_handoff(
    from_agent: str,
    to_agent: str,
    reason: str,
    user_id: str = "system",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Log a structured agent-to-agent handoff event for audit trail.

    Args:
        from_agent: Source agent identifier
        to_agent: Destination agent identifier
        reason: Reason for the handoff
        user_id: User who triggered the handoff
        context: Additional context

    Returns:
        Dict with handoff record
    """
    import datetime

    handoff_record = {
        "type": "agent_handoff",
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        "from_agent": from_agent,
        "to_agent": to_agent,
        "reason": reason,
        "user_id": user_id,
        "context": context or {},
    }

    logger.info(
        "Agent handoff: %s -> %s | reason=%s | user=%s",
        from_agent,
        to_agent,
        reason,
        user_id,
    )

    return handoff_record


# Re-export get_current_user for convenience
get_authenticated_user = get_current_user

"""
Smart Agent Auto-Selection
==========================

Enhanced agent routing that goes beyond keyword matching.
Combines three signals:

1. **Intent classification** — classifies the user message into task categories
   (code, debug, plan, write, explain, security, data, design, ops, emotional)
   and maps to optimal agents.

2. **Reputation weighting** — boosts agents with higher satisfaction scores
   for the current user.

3. **Keyword scoring** — the existing substring-match scorer as a baseline.

Falls back gracefully: intent → keyword → page default.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Intent categories → ranked agent lists
# ---------------------------------------------------------------------------

INTENT_CATEGORIES: dict[str, dict[str, Any]] = {
    "code_write": {
        "signals": [
            "write code",
            "implement",
            "create a function",
            "build a",
            "add a feature",
            "scaffold",
            "boilerplate",
            "coding",
        ],
        "agents": ["arjuna", "gemini", "nova"],
    },
    "code_debug": {
        "signals": [
            "debug",
            "fix bug",
            "error",
            "traceback",
            "exception",
            "not working",
            "broken",
            "failing",
            "stack trace",
        ],
        "agents": ["arjuna", "shadow", "echo"],
    },
    "code_review": {
        "signals": [
            "review code",
            "code review",
            "audit code",
            "check my code",
            "improve code",
            "refactor",
            "clean up",
        ],
        "agents": ["kavach", "shadow", "arjuna"],
    },
    "architecture": {
        "signals": [
            "architecture",
            "system design",
            "design pattern",
            "scale",
            "microservice",
            "monolith",
            "database design",
            "schema design",
        ],
        "agents": ["vega", "nexus", "atlas"],
    },
    "security": {
        "signals": [
            "security",
            "vulnerability",
            "cve",
            "penetration",
            "auth",
            "permission",
            "encryption",
            "xss",
            "sql injection",
            "owasp",
        ],
        "agents": ["kavach", "shadow", "varuna"],
    },
    "data_analysis": {
        "signals": [
            "analyze data",
            "data analysis",
            "query",
            "sql",
            "metrics",
            "dashboard",
            "visualization",
            "chart",
            "statistics",
        ],
        "agents": ["oracle", "nexus", "echo"],
    },
    "content_writing": {
        "signals": [
            "write",
            "draft",
            "blog",
            "documentation",
            "readme",
            "copy",
            "summarize",
            "translate",
            "rephrase",
            "proofread",
        ],
        "agents": ["nova", "surya", "sage"],
    },
    "planning": {
        "signals": [
            "plan",
            "roadmap",
            "strategy",
            "prioritize",
            "todo",
            "milestone",
            "timeline",
            "project plan",
            "sprint",
        ],
        "agents": ["vega", "oracle", "helix"],
    },
    "devops": {
        "signals": [
            "deploy",
            "ci/cd",
            "docker",
            "kubernetes",
            "pipeline",
            "infrastructure",
            "terraform",
            "monitoring",
            "uptime",
        ],
        "agents": ["atlas", "iris", "titan"],
    },
    "emotional_support": {
        "signals": [
            "feeling",
            "stressed",
            "anxious",
            "overwhelmed",
            "frustrated",
            "burned out",
            "motivation",
            "stuck",
            "help me feel",
        ],
        "agents": ["lumina", "phoenix", "sanghacore"],
    },
    "explanation": {
        "signals": [
            "explain",
            "how does",
            "what is",
            "why does",
            "understand",
            "teach me",
            "clarify",
            "break down",
            "eli5",
        ],
        "agents": ["surya", "sage", "gemini"],
    },
    "workflow_automation": {
        "signals": [
            "automate",
            "workflow",
            "spiral",
            "trigger",
            "webhook",
            "schedule",
            "integration",
            "connect",
            "zapier",
        ],
        "agents": ["arjuna", "iris", "helix"],
    },
    "ethics_governance": {
        "signals": [
            "ethics",
            "moral",
            "fairness",
            "bias",
            "responsible",
            "governance",
            "compliance",
            "policy",
            "regulation",
        ],
        "agents": ["kael", "varuna", "sage"],
    },
    "creative": {
        "signals": [
            "brainstorm",
            "idea",
            "creative",
            "innovate",
            "imagine",
            "what if",
            "concept",
            "design thinking",
            "prototype",
        ],
        "agents": ["nova", "agni", "gemini"],
    },
}


def classify_intent(message: str) -> list[tuple[str, float]]:
    """Classify a message into intent categories with confidence scores.

    Returns a sorted list of (category, score) tuples, highest first.
    Uses phrase-level matching (not just single keywords) for better precision.
    """
    message_lower = message.lower()
    scores: dict[str, float] = {}

    for category, info in INTENT_CATEGORIES.items():
        score = 0.0
        for signal in info["signals"]:
            if signal in message_lower:
                # Longer signals are more precise, weight them higher
                weight = 1.0 + (len(signal.split()) - 1) * 0.5
                score += weight
        if score > 0:
            scores[category] = score

    # Normalize to 0-1 range
    if scores:
        max_score = max(scores.values())
        if max_score > 0:
            scores = {k: round(v / max_score, 3) for k, v in scores.items()}

    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_scores


async def _get_reputation_scores(user_id: str) -> dict[str, float]:
    """Fetch agent reputation scores for the user. Returns agent_id → satisfaction (0-1)."""
    try:
        from apps.backend.services.agent_performance_service import get_agent_performance_service

        service = get_agent_performance_service()
        summary = await service.get_all_agents_summary(user_id)
        scores = {}
        for agent in summary:
            agent_id = agent.get("agent_id", "")
            satisfaction = agent.get("satisfaction_rate", 0)
            if agent_id and satisfaction > 0:
                scores[agent_id] = satisfaction / 100.0  # Convert percentage to 0-1
        return scores
    except Exception as e:
        logger.debug("Could not fetch reputation scores: %s", e)
        return {}


async def smart_select_agent(
    message: str,
    page: str,
    user_id: str = "anonymous",
    page_agent_map: dict[str, str] | None = None,
    keyword_scores: dict[str, float] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Select the best agent for a message using multi-signal scoring.

    Returns (agent_id, metadata) where metadata includes:
    - intent: top classified intent category
    - confidence: selection confidence (0-1)
    - method: "intent", "keyword", or "page_default"
    - candidates: top 3 agent candidates with scores

    Falls back: intent classification → keyword scoring → page default.
    """
    metadata: dict[str, Any] = {"method": "page_default", "intent": None, "confidence": 0.0}

    # Default from page
    default_map = page_agent_map or {}
    page_agent = default_map.get(page, "helix")

    # 1. Intent classification
    intents = classify_intent(message)
    top_intent = intents[0] if intents else None

    # 2. Get reputation scores (non-blocking, best-effort)
    reputation = {}
    if user_id != "anonymous":
        reputation = await _get_reputation_scores(user_id)

    # 3. Build candidate scores from intent
    candidate_scores: dict[str, float] = {}

    if top_intent and top_intent[1] >= 0.5:
        category_name = top_intent[0]
        agents = INTENT_CATEGORIES[category_name]["agents"]
        for rank, agent_id in enumerate(agents):
            # Higher rank = higher base score
            base = 3.0 - rank * 0.8
            candidate_scores[agent_id] = candidate_scores.get(agent_id, 0) + base

        metadata["intent"] = category_name
        metadata["method"] = "intent"
        metadata["confidence"] = top_intent[1]

    # 4. Mix in keyword scores (if provided)
    if keyword_scores:
        for agent_id, score in keyword_scores.items():
            candidate_scores[agent_id] = candidate_scores.get(agent_id, 0) + score * 0.5

    # 5. Apply reputation boost (up to +1.0 for perfect satisfaction)
    for agent_id, rep in reputation.items():
        if agent_id in candidate_scores:
            candidate_scores[agent_id] += rep * 1.0

    # 6. Boost page-context agent
    if page_agent in candidate_scores:
        candidate_scores[page_agent] += 0.3

    if candidate_scores:
        # Sort and pick best
        sorted_candidates = sorted(candidate_scores.items(), key=lambda x: x[1], reverse=True)
        metadata["candidates"] = [{"agent": a, "score": round(s, 2)} for a, s in sorted_candidates[:3]]
        best_agent = sorted_candidates[0][0]

        if not metadata.get("intent"):
            metadata["method"] = "keyword" if keyword_scores else "page_default"

        return best_agent, metadata

    # Fallback
    metadata["candidates"] = [{"agent": page_agent, "score": 0}]
    return page_agent, metadata

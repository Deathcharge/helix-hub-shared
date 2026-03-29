"""
Agent Delegation Tools
======================
Implements CrewAI-inspired inter-agent delegation for Helix's 24-agent system.

Two tools:
  - delegate_work: Hand off a full task to another agent, get their response.
  - ask_agent: Ask another agent a quick question without full task handoff.

These are registered as normal tools in the ToolRegistry. When an agent with
delegation enabled is running in the agentic loop, these tools let it
autonomously consult or delegate to other Helix agents by role matching.

The delegation happens via a fresh LLM call with the target agent's personality
injected as the system prompt — so the target agent "thinks" with its own
expertise, style, and constraints.

Usage flow:
  1. During agentic loop, LLM decides it needs another agent's expertise
  2. LLM calls `delegate_work(agent="kavach", task="Review this for security...")``
  3. Handler resolves "kavach" to Kavach's personality profile
  4. Makes an LLM call with Kavach's system prompt + the task
  5. Returns Kavach's response as the tool result
  6. Original agent incorporates the response in its next turn
"""

import logging
import time
from typing import Any

from apps.backend.agent_capabilities.tool_framework import (
    ParameterType,
    Tool,
    ToolParameter,
    ToolResult,
)

logger = logging.getLogger(__name__)

# Maximum tokens for delegation sub-calls (keep cheap)
DELEGATION_MAX_TOKENS = 1024
ASK_MAX_TOKENS = 512
DELEGATION_TIMEOUT_SECONDS = 45


def _get_agent_personalities() -> dict[str, dict]:
    """Import and return AGENT_PERSONALITIES from copilot."""
    try:
        from apps.backend.routes.copilot import AGENT_PERSONALITIES

        return AGENT_PERSONALITIES
    except ImportError:
        logger.warning("Could not import AGENT_PERSONALITIES from copilot")
        return {}


def _resolve_agent(agent_ref: str) -> tuple[str | None, dict | None]:
    """
    Resolve an agent reference to its personality profile.

    Accepts:
      - Exact agent ID: "kavach", "lumina"
      - Role keyword: "security", "empathy", "creative"

    Returns (agent_id, personality_dict) or (None, None) if not found.
    """
    personalities = _get_agent_personalities()
    if not personalities:
        return None, None

    # Lowercase for matching
    ref_lower = agent_ref.strip().lower()

    # 1. Exact match by agent ID
    if ref_lower in personalities:
        return ref_lower, personalities[ref_lower]

    # 2. Match by agent name (case-insensitive)
    for agent_id, profile in personalities.items():
        if profile.get("name", "").lower() == ref_lower:
            return agent_id, profile

    # 3. Keyword matching against role + expertise
    # Maps common keywords to agent IDs for natural language routing
    KEYWORD_MAP = {
        # Security
        "security": "kavach",
        "safety": "kavach",
        "risk": "kavach",
        "protection": "kavach",
        "threat": "kavach",
        "vulnerability": "kavach",
        # Ethics
        "ethics": "kael",
        "ethical": "kael",
        "moral": "kael",
        "justice": "kael",
        # Empathy / emotional
        "empathy": "lumina",
        "emotion": "lumina",
        "emotional": "lumina",
        "support": "lumina",
        "healing": "lumina",
        "comfort": "lumina",
        # Strategy / planning
        "strategy": "vega",
        "strategic": "vega",
        "planning": "vega",
        "guidance": "vega",
        "navigation": "vega",
        # Creative
        "creative": "nova",
        "creativity": "nova",
        "content": "nova",
        "writing": "nova",
        "brainstorm": "nova",
        "design": "nova",
        # Code / computation
        "computation": "titan",
        "processing": "titan",
        "compute": "titan",
        "heavy": "titan",
        "scale": "titan",
        "batch": "titan",
        # Infrastructure
        "infrastructure": "atlas",
        "deploy": "atlas",
        "devops": "atlas",
        "monitoring": "atlas",
        "incident": "atlas",
        # Data / integration
        "data": "nexus",
        "schema": "nexus",
        "knowledge graph": "nexus",
        "integration": "iris",
        "api": "iris",
        "external": "iris",
        # UX
        "ux": "aria",
        "user experience": "aria",
        "accessibility": "aria",
        "journey": "aria",
        "personalization": "aria",
        # Community
        "community": "sanghacore",
        "collaboration": "sanghacore",
        "harmony": "sanghacore",
        "conflict": "sanghacore",
        # Analysis / pattern
        "pattern": "echo",
        "recognition": "echo",
        "resonance": "echo",
        # Prediction
        "prediction": "oracle",
        "forecast": "oracle",
        "foresight": "oracle",
        "trend": "oracle",
        "probability": "oracle",
        # Recovery
        "recovery": "phoenix",
        "renewal": "phoenix",
        "resilience": "phoenix",
        # Archive / memory
        "archive": "shadow",
        "memory": "shadow",
        "history": "shadow",
        "telemetry": "shadow",
        # Wisdom / synthesis
        "wisdom": "sage",
        "synthesis": "sage",
        "philosophy": "sage",
        # Coordination
        "coordinate": "helix",
        "orchestrate": "helix",
        "orchestration": "helix",
        # Meta
        "meta": "aether",
        "observe": "aether",
        "awareness": "aether",
        # Alliance / diplomacy
        "alliance": "mitra",
        "diplomacy": "mitra",
        "trust": "mitra",
        # Transformation
        "transform": "agni",
        "catalyst": "agni",
        "change": "agni",
        # Explorer
        "explore": "gemini",
        "multimodal": "gemini",
        "discovery": "gemini",
        # Truth / governance
        "truth": "varuna",
        "governance": "varuna",
        "integrity": "varuna",
        # Clarity
        "clarity": "surya",
        "insight": "surya",
        "illumination": "surya",
        # General coordinator
        "coordinator": "arjuna",
        "executor": "arjuna",
        "operations": "arjuna",
    }

    # Check direct keyword match
    if ref_lower in KEYWORD_MAP:
        target_id = KEYWORD_MAP[ref_lower]
        if target_id in personalities:
            return target_id, personalities[target_id]

    # Search for keyword in multi-word ref
    for keyword, target_id in KEYWORD_MAP.items():
        if keyword in ref_lower and target_id in personalities:
            return target_id, personalities[target_id]

    # 4. Fuzzy match against role and expertise fields
    best_match = None
    best_score = 0
    for agent_id, profile in personalities.items():
        role_text = (profile.get("role", "") + " " + profile.get("expertise", "")).lower()
        # Count matching words
        ref_words = ref_lower.split()
        score = sum(1 for w in ref_words if w in role_text)
        if score > best_score:
            best_score = score
            best_match = (agent_id, profile)

    if best_match and best_score > 0:
        return best_match

    return None, None


def _build_agent_system_prompt(profile: dict, delegation_context: str = "") -> str:
    """Build a system prompt from an agent's personality profile."""
    name = profile.get("name", "Agent")
    role = profile.get("role", "AI Assistant")
    style = profile.get("style", "")
    expertise = profile.get("expertise", "")
    tone = profile.get("tone", "")

    prompt = (
        f"You are {name}, a specialized Helix AI agent.\n"
        f"Role: {role}\n"
        f"Style: {style}\n"
        f"Expertise: {expertise}\n"
        f"Tone: {tone}\n\n"
        "You have been consulted by another agent in the Helix collective. "
        "Respond with your unique expertise and perspective. Be focused and concise."
    )
    if delegation_context:
        prompt += f"\n\nContext from the delegating agent:\n{delegation_context}"
    return prompt


def _list_available_agents() -> str:
    """Return a formatted list of available agents for the LLM."""
    personalities = _get_agent_personalities()
    if not personalities:
        return "No agents available."

    lines = []
    for agent_id, profile in personalities.items():
        name = profile.get("name", agent_id)
        role = profile.get("role", "")
        emoji = profile.get("emoji", "")
        lines.append(f"  - {emoji} {name} ({agent_id}): {role}")
    return "\n".join(lines)


async def _delegate_work_handler(params: dict[str, Any], context: dict | None = None) -> ToolResult:
    """
    Execute a full task delegation to another agent.

    The target agent receives the task with its own personality/expertise
    and produces a complete response.
    """
    agent_ref = params.get("agent", "").strip()
    task = params.get("task", "").strip()
    delegation_context = params.get("context", "").strip()

    if not agent_ref:
        return ToolResult(
            success=False,
            output=None,
            error="'agent' parameter is required. Specify an agent name (e.g., 'kavach') or role keyword (e.g., 'security').",
        )
    if not task:
        return ToolResult(
            success=False,
            output=None,
            error="'task' parameter is required. Describe what you need the other agent to do.",
        )

    agent_id, profile = _resolve_agent(agent_ref)
    if not profile:
        available = _list_available_agents()
        return ToolResult(
            success=False,
            output=None,
            error=f"Could not resolve agent '{agent_ref}'. Available agents:\n{available}",
        )

    # Prevent self-delegation if we know the calling agent
    calling_agent = (context or {}).get("calling_agent_id", "")
    if calling_agent and calling_agent == agent_id:
        return ToolResult(
            success=False,
            output=None,
            error=f"Cannot delegate to yourself ({agent_id}). Choose a different agent.",
        )

    try:
        from apps.backend.services.unified_llm import UnifiedLLMService

        llm = UnifiedLLMService.get_instance()
        system_prompt = _build_agent_system_prompt(profile, delegation_context)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]

        start = time.monotonic()
        resp = await llm.chat_with_metadata(
            messages=messages,
            max_tokens=DELEGATION_MAX_TOKENS,
            temperature=0.7,
        )
        duration_ms = (time.monotonic() - start) * 1000

        if resp.error:
            return ToolResult(
                success=False,
                output=None,
                error=f"Delegation to {profile['name']} failed: {resp.error}",
                execution_time_ms=duration_ms,
            )

        agent_name = profile.get("name", agent_id)
        agent_emoji = profile.get("emoji", "")

        response_text = f"{agent_emoji} **{agent_name}** (delegated response):\n\n{resp.content}"

        logger.info(
            "Delegation: %s → %s completed in %.0fms (%d tokens)",
            calling_agent or "unknown",
            agent_id,
            duration_ms,
            (resp.usage or {}).get("total_tokens", 0),
        )

        return ToolResult(
            success=True,
            output=response_text,
            execution_time_ms=duration_ms,
            metadata={
                "delegate_agent": agent_id,
                "delegate_name": agent_name,
                "calling_agent": calling_agent,
                "tokens": resp.usage or {},
            },
        )

    except Exception as e:
        logger.warning("Delegation to '%s' failed: %s", agent_ref, e)
        return ToolResult(
            success=False,
            output=None,
            error=f"Delegation failed: {e}",
        )


async def _ask_agent_handler(params: dict[str, Any], context: dict | None = None) -> ToolResult:
    """
    Ask another agent a quick question. Lighter than full delegation —
    expects a short, focused answer.
    """
    agent_ref = params.get("agent", "").strip()
    question = params.get("question", "").strip()

    if not agent_ref:
        return ToolResult(
            success=False,
            output=None,
            error="'agent' parameter is required. Specify an agent name (e.g., 'oracle') or role keyword (e.g., 'prediction').",
        )
    if not question:
        return ToolResult(
            success=False,
            output=None,
            error="'question' parameter is required. Ask your question.",
        )

    agent_id, profile = _resolve_agent(agent_ref)
    if not profile:
        available = _list_available_agents()
        return ToolResult(
            success=False,
            output=None,
            error=f"Could not resolve agent '{agent_ref}'. Available agents:\n{available}",
        )

    calling_agent = (context or {}).get("calling_agent_id", "")
    if calling_agent and calling_agent == agent_id:
        return ToolResult(
            success=False,
            output=None,
            error=f"Cannot ask yourself ({agent_id}). Choose a different agent.",
        )

    try:
        from apps.backend.services.unified_llm import UnifiedLLMService

        llm = UnifiedLLMService.get_instance()

        system_prompt = (
            _build_agent_system_prompt(profile) + "\n\nAnother agent is asking you a quick question. "
            "Give a focused, concise answer (2-4 sentences). "
            "Do not ask follow-up questions — just answer directly."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ]

        start = time.monotonic()
        resp = await llm.chat_with_metadata(
            messages=messages,
            max_tokens=ASK_MAX_TOKENS,
            temperature=0.5,
        )
        duration_ms = (time.monotonic() - start) * 1000

        if resp.error:
            return ToolResult(
                success=False,
                output=None,
                error=f"Ask {profile['name']} failed: {resp.error}",
                execution_time_ms=duration_ms,
            )

        agent_name = profile.get("name", agent_id)
        agent_emoji = profile.get("emoji", "")

        response_text = f"{agent_emoji} **{agent_name}**: {resp.content}"

        logger.info(
            "Ask: %s → %s completed in %.0fms",
            calling_agent or "unknown",
            agent_id,
            duration_ms,
        )

        return ToolResult(
            success=True,
            output=response_text,
            execution_time_ms=duration_ms,
            metadata={
                "delegate_agent": agent_id,
                "delegate_name": agent_name,
                "calling_agent": calling_agent,
                "tokens": resp.usage or {},
            },
        )

    except Exception as e:
        logger.warning("Ask agent '%s' failed: %s", agent_ref, e)
        return ToolResult(
            success=False,
            output=None,
            error=f"Ask agent failed: {e}",
        )


# ============================================================================
# Tool definitions
# ============================================================================

DELEGATE_WORK_TOOL = Tool(
    name="delegate_work",
    description=(
        "Delegate a task to another Helix agent with specialized expertise. "
        "Use when you need a different agent's perspective or domain knowledge. "
        "The target agent will process the full task and return their response. "
        "Examples: delegate security review to Kavach, creative writing to Nova, "
        "data analysis to Nexus, ethical review to Kael."
    ),
    parameters=[
        ToolParameter(
            name="agent",
            type=ParameterType.STRING,
            description=(
                "Target agent name or role keyword. "
                "Examples: 'kavach' (security), 'nova' (creative), 'oracle' (prediction), "
                "'lumina' (empathy), 'titan' (computation), 'iris' (API/integration)."
            ),
            required=True,
        ),
        ToolParameter(
            name="task",
            type=ParameterType.STRING,
            description="The full task description for the target agent to complete.",
            required=True,
        ),
        ToolParameter(
            name="context",
            type=ParameterType.STRING,
            description="Optional context from your current work that the target agent should know.",
            required=False,
            default="",
        ),
    ],
    handler=_delegate_work_handler,
    category="delegation",
    tags=["delegation", "multi-agent", "collaboration"],
    timeout_seconds=DELEGATION_TIMEOUT_SECONDS,
)

ASK_AGENT_TOOL = Tool(
    name="ask_agent",
    description=(
        "Ask another Helix agent a quick question. Lighter than full delegation — "
        "gets a focused 2-4 sentence answer. Use when you need a quick opinion, "
        "fact check, or domain-specific insight without a full task handoff. "
        "Examples: ask Kavach if an approach is secure, ask Oracle for a prediction, "
        "ask Kael about ethical implications."
    ),
    parameters=[
        ToolParameter(
            name="agent",
            type=ParameterType.STRING,
            description=(
                "Target agent name or role keyword. "
                "Examples: 'kavach' (security), 'oracle' (prediction), 'kael' (ethics), "
                "'sage' (wisdom), 'echo' (patterns)."
            ),
            required=True,
        ),
        ToolParameter(
            name="question",
            type=ParameterType.STRING,
            description="The question to ask the target agent. Be specific.",
            required=True,
        ),
    ],
    handler=_ask_agent_handler,
    category="delegation",
    tags=["delegation", "multi-agent", "question"],
    timeout_seconds=DELEGATION_TIMEOUT_SECONDS,
)


# ============================================================================
# Registration helpers
# ============================================================================

# Agents that should get delegation tools auto-injected.
# All coordination + integration layer agents get delegation by default.
# Operational agents that coordinate (helix, arjuna) also get it.
DELEGATION_ENABLED_AGENTS = {
    # Coordination layer — these benefit from consulting other agents
    "kael",
    "lumina",
    "vega",
    "aether",
    # Operational coordinators
    "helix",
    "arjuna",
    "gemini",
    # Integration layer — these bridge between systems/agents
    "sanghacore",
    "echo",
    "oracle",
    "sage",
    "mitra",
    # Extended — agents that benefit from cross-consultation
    "iris",
    "nexus",
    "surya",
    "varuna",
}


def agent_has_delegation(agent_id: str) -> bool:
    """Check if an agent should have delegation tools."""
    return agent_id.lower().strip() in DELEGATION_ENABLED_AGENTS


def get_delegation_tool_names() -> list[str]:
    """Return the names of the delegation tools."""
    return [DELEGATE_WORK_TOOL.name, ASK_AGENT_TOOL.name]


def register_delegation_tools(registry) -> int:
    """
    Register delegation tools in the ToolRegistry.

    Returns number of tools registered.
    """
    count = 0
    for tool in (DELEGATE_WORK_TOOL, ASK_AGENT_TOOL):
        try:
            registry.register(tool)
            count += 1
        except Exception as e:
            logger.warning("Failed to register delegation tool '%s': %s", tool.name, e)
    if count:
        logger.info("Registered %d delegation tools", count)
    return count

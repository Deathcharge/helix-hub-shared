"""
Agent Memory Tools
==================
Provides memory-related tools that agents can call during the agentic loop
to explicitly remember facts, recall stored memories, and update core memory.

Three tools:
  - remember_fact: Store a fact about the user for future conversations.
  - recall_memories: Search for relevant facts about the user.
  - update_core_memory: Directly update the agent's core (pinned) memory.

These are registered as normal tools in the ToolRegistry. When an agent is
running in the agentic loop, these tools let it explicitly manage its own
memory across conversations.

Usage flow:
  1. During agentic loop, LLM decides it should remember something
  2. LLM calls `remember_fact(subject="User", predicate="prefers", object="dark mode")`
  3. Handler stores the fact in the knowledge graph + promotes to core memory
  4. Future conversations automatically include this fact in context

Copyright (c) 2025 Andrew John Ward. All Rights Reserved.
"""

import logging
from typing import Any

from apps.backend.agent_capabilities.tool_framework import (
    ParameterType,
    Tool,
    ToolParameter,
    ToolResult,
)

logger = logging.getLogger(__name__)

MEMORY_TOOL_TIMEOUT_SECONDS = 15


# ============================================================================
# Tool handlers
# ============================================================================


async def _remember_fact_handler(params: dict[str, Any], context: dict | None = None) -> ToolResult:
    """Store a fact about the user for future conversations."""
    subject = params.get("subject", "").strip()
    predicate = params.get("predicate", "").strip()
    obj = params.get("object", "").strip()

    if not all([subject, predicate, obj]):
        return ToolResult(
            success=False,
            output=None,
            error="All three parameters are required: subject, predicate, object.",
        )

    # Extract user_id and agent_id from execution context
    user_id = (context or {}).get("user_id", "")
    agent_id = (context or {}).get("agent_id", "")

    if not user_id:
        return ToolResult(
            success=False,
            output=None,
            error="Cannot store memory without a user context.",
        )

    try:
        from apps.backend.services.knowledge_extraction import get_knowledge_service

        ks = get_knowledge_service()
        facts = [
            {
                "subject": subject,
                "predicate": predicate,
                "object": obj,
                "confidence": 0.9,
            }
        ]
        stored = await ks.store_facts(user_id, agent_id, facts)
        promoted = await ks.promote_to_core_memory(user_id, agent_id, facts)

        return ToolResult(
            success=True,
            output={
                "stored": stored,
                "promoted_to_core": promoted,
                "message": f"Remembered: {subject} {predicate} {obj}",
            },
            metadata={"user_id": user_id, "agent_id": agent_id},
        )

    except Exception as e:
        logger.warning("remember_fact tool failed: %s", e)
        return ToolResult(
            success=False,
            output=None,
            error=f"Failed to store fact: {e}",
        )


async def _recall_memories_handler(params: dict[str, Any], context: dict | None = None) -> ToolResult:
    """Search for relevant facts about the user."""
    query = params.get("query", "").strip()

    if not query:
        return ToolResult(
            success=False,
            output=None,
            error="'query' parameter is required. Describe what you want to recall.",
        )

    user_id = (context or {}).get("user_id", "")
    if not user_id:
        return ToolResult(
            success=False,
            output=None,
            error="Cannot search memories without a user context.",
        )

    try:
        from apps.backend.services.knowledge_extraction import get_knowledge_service

        ks = get_knowledge_service()
        facts = await ks.search_facts(user_id, query, limit=5)

        # Format facts for the LLM
        formatted = []
        for f in facts:
            formatted.append(
                {
                    "subject": f.get("subject", ""),
                    "predicate": f.get("predicate", ""),
                    "object": f.get("object", ""),
                    "confidence": f.get("confidence", 0),
                }
            )

        return ToolResult(
            success=True,
            output={"facts": formatted, "count": len(formatted)},
            metadata={"user_id": user_id, "query": query},
        )

    except Exception as e:
        logger.warning("recall_memories tool failed: %s", e)
        return ToolResult(
            success=False,
            output=None,
            error=f"Failed to search memories: {e}",
        )


async def _update_core_memory_handler(params: dict[str, Any], context: dict | None = None) -> ToolResult:
    """Update the agent's core memory with an important persistent fact."""
    key = params.get("key", "").strip()
    value = params.get("value", "").strip()

    if not key or not value:
        return ToolResult(
            success=False,
            output=None,
            error="Both 'key' and 'value' parameters are required.",
        )

    user_id = (context or {}).get("user_id", "")
    agent_id = (context or {}).get("agent_id", "")

    if not user_id:
        return ToolResult(
            success=False,
            output=None,
            error="Cannot update core memory without a user context.",
        )

    try:
        from apps.backend.integrations.agent_memory_service import (
            get_three_tier_manager,
        )

        mem_key = f"{user_id}:{agent_id}" if agent_id else f"{user_id}:helix"
        mgr = get_three_tier_manager(mem_key)
        success = await mgr.update_core(key, value)

        if success:
            return ToolResult(
                success=True,
                output={
                    "success": True,
                    "key": key,
                    "message": f"Core memory updated: {key}",
                },
                metadata={"user_id": user_id, "agent_id": agent_id},
            )
        else:
            return ToolResult(
                success=True,
                output={
                    "success": False,
                    "key": key,
                    "message": "Core memory is full (2KB limit). Consider removing old entries first.",
                },
            )

    except Exception as e:
        logger.warning("update_core_memory tool failed: %s", e)
        return ToolResult(
            success=False,
            output=None,
            error=f"Failed to update core memory: {e}",
        )


# ============================================================================
# Tool definitions
# ============================================================================

REMEMBER_FACT_TOOL = Tool(
    name="remember_fact",
    description=(
        "Store a fact about the user for future conversations. Use this when "
        "the user shares important personal information, preferences, project "
        "details, or decisions that should be remembered across sessions. "
        "Facts are stored as (subject, predicate, object) triples. "
        "Examples: ('User', 'prefers', 'dark mode'), "
        "('User project', 'uses', 'React with TypeScript'), "
        "('User', 'works at', 'Acme Corp')."
    ),
    parameters=[
        ToolParameter(
            name="subject",
            type=ParameterType.STRING,
            description="The subject of the fact (e.g., 'User', 'User project', 'User preference').",
            required=True,
        ),
        ToolParameter(
            name="predicate",
            type=ParameterType.STRING,
            description="The relationship or action (e.g., 'prefers', 'works at', 'uses', 'is located in').",
            required=True,
        ),
        ToolParameter(
            name="object",
            type=ParameterType.STRING,
            description="The object or value of the fact (e.g., 'dark mode', 'React with TypeScript').",
            required=True,
        ),
    ],
    handler=_remember_fact_handler,
    category="memory",
    tags=["memory", "knowledge", "persistence"],
    timeout_seconds=MEMORY_TOOL_TIMEOUT_SECONDS,
)

RECALL_MEMORIES_TOOL = Tool(
    name="recall_memories",
    description=(
        "Search for relevant facts and memories about the user. Use this when "
        "you need to recall something the user has previously shared — their "
        "preferences, project details, past decisions, or personal information. "
        "Provide a natural language query describing what you want to recall."
    ),
    parameters=[
        ToolParameter(
            name="query",
            type=ParameterType.STRING,
            description="Natural language search query (e.g., 'user preferences', 'project tech stack', 'where does user work').",
            required=True,
        ),
    ],
    handler=_recall_memories_handler,
    category="memory",
    tags=["memory", "knowledge", "search", "recall"],
    timeout_seconds=MEMORY_TOOL_TIMEOUT_SECONDS,
)

UPDATE_CORE_MEMORY_TOOL = Tool(
    name="update_core_memory",
    description=(
        "Directly update the agent's core (pinned) memory with an important "
        "persistent fact. Core memory is injected into every future conversation, "
        "so use this sparingly for truly important information. "
        "Core memory has a 2KB limit — keep values concise. "
        "Use a descriptive key like 'user_name', 'user_timezone', 'project_language'."
    ),
    parameters=[
        ToolParameter(
            name="key",
            type=ParameterType.STRING,
            description="A descriptive key for the memory entry (e.g., 'user_name', 'project_stack', 'user_timezone').",
            required=True,
        ),
        ToolParameter(
            name="value",
            type=ParameterType.STRING,
            description="The value to store. Keep concise — core memory has a 2KB total limit.",
            required=True,
        ),
    ],
    handler=_update_core_memory_handler,
    category="memory",
    tags=["memory", "core", "pinned", "persistent"],
    timeout_seconds=MEMORY_TOOL_TIMEOUT_SECONDS,
)


# ============================================================================
# Registration
# ============================================================================

MEMORY_TOOLS = [REMEMBER_FACT_TOOL, RECALL_MEMORIES_TOOL, UPDATE_CORE_MEMORY_TOOL]


def get_memory_tool_names() -> list[str]:
    """Return the names of the memory tools."""
    return [t.name for t in MEMORY_TOOLS]


def register_memory_tools(registry) -> int:
    """
    Register memory tools in the ToolRegistry.

    Returns number of tools registered.
    """
    count = 0
    for tool in MEMORY_TOOLS:
        try:
            registry.register(tool)
            count += 1
        except Exception as e:
            logger.warning("Failed to register memory tool '%s': %s", tool.name, e)
    if count:
        logger.info("Registered %d memory tools", count)
    return count

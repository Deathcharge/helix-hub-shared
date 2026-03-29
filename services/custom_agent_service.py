"""
Custom Agent Service
====================

CRUD operations for user-created custom agents (Enhanced Agent Builder).
Persists to PostgreSQL via the async Database abstraction (asyncpg pool).

Tier enforcement is handled at the route layer, not here.
"""

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


async def _get_db():
    """Import and return the async Database class."""
    try:
        from apps.backend.core.unified_auth import Database
    except ImportError:
        from apps.backend.saas_auth import Database

    return Database


def _get_tool_registry():
    """Import and return the global ToolRegistry."""
    from apps.backend.agent_capabilities.tool_framework import get_tool_registry

    return get_tool_registry()


def _row_to_dict(row) -> dict[str, Any]:
    """Convert an asyncpg Record to a JSON-serializable dict."""
    d = dict(row)
    # Serialize datetime fields to ISO strings
    for key in ("created_at", "updated_at"):
        if key in d and d[key] is not None:
            d[key] = d[key].isoformat()
    # Parse JSON string fields back to Python objects if needed
    for key in ("personality", "tools", "ucf_metrics", "critical_rules", "success_metrics", "deliverables"):
        if key in d and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError) as e:
                logger.debug("Failed to parse JSON field '%s' in custom agent: %s", key, e)
    return d


class CustomAgentService:
    """CRUD operations for custom agents. Persists to PostgreSQL."""

    async def create_agent(self, user_id: str, data: dict) -> dict:
        """
        Create a new custom agent.

        Validates tool names against the ToolRegistry before persisting.
        Returns the created agent as a dict.
        """
        try:
            Database = await _get_db()

            agent_id = str(uuid.uuid4())
            now = datetime.now(UTC)

            # Validate tools if provided
            tool_names = data.get("tools", [])
            if tool_names:
                valid_tools, invalid_tools = await self.validate_tools(tool_names)
                if invalid_tools:
                    logger.warning(
                        "Custom agent creation included invalid tools: %s",
                        invalid_tools,
                    )
                # Only persist valid tools
                tool_names = valid_tools

            personality = data.get("personality", {})
            ucf_metrics = data.get("ucf_metrics")

            await Database.execute(
                """
                INSERT INTO custom_agents
                    (id, user_id, name, description, template_id, icon, color,
                     personality, system_prompt, tools, max_tool_rounds,
                     ucf_metrics, vibe, critical_rules, success_metrics,
                     deliverables, communication_style,
                     is_active, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                        $13, $14, $15, $16, $17, $18, $19, $20)
                """,
                agent_id,
                user_id,
                data.get("name", "Unnamed Agent"),
                data.get("description"),
                data.get("template_id"),
                data.get("icon", "\U0001f916"),  # 🤖
                data.get("color"),
                json.dumps(personality),
                data.get("system_prompt"),
                json.dumps(tool_names),
                data.get("max_tool_rounds", 5),
                json.dumps(ucf_metrics) if ucf_metrics else None,
                data.get("vibe"),
                json.dumps(data["critical_rules"]) if data.get("critical_rules") else None,
                json.dumps(data["success_metrics"]) if data.get("success_metrics") else None,
                json.dumps(data["deliverables"]) if data.get("deliverables") else None,
                data.get("communication_style"),
                True,
                now,
                now,
            )

            # Fetch the created row to return
            row = await Database.fetchrow(
                "SELECT * FROM custom_agents WHERE id = $1",
                agent_id,
            )
            return _row_to_dict(row)

        except Exception as e:
            logger.warning("Failed to create custom agent: %s", e)
            raise

    async def get_agent(self, agent_id: str, user_id: str) -> dict | None:
        """
        Get a single custom agent by ID, scoped to the owning user.

        Returns None if not found or not owned by user.
        """
        try:
            Database = await _get_db()
            row = await Database.fetchrow(
                """
                SELECT * FROM custom_agents
                WHERE id = $1 AND user_id = $2 AND is_active = true
                """,
                agent_id,
                user_id,
            )
            if row is None:
                return None
            return _row_to_dict(row)
        except Exception as e:
            logger.warning("Failed to get custom agent %s: %s", agent_id, e)
            return None

    async def list_agents(self, user_id: str) -> list[dict]:
        """
        List all active custom agents for a user, ordered by creation date.
        """
        try:
            Database = await _get_db()
            rows = await Database.fetch(
                """
                SELECT * FROM custom_agents
                WHERE user_id = $1 AND is_active = true
                ORDER BY created_at DESC
                """,
                user_id,
            )
            return [_row_to_dict(r) for r in rows]
        except Exception as e:
            logger.warning("Failed to list custom agents for user %s: %s", user_id, e)
            return []

    async def update_agent(self, agent_id: str, user_id: str, data: dict) -> dict | None:
        """
        Update a custom agent. Only updates fields present in ``data``.

        Returns the updated agent dict, or None if not found/not owned.
        """
        try:
            Database = await _get_db()

            # Verify ownership first
            existing = await Database.fetchrow(
                """
                SELECT id FROM custom_agents
                WHERE id = $1 AND user_id = $2 AND is_active = true
                """,
                agent_id,
                user_id,
            )
            if existing is None:
                return None

            # Validate tools if being updated
            if data.get("tools"):
                valid_tools, invalid_tools = await self.validate_tools(data["tools"])
                if invalid_tools:
                    logger.warning(
                        "Custom agent update included invalid tools: %s",
                        invalid_tools,
                    )
                data["tools"] = valid_tools

            # Build SET clause dynamically from provided fields
            allowed_fields = {
                "name",
                "description",
                "template_id",
                "icon",
                "color",
                "personality",
                "system_prompt",
                "tools",
                "max_tool_rounds",
                "ucf_metrics",
                "vibe",
                "critical_rules",
                "success_metrics",
                "deliverables",
                "communication_style",
            }
            set_parts = []
            params = []
            param_idx = 1

            for field in allowed_fields:
                if field not in data:
                    continue
                value = data[field]
                # JSON-encode dict/list fields
                if (
                    field
                    in ("personality", "tools", "ucf_metrics", "critical_rules", "success_metrics", "deliverables")
                    and value is not None
                ):
                    value = json.dumps(value)
                set_parts.append(f"{field} = ${param_idx}")
                params.append(value)
                param_idx += 1

            if not set_parts:
                # Nothing to update — just return the current row
                row = await Database.fetchrow(
                    "SELECT * FROM custom_agents WHERE id = $1",
                    agent_id,
                )
                return _row_to_dict(row) if row else None

            # Always bump updated_at
            set_parts.append(f"updated_at = ${param_idx}")
            params.append(datetime.now(UTC))
            param_idx += 1

            # Add WHERE params
            params.append(agent_id)
            params.append(user_id)

            query = f"""
                UPDATE custom_agents
                SET {', '.join(set_parts)}
                WHERE id = ${param_idx} AND user_id = ${param_idx + 1}
            """

            await Database.execute(query, *params)

            # Return updated row
            row = await Database.fetchrow(
                "SELECT * FROM custom_agents WHERE id = $1",
                agent_id,
            )
            return _row_to_dict(row) if row else None

        except Exception as e:
            logger.warning("Failed to update custom agent %s: %s", agent_id, e)
            return None

    async def delete_agent(self, agent_id: str, user_id: str) -> bool:
        """
        Soft-delete a custom agent (sets is_active=False).

        Returns True if the agent was found and deactivated, False otherwise.
        """
        try:
            Database = await _get_db()
            result = await Database.execute(
                """
                UPDATE custom_agents
                SET is_active = false, updated_at = $1
                WHERE id = $2 AND user_id = $3 AND is_active = true
                """,
                datetime.now(UTC),
                agent_id,
                user_id,
            )
            # asyncpg execute returns a status string like "UPDATE 1"
            if isinstance(result, str):
                return result.endswith("1")
            return bool(result)
        except Exception as e:
            logger.warning("Failed to delete custom agent %s: %s", agent_id, e)
            return False

    async def validate_tools(self, tool_names: list[str]) -> tuple[list[str], list[str]]:
        """
        Validate tool names against the ToolRegistry.

        Returns a tuple of (valid_names, invalid_names).
        """
        valid = []
        invalid = []
        try:
            registry = _get_tool_registry()
            registered_names = set(registry.tools.keys())
            for name in tool_names:
                if name in registered_names:
                    valid.append(name)
                else:
                    invalid.append(name)
        except Exception as e:
            logger.warning("Failed to validate tools against registry: %s", e)
            # If registry is unavailable, accept all tools optimistically
            valid = list(tool_names)
        return valid, invalid


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_service: CustomAgentService | None = None


def get_custom_agent_service() -> CustomAgentService:
    """Get the singleton CustomAgentService instance."""
    global _service
    if _service is None:
        _service = CustomAgentService()
    return _service

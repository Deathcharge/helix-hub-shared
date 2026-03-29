"""
Agent Performance Logging Service
==================================

Records agent interaction metrics (response time, success, tokens used, etc.)
for real performance analytics instead of UCF-derived estimates.

Uses the async Database abstraction (asyncpg pool) for persistence,
matching the pattern used by the copilot route.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


async def _get_db():
    """Import and return the async Database class."""
    from apps.backend.saas_auth import Database

    return Database


class AgentPerformanceService:
    """Service for recording and querying agent interaction performance data."""

    async def log_interaction(
        self,
        agent_id: str,
        coordination_score: float = 0.0,
        response_time_ms: float | None = None,
        success: bool = True,
        interaction_type: str = "chat",
        user_id: str | None = None,
        tokens_used: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """
        Record an agent interaction for performance tracking.

        Returns True if the record was persisted, False otherwise.
        """
        try:
            Database = await _get_db()
            await Database.execute(
                """
                INSERT INTO agent_performance_logs
                    (agent_id, timestamp, coordination_score, response_time_ms,
                     success, interaction_type, user_id, tokens_used, performance_metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                agent_id,
                datetime.now(UTC),
                coordination_score,
                response_time_ms,
                success,
                interaction_type,
                user_id,
                tokens_used,
                json.dumps(metadata) if metadata else None,
            )
            return True
        except Exception as e:
            logger.warning("Failed to log agent performance: %s", e)
            return False

    async def get_agent_performance(
        self,
        agent_id: str | None = None,
        minutes: int = 1440,
        interaction_type: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Query agent performance data."""
        try:
            Database = await _get_db()
            cutoff = datetime.now(UTC) - timedelta(minutes=minutes)

            if agent_id and interaction_type:
                rows = await Database.fetch(
                    """
                    SELECT id, agent_id, timestamp, coordination_score, response_time_ms,
                           success, interaction_type, user_id, tokens_used
                    FROM agent_performance_logs
                    WHERE timestamp >= $1 AND agent_id = $2 AND interaction_type = $3
                    ORDER BY timestamp DESC LIMIT $4
                    """,
                    cutoff,
                    agent_id,
                    interaction_type,
                    limit,
                )
            elif agent_id:
                rows = await Database.fetch(
                    """
                    SELECT id, agent_id, timestamp, coordination_score, response_time_ms,
                           success, interaction_type, user_id, tokens_used
                    FROM agent_performance_logs
                    WHERE timestamp >= $1 AND agent_id = $2
                    ORDER BY timestamp DESC LIMIT $3
                    """,
                    cutoff,
                    agent_id,
                    limit,
                )
            elif interaction_type:
                rows = await Database.fetch(
                    """
                    SELECT id, agent_id, timestamp, coordination_score, response_time_ms,
                           success, interaction_type, user_id, tokens_used
                    FROM agent_performance_logs
                    WHERE timestamp >= $1 AND interaction_type = $2
                    ORDER BY timestamp DESC LIMIT $3
                    """,
                    cutoff,
                    interaction_type,
                    limit,
                )
            else:
                rows = await Database.fetch(
                    """
                    SELECT id, agent_id, timestamp, coordination_score, response_time_ms,
                           success, interaction_type, user_id, tokens_used
                    FROM agent_performance_logs
                    WHERE timestamp >= $1
                    ORDER BY timestamp DESC LIMIT $2
                    """,
                    cutoff,
                    limit,
                )

            return [
                {
                    "id": r["id"],
                    "agent_id": r["agent_id"],
                    "timestamp": r["timestamp"].isoformat() if r["timestamp"] else "",
                    "coordination_score": r["coordination_score"] or 0.0,
                    "response_time_ms": r["response_time_ms"],
                    "success": r["success"],
                    "interaction_type": r["interaction_type"] or "chat",
                    "user_id": r["user_id"],
                    "tokens_used": r["tokens_used"] or 0,
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning("Failed to query agent performance: %s", e)
            return []

    async def get_agent_summary(self, agent_id: str, minutes: int = 1440) -> dict[str, Any]:
        """Get summary statistics for an agent."""
        try:
            Database = await _get_db()
            cutoff = datetime.now(UTC) - timedelta(minutes=minutes)

            row = await Database.fetchrow(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE success = true) AS success_count,
                    AVG(response_time_ms) AS avg_response,
                    SUM(tokens_used) AS total_tokens,
                    AVG(coordination_score) AS avg_coordination
                FROM agent_performance_logs
                WHERE agent_id = $1 AND timestamp >= $2
                """,
                agent_id,
                cutoff,
            )

            total = row["total"] or 0
            success_count = row["success_count"] or 0
            return {
                "agent_id": agent_id,
                "total_interactions": total,
                "success_rate": round((success_count / total * 100), 1) if total > 0 else 0.0,
                "avg_response_time_ms": round(float(row["avg_response"] or 0), 1),
                "total_tokens_used": int(row["total_tokens"] or 0),
                "avg_coordination_score": round(float(row["avg_coordination"] or 0), 3),
                "period_minutes": minutes,
            }
        except Exception as e:
            logger.warning("Failed to get agent summary: %s", e)
            return self._empty_summary(agent_id)

    async def get_all_agents_summary(self, minutes: int = 1440) -> list[dict[str, Any]]:
        """Get summary for all agents that have data in the time window."""
        try:
            Database = await _get_db()
            cutoff = datetime.now(UTC) - timedelta(minutes=minutes)

            rows = await Database.fetch(
                """
                SELECT
                    agent_id,
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE success = true) AS success_count,
                    AVG(response_time_ms) AS avg_response,
                    SUM(tokens_used) AS total_tokens,
                    AVG(coordination_score) AS avg_coordination
                FROM agent_performance_logs
                WHERE timestamp >= $1
                GROUP BY agent_id
                ORDER BY total DESC
                """,
                cutoff,
            )

            return [
                {
                    "agent_id": r["agent_id"],
                    "total_interactions": r["total"] or 0,
                    "success_rate": round((r["success_count"] / r["total"] * 100), 1) if r["total"] else 0.0,
                    "avg_response_time_ms": round(float(r["avg_response"] or 0), 1),
                    "total_tokens_used": int(r["total_tokens"] or 0),
                    "avg_coordination_score": round(float(r["avg_coordination"] or 0), 3),
                    "period_minutes": minutes,
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning("Failed to get all agents summary: %s", e)
            return []

    def _empty_summary(self, agent_id: str) -> dict[str, Any]:
        return {
            "agent_id": agent_id,
            "total_interactions": 0,
            "success_rate": 0.0,
            "avg_response_time_ms": 0.0,
            "total_tokens_used": 0,
            "avg_coordination_score": 0.0,
            "period_minutes": 0,
        }


# Singleton instance
_perf_service: AgentPerformanceService | None = None


def get_performance_service() -> AgentPerformanceService:
    """Get singleton agent performance service"""
    global _perf_service
    if _perf_service is None:
        _perf_service = AgentPerformanceService()
    return _perf_service

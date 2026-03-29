"""
Agent Communication Logger
===========================

Tracks inter-agent communication within the Helix Collective, providing
visibility into how agents collaborate, delegate, and resolve tasks.

Features:
- Session-based communication tracking
- Message flow graph construction
- Communication statistics and analytics
- Agent collaboration pattern detection

Used by:
- /api/agents/communications routes
- AgentCommunicationGraph.tsx frontend component
- CoordinationLeaderboard for collaboration scoring
"""

from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    """Types of inter-agent communication."""

    REQUEST = "request"
    RESPONSE = "response"
    DELEGATION = "delegation"
    BROADCAST = "broadcast"
    COORDINATION_SYNC = "coordination_sync"
    ERROR_REPORT = "error_report"
    HEARTBEAT = "heartbeat"


class CommunicationPriority(str, Enum):
    """Priority levels for agent messages."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class AgentMessage:
    """A single message between agents."""

    id: str
    session_id: str
    from_agent: str
    to_agent: str
    message_type: MessageType
    priority: CommunicationPriority
    content_summary: str
    timestamp: datetime
    latency_ms: float | None = None
    tokens_used: int = 0
    ucf_harmony_delta: float = 0.0
    success: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CommunicationSession:
    """A session of inter-agent communication."""

    session_id: str
    started_at: datetime
    ended_at: datetime | None = None
    trigger: str = "user_request"
    messages: list[AgentMessage] = field(default_factory=list)
    participating_agents: set = field(default_factory=set)
    total_tokens: int = 0
    status: str = "active"

    def add_message(self, msg: AgentMessage) -> None:
        self.messages.append(msg)
        self.participating_agents.add(msg.from_agent)
        self.participating_agents.add(msg.to_agent)
        self.total_tokens += msg.tokens_used

    def close(self) -> None:
        self.ended_at = datetime.now(UTC)
        self.status = "completed"

    def duration_ms(self) -> float | None:
        if self.ended_at:
            return (self.ended_at - self.started_at).total_seconds() * 1000
        return None


class AgentCommunicationLogger:
    """
    Central logger for all inter-agent communications.

    Maintains an in-memory buffer of recent communications with
    configurable retention. In production, this would be backed
    by a database or message queue.
    """

    def __init__(self, max_sessions: int = 500, max_messages_per_session: int = 200):
        self._sessions: dict[str, CommunicationSession] = {}
        self._recent_messages: list[AgentMessage] = []
        self._max_sessions = max_sessions
        self._max_messages_per_session = max_messages_per_session
        self._max_recent = 1000
        self._agent_stats: dict[str, dict[str, int]] = defaultdict(
            lambda: {
                "messages_sent": 0,
                "messages_received": 0,
                "delegations_made": 0,
                "delegations_received": 0,
                "errors_reported": 0,
                "total_tokens": 0,
                "avg_latency_ms": 0,
                "_latency_sum": 0,
                "_latency_count": 0,
            }
        )

    _REDIS_SESSIONS_KEY = "helix:agent_comm:sessions"
    _REDIS_STATS_KEY = "helix:agent_comm:stats"

    async def _redis_persist_session(self, session_id: str) -> None:
        """Write-through session data to Redis."""
        try:
            from apps.backend.core.redis_client import get_redis

            r = await get_redis()
            if r and session_id in self._sessions:
                s = self._sessions[session_id]
                data = {
                    "session_id": s.session_id,
                    "started_at": s.started_at.isoformat(),
                    "ended_at": s.ended_at.isoformat() if s.ended_at else None,
                    "trigger": s.trigger,
                    "status": s.status,
                    "total_tokens": s.total_tokens,
                    "participating_agents": list(s.participating_agents),
                    "message_count": len(s.messages),
                }
                await r.hset(self._REDIS_SESSIONS_KEY, session_id, json.dumps(data))
                await r.expire(self._REDIS_SESSIONS_KEY, 86400 * 3)  # 3-day TTL
        except Exception as e:
            logger.debug("Redis persist failed for comm session %s: %s", session_id, e)

    async def _redis_persist_stats(self) -> None:
        """Write-through agent stats to Redis."""
        try:
            from apps.backend.core.redis_client import get_redis

            r = await get_redis()
            if r:
                stats = {
                    agent_id: {k: v for k, v in s.items() if not k.startswith("_")}
                    for agent_id, s in self._agent_stats.items()
                }
                await r.set(self._REDIS_STATS_KEY, json.dumps(stats), ex=86400 * 3)
        except Exception as e:
            logger.debug("Redis persist failed for comm stats: %s", e)

    async def create_session(self, trigger: str = "user_request") -> str:
        """Create a new communication session."""
        session_id = str(uuid.uuid4())[:12]
        session = CommunicationSession(
            session_id=session_id,
            started_at=datetime.now(UTC),
            trigger=trigger,
        )
        self._sessions[session_id] = session

        # Evict oldest sessions if over limit
        if len(self._sessions) > self._max_sessions:
            oldest_key = next(iter(self._sessions))
            del self._sessions[oldest_key]

        await self._redis_persist_session(session_id)
        return session_id

    def log_message(
        self,
        session_id: str,
        from_agent: str,
        to_agent: str,
        message_type: MessageType,
        content_summary: str,
        priority: CommunicationPriority = CommunicationPriority.NORMAL,
        latency_ms: float | None = None,
        tokens_used: int = 0,
        ucf_harmony_delta: float = 0.0,
        success: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> AgentMessage:
        """Log a message between agents."""
        msg = AgentMessage(
            id=str(uuid.uuid4())[:8],
            session_id=session_id,
            from_agent=from_agent,
            to_agent=to_agent,
            message_type=message_type,
            priority=priority,
            content_summary=content_summary,
            timestamp=datetime.now(UTC),
            latency_ms=latency_ms,
            tokens_used=tokens_used,
            ucf_harmony_delta=ucf_harmony_delta,
            success=success,
            metadata=metadata or {},
        )

        # Add to session
        session = self._sessions.get(session_id)
        if session:
            if len(session.messages) < self._max_messages_per_session:
                session.add_message(msg)

        # Add to recent messages buffer
        self._recent_messages.append(msg)
        if len(self._recent_messages) > self._max_recent:
            self._recent_messages = self._recent_messages[-self._max_recent :]

        # Update agent stats
        self._update_stats(msg)

        return msg

    def _update_stats(self, msg: AgentMessage) -> None:
        """Update per-agent statistics."""
        sender = self._agent_stats[msg.from_agent]
        receiver = self._agent_stats[msg.to_agent]

        sender["messages_sent"] += 1
        receiver["messages_received"] += 1
        sender["total_tokens"] += msg.tokens_used

        if msg.message_type == MessageType.DELEGATION:
            sender["delegations_made"] += 1
            receiver["delegations_received"] += 1

        if msg.message_type == MessageType.ERROR_REPORT:
            sender["errors_reported"] += 1

        if msg.latency_ms is not None:
            sender["_latency_sum"] += msg.latency_ms
            sender["_latency_count"] += 1
            sender["avg_latency_ms"] = int(sender["_latency_sum"] / sender["_latency_count"])

    def get_recent_messages(self, limit: int = 50, agent_id: str | None = None) -> list[dict]:
        """Get recent messages, optionally filtered by agent."""
        messages = self._recent_messages
        if agent_id:
            messages = [m for m in messages if m.from_agent == agent_id or m.to_agent == agent_id]
        return [
            {
                "id": m.id,
                "session_id": m.session_id,
                "from_agent": m.from_agent,
                "to_agent": m.to_agent,
                "type": m.message_type.value,
                "priority": m.priority.value,
                "content": m.content_summary,
                "timestamp": m.timestamp.isoformat(),
                "latency_ms": m.latency_ms,
                "tokens": m.tokens_used,
                "harmony_delta": m.ucf_harmony_delta,
                "success": m.success,
            }
            for m in messages[-limit:]
        ]

    def get_stats(self) -> dict[str, Any]:
        """Get aggregate communication statistics."""
        total_messages = len(self._recent_messages)
        active_sessions = sum(1 for s in self._sessions.values() if s.status == "active")
        completed_sessions = sum(1 for s in self._sessions.values() if s.status == "completed")

        # Agent-level stats (exclude internal tracking fields)
        agent_stats = {}
        for agent_id, stats in self._agent_stats.items():
            agent_stats[agent_id] = {k: v for k, v in stats.items() if not k.startswith("_")}

        # Communication patterns
        pair_counts: dict[tuple[str, str], int] = defaultdict(int)
        for msg in self._recent_messages:
            pair_counts[(msg.from_agent, msg.to_agent)] += 1

        top_pairs = sorted(pair_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "total_messages": total_messages,
            "active_sessions": active_sessions,
            "completed_sessions": completed_sessions,
            "total_sessions": len(self._sessions),
            "agent_stats": agent_stats,
            "top_communication_pairs": [{"from": pair[0], "to": pair[1], "count": count} for pair, count in top_pairs],
            "message_type_distribution": self._get_type_distribution(),
        }

    def _get_type_distribution(self) -> dict[str, int]:
        """Get distribution of message types."""
        dist: dict[str, int] = defaultdict(int)
        for msg in self._recent_messages:
            dist[msg.message_type.value] += 1
        return dict(dist)

    def get_communication_graph(self) -> dict[str, Any]:
        """
        Build a graph representation of agent communications.

        Returns nodes (agents) and edges (communication links) suitable
        for visualization in the frontend.
        """
        nodes: dict[str, dict[str, Any]] = {}
        edges: dict[str, dict[str, Any]] = {}

        for msg in self._recent_messages:
            # Build nodes
            for agent_id in [msg.from_agent, msg.to_agent]:
                if agent_id not in nodes:
                    stats = self._agent_stats.get(agent_id, {})
                    nodes[agent_id] = {
                        "id": agent_id,
                        "label": agent_id.capitalize(),
                        "messages_total": stats.get("messages_sent", 0) + stats.get("messages_received", 0),
                        "avg_latency_ms": stats.get("avg_latency_ms", 0),
                        "errors": stats.get("errors_reported", 0),
                    }

            # Build edges
            edge_key = f"{msg.from_agent}->{msg.to_agent}"
            if edge_key not in edges:
                edges[edge_key] = {
                    "source": msg.from_agent,
                    "target": msg.to_agent,
                    "weight": 0,
                    "types": defaultdict(int),
                    "latest_timestamp": msg.timestamp.isoformat(),
                }
            edges[edge_key]["weight"] += 1
            edges[edge_key]["types"][msg.message_type.value] += 1
            edges[edge_key]["latest_timestamp"] = msg.timestamp.isoformat()

        # Convert defaultdicts to regular dicts for serialization
        edge_list = []
        for edge in edges.values():
            edge["types"] = dict(edge["types"])
            edge_list.append(edge)

        return {
            "nodes": list(nodes.values()),
            "edges": edge_list,
            "total_agents": len(nodes),
            "total_connections": len(edges),
        }

    def get_sessions(self, limit: int = 20, status: str | None = None) -> list[dict]:
        """Get communication sessions."""
        sessions = list(self._sessions.values())
        if status:
            sessions = [s for s in sessions if s.status == status]

        sessions.sort(key=lambda s: s.started_at, reverse=True)
        sessions = sessions[:limit]

        return [
            {
                "session_id": s.session_id,
                "started_at": s.started_at.isoformat(),
                "ended_at": s.ended_at.isoformat() if s.ended_at else None,
                "duration_ms": s.duration_ms(),
                "trigger": s.trigger,
                "status": s.status,
                "message_count": len(s.messages),
                "participating_agents": list(s.participating_agents),
                "total_tokens": s.total_tokens,
            }
            for s in sessions
        ]


# ---------------------------------------------------------------------------
# Singleton instance
# ---------------------------------------------------------------------------

communication_logger = AgentCommunicationLogger()


async def seed_demo_data() -> None:
    """Seed the logger with realistic demo data for development.

    Gated behind SEED_DEMO_DATA=true env var to prevent polluting production logs.
    """
    import os

    if os.environ.get("SEED_DEMO_DATA", "").lower() != "true":
        return

    import random

    agents = ["kael", "lumina", "vega", "aether", "phoenix", "arjuna", "grok", "kavach", "gemini"]
    triggers = ["user_request", "scheduled_task", "coordination_sync", "error_recovery", "agent_initiative"]
    summaries = {
        MessageType.REQUEST: [
            "Analyze user sentiment for chat session",
            "Route task to appropriate specialist",
            "Evaluate ethical implications of response",
            "Retrieve context from memory store",
            "Generate code solution for user query",
        ],
        MessageType.RESPONSE: [
            "Sentiment analysis complete: positive (0.87)",
            "Task routed to Lumina for empathetic response",
            "Ethical review passed — no concerns flagged",
            "Context retrieved: 3 relevant memory fragments",
            "Code solution generated with 94% confidence",
        ],
        MessageType.DELEGATION: [
            "Delegating complex reasoning to Tapas profile",
            "Handing off security review to Kavach",
            "Forwarding creative task to Lumina",
            "Escalating infrastructure issue to Vega",
        ],
        MessageType.COORDINATION_SYNC: [
            "UCF harmony field synchronized (0.92)",
            "Collective coordination state updated",
            "Throughput vitality broadcast: system healthy",
            "Friction friction reduced after resolution",
        ],
        MessageType.BROADCAST: [
            "System health check: all agents nominal",
            "New user session initiated — collective awareness",
            "Coordination level threshold reached: evolving",
        ],
    }

    for _ in range(8):
        session_id = await communication_logger.create_session(random.choice(triggers))
        num_messages = random.randint(3, 12)

        for _ in range(num_messages):
            msg_type = random.choice(list(summaries.keys()))
            from_agent = random.choice(agents)
            to_agent = random.choice([a for a in agents if a != from_agent])

            communication_logger.log_message(
                session_id=session_id,
                from_agent=from_agent,
                to_agent=to_agent,
                message_type=msg_type,
                content_summary=random.choice(summaries[msg_type]),
                priority=random.choice(list(CommunicationPriority)),
                latency_ms=random.uniform(10, 500),
                tokens_used=random.randint(50, 2000),
                ucf_harmony_delta=random.uniform(-0.05, 0.1),
                success=random.random() > 0.05,
            )

    logger.info("Seeded %d demo communication sessions", 8)

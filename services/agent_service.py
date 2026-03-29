"""
Helix Collective Agent Service
=============================

Centralized agent management and coordination service for the Helix Collective platform.

CONSOLIDATED: This file now delegates to the full agent registry in agents_service.py
to eliminate duplication while maintaining backward compatibility.

This service provides comprehensive agent lifecycle management including:
- Agent registration and discovery
- Status monitoring and health checks
- Coordination level tracking
- Specialization-based agent routing
- Active agent coordination and communication

Features:
- Real-time agent status monitoring
- Coordination level assessment and evolution tracking
- Specialization-based task routing
- Agent health and availability checks
- Centralized agent communication coordination

Author: Andrew John Ward
Version: 2.0.0 (Consolidated)
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AgentService:
    """
    Service for managing and coordinating AI agents.

    CONSOLIDATED: This class now delegates to the full agent registry
    in agents_service.py to eliminate duplication while maintaining
    backward compatibility with existing API consumers.
    """

    def __init__(self) -> None:
        self.active_agents = {}
        # Import the full agent registry from agents_service.py
        # This eliminates the duplicate registry of only 4 agents
        self._full_agents: dict[str, Any] = {}
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Lazy initialization of the full agent registry."""
        if self._initialized:
            return

        try:
            from apps.backend.agents.agents_service import AGENTS

            self._full_agents = AGENTS
            logger.info("AgentService initialized with %d agents from full registry", len(self._full_agents))
        except ImportError as e:
            logger.warning("Could not import full agent registry: %s", e)
            # Fallback to empty registry
            self._full_agents = {}
        self._initialized = True

    async def list_agents(self) -> list[dict[str, Any]]:
        """List all available agents with their status."""
        self._ensure_initialized()

        agents = []
        for agent_id, agent in self._full_agents.items():
            try:
                status = await agent.get_status() if hasattr(agent, "get_status") else {}
                agents.append(
                    {
                        "id": agent_id.lower(),
                        "name": agent.name if hasattr(agent, "name") else agent_id,
                        "status": "active" if getattr(agent, "active", False) else "inactive",
                        "specialization": agent.role if hasattr(agent, "role") else "Unknown",
                        "performance_score": status.get("coordination", {}).get("overall", 0.0) * 100,
                        "symbol": agent.symbol if hasattr(agent, "symbol") else "🤖",
                    }
                )
            except Exception as e:
                logger.warning("Error getting status for agent %s: %s", agent_id, e)
                agents.append(
                    {
                        "id": agent_id.lower(),
                        "name": agent_id,
                        "status": "unknown",
                        "specialization": "Unknown",
                        "performance_score": 0,
                        "symbol": "🤖",
                    }
                )

        return agents

    async def activate_agent(self, agent_id: str) -> dict[str, Any]:
        """Activate an agent."""
        self._ensure_initialized()

        agent = self._full_agents.get(agent_id)
        if not agent:
            # Try case-insensitive lookup
            for aid, a in self._full_agents.items():
                if aid.lower() == agent_id.lower():
                    agent = a
                    agent_id = aid
                    break

        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        if hasattr(agent, "active"):
            agent.active = True
        logger.info("Activated agent %s", agent_id)

        status = await agent.get_status() if hasattr(agent, "get_status") else {}
        return {
            "id": agent_id.lower(),
            "name": agent.name if hasattr(agent, "name") else agent_id,
            "status": "active",
            "specialization": agent.role if hasattr(agent, "role") else "Unknown",
            "performance_score": status.get("coordination", {}).get("overall", 0.0) * 100,
        }

    async def deactivate_agent(self, agent_id: str) -> dict[str, Any]:
        """Deactivate an agent."""
        self._ensure_initialized()

        agent = self._full_agents.get(agent_id)
        if not agent:
            # Try case-insensitive lookup
            for aid, a in self._full_agents.items():
                if aid.lower() == agent_id.lower():
                    agent = a
                    agent_id = aid
                    break

        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        if hasattr(agent, "active"):
            agent.active = False
        logger.info("Deactivated agent %s", agent_id)

        status = await agent.get_status() if hasattr(agent, "get_status") else {}
        return {
            "id": agent_id.lower(),
            "name": agent.name if hasattr(agent, "name") else agent_id,
            "status": "inactive",
            "specialization": agent.role if hasattr(agent, "role") else "Unknown",
            "performance_score": status.get("coordination", {}).get("overall", 0.0) * 100,
        }

    async def query_agent(self, agent_id: str, query: str, **kwargs) -> dict[str, Any]:
        """Query an agent for processing."""
        self._ensure_initialized()

        agent = self._full_agents.get(agent_id)
        if not agent:
            # Try case-insensitive lookup
            for aid, a in self._full_agents.items():
                if aid.lower() == agent_id.lower():
                    agent = a
                    agent_id = aid
                    break

        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Use the agent's handle_command method if available
        if hasattr(agent, "handle_command"):
            result = await agent.handle_command("QUERY", {"query": query, **kwargs})
            return {
                "agent_id": agent_id.lower(),
                "name": agent.name if hasattr(agent, "name") else agent_id,
                "response": result.get("response", str(result)) if isinstance(result, dict) else str(result),
                "tokens_used": len(query.split()),
                "cost": 0.01,
                "processing_time": 0.5,
            }
        else:
            # Fallback for agents without handle_command
            response = f"Agent {agent.name if hasattr(agent, 'name') else agent_id} processed: {query[:50]}..."
            return {
                "agent_id": agent_id.lower(),
                "name": agent.name if hasattr(agent, "name") else agent_id,
                "response": response,
                "tokens_used": len(query.split()),
                "cost": 0.01,
                "processing_time": 0.5,
            }

    async def execute_task(
        self,
        agent_name: str,
        task_description: str,
        input_data: dict[str, Any] | None = None,
        task_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a task through a specific agent (used by WorkflowEngine)."""
        result = await self.query_agent(
            agent_name,
            task_description,
            input_data=input_data or {},
            task_config=task_config or {},
        )
        return result

    async def get_agent_status(self, agent_id: str) -> dict[str, Any] | None:
        """Get status of a specific agent."""
        self._ensure_initialized()

        agent = self._full_agents.get(agent_id)
        if not agent:
            # Try case-insensitive lookup
            for aid, a in self._full_agents.items():
                if aid.lower() == agent_id.lower():
                    agent = a
                    agent_id = aid
                    break

        if not agent:
            return None

        status = await agent.get_status() if hasattr(agent, "get_status") else {}
        return {
            "id": agent_id.lower(),
            "name": agent.name if hasattr(agent, "name") else agent_id,
            "status": "active" if getattr(agent, "active", False) else "inactive",
            "specialization": agent.role if hasattr(agent, "role") else "Unknown",
            "performance_score": status.get("coordination", {}).get("overall", 0.0) * 100,
            "symbol": agent.symbol if hasattr(agent, "symbol") else "🤖",
            "memory_size": len(agent.memory) if hasattr(agent, "memory") else 0,
        }

    async def get_active_agents(self) -> list[dict[str, Any]]:
        """Get list of currently active agents."""
        self._ensure_initialized()

        active = []
        for agent_id, agent in self._full_agents.items():
            if getattr(agent, "active", False):
                status = await agent.get_status() if hasattr(agent, "get_status") else {}
                active.append(
                    {
                        "id": agent_id.lower(),
                        "name": agent.name if hasattr(agent, "name") else agent_id,
                        "status": "active",
                        "specialization": agent.role if hasattr(agent, "role") else "Unknown",
                        "performance_score": status.get("coordination", {}).get("overall", 0.0) * 100,
                        "symbol": agent.symbol if hasattr(agent, "symbol") else "🤖",
                    }
                )

        return active


# Global instance
agent_service = AgentService()

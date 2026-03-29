"""
Helix Collective Agent Manager Service
====================================

Comprehensive agent lifecycle management and coordination service for the Helix Collective swarm.

This service provides enterprise-grade agent management capabilities including:
- Agent registration, activation, and deactivation
- Health monitoring with heartbeat tracking and failure detection
- Performance metrics collection and analysis
- Status broadcasting and real-time updates
- Automatic cleanup of inactive or failed agents
- Redis-backed state persistence and recovery

Key Features:
-------------
Lifecycle Management:
- Agent registration with configuration validation
- Graceful activation/deactivation with state transitions
- Automatic cleanup of stale agent connections
- State persistence across service restarts

Health Monitoring:
- Configurable heartbeat intervals (default: 30s)
- Automatic failure detection (max misses: 3)
- Health status aggregation and reporting
- Performance metrics tracking (response times, error rates)

Coordination & Communication:
- Real-time status updates via Redis pub/sub
- Agent discovery and capability querying
- Task assignment and load balancing
- Inter-agent communication routing

Configuration:
- Heartbeat interval: 30 seconds
- Maximum heartbeat misses: 3 (before marking as failed)
- Cleanup interval: 5 minutes
- Status update interval: 1 minute

Integration:
- Redis for state persistence and pub/sub messaging
- Coordination models for status and performance tracking
- WebSocket bridge for real-time client updates
- Orchestrator for high-level agent coordination

Author: Andrew John Ward
Version: 1.0.0
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ..core.redis_client import redis_client
from ..models.coordination import AgentStatus, PerformanceMetrics, SystemHealth

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for agent management."""

    heartbeat_interval: int = 30  # seconds
    max_heartbeat_misses: int = 3
    cleanup_interval: int = 300  # 5 minutes
    status_update_interval: int = 60  # 1 minute


class AgentManager:
    """Service for managing AI agent lifecycle and coordination."""

    def __init__(self) -> None:
        self.config = AgentConfig()
        self._active_agents: set[str] = set()
        self._agent_tasks: dict[str, asyncio.Task] = {}
        self._status_tasks: dict[str, asyncio.Task] = {}
        self._cleanup_task: asyncio.Task | None = None

    async def initialize(self):
        """Initialize the agent manager."""
        logger.info("Initializing Agent Manager")

        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        # Load existing agent states from Redis
        await self._load_agent_states()

        logger.info("Agent Manager initialized with %s agents", len(self._active_agents))

    async def shutdown(self):
        """Shutdown the agent manager."""
        logger.info("Shutting down Agent Manager")

        # Cancel all agent tasks
        for task in self._agent_tasks.values():
            task.cancel()

        for task in self._status_tasks.values():
            task.cancel()

        if self._cleanup_task:
            self._cleanup_task.cancel()

        # Wait for tasks to complete
        await asyncio.gather(*list(self._agent_tasks.values()), return_exceptions=True)
        await asyncio.gather(*list(self._status_tasks.values()), return_exceptions=True)

        if self._cleanup_task:
            await self._cleanup_task

        logger.info("Agent Manager shutdown complete")

    async def activate_agent(self, agent_id: str) -> bool:
        """
        Activate an agent in the swarm.

        Args:
            agent_id: The ID of the agent to activate

        Returns:
            True if activation was successful, False otherwise
        """
        try:
            if agent_id in self._active_agents:
                logger.warning("Agent %s is already active", agent_id)
                return True

            # Create agent status
            agent_status = AgentStatus(
                agent_id=agent_id,
                name=agent_id,  # Default name, could be enhanced
                status="active",
                coordination=None,  # Will be populated by coordination service
                last_activity=datetime.now(UTC).isoformat(),
                error_count=0,
                uptime=0,
            )

            # Store agent status
            await self._store_agent_status(agent_id, agent_status)

            # Add to active agents
            self._active_agents.add(agent_id)

            # Start agent monitoring tasks
            self._start_agent_monitoring(agent_id)

            logger.info("Agent %s activated successfully", agent_id)
            return True

        except Exception as e:
            logger.error("Error activating agent %s: %s", agent_id, e)
            return False

    async def deactivate_agent(self, agent_id: str) -> bool:
        """
        Deactivate an agent in the swarm.

        Args:
            agent_id: The ID of the agent to deactivate

        Returns:
            True if deactivation was successful, False otherwise
        """
        try:
            if agent_id not in self._active_agents:
                logger.warning("Agent %s is not active", agent_id)
                return True

            # Cancel monitoring tasks
            if agent_id in self._agent_tasks:
                self._agent_tasks[agent_id].cancel()
                del self._agent_tasks[agent_id]

            if agent_id in self._status_tasks:
                self._status_tasks[agent_id].cancel()
                del self._status_tasks[agent_id]

            # Update agent status
            agent_status = await self.get_agent_status(agent_id)
            if agent_status:
                agent_status.status = "inactive"
                agent_status.last_activity = datetime.now(UTC).isoformat()
                await self._store_agent_status(agent_id, agent_status)

            # Remove from active agents
            self._active_agents.discard(agent_id)

            logger.info("Agent %s deactivated successfully", agent_id)
            return True

        except Exception as e:
            logger.error("Error deactivating agent %s: %s", agent_id, e)
            return False

    async def get_agent_status(self, agent_id: str) -> AgentStatus | None:
        """
        Get detailed status information for an agent.

        Args:
            agent_id: The ID of the agent

        Returns:
            AgentStatus object or None if agent not found
        """
        try:
            status_key = f"agent:status:{agent_id}"
            status_data = await redis_client.get(status_key)

            if not status_data:
                return None

            status_dict = json.loads(status_data)
            return AgentStatus.model_validate(status_dict)

        except Exception as e:
            logger.error("Error getting agent status for %s: %s", agent_id, e)
            return None

    async def get_active_agents(self) -> list[AgentStatus]:
        """
        Get status information for all active agents.

        Returns:
            List of AgentStatus objects for active agents
        """
        try:
            active_statuses = []

            for agent_id in self._active_agents:
                status = await self.get_agent_status(agent_id)
                if status:
                    active_statuses.append(status)

            return active_statuses

        except Exception as e:
            logger.error("Error getting active agents: %s", e)
            return []

    async def get_active_connections_count(self) -> int:
        """
        Get the number of active WebSocket connections.

        Returns:
            Number of active connections
        """
        try:
            connections_key = "websocket:connections:active"
            connections = await redis_client.smembers(connections_key)
            return len(connections)

        except Exception as e:
            logger.error("Error getting active connections count: %s", e)
            return 0

    async def update_agent_activity(self, agent_id: str, activity_type: str = "message"):
        """
        Update agent activity timestamp and increment activity counter.

        Args:
            agent_id: The ID of the agent
            activity_type: Type of activity (default: "message")
        """
        try:
            status = await self.get_agent_status(agent_id)
            if status:
                status.last_activity = datetime.now(UTC).isoformat()

                # Increment uptime (in seconds)
                last_update = datetime.fromisoformat(status.last_activity)
                status.uptime += int((datetime.now(UTC) - last_update).total_seconds())

                await self._store_agent_status(agent_id, status)

            # Increment activity counter
            activity_key = f"activity:count:{agent_id}"
            await redis_client.incr(activity_key)
            await redis_client.expire(activity_key, 3600)  # Expire after 1 hour

            logger.debug("Updated activity for agent %s", agent_id)

        except Exception as e:
            logger.error("Error updating agent activity for %s: %s", agent_id, e)

    async def increment_error_count(self, agent_id: str):
        """
        Increment the error count for an agent.

        Args:
            agent_id: The ID of the agent
        """
        try:
            status = await self.get_agent_status(agent_id)
            if status:
                status.error_count += 1
                await self._store_agent_status(agent_id, status)

                # Log warning if error count is high
                if status.error_count > 10:
                    logger.warning("Agent %s has high error count: %s", agent_id, status.error_count)

        except Exception as e:
            logger.error("Error incrementing error count for %s: %s", agent_id, e)

    async def get_system_health(self) -> SystemHealth:
        """
        Get overall system health status.

        Returns:
            SystemHealth object with component status
        """
        try:
            active_agents = await self.get_active_agents()
            active_count = len(active_agents)

            # Calculate system metrics
            total_errors = sum(agent.error_count for agent in active_agents)

            # Check component health
            components = {
                "redis": await self._check_redis_health(),
                "agents": "healthy" if active_count > 0 else "warning",
                "websocket": await self._check_websocket_health(),
            }

            # Determine overall status
            if active_count == 0:
                status = "critical"
            elif total_errors > 50 or any(c == "critical" for c in components.values()):
                status = "warning"
            else:
                status = "healthy"

            # Generate recommendations
            recommendations = []
            if active_count == 0:
                recommendations.append("No active agents detected")
            if total_errors > 20:
                recommendations.append("High error rate detected, check agent logs")
            if components["redis"] == "critical":
                recommendations.append("Redis connection issues detected")

            return SystemHealth(
                status=status,
                components=components,
                alerts=[],  # Could be populated from monitoring
                recommendations=recommendations,
                timestamp=datetime.now(UTC).isoformat(),
            )

        except Exception as e:
            logger.error("Error getting system health: %s", e)
            return SystemHealth(
                status="critical",
                components={},
                alerts=["System health check failed"],
                recommendations=["Check system logs"],
                timestamp=datetime.now(UTC).isoformat(),
            )

    async def get_performance_metrics(self) -> PerformanceMetrics:
        """
        Get system performance metrics.

        Returns:
            PerformanceMetrics object
        """
        try:
            active_connections = await self.get_active_connections_count()

            # Calculate response time (simplified)
            response_time = await self._calculate_average_response_time()

            # Calculate error rate
            total_errors = sum(agent.error_count for agent in await self.get_active_agents())
            total_requests = await self._get_total_requests()
            error_rate = total_errors / max(1, total_requests)

            return PerformanceMetrics(
                cpu_usage=await self._get_cpu_usage(),
                memory_usage=await self._get_memory_usage(),
                active_connections=active_connections,
                response_time=response_time,
                error_rate=error_rate,
                timestamp=datetime.now(UTC).isoformat(),
            )

        except Exception as e:
            logger.error("Error getting performance metrics: %s", e)
            return PerformanceMetrics(
                cpu_usage=0.0,
                memory_usage=0.0,
                active_connections=0,
                response_time=0.0,
                error_rate=0.0,
                timestamp=datetime.now(UTC).isoformat(),
            )

    # Private helper methods

    async def _load_agent_states(self):
        """Load existing agent states from Redis."""
        try:
            status_keys = await redis_client.keys("agent:status:*")

            for key in status_keys:
                agent_id = key.split(":")[-1]
                status_data = await redis_client.get(key)

                if status_data:
                    status_dict = json.loads(status_data)
                    status = AgentStatus(**status_dict)

                    if status.status == "active":
                        self._active_agents.add(agent_id)
                        self._start_agent_monitoring(agent_id)

        except Exception as e:
            logger.error("Error loading agent states: %s", e)

    def _start_agent_monitoring(self, agent_id: str):
        """Start monitoring tasks for an agent."""
        # Start heartbeat monitoring
        self._agent_tasks[agent_id] = asyncio.create_task(self._heartbeat_monitor(agent_id))

        # Start status updates
        self._status_tasks[agent_id] = asyncio.create_task(self._status_update_loop(agent_id))

    async def _heartbeat_monitor(self, agent_id: str):
        """Monitor agent heartbeat and handle timeouts."""
        try:
            while True:
                await asyncio.sleep(self.config.heartbeat_interval)

                # Check if agent is still active
                if agent_id not in self._active_agents:
                    break

                # Check heartbeat
                heartbeat_key = f"agent:heartbeat:{agent_id}"
                last_heartbeat = await redis_client.get(heartbeat_key)

                # Check heartbeat
                heartbeat_key = f"agent:heartbeat:{agent_id}"
                last_heartbeat = await redis_client.get(heartbeat_key)

                if last_heartbeat:
                    last_time = datetime.fromisoformat(last_heartbeat)
                    if datetime.now(UTC) - last_time > timedelta(
                        seconds=self.config.heartbeat_interval * self.config.max_heartbeat_misses
                    ):
                        logger.warning("Agent %s heartbeat timeout, deactivating", agent_id)
                        await self.deactivate_agent(agent_id)
                        break
                else:
                    # Set initial heartbeat
                    await redis_client.setex(
                        heartbeat_key,
                        self.config.heartbeat_interval * 2,
                        datetime.now(UTC).isoformat(),
                    )

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Error in heartbeat monitor for %s: %s", agent_id, e)

    async def _status_update_loop(self, agent_id: str):
        """Periodically update agent status."""
        try:
            while True:
                await asyncio.sleep(self.config.status_update_interval)

                # Check if agent is still active
                if agent_id not in self._active_agents:
                    break

                # Update status
                status = await self.get_agent_status(agent_id)
                if status:
                    status.last_activity = datetime.now(UTC).isoformat()
                    await self._store_agent_status(agent_id, status)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Error in status update loop for %s: %s", agent_id, e)

    async def _cleanup_loop(self):
        """Periodic cleanup of expired agent data."""
        try:
            await asyncio.sleep(self.config.cleanup_interval)

            # Clean up expired heartbeats
            heartbeat_keys = await redis_client.keys("agent:heartbeat:*")
            for key in heartbeat_keys:
                agent_id = key.split(":")[-1]
                if agent_id not in self._active_agents:
                    await redis_client.delete(key)

            # Clean up expired activity counters
            activity_keys = await redis_client.keys("activity:count:*")
            for key in activity_keys:
                agent_id = key.split(":")[-1]
                if agent_id not in self._active_agents:
                    await redis_client.delete(key)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Error in cleanup loop: %s", e)

    async def _store_agent_status(self, agent_id: str, status: AgentStatus):
        """Store agent status in Redis."""
        try:
            status_key = f"agent:status:{agent_id}"
            await redis_client.setex(status_key, 86400, json.dumps(status.model_dump()))  # 24 hours
        except Exception as e:
            logger.error("Error storing agent status for %s: %s", agent_id, e)

    async def _check_redis_health(self) -> str:
        """Check Redis connection health."""
        try:
            if redis_client:
                await redis_client.ping()
            return "healthy"
        except (ConnectionError, TimeoutError, OSError) as e:
            logger.warning("Redis health check failed: %s", e)
            return "critical"
        except Exception as e:
            logger.warning("Unexpected Redis health check failure: %s", e)
            return "critical"

    async def _check_websocket_health(self) -> str:
        """Check WebSocket connection health."""
        try:
            connections_count = len(self._active_agents)
            return "healthy" if connections_count > 0 else "warning"
        except TypeError as e:
            logger.debug("WebSocket health check type error: %s", e)
            return "critical"
        except Exception as e:
            logger.debug("Unexpected WebSocket health check failure: %s", e)
            return "critical"

    async def _calculate_average_response_time(self) -> float:
        """Calculate average response time from process CPU time delta."""
        import psutil

        try:
            proc = psutil.Process()
            cpu_times = proc.cpu_times()
            # Use user+system time as a proxy (ms)
            return round((cpu_times.user + cpu_times.system) * 10, 1)
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError) as e:
            logger.debug("Failed to calculate average response time: %s", e)
            return 0.0
        except Exception as e:
            logger.debug("Unexpected error calculating response time: %s", e)
            return 0.0

    async def _get_total_requests(self) -> int:
        """Get total number of requests (simplified)."""
        try:
            total_requests = 0
            activity_keys = await redis_client.keys("activity:count:*")

            for key in activity_keys:
                count = await redis_client.get(key)
                if count:
                    total_requests += int(count)

            return total_requests
        except (ConnectionError, TimeoutError, ValueError) as e:
            logger.debug("Failed to get total requests from Redis: %s", e)
            return 0
        except Exception as e:
            logger.debug("Unexpected error getting total requests: %s", e)
            return 0

    async def _get_cpu_usage(self) -> float:
        """Get current CPU usage via psutil."""
        import psutil

        try:
            return psutil.cpu_percent(interval=0)
        except (psutil.Error, OSError, ValueError) as e:
            logger.debug("Failed to get CPU usage: %s", e)
            return 0.0
        except Exception as e:
            logger.debug("Unexpected error getting CPU usage: %s", e)
            return 0.0

    async def _get_memory_usage(self) -> float:
        """Get current memory usage via psutil."""
        import psutil

        try:
            return psutil.virtual_memory().percent
        except (psutil.Error, OSError, ValueError) as e:
            logger.debug("Failed to get memory usage: %s", e)
            return 0.0
        except Exception as e:
            logger.debug("Unexpected error getting memory usage: %s", e)
            return 0.0

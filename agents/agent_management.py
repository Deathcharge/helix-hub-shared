"""
Enhanced Agent Management System - Helix Collective v15.6
Advanced agent lifecycle management with performance monitoring and coordination
"""

import asyncio
import logging
import threading
import time
from datetime import UTC, datetime
from typing import Any

from ..types.agent_orchestration import AgentMetrics, AgentStatus

logger = logging.getLogger(__name__)

# Constants
MAX_AGENT_EVENTS = 1000
MAX_AGENTS = 16
HEALTH_CHECK_INTERVAL = 30  # seconds
PERFORMANCE_UPDATE_INTERVAL = 60  # seconds
OPTIMIZATION_INTERVAL = 300  # 5 minutes


class AgentManager:
    """
    Advanced agent lifecycle and performance management system
    Handles agent deployment, monitoring, coordination, and optimization
    """

    def __init__(self):
        self.agents = {}  # agent_id -> agent_instance
        self.agent_metrics = {}  # agent_id -> AgentMetrics
        self.performance_history = {}  # agent_id -> list of metrics
        self.coordination_matrix = {}  # agent_id -> set of coordinated agents
        self.health_monitor = AgentHealthMonitor()
        self.performance_optimizer = AgentPerformanceOptimizer()
        self.lifecycle_manager = AgentLifecycleManager()

        # Management parameters
        self.max_agents = MAX_AGENTS
        self.health_check_interval = HEALTH_CHECK_INTERVAL  # seconds
        self.performance_update_interval = PERFORMANCE_UPDATE_INTERVAL  # seconds
        self.optimization_interval = OPTIMIZATION_INTERVAL  # 5 minutes

        # Start background management tasks
        self._start_background_tasks()

        logger.info("🎯 Agent Manager initialized")

    def register_agent(self, agent_id: str, agent_config: dict[str, Any]) -> bool:
        """
        Register a new agent with the management system

        Parameters:
            agent_id: Unique identifier for the agent
            agent_config: Agent configuration dictionary

        Returns:
            Success status of registration
        """
        try:
            if len(self.agents) >= self.max_agents:
                logger.warning("Maximum agent capacity reached")
                return False

            if agent_id in self.agents:
                logger.warning("Agent %s already registered", agent_id)
                return False

            # Create agent instance
            agent = ManagedAgent(agent_id, agent_config)

            # Register with subsystems
            self.agents[agent_id] = agent
            self.agent_metrics[agent_id] = AgentMetrics(
                agent_id=agent_id,
                status=AgentStatus.INITIALIZING,
                performance_score=0.0,
                response_time=0.0,
                success_rate=0.0,
                last_activity=datetime.now(UTC),
                error_count=0,
                task_completion_rate=0.0,
            )
            self.performance_history[agent_id] = []
            self.coordination_matrix[agent_id] = set()

            # Initialize health monitoring
            self.health_monitor.register_agent(agent_id)

            logger.info("✅ Agent %s registered successfully", agent_id)
            return True

        except Exception as e:
            logger.error("Failed to register agent %s: %s", agent_id, e)
            return False

    def unregister_agent(self, agent_id: str) -> bool:
        """
        Unregister an agent from the management system

        Parameters:
            agent_id: Agent to unregister

        Returns:
            Success status of unregistration
        """
        try:
            if agent_id not in self.agents:
                logger.warning("Agent %s not found", agent_id)
                return False

            # Graceful shutdown
            agent = self.agents[agent_id]
            agent.shutdown()

            # Remove from all systems
            del self.agents[agent_id]
            del self.agent_metrics[agent_id]
            del self.performance_history[agent_id]
            del self.coordination_matrix[agent_id]

            # Remove from health monitoring
            self.health_monitor.unregister_agent(agent_id)

            logger.info("✅ Agent %s unregistered successfully", agent_id)
            return True

        except Exception as e:
            logger.error("Failed to unregister agent %s: %s", agent_id, e)
            return False

    def update_agent_metrics(self, agent_id: str, metrics: dict[str, Any]) -> None:
        """
        Update performance metrics for an agent

        Parameters:
            agent_id: Agent identifier
            metrics: New metrics data
        """
        try:
            if agent_id not in self.agent_metrics:
                logger.warning("Agent %s not found for metrics update", agent_id)
                return

            current_metrics = self.agent_metrics[agent_id]

            # Update metrics
            for key, value in metrics.items():
                if hasattr(current_metrics, key):
                    setattr(current_metrics, key, value)

            current_metrics.last_activity = datetime.now(UTC)

            # Store in history
            self.performance_history[agent_id].append(
                {
                    "timestamp": datetime.now(UTC),
                    "metrics": (current_metrics.dict() if hasattr(current_metrics, "dict") else vars(current_metrics)),
                }
            )

            # Keep only last 100 entries
            if len(self.performance_history[agent_id]) > 100:
                self.performance_history[agent_id] = self.performance_history[agent_id][-100:]

            logger.debug("📊 Metrics updated for agent %s", agent_id)

        except Exception as e:
            logger.error("Failed to update metrics for agent %s: %s", agent_id, e)

    def get_agent_status(self, agent_id: str) -> dict[str, Any] | None:
        """
        Get comprehensive status for an agent

        Parameters:
            agent_id: Agent identifier

        Returns:
            Agent status dictionary or None if not found
        """
        try:
            if agent_id not in self.agents:
                return None

            agent = self.agents[agent_id]
            metrics = self.agent_metrics[agent_id]

            return {
                "agent_id": agent_id,
                "status": metrics.status.value,
                "performance_score": metrics.performance_score,
                "response_time": metrics.response_time,
                "success_rate": metrics.success_rate,
                "last_activity": metrics.last_activity.isoformat(),
                "error_count": metrics.error_count,
                "task_completion_rate": metrics.task_completion_rate,
                "coordinated_agents": list(self.coordination_matrix[agent_id]),
                "health_status": self.health_monitor.get_agent_health(agent_id),
                "config": agent.config,
            }

        except Exception as e:
            logger.error("Failed to get status for agent %s: %s", agent_id, e)
            return None

    def coordinate_agents(self, agent_a: str, agent_b: str) -> bool:
        """
        Establish coordination relationship between two agents

        Parameters:
            agent_a: First agent ID
            agent_b: Second agent ID

        Returns:
            Success status of coordination establishment
        """
        try:
            if agent_a not in self.agents or agent_b not in self.agents:
                logger.warning("One or both agents not found: %s, %s", agent_a, agent_b)
                return False

            # Add bidirectional coordination
            self.coordination_matrix[agent_a].add(agent_b)
            self.coordination_matrix[agent_b].add(agent_a)

            logger.info("🤝 Agents %s and %s now coordinated", agent_a, agent_b)
            return True

        except Exception as e:
            logger.error("Failed to coordinate agents %s, %s: %s", agent_a, agent_b, e)
            return False

    def get_system_overview(self) -> dict[str, Any]:
        """
        Get comprehensive overview of the agent management system

        Returns:
            System overview dictionary
        """
        try:
            total_agents = len(self.agents)
            active_agents = sum(1 for m in self.agent_metrics.values() if m.status == AgentStatus.ACTIVE)
            healthy_agents = sum(
                1 for agent_id in self.agents.keys() if self.health_monitor.get_agent_health(agent_id) == "healthy"
            )

            avg_performance = (
                sum(m.performance_score for m in self.agent_metrics.values()) / total_agents
                if total_agents > 0
                else 0.0
            )

            return {
                "total_agents": total_agents,
                "active_agents": active_agents,
                "healthy_agents": healthy_agents,
                "average_performance": avg_performance,
                "coordination_pairs": sum(len(coords) for coords in self.coordination_matrix.values()) // 2,
                "system_health": self.health_monitor.get_system_health(),
                "timestamp": datetime.now(UTC).isoformat(),
            }

        except Exception as e:
            logger.error("Failed to get system overview: %s", e)
            return {"error": str(e)}

    def optimize_agent_performance(self, agent_id: str) -> dict[str, Any]:
        """
        Optimize performance for a specific agent

        Parameters:
            agent_id: Agent to optimize

        Returns:
            Optimization results
        """
        try:
            if agent_id not in self.agents:
                return {"status": "error", "message": "Agent not found"}

            agent = self.agents[agent_id]
            metrics = self.agent_metrics[agent_id]
            history = self.performance_history[agent_id]

            # Use performance optimizer
            optimization = self.performance_optimizer.optimize_agent(agent, metrics, history)

            logger.info("⚡ Performance optimized for agent %s", agent_id)
            return optimization

        except Exception as e:
            logger.error("Failed to optimize agent %s: %s", agent_id, e)
            return {"status": "error", "message": str(e)}

    def _start_background_tasks(self) -> None:
        """Start background management tasks"""
        # Health monitoring thread
        health_thread = threading.Thread(target=self._health_monitoring_loop, daemon=True)
        health_thread.start()

        # Performance optimization thread
        perf_thread = threading.Thread(target=self._performance_optimization_loop, daemon=True)
        perf_thread.start()

        logger.debug("🔄 Background management tasks started")

    def _health_monitoring_loop(self) -> None:
        """Background health monitoring loop"""
        while True:
            try:
                time.sleep(self.health_check_interval)
            except Exception as e:
                logger.error("Health monitoring loop error: %s", e)
                time.sleep(5)

    def _performance_optimization_loop(self) -> None:
        """Background performance optimization loop"""
        while True:
            try:
                for agent_id in list(self.agents.keys()):
                    self.optimize_agent_performance(agent_id)
                time.sleep(self.optimization_interval)
            except Exception as e:
                logger.error("Performance optimization loop error: %s", e)
                time.sleep(30)


class ManagedAgent:
    """Represents a managed agent instance"""

    def __init__(self, agent_id: str, config: dict[str, Any]):
        self.agent_id = agent_id
        self.config = config
        self.status = AgentStatus.INITIALIZING
        self.start_time = datetime.now(UTC)
        self.task_queue = asyncio.Queue()
        self.is_running = False

        # Start agent processing
        self._start_processing()

    def _start_processing(self) -> None:
        """Start agent processing loop as an asyncio background task."""
        self.is_running = True
        try:
            loop = asyncio.get_running_loop()
            self._task = loop.create_task(self._process_loop())
        except RuntimeError:
            # No running loop yet — task will be started when event loop runs
            logger.debug("No event loop running, agent %s will start processing on first await", self.agent_id)

    async def _process_loop(self) -> None:
        """Continuously process tasks from the agent's task queue."""
        self.status = AgentStatus.IDLE
        logger.info("Agent %s processing loop started", self.agent_id)
        while self.is_running:
            try:
                task = await asyncio.wait_for(self.task_queue.get(), timeout=5.0)
                self.status = AgentStatus.BUSY
                logger.info("Agent %s processing task: %s", self.agent_id, task.get("type", "unknown"))
                handler = self.config.get("task_handler")
                if callable(handler):
                    await handler(task)
                self.task_queue.task_done()
                self.status = AgentStatus.IDLE
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Agent %s task error: %s", self.agent_id, e)
                self.status = AgentStatus.IDLE

    def shutdown(self) -> None:
        """Shutdown the agent gracefully"""
        self.is_running = False
        self.status = AgentStatus.SHUTDOWN
        if hasattr(self, "_task") and not self._task.done():
            self._task.cancel()
        logger.info("Agent %s shutdown", self.agent_id)


class AgentHealthMonitor:
    """Monitors health of all managed agents"""

    def __init__(self):
        self.agent_health = {}  # agent_id -> health_status
        self.last_check = {}  # agent_id -> last_check_time

    def register_agent(self, agent_id: str) -> None:
        """Register agent for health monitoring"""
        self.agent_health[agent_id] = "initializing"
        self.last_check[agent_id] = datetime.now(UTC)

    def unregister_agent(self, agent_id: str) -> None:
        """Unregister agent from health monitoring"""
        if agent_id in self.agent_health:
            del self.agent_health[agent_id]
            del self.last_check[agent_id]

    def check_agent_health(self, agent_id: str) -> str:
        """
        Check health of specific agent

        Returns:
            Health status string: "healthy", "degraded", "unhealthy", "unknown"
        """
        try:
            time_since_last_check = (datetime.now(UTC) - self.last_check[agent_id]).seconds

            if time_since_last_check < 60:
                return "healthy"
            elif time_since_last_check < 300:
                return "degraded"
            else:
                return "unhealthy"

        except (KeyError, TypeError, ValueError) as e:
            logger.debug("Health check validation error: %s", e)
            return "unknown"
        except Exception as e:
            logger.warning("Unexpected health check error: %s", e)
            return "unknown"

    def check_all_agents(self) -> None:
        """Check health of all registered agents"""
        for agent_id in list(self.agent_health.keys()):
            health = self.check_agent_health(agent_id)
            self.agent_health[agent_id] = health
            self.last_check[agent_id] = datetime.now(UTC)

    def get_agent_health(self, agent_id: str) -> str:
        """Get cached health status for agent"""
        return self.agent_health.get(agent_id, "unknown")

    def get_system_health(self) -> dict[str, Any]:
        """Get overall system health status"""
        total_agents = len(self.agent_health)
        if total_agents == 0:
            return {"status": "empty", "healthy_count": 0, "total_count": 0}

        healthy_count = sum(1 for health in self.agent_health.values() if health == "healthy")
        degraded_count = sum(1 for health in self.agent_health.values() if health == "degraded")
        unhealthy_count = sum(1 for health in self.agent_health.values() if health == "unhealthy")

        if unhealthy_count > 0:
            status = "critical"
        elif degraded_count > total_agents * 0.5:
            status = "degraded"
        elif healthy_count == total_agents:
            status = "healthy"
        else:
            status = "warning"

        return {
            "status": status,
            "healthy_count": healthy_count,
            "degraded_count": degraded_count,
            "unhealthy_count": unhealthy_count,
            "total_count": total_agents,
        }


class AgentPerformanceOptimizer:
    """Optimizes agent performance based on metrics and history"""

    def __init__(self):
        self.optimization_rules = self._load_optimization_rules()

    def _load_optimization_rules(self) -> dict[str, Any]:
        """Load performance optimization rules"""
        return {
            "high_response_time": {
                "threshold": 2.0,  # seconds
                "action": "reduce_complexity",
                "description": "Response time too high, reducing task complexity",
            },
            "low_success_rate": {
                "threshold": 0.8,
                "action": "increase_redundancy",
                "description": "Success rate low, increasing redundancy",
            },
            "high_error_rate": {
                "threshold": 0.1,
                "action": "circuit_breaker",
                "description": "Error rate high, activating circuit breaker",
            },
        }

    def optimize_agent(
        self, agent: ManagedAgent, metrics: AgentMetrics, history: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Optimize performance for a specific agent

        Parameters:
            agent: Agent instance
            metrics: Current metrics
            history: Performance history

        Returns:
            Optimization results
        """
        optimizations = []

        # Check response time
        if metrics.response_time > self.optimization_rules["high_response_time"]["threshold"]:
            optimizations.append(
                {
                    "rule": "high_response_time",
                    "action": self.optimization_rules["high_response_time"]["action"],
                    "description": self.optimization_rules["high_response_time"]["description"],
                }
            )

        # Check success rate
        if metrics.success_rate < self.optimization_rules["low_success_rate"]["threshold"]:
            optimizations.append(
                {
                    "rule": "low_success_rate",
                    "action": self.optimization_rules["low_success_rate"]["action"],
                    "description": self.optimization_rules["low_success_rate"]["description"],
                }
            )

        # Check error rate
        error_rate = metrics.error_count / max(1, len(history))
        if error_rate > self.optimization_rules["high_error_rate"]["threshold"]:
            optimizations.append(
                {
                    "rule": "high_error_rate",
                    "action": self.optimization_rules["high_error_rate"]["action"],
                    "description": self.optimization_rules["high_error_rate"]["description"],
                }
            )

        # Apply optimizations
        for opt in optimizations:
            self._apply_optimization(agent, opt)

        return {
            "status": "success",
            "optimizations_applied": len(optimizations),
            "optimizations": optimizations,
        }

    def _apply_optimization(self, agent: ManagedAgent, optimization: dict[str, Any]) -> None:
        """Apply a specific optimization to an agent"""
        action = optimization["action"]

        try:
            if action == "reduce_complexity":
                # Reduce task complexity (simplified)
                agent.config["max_complexity"] = agent.config.get("max_complexity", 1.0) * 0.8
            elif action == "increase_redundancy":
                # Increase redundancy (simplified)
                agent.config["redundancy_level"] = agent.config.get("redundancy_level", 1) + 1
            elif action == "circuit_breaker":
                # Activate circuit breaker (simplified)
                agent.config["circuit_breaker"] = True

            logger.info("⚡ Applied optimization '%s' to agent %s", action, agent.agent_id)

        except Exception as e:
            logger.error(
                "Failed to apply optimization %s to agent %s: %s",
                action,
                agent.agent_id,
                e,
            )


class AgentLifecycleManager:
    """Manages agent lifecycle events"""

    def __init__(self):
        self.lifecycle_events = []  # List of lifecycle events
        self.max_events = MAX_AGENT_EVENTS

    def record_event(self, event_type: str, agent_id: str, details: dict[str, Any] = None) -> None:
        """Record a lifecycle event"""
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            "agent_id": agent_id,
            "details": details or {},
        }

        self.lifecycle_events.append(event)

        # Keep only recent events
        if len(self.lifecycle_events) > self.max_events:
            self.lifecycle_events = self.lifecycle_events[-self.max_events :]

        logger.info("📝 Lifecycle event: %s for agent %s", event_type, agent_id)

    def get_agent_history(self, agent_id: str) -> list[dict[str, Any]]:
        """Get lifecycle history for an agent"""
        return [event for event in self.lifecycle_events if event["agent_id"] == agent_id]

    def get_recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent lifecycle events"""
        return self.lifecycle_events[-limit:]


# Global agent manager instance
agent_manager = AgentManager()


def get_agent_manager() -> AgentManager:
    """Get the global agent manager instance"""
    return agent_manager

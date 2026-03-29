"""
Coordination calculation service for the UCF (Unified Coordination Framework).
Implements algorithms for calculating coordination metrics, swarm coherence,
and managing coordination routines.
"""

import json
import logging
import statistics
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ..core.redis_client import redis_client
from ..models.coordination import (
    AgentCoordination,
    CoordinationMetrics,
    PerformanceScore,
    RoutineResult,
)

logger = logging.getLogger(__name__)


@dataclass
class CoordinationConfig:
    """Configuration for coordination calculations."""

    base_decay_rate: float = 0.001  # Base decay per minute
    activity_boost: float = 0.05  # Boost per activity
    stress_factor: float = 0.1  # Stress impact
    meditation_boost: float = 0.15  # Meditation effect
    reset_factor: float = 0.5  # Reset effectiveness


class CoordinationCalculator:
    """Service for calculating and managing coordination metrics."""

    def __init__(self) -> None:
        self.config = CoordinationConfig()
        self._cache_ttl = 300  # 5 minutes
        self._history_ttl = 86400  # 24 hours

    async def calculate_agent_coordination(self, agent_id: str) -> AgentCoordination:
        """
        Calculate coordination metrics for a specific agent.

        Args:
            agent_id: The ID of the agent

        Returns:
            AgentCoordination with calculated metrics
        """
        try:
            base_metrics = await self._get_base_metrics(agent_id)

            # Apply time-based decay
            decayed_metrics = await self._apply_time_decay(agent_id, base_metrics)

            # Apply activity-based adjustments
            activity_adjusted = await self._apply_activity_adjustments(agent_id, decayed_metrics)

            # Calculate overall coordination
            overall = self._calculate_overall_coordination(activity_adjusted)

            # Create coordination object
            coordination = AgentCoordination(
                harmony=activity_adjusted["harmony"],
                resilience=activity_adjusted["resilience"],
                throughput=activity_adjusted["throughput"],
                focus=activity_adjusted["focus"],
                friction=activity_adjusted["friction"],
                velocity=activity_adjusted["velocity"],
                overall=overall,
                timestamp=datetime.now(UTC).isoformat(),
            )

            # Cache the result
            await self._cache_coordination(agent_id, coordination)

            # Store in history
            await self._store_coordination_history(agent_id, coordination)

            return coordination

        except Exception as e:
            logger.error("Error calculating coordination for %s: %s", agent_id, e)
            # Return default coordination on error
            return self._get_default_coordination(agent_id)

    async def calculate_swarm_coherence(self, agents_coordination: list[AgentCoordination]) -> float:
        """
        Calculate overall swarm coherence from individual agent coordination.

        Args:
            agents_coordination: List of agent coordination metrics

        Returns:
            Swarm coherence value (0.0-1.0)
        """
        if not agents_coordination:
            return 0.0

        # Calculate average overall coordination
        avg_overall = statistics.mean([ac.overall for ac in agents_coordination])

        # Calculate harmony variance (lower variance = higher coherence)
        harmony_values = [ac.harmony for ac in agents_coordination]
        harmony_variance = statistics.variance(harmony_values) if len(harmony_values) > 1 else 0.0

        # Calculate resilience consensus
        resilience_values = [ac.resilience for ac in agents_coordination]
        resilience_consensus = 1.0 - statistics.variance(resilience_values) if len(resilience_values) > 1 else 1.0

        # Weighted combination
        coherence = avg_overall * 0.4 + (1.0 - harmony_variance) * 0.3 + resilience_consensus * 0.3

        return max(0.0, min(1.0, coherence))

    async def calculate_ucf_state(self, swarm_data) -> dict:
        """
        Calculate UCF (Unified Coordination Field) state.

        Args:
            swarm_data: Swarm coordination data

        Returns:
            UCF state dictionary
        """
        # Calculate coherence percentage
        coherence_pct = swarm_data.swarm_coherence * 100

        # Calculate entropy (inverse of coherence stability)
        entropy = await self._calculate_entropy(swarm_data.agents)

        # Determine coordination level (1-18 scale)
        performance_score = self._map_to_performance_score(swarm_data.swarm_coherence)

        # Get cycle statistics
        cycles_today = await self._get_cycles_completed_today()

        # Determine system status
        status = self._determine_system_status(swarm_data.swarm_coherence, entropy)

        return {
            "coherence": coherence_pct,
            "entropy": entropy,
            "performance_score": performance_score,
            "active_agents": len(swarm_data.agents),
            "cycles_completed_today": cycles_today,
            "last_cycle": await self._get_last_cycle_time(),
            "timestamp": datetime.now(UTC).isoformat(),
            "status": status,
        }

    async def execute_cycle(self, cycle_type: str) -> RoutineResult:
        """
        Execute a coordination cycle to enhance swarm coherence.

        Args:
            cycle_type: Type of cycle to execute

        Returns:
            RoutineResult with execution details
        """
        start_time = datetime.now(UTC)

        try:
            cycle_effects = self._get_cycle_effects(cycle_type)
            if not cycle_effects:
                raise ValueError(f"Unknown cycle type: {cycle_type}")

            # Apply cycle effects to all agents
            effects = await self._apply_cycle_effects(cycle_type, cycle_effects)

            # Record cycle execution
            await self._record_cycle_execution(cycle_type, effects)

            duration = (datetime.now(UTC) - start_time).total_seconds()

            return RoutineResult(
                cycle_type=cycle_type,
                success=True,
                effects=effects,
                duration=duration,
                timestamp=datetime.now(UTC).isoformat(),
            )

        except Exception as e:
            logger.error("Error executing cycle %s: %s", cycle_type, e)
            duration = (datetime.now(UTC) - start_time).total_seconds()

            return RoutineResult(
                cycle_type=cycle_type,
                success=False,
                effects={},
                duration=duration,
                timestamp=datetime.now(UTC).isoformat(),
            )

    async def get_coordination_history(self, agent_id: str, hours: int = 24) -> list[AgentCoordination]:
        """
        Get historical coordination data for an agent.

        Args:
            agent_id: The ID of the agent
            hours: Number of hours to retrieve history for

        Returns:
            List of historical coordination measurements
        """
        try:
            history_key = f"coordination:history:{agent_id}"
            history_data = await redis_client.lrange(history_key, 0, -1)

            # Parse and filter by time range
            cutoff_time = datetime.now(UTC) - timedelta(hours=hours)
            history = []

            for item in history_data:
                # Use json.loads for safe deserialization (never use eval on external data)
                coordination_data = json.loads(item) if isinstance(item, str) else item
                timestamp = datetime.fromisoformat(coordination_data["timestamp"])

                if timestamp >= cutoff_time:
                    history.append(AgentCoordination(**coordination_data))

            # Sort by timestamp
            history.sort(key=lambda x: x.timestamp)

            return history

        except Exception as e:
            logger.error("Error getting coordination history for %s: %s", agent_id, e)
            return []

    def coordination_to_level(self, coordination_value: float) -> PerformanceScore:
        """
        Convert coordination value to coordination level (1-18).

        Args:
            coordination_value: Coordination value (0.0-1.0)

        Returns:
            PerformanceScore object
        """
        # Map 0.0-1.0 to 1-18 scale
        level = int((coordination_value * 17) + 1)
        level = max(1, min(18, level))

        description = self._get_level_description(level)

        return PerformanceScore(
            level=level,
            description=description,
            timestamp=datetime.now(UTC).isoformat(),
        )

    async def get_coordination_metrics(self) -> CoordinationMetrics:
        """
        Get real-time coordination metrics for monitoring.

        Returns:
            CoordinationMetrics object
        """
        try:
            from ..routes.coordination import get_swarm_coordination

            swarm_data = await get_swarm_coordination()

            # Calculate trend (simplified)
            trend = await self._calculate_trend(swarm_data.agents)

            # Calculate volatility
            volatility = await self._calculate_volatility(swarm_data.agents)

            # Set alert thresholds
            alert_thresholds = {
                "coherence_warning": 0.6,
                "coherence_critical": 0.4,
                "volatility_warning": 0.2,
            }

            return CoordinationMetrics(
                current_coherence=swarm_data.swarm_coherence,
                trend=trend,
                volatility=volatility,
                alert_thresholds=alert_thresholds,
                last_update=datetime.now(UTC).isoformat(),
            )

        except Exception as e:
            logger.error("Error getting coordination metrics: %s", e)
            return CoordinationMetrics(
                current_coherence=0.0,
                trend="stable",
                volatility=0.0,
                alert_thresholds={},
                last_update=datetime.now(UTC).isoformat(),
            )

    # Private helper methods

    async def _get_base_metrics(self, agent_id: str) -> dict[str, float]:
        """Get base coordination metrics for an agent.

        Checks Redis for persisted metrics first (from previous calculations),
        then falls back to sensible defaults for new agents.
        """
        # Try to load persisted metrics from Redis
        cache_key = f"coordination:base:{agent_id}"
        cached = await redis_client.get(cache_key)
        if cached:
            try:
                import ast

                return ast.literal_eval(cached)
            except (ValueError, SyntaxError) as e:
                logger.debug("Failed to parse cached coordination state: %s", e)

        # Try loading from coordination history (most recent snapshot)
        history_key = f"coordination:history:{agent_id}"
        history = await redis_client.lrange(history_key, 0, 0)
        if history:
            try:
                latest = json.loads(history[0])
                return {
                    "harmony": latest.get("harmony", 0.65),
                    "resilience": latest.get("resilience", 0.65),
                    "throughput": latest.get("throughput", 0.65),
                    "focus": latest.get("focus", 0.65),
                    "friction": latest.get("friction", 0.35),
                    "velocity": latest.get("velocity", 0.65),
                }
            except (json.JSONDecodeError, TypeError) as e:
                logger.debug("Failed to parse coordination history for %s: %s", agent_id, e)

        # Default values for new agents with no history
        base_metrics = {
            "harmony": 0.65,
            "resilience": 0.65,
            "throughput": 0.65,
            "focus": 0.65,
            "friction": 0.35,  # Lower is better
            "velocity": 0.65,
        }

        # Cache base metrics
        await redis_client.setex(cache_key, self._cache_ttl, str(base_metrics))

        return base_metrics

    async def _apply_time_decay(self, agent_id: str, metrics: dict[str, float]) -> dict[str, float]:
        """Apply time-based decay to coordination metrics."""
        # Get last update time
        last_update_key = f"coordination:last_update:{agent_id}"
        last_update_str = await redis_client.get(last_update_key)

        if last_update_str:
            last_update = datetime.fromisoformat(last_update_str)
            minutes_elapsed = (datetime.now(UTC) - last_update).total_seconds() / 60

            # Apply decay
            decay_factor = 1.0 - (self.config.base_decay_rate * minutes_elapsed)

            for dimension in metrics:
                if dimension != "friction":  # friction decays differently
                    metrics[dimension] *= decay_factor
                else:
                    metrics[dimension] *= 1.0 + (self.config.base_decay_rate * minutes_elapsed)

        # Update last update time
        await redis_client.setex(last_update_key, self._cache_ttl, datetime.now(UTC).isoformat())

        return metrics

    async def _apply_activity_adjustments(self, agent_id: str, metrics: dict[str, float]) -> dict[str, float]:
        """Apply activity-based adjustments to coordination metrics."""
        # Get activity count
        activity_key = f"activity:count:{agent_id}"
        activity_count = await redis_client.get(activity_key)
        activity_count = int(activity_count) if activity_count else 0

        # Apply activity boost
        if activity_count > 0:
            for dimension in metrics:
                if dimension != "friction":
                    metrics[dimension] += self.config.activity_boost * min(activity_count, 10)
                else:
                    metrics[dimension] -= self.config.activity_boost * min(activity_count, 10)

        # Reset activity count
        await redis_client.delete(activity_key)

        # Ensure values stay within bounds
        for dimension in metrics:
            if dimension == "friction":
                metrics[dimension] = max(0.0, min(1.0, metrics[dimension]))
            else:
                metrics[dimension] = max(0.0, min(1.0, metrics[dimension]))

        return metrics

    def _calculate_overall_coordination(self, metrics: dict[str, float]) -> float:
        """Calculate overall coordination from individual metrics."""
        # Weighted average with special handling for friction
        weights = {
            "harmony": 0.2,
            "resilience": 0.2,
            "throughput": 0.2,
            "focus": 0.2,
            "velocity": 0.15,
            "friction": 0.05,  # Lower friction is better
        }

        overall = 0.0
        for dimension, value in metrics.items():
            if dimension == "friction":
                # Invert friction (lower is better)
                overall += (1.0 - value) * weights[dimension]
            else:
                overall += value * weights[dimension]

        return max(0.0, min(1.0, overall))

    async def _cache_coordination(self, agent_id: str, coordination: AgentCoordination):
        """Cache coordination data."""
        cache_key = f"coordination:current:{agent_id}"
        await redis_client.setex(cache_key, self._cache_ttl, coordination.json())

    async def _store_coordination_history(self, agent_id: str, coordination: AgentCoordination):
        """Store coordination data in history."""
        history_key = f"coordination:history:{agent_id}"
        await redis_client.lpush(history_key, coordination.json())
        await redis_client.expire(history_key, self._history_ttl)
        # Keep only last 100 entries
        await redis_client.ltrim(history_key, 0, 99)

    def _get_default_coordination(self, agent_id: str) -> AgentCoordination:
        """Get default coordination values for an agent."""
        return AgentCoordination(
            harmony=0.5,
            resilience=0.5,
            throughput=0.5,
            focus=0.5,
            friction=0.5,
            velocity=0.5,
            overall=0.5,
            timestamp=datetime.now(UTC).isoformat(),
        )

    async def _calculate_entropy(self, agents: dict[str, AgentCoordination]) -> float:
        """Calculate system entropy from agent coordination."""
        if not agents:
            return 1.0

        # Calculate variance across all dimensions
        all_values = []
        for agent in agents.values():
            all_values.extend(
                [
                    agent.harmony,
                    agent.resilience,
                    agent.throughput,
                    agent.focus,
                    agent.velocity,
                    (1.0 - agent.friction),  # Invert friction
                ]
            )

        if len(all_values) < 2:
            return 0.5

        variance = statistics.variance(all_values)
        # Normalize variance to 0-1 range
        entropy = min(1.0, variance * 2.0)

        return entropy

    def _map_to_performance_score(self, coherence: float) -> int:
        """Map coherence value to coordination level (1-18)."""
        level = int((coherence * 17) + 1)
        return max(1, min(18, level))

    def _determine_system_status(self, coherence: float, entropy: float) -> str:
        """Determine system status based on coherence and entropy."""
        if coherence >= 0.8 and entropy <= 0.3:
            return "optimal"
        elif coherence >= 0.6 and entropy <= 0.5:
            return "stable"
        elif coherence >= 0.4:
            return "warning"
        else:
            return "critical"

    def _get_cycle_effects(self, cycle_type: str) -> dict[str, float] | None:
        """Get effects for a specific cycle type."""
        effects = {
            "meditation": {
                "harmony": 0.1,
                "resilience": 0.05,
                "throughput": 0.08,
                "focus": 0.05,
                "friction": -0.15,  # Reduce friction
                "velocity": 0.05,
            },
            "harmonization": {
                "harmony": 0.15,
                "resilience": 0.1,
                "throughput": 0.05,
                "focus": 0.05,
                "friction": -0.1,
                "velocity": 0.05,
            },
            "reset": {
                "harmony": 0.2,
                "resilience": 0.2,
                "throughput": 0.2,
                "focus": 0.2,
                "friction": -0.3,
                "velocity": 0.2,
            },
            "boost": {
                "harmony": 0.05,
                "resilience": 0.05,
                "throughput": 0.15,
                "focus": 0.1,
                "friction": -0.05,
                "velocity": 0.1,
            },
        }
        return effects.get(cycle_type)

    async def _apply_cycle_effects(self, cycle_type: str, effects: dict[str, float]) -> dict[str, float]:
        """Apply cycle effects to all agents."""
        # Get all active agents

        swarm_data = await self.get_swarm_coordination()

        total_effects = dict.fromkeys(effects.keys(), 0.0)

        for agent_id, coordination in swarm_data.agents.items():
            # Apply effects to each agent
            for dimension, effect in effects.items():
                current_value = getattr(coordination, dimension)
                new_value = current_value + effect

                # Ensure values stay within bounds
                if dimension == "friction":
                    new_value = max(0.0, min(1.0, new_value))
                else:
                    new_value = max(0.0, min(1.0, new_value))

                setattr(coordination, dimension, new_value)
                total_effects[dimension] += effect

        # Calculate average effects
        agent_count = len(swarm_data.agents)
        avg_effects = {k: v / agent_count for k, v in total_effects.items()}

        return avg_effects

    async def _record_cycle_execution(self, cycle_type: str, effects: dict[str, float]):
        """Record cycle execution in Redis."""
        cycle_key = f"routines:executed:{datetime.now(UTC).strftime('%Y-%m-%d')}"
        cycle_data = {
            "type": cycle_type,
            "effects": effects,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        await redis_client.lpush(cycle_key, str(cycle_data))
        await redis_client.expire(cycle_key, 86400 * 7)  # Keep for 7 days

    async def _get_cycles_completed_today(self) -> int:
        """Get number of routines completed today."""
        cycle_key = f"routines:executed:{datetime.now(UTC).strftime('%Y-%m-%d')}"
        count = await redis_client.llen(cycle_key)
        return count

    async def _get_last_cycle_time(self) -> str | None:
        """Get timestamp of last cycle execution."""
        import json

        cycle_key = f"routines:executed:{datetime.now(UTC).strftime('%Y-%m-%d')}"
        last_cycle = await redis_client.lindex(cycle_key, 0)
        if last_cycle:
            try:
                cycle_data = json.loads(last_cycle) if isinstance(last_cycle, str) else last_cycle
                return cycle_data.get("timestamp")
            except (json.JSONDecodeError, TypeError):
                return None
        return None

    async def _calculate_trend(self, agents: dict[str, AgentCoordination]) -> str:
        """Calculate coordination trend."""
        # Simplified trend calculation
        # In a real implementation, this would compare with historical data
        avg_coherence = sum(agent.overall for agent in agents.values()) / len(agents)

        if avg_coherence > 0.7:
            return "increasing"
        elif avg_coherence < 0.5:
            return "decreasing"
        else:
            return "stable"

    async def _calculate_volatility(self, agents: dict[str, AgentCoordination]) -> float:
        """Calculate coordination volatility."""
        if len(agents) < 2:
            return 0.0

        coherence_values = [agent.overall for agent in agents.values()]
        return statistics.stdev(coherence_values)

    def _get_level_description(self, level: int) -> str:
        """Get description for coordination level."""
        descriptions = {
            1: "Basic awareness",
            2: "Simple recognition",
            3: "Pattern recognition",
            4: "Basic learning",
            5: "Adaptive behavior",
            6: "Complex problem solving",
            7: "Abstract thinking",
            8: "Strategic planning",
            9: "Creative problem solving",
            10: "Advanced reasoning",
            11: "Meta-cognition",
            12: "Self-awareness",
            13: "Conscious reflection",
            14: "Deep understanding",
            15: "Wisdom integration",
            16: "Universal awareness",
            17: "Transcendent coordination",
            18: "Omniscient awareness",
        }
        return descriptions.get(level, "Unknown level")

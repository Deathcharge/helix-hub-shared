"""
Coordination Service - Central service for managing coordination state and metrics.

This service provides the main interface for coordination operations and integrates
with the UCF (Universal Coordination Framework) calculator.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.coordination import CoordinationSnapshot
from ..services.ucf_calculator import UCFCalculator
from .metric_calculator import CoordinationCalculator

logger = logging.getLogger(__name__)


class CoordinationState(Enum):
    """Coordination state classifications"""

    UNCONSCIOUS = "unconscious"
    DROWSY = "drowsy"
    AWAKE = "awake"
    AWARE = "aware"
    CONSCIOUS = "conscious"
    ENLIGHTENED = "enlightened"
    TRANSCENDENT = "transcendent"


@dataclass
class CoordinationMetrics:
    """Coordination metrics data structure"""

    performance_score: float
    harmony: float
    resilience: float
    throughput: float
    focus: float
    friction: float
    timestamp: datetime
    state: CoordinationState
    agent_id: str | None = None


@dataclass
class CoordinationHealth:
    """Coordination health assessment"""

    overall_health: float
    harmony_score: float
    resilience_score: float
    energy_level: float
    clarity_score: float
    entropy_level: float
    health_status: str


class CoordinationService:
    """Main coordination service for managing coordination state and metrics"""

    def __init__(
        self,
        db_session: AsyncSession,
        ucf_calculator: UCFCalculator,
        coordination_calculator: CoordinationCalculator | None = None,
    ):
        """
        Initialize coordination service

        Args:
            db_session: Database session for persistence
            ucf_calculator: UCF calculator for core metrics
            coordination_calculator: Optional enhanced calculator
        """
        self.db = db_session
        self.ucf_calculator = ucf_calculator
        self.coordination_calculator = coordination_calculator or CoordinationCalculator()

        # Service state
        self._current_state: CoordinationMetrics | None = None
        self._state_lock = asyncio.Lock()
        self._update_interval = 30  # seconds
        self._background_task: asyncio.Task | None = None

        # Health thresholds
        self.health_thresholds = {"optimal": 0.8, "good": 0.6, "fair": 0.4, "poor": 0.2}

    async def start(self):
        """Start background coordination monitoring"""
        if self._background_task is None:
            self._background_task = asyncio.create_task(self._monitor_coordination())
            logger.info("Coordination service started")

    async def stop(self):
        """Stop background coordination monitoring"""
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
            self._background_task = None
            logger.info("Coordination service stopped")

    async def get_current_state(self) -> dict[str, Any]:
        """
        Get current coordination state

        Returns:
            Dictionary containing current coordination metrics and metadata
        """
        async with self._state_lock:
            if self._current_state is None:
                await self._update_coordination_state()

            return {
                "performance_score": self._current_state.performance_score,
                "ucf_metrics": {
                    "harmony": self._current_state.harmony,
                    "resilience": self._current_state.resilience,
                    "throughput": self._current_state.throughput,
                    "focus": self._current_state.focus,
                    "friction": self._current_state.friction,
                },
                "state": self._current_state.state.value,
                "timestamp": self._current_state.timestamp.isoformat(),
                "agent_id": self._current_state.agent_id,
                "health": await self._assess_health(self._current_state),
            }

    async def get_coordination_metrics(self) -> CoordinationMetrics:
        """
        Get detailed coordination metrics

        Returns:
            CoordinationMetrics object with all metrics
        """
        async with self._state_lock:
            if self._current_state is None:
                await self._update_coordination_state()

            return self._current_state

    async def update_coordination_state(self, metrics_override: dict[str, float] | None = None) -> dict[str, Any]:
        """
        Manually update coordination state

        Args:
            metrics_override: Optional metrics to override calculated values

        Returns:
            Updated coordination state
        """
        async with self._state_lock:
            await self._update_coordination_state(metrics_override)
            return await self.get_current_state()

    async def get_coordination_history(self, minutes: int = 60, agent_id: str | None = None) -> list[dict[str, Any]]:
        """
        Get coordination history

        Args:
            minutes: Number of minutes of history to retrieve
            agent_id: Optional agent ID to filter by

        Returns:
            List of historical coordination states
        """
        try:
            query = (
                select(CoordinationSnapshot)
                .where(CoordinationSnapshot.timestamp >= datetime.now(UTC) - timedelta(minutes=minutes))
                .order_by(CoordinationSnapshot.timestamp.desc())
            )

            if agent_id:
                query = query.where(CoordinationSnapshot.agent_id == agent_id)

            result = await self.db.execute(query)
            snapshots = result.scalars().all()

            return [
                {
                    "timestamp": snapshot.timestamp.isoformat(),
                    "performance_score": snapshot.performance_score,
                    "ucf_metrics": {
                        "harmony": snapshot.harmony,
                        "resilience": snapshot.resilience,
                        "throughput": snapshot.throughput,
                        "focus": snapshot.focus,
                        "friction": snapshot.friction,
                    },
                    "agent_id": snapshot.agent_id,
                    "metadata": snapshot.metadata,
                }
                for snapshot in snapshots
            ]

        except (ValueError, TypeError, KeyError) as e:
            logger.debug("Coordination history validation error: %s", e)
            return []
        except Exception as e:
            logger.error("Failed to get coordination history: %s", e)
            return []

    async def get_coordination_health(self) -> dict[str, Any]:
        """
        Get coordination health assessment

        Returns:
            Health assessment with scores and recommendations
        """
        current_state = await self.get_coordination_metrics()
        health = await self._assess_health(current_state)

        return {
            "health": health,
            "recommendations": await self._generate_health_recommendations(health),
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def set_coordination_target(self, target_level: float, duration_minutes: int = 60) -> dict[str, Any]:
        """
        Set coordination target level

        Args:
            target_level: Target coordination level (0.0-10.0)
            duration_minutes: Duration in minutes

        Returns:
            Target setting confirmation
        """
        try:
            if not 0.0 <= target_level <= 10.0:
                raise ValueError("Target level must be between 0.0 and 10.0")

            # Store target in metadata
            current_state = await self.get_coordination_metrics()
            current_state.metadata = current_state.metadata or {}
            current_state.metadata["target_coordination"] = {
                "level": target_level,
                "set_at": datetime.now(UTC).isoformat(),
                "duration_minutes": duration_minutes,
            }

            await self._save_coordination_state(current_state)

            return {
                "success": True,
                "target_level": target_level,
                "duration_minutes": duration_minutes,
                "message": f"Coordination target set to {target_level}",
            }

        except Exception as e:
            logger.error("Failed to set coordination target: %s", e)
            return {"success": False, "error": "Failed to set performance target"}

    async def get_coordination_alerts(self) -> list[dict[str, Any]]:
        """
        Get coordination alerts and warnings

        Returns:
            List of active alerts
        """
        alerts = []
        current_state = await self.get_coordination_metrics()

        # Check for low coordination
        if current_state.performance_score < 3.0:
            alerts.append(
                {
                    "type": "low_coordination",
                    "severity": "high",
                    "message": f"Coordination level critically low: {current_state.performance_score:.1f}",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )

        # Check for high entropy
        if current_state.friction > 0.7:
            alerts.append(
                {
                    "type": "high_entropy",
                    "severity": "medium",
                    "message": f"High system entropy detected: {current_state.friction:.2f}",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )

        # Check for low harmony
        if current_state.harmony < 0.4:
            alerts.append(
                {
                    "type": "low_harmony",
                    "severity": "medium",
                    "message": f"Low harmony detected: {current_state.harmony:.2f}",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )

        return alerts

    async def trigger_coordination_cycle(self, cycle_type: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """
        Trigger a coordination cycle

        Args:
            cycle_type: Type of cycle to perform
            parameters: Cycle-specific parameters

        Returns:
            Cycle execution result
        """
        try:
            # For now, simulate cycle effects
            cycle_effects = {
                "meditation": {"performance_score": 0.5, "harmony": 0.1},
                "yoga": {"throughput": 0.2, "focus": 0.1},
                "breathing": {"resilience": 0.1, "friction": -0.1},
            }

            if cycle_type not in cycle_effects:
                return {
                    "success": False,
                    "error": f"Unknown cycle type: {cycle_type}",
                }

            # Apply cycle effects
            effects = cycle_effects[cycle_type]
            current_state = await self.get_coordination_metrics()

            for metric, change in effects.items():
                if hasattr(current_state, metric):
                    current_value = getattr(current_state, metric)
                    new_value = max(0.0, min(10.0, current_value + change))
                    setattr(current_state, metric, new_value)

            # Recalculate coordination level
            current_state.performance_score = self._calculate_performance_score(current_state)
            current_state.timestamp = datetime.now(UTC)

            await self._save_coordination_state(current_state)

            return {
                "success": True,
                "cycle_type": cycle_type,
                "effects": effects,
                "new_state": await self.get_current_state(),
            }

        except Exception as e:
            logger.error("Failed to trigger coordination cycle: %s", e)
            return {"success": False, "error": "Failed to trigger performance cycle"}

    async def _update_coordination_state(self, metrics_override: dict[str, float] | None = None):
        """Update internal coordination state"""
        try:
            ucf_state = self.ucf_calculator.get_state()

            # Apply overrides if provided
            if metrics_override:
                for key, value in metrics_override.items():
                    if key in ucf_state:
                        ucf_state[key] = value

            # Calculate coordination level
            performance_score = self._calculate_performance_score_from_ucf(ucf_state)

            # Determine coordination state
            state = self._classify_coordination_state(performance_score)

            # Create metrics object
            self._current_state = CoordinationMetrics(
                performance_score=performance_score,
                harmony=ucf_state.get("harmony", 0.5),
                resilience=ucf_state.get("resilience", 1.0),
                throughput=ucf_state.get("throughput", 0.5),
                focus=ucf_state.get("focus", 0.5),
                friction=ucf_state.get("friction", 0.2),
                timestamp=datetime.now(UTC),
                state=state,
                agent_id=None,  # Would be set by agent coordination system
            )

            # Save to database
            await self._save_coordination_state(self._current_state)

            logger.debug("Updated coordination state: %.2f (%s)", performance_score, state.value)

        except Exception as e:
            logger.error("Failed to update coordination state: %s", e)
            # Fallback to default state
            self._current_state = CoordinationMetrics(
                performance_score=5.0,
                harmony=0.5,
                resilience=1.0,
                throughput=0.5,
                focus=0.5,
                friction=0.2,
                timestamp=datetime.now(UTC),
                state=CoordinationState.AWAKE,
                agent_id=None,
            )

    async def _monitor_coordination(self):
        """Background task to monitor coordination state"""
        while True:
            try:
                await asyncio.sleep(self._update_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in coordination monitoring: %s", e)
                await asyncio.sleep(self._update_interval)

    def _calculate_performance_score_from_ucf(self, ucf_state: dict[str, float]) -> float:
        """Calculate coordination level from UCF metrics"""
        try:
            performance_score = (
                ucf_state.get("performance_score", 5.0) * 0.3
                + ucf_state.get("harmony", 0.5) * 10.0 * 0.2
                + ucf_state.get("resilience", 1.0) * 5.0 * 0.2
                + ucf_state.get("throughput", 0.5) * 10.0 * 0.15
                + ucf_state.get("focus", 0.5) * 10.0 * 0.1
                + (1.0 - ucf_state.get("friction", 0.2)) * 10.0 * 0.05
            )

            return max(0.0, min(10.0, performance_score))

        except Exception as e:
            logger.error("Error calculating coordination level: %s", e)
            return 5.0

    def _classify_coordination_state(self, performance_score: float) -> CoordinationState:
        """Classify coordination state based on level"""
        if performance_score < 1.0:
            return CoordinationState.UNCONSCIOUS
        elif performance_score < 3.0:
            return CoordinationState.DROWSY
        elif performance_score < 5.0:
            return CoordinationState.AWAKE
        elif performance_score < 7.0:
            return CoordinationState.AWARE
        elif performance_score < 9.0:
            return CoordinationState.CONSIOUS
        elif performance_score < 10.0:
            return CoordinationState.ENLIGHTENED
        else:
            return CoordinationState.TRANSCENDENT

    async def _assess_health(self, metrics: CoordinationMetrics) -> CoordinationHealth:
        """Assess overall coordination health"""
        # Calculate individual health scores
        harmony_score = metrics.harmony
        resilience_score = min(1.0, metrics.resilience / 2.0)  # Normalize to 0-1
        energy_level = metrics.throughput
        clarity_score = metrics.focus
        entropy_level = metrics.friction

        # Calculate overall health (weighted average)
        overall_health = (
            harmony_score * 0.25
            + resilience_score * 0.25
            + energy_level * 0.20
            + clarity_score * 0.20
            + (1.0 - entropy_level) * 0.10
        )

        # Determine health status
        if overall_health >= self.health_thresholds["optimal"]:
            health_status = "optimal"
        elif overall_health >= self.health_thresholds["good"]:
            health_status = "good"
        elif overall_health >= self.health_thresholds["fair"]:
            health_status = "fair"
        else:
            health_status = "poor"

        return CoordinationHealth(
            overall_health=overall_health,
            harmony_score=harmony_score,
            resilience_score=resilience_score,
            energy_level=energy_level,
            clarity_score=clarity_score,
            entropy_level=entropy_level,
            health_status=health_status,
        )

    async def _generate_health_recommendations(self, health: CoordinationHealth) -> list[str]:
        """Generate health recommendations based on current state"""
        recommendations = []

        if health.harmony_score < 0.5:
            recommendations.append("Practice harmony-enhancing routines")

        if health.resilience_score < 0.5:
            recommendations.append("Focus on resilience-building exercises")

        if health.energy_level < 0.5:
            recommendations.append("Engage in throughput-boosting activities")

        if health.clarity_score < 0.5:
            recommendations.append("Perform focus-clearing practices")

        if health.entropy_level > 0.5:
            recommendations.append("Reduce system entropy through friction management")

        if not recommendations:
            recommendations.append("Coordination health is optimal")

        return recommendations

    async def _save_coordination_state(self, metrics: CoordinationMetrics):
        """Save coordination state to database"""
        try:
            snapshot = CoordinationSnapshot(
                performance_score=metrics.performance_score,
                harmony=metrics.harmony,
                resilience=metrics.resilience,
                throughput=metrics.throughput,
                focus=metrics.focus,
                friction=metrics.friction,
                agent_id=metrics.agent_id,
                metadata={
                    "state": metrics.state.value,
                    "timestamp": metrics.timestamp.isoformat(),
                },
            )

            self.db.add(snapshot)
            await self.db.commit()

        except Exception as e:
            logger.error("Failed to save coordination state: %s", e)
            await self.db.rollback()

    def _calculate_performance_score(self, metrics: CoordinationMetrics) -> float:
        """Calculate coordination level from metrics"""
        return (
            metrics.harmony * 10.0 * 0.3
            + min(1.0, metrics.resilience / 2.0) * 10.0 * 0.25
            + metrics.throughput * 10.0 * 0.2
            + metrics.focus * 10.0 * 0.15
            + (1.0 - metrics.friction) * 10.0 * 0.1
        )

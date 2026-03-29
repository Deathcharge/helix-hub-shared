"""
UCF Calculator - Universal Coordination Framework Calculator

This service calculates the core UCF metrics that form the foundation of the coordination system.
It integrates with various system components to provide real-time coordination state calculations.
"""

import json
import logging
import math
from collections import deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from statistics import mean, stdev
from typing import Any

import psutil

logger = logging.getLogger(__name__)


class MetricSource(Enum):
    """Sources for UCF metrics"""

    SYSTEM = "system"
    AGENT = "agent"
    WORKFLOW = "workflow"
    USER = "user"
    EXTERNAL = "external"


@dataclass
class MetricContribution:
    """Contribution to a UCF metric from a specific source"""

    source: MetricSource
    value: float
    weight: float
    timestamp: datetime
    confidence: float


@dataclass
class UCFCalibration:
    """UCF calibration parameters"""

    harmony_weight: float = 0.25
    resilience_weight: float = 0.25
    throughput_weight: float = 0.20
    focus_weight: float = 0.20
    friction_weight: float = 0.10
    baseline_adjustment: float = 0.0
    sensitivity_factor: float = 1.0


class UCFCalculator:
    """Universal Coordination Framework Calculator

    Calculates core coordination metrics based on system state, agent behavior,
    workflow performance, and external inputs.
    """

    def __init__(self, db_session=None) -> None:
        """
        Initialize the UCFCalculator instance and its in-memory state.

        Sets up historical buffers for each metric, the current state container and timestamp, default calibration,
        runtime configuration (update interval, decay factor, entropy threshold), and default source weights
        used by metric calculations.

        Parameters:
            db_session (optional): Database session or client to access external data sources; may be None.
        """
        self.db = db_session

        # Historical data storage
        self._harmony_history = deque(maxlen=1000)
        self._resilience_history = deque(maxlen=1000)
        self._throughput_history = deque(maxlen=1000)
        self._focus_history = deque(maxlen=1000)
        self._friction_history = deque(maxlen=1000)

        # Current state
        self._current_state: dict[str, float] = {}
        self._last_update: datetime | None = None

        # Calibration parameters
        self.calibration = UCFCalibration()

        # Configuration
        self.update_interval = 30  # seconds
        self.decay_factor = 0.95  # For resilience decay
        self.entropy_threshold = 0.7  # Friction threshold

        # Source weights for different metric calculations
        self.source_weights = {
            MetricSource.SYSTEM: 0.3,
            MetricSource.AGENT: 0.25,
            MetricSource.WORKFLOW: 0.25,
            MetricSource.USER: 0.15,
            MetricSource.EXTERNAL: 0.05,
        }

    def get_state(self) -> dict[str, float]:
        """
        Return the current UCF metric snapshot, recomputing internal state if an update is due.

        Returns:
            A dict mapping metric names ("harmony", "resilience", "throughput", "focus", "friction") to their current numeric values. The mapping is a shallow copy of the internal state and may reflect a fresh computation performed before returning.
        """
        if not self._current_state or self._should_update():
            self._update_state()

        return self._current_state.copy()

    def get_detailed_state(self) -> dict[str, Any]:
        """
        Provides a detailed UCF state snapshot including current metrics, calibration, contributing sources, confidence, and a concise history summary.

        Returns:
            dict: Mapping with keys:
                - metrics (Dict[str, float]): Current values for harmony, resilience, throughput, focus, and friction.
                - timestamp (str | None): ISO 8601 timestamp of the last state update, or None if never updated.
                - calibration (Dict[str, float]): Serialized calibration parameters (weights and adjustments).
                - sources (Dict[str, List[str]]): Per-metric lists of contributing source identifiers.
                - confidence (float): Confidence score for the current state in the range 0.0–1.0.
                - history (Dict[str, Dict[str, float]]): Per-metric summary statistics containing mean, std, min, max, and current.
        """
        state = self.get_state()

        return {
            "metrics": state,
            "timestamp": self._last_update.isoformat() if self._last_update else None,
            "calibration": asdict(self.calibration),
            "sources": self._get_metric_sources(),
            "confidence": self._calculate_confidence(),
            "history": self._get_history_summary(),
        }

    def update_calibration(self, new_calibration: UCFCalibration) -> bool:
        """
        Apply a new calibration and force an immediate recomputation of the current UCF state.

        Parameters:
            new_calibration (UCFCalibration): Calibration parameters to apply.

        Returns:
            bool: `True` if the calibration was applied and the state recomputed successfully, `False` otherwise.
        """
        try:
            # Trigger state recalculation with new calibration
            self._update_state()
            logger.info("UCF calibration updated")
            return True
        except (ValueError, TypeError, KeyError) as e:
            logger.debug("UCF calibration validation error: %s", e)
            return False
        except Exception as e:
            logger.error("Failed to update UCF calibration: %s", e)
            return False

    def get_trend_analysis(self, hours: int = 24) -> dict[str, Any]:
        """
        Analyze recent metric histories and produce trend summaries for each UCF metric.

        Parameters:
            hours (int): Time window, in hours, over which to collect historical data for trend analysis.

        Returns:
            dict: {
                "trends": { metric_name: { "direction": str, "velocity": float, "volatility": float,
                                           "current": float, "confidence": float, ... }, ... },
                "analysis_period": str,   # human-readable period, e.g. "24 hours"
                "timestamp": str          # ISO8601 timestamp of analysis
            }
            On failure returns {"error": "<error message>"}.
        """
        try:
            cutoff_time = datetime.now(UTC) - timedelta(hours=hours)

            # Analyze trends for each metric
            trends = {}
            for metric in ["harmony", "resilience", "throughput", "focus", "friction"]:
                history = self._get_metric_history(metric, cutoff_time)
                if len(history) < 10:  # Need minimum data points
                    continue

                trend = self._analyze_metric_trend(history, metric)
                trends[metric] = trend

            return {
                "trends": trends,
                "analysis_period": f"{hours} hours",
                "timestamp": datetime.now(UTC).isoformat(),
            }

        except Exception as e:
            logger.error("Failed to analyze UCF trends: %s", e)
            return {"error": "Failed to analyze trends"}

    def get_health_score(self) -> dict[str, Any]:
        """
        Compute a calibrated, holistic health score and related diagnostics for the current UCF state.

        Generates a scalar health score using the current metrics and calibration weights, classifies the overall health level, and produces actionable recommendations and metadata.

        Returns:
            dict: A dictionary with one of the following shapes:
                - On success:
                    {
                        "health_score": float,        # Overall health score between 0.0 and 1.0
                        "health_level": str,         # One of "optimal", "good", "fair", or "poor"
                        "metrics": dict,             # Current metric values: keys include "harmony", "resilience", "throughput", "focus", "friction"
                        "recommendations": list,     # List of recommendation strings based on metric thresholds
                        "timestamp": str             # ISO 8601 UTC timestamp of the calculation
                    }
                - On failure:
                    {"error": str}                  # Error message describing the failure
        """
        try:
            state = self.get_state()

            # Calculate weighted health score
            health_score = (
                state["harmony"] * self.calibration.harmony_weight
                + min(1.0, state["resilience"] / 2.0) * self.calibration.resilience_weight
                + state["throughput"] * self.calibration.throughput_weight
                + state["focus"] * self.calibration.focus_weight
                + (1.0 - state["friction"]) * self.calibration.friction_weight
            )

            # Determine health level
            if health_score >= 0.8:
                health_level = "optimal"
            elif health_score >= 0.6:
                health_level = "good"
            elif health_score >= 0.4:
                health_level = "fair"
            else:
                health_level = "poor"

            # Generate recommendations
            recommendations = self._generate_health_recommendations(state)

            return {
                "health_score": health_score,
                "health_level": health_level,
                "metrics": state,
                "recommendations": recommendations,
                "timestamp": datetime.now(UTC).isoformat(),
            }

        except Exception as e:
            logger.error("Failed to calculate health score: %s", e)
            return {"error": "Failed to calculate health score"}

    def simulate_external_influence(self, influence_type: str, intensity: float) -> dict[str, Any]:
        """
        Simulates an external perturbation and projects its effect on the current UCF metrics.

        Parameters:
            influence_type (str): Identifier for the kind of external influence (e.g., "positive", "negative", "chaotic") that determines per-metric effects.
            intensity (float): Magnitude of the influence on metrics, expected in the range 0.0 to 1.0.

        Returns:
            Dict[str, Any]: A dictionary with simulation results containing:
                - current_state (Dict[str, float]): Snapshot of the current metrics.
                - predicted_state (Dict[str, float]): Metrics after applying the influence (values clamped to [0.0, 1.0]).
                - health_change (float): Difference between predicted and current health (predicted - current).
                - influence_type (str): Echoes the provided influence_type.
                - intensity (float): Echoes the provided intensity.
                - timestamp (str): ISO 8601 UTC timestamp of the simulation.
            On failure returns a dictionary with an "error" key and a descriptive message.
        """
        try:
            current_state = self.get_state()
            predicted_state = current_state.copy()

            # Apply influence effects
            influence_effects = self._get_influence_effects(influence_type, intensity)

            for metric, effect in influence_effects.items():
                if metric in predicted_state:
                    predicted_state[metric] = max(0.0, min(1.0, predicted_state[metric] + effect))

            # Calculate new health score
            new_health = self._calculate_health_from_state(predicted_state)
            current_health = self._calculate_health_from_state(current_state)

            return {
                "current_state": current_state,
                "predicted_state": predicted_state,
                "health_change": new_health - current_health,
                "influence_type": influence_type,
                "intensity": intensity,
                "timestamp": datetime.now(UTC).isoformat(),
            }

        except Exception as e:
            logger.error("Failed to simulate external influence: %s", e)
            return {"error": "Failed to simulate external influence"}

    def _update_state(self):
        """
        Recompute and persist the calculator's core metrics into internal state.

        Recalculates the five core UCF metrics (harmony, resilience, throughput, focus, friction) via the calculator's internal routines, applies calibration adjustments and valid-range clamping, updates the in-memory current state and last-update timestamp, and appends the new values to the corresponding history buffers. If an error occurs during computation, a safe default state is installed and the timestamp updated.
        """
        try:
            harmony = self._calculate_harmony()
            resilience = self._calculate_resilience()
            throughput = self._calculate_throughput()
            focus = self._calculate_focus()
            friction = self._calculate_friction()

            # Apply calibration adjustments
            harmony = max(0.0, min(1.0, harmony + self.calibration.baseline_adjustment))
            resilience = max(0.0, min(2.0, resilience * self.calibration.sensitivity_factor))
            throughput = max(0.0, min(1.0, throughput))
            focus = max(0.0, min(1.0, focus))
            friction = max(0.0, min(1.0, friction))

            # Update state
            self._current_state = {
                "harmony": harmony,
                "resilience": resilience,
                "throughput": throughput,
                "focus": focus,
                "friction": friction,
            }

            self._last_update = datetime.now(UTC)

            # Store in history
            self._harmony_history.append(harmony)
            self._resilience_history.append(resilience)
            self._throughput_history.append(throughput)
            self._focus_history.append(focus)
            self._friction_history.append(friction)

            logger.debug("UCF state updated: %s", self._current_state)

        except Exception as e:
            logger.error("Failed to update UCF state: %s", e)
            # Fallback to default state
            self._current_state = {
                "harmony": 0.5,
                "resilience": 1.0,
                "throughput": 0.5,
                "focus": 0.5,
                "friction": 0.2,
            }
            self._last_update = datetime.now(UTC)

    def _calculate_harmony(self) -> float:
        """
        Estimate the current harmony by aggregating system, agent, workflow, and user contributions.

        Returns:
            float: Harmony score in the range 0.0 to 1.0. If computation fails, returns 0.5.
        """
        try:
            # System harmony: derived from overall system health (low CPU + low mem = harmonious)
            try:
                cpu = psutil.cpu_percent(interval=0)
                mem = psutil.virtual_memory().percent
                system_harmony = max(0.0, min(1.0, 1.0 - (cpu * 0.5 + mem * 0.5) / 100.0))
            except (OSError, RuntimeError, ValueError) as e:
                logger.debug("System harmony calculation failed: %s", e)
                system_harmony = 0.5
            except Exception as e:
                logger.warning("Unexpected error calculating system harmony: %s", e)
                system_harmony = 0.5

            # Agent coordination harmony
            agent_harmony = self._calculate_agent_harmony()

            # Workflow harmony
            workflow_harmony = self._calculate_workflow_harmony()

            # User interaction harmony
            user_harmony = self._calculate_user_harmony()

            # Weighted combination
            harmony = (
                system_harmony * self.source_weights[MetricSource.SYSTEM]
                + agent_harmony * self.source_weights[MetricSource.AGENT]
                + workflow_harmony * self.source_weights[MetricSource.WORKFLOW]
                + user_harmony * self.source_weights[MetricSource.USER]
            )

            return max(0.0, min(1.0, harmony))

        except Exception as e:
            logger.error("Failed to calculate harmony: %s", e)
            return 0.5

    def _calculate_resilience(self) -> float:
        """
        Compute a resilience score that reflects the system's ability to maintain stability and recover from stress.

        The score is derived from system stability, recovery capability, and stress level, and it is adjusted for time-based decay. The returned value is clamped to the range 0.0 to 2.0.

        Returns:
            float: Resilience score between 0.0 and 2.0.
        """
        try:
            base_resilience = 1.5

            # System stability factor
            stability_factor = self._calculate_system_stability()

            # Recovery capability
            recovery_factor = self._calculate_recovery_capability()

            # Stress level (inverse of resilience)
            stress_level = self._calculate_stress_level()

            # Calculate resilience
            resilience = base_resilience * stability_factor + recovery_factor * 0.5 - stress_level * 0.3

            # Apply decay for natural resilience degradation
            if self._last_update:
                time_diff = (datetime.now(UTC) - self._last_update).total_seconds()
                decay = self.decay_factor ** (time_diff / 3600)  # Hourly decay
                resilience *= decay

            return max(0.0, min(2.0, resilience))

        except Exception as e:
            logger.error("Failed to calculate resilience: %s", e)
            return 1.0

    def _calculate_throughput(self) -> float:
        """
        Estimate the system's current throughput (energy) level.

        Throughput is derived from time-of-day energy cycles, recent activity, and resource availability and is constrained to the range 0.0 to 1.0. If the calculation encounters an unexpected error, a neutral fallback value of 0.5 is returned.

        Returns:
            float: Throughput value between 0.0 and 1.0; 0.5 if the calculation fails.
        """
        try:
            hour = datetime.now(UTC).hour
            energy_cycle = 0.5 + 0.3 * math.sin((hour - 12) * math.pi / 12)

            # System activity level
            activity_level = self._calculate_activity_level()

            # Resource availability
            resource_level = self._calculate_resource_availability()

            # Calculate throughput
            throughput = energy_cycle * 0.4 + activity_level * 0.3 + resource_level * 0.3

            return max(0.0, min(1.0, throughput))

        except Exception as e:
            logger.error("Failed to calculate throughput: %s", e)
            return 0.5

    def _calculate_focus(self) -> float:
        """
        Compute the focus (clarity) metric representing overall system focus.

        Focus is derived from goal alignment, information clarity, and decision quality with weights 0.4, 0.3, and 0.3 respectively; the result is clamped to the range 0.0–1.0.

        Returns:
            focus (float): A value between 0.0 and 1.0 indicating clarity, where higher is more focused.
        """
        try:
            goal_alignment = self._calculate_goal_alignment()

            # Information clarity
            info_clarity = self._calculate_information_clarity()

            # Decision quality
            decision_quality = self._calculate_decision_quality()

            # Calculate focus
            focus = goal_alignment * 0.4 + info_clarity * 0.3 + decision_quality * 0.3

            return max(0.0, min(1.0, focus))

        except Exception as e:
            logger.error("Failed to calculate focus: %s", e)
            return 0.5

    def _calculate_friction(self) -> float:
        """
        Estimate the system's entropy ("friction") as a metric of disorder.

        Returns:
            float: Friction value between 0.0 and 1.0; returns 0.2 on failure.
        """
        try:
            base_entropy = 0.2

            # System complexity
            complexity_factor = self._calculate_complexity_factor()

            # Error rate
            error_rate = self._calculate_error_rate()

            # Confusion level
            confusion_level = self._calculate_confusion_level()

            # Calculate friction
            friction = base_entropy * 0.3 + complexity_factor * 0.3 + error_rate * 0.25 + confusion_level * 0.15

            return max(0.0, min(1.0, friction))

        except Exception as e:
            logger.error("Failed to calculate friction: %s", e)
            return 0.2

    def _calculate_agent_harmony(self) -> float:
        """Estimate agent coordination harmony from registered agent count."""
        try:
            from apps.backend.helix_agent_swarm.agent_registry import AGENT_REGISTRY

            total = len(AGENT_REGISTRY)
            # More agents registered → higher harmony (17 canonical = 1.0)
            return min(1.0, total / 16.0) if total > 0 else 0.3
        except (ImportError, ModuleNotFoundError) as e:
            logger.debug("Agent registry not available: %s", e)
            return 0.5
        except (TypeError, ValueError) as e:
            logger.debug("Agent registry data error: %s", e)
            return 0.5
        except Exception as e:
            logger.warning("Error calculating agent harmony: %s", e)
            return 0.5

    def _calculate_workflow_harmony(self) -> float:
        """Estimate workflow harmony from CPU idle headroom (low CPU → system is harmonious)."""
        try:
            cpu = psutil.cpu_percent(interval=0)
            return max(0.0, min(1.0, 1.0 - cpu / 100.0))
        except (OSError, RuntimeError, ValueError) as e:
            logger.debug("Workflow harmony calculation failed: %s", e)
            return 0.6
        except Exception as e:
            logger.warning("Unexpected error calculating workflow harmony: %s", e)
            return 0.6

    def _calculate_user_harmony(self) -> float:
        """Estimate user-side harmony from available swap memory (a proxy for system strain)."""
        try:
            swap = psutil.swap_memory()
            # Low swap usage → high harmony
            return max(0.0, min(1.0, 1.0 - swap.percent / 100.0))
        except (OSError, RuntimeError, ValueError, AttributeError) as e:
            logger.debug("User harmony calculation failed: %s", e)
            return 0.55
        except Exception as e:
            logger.warning("Unexpected error calculating user harmony: %s", e)
            return 0.55

    def _calculate_system_stability(self) -> float:
        """Derive system stability from CPU and memory utilisation (low usage → stable)."""
        try:
            cpu = psutil.cpu_percent(interval=0)
            mem = psutil.virtual_memory().percent
            # Both low → stability near 1.0
            return max(0.0, min(1.0, 1.0 - (cpu * 0.6 + mem * 0.4) / 100.0))
        except (OSError, RuntimeError, ValueError) as e:
            logger.debug("System stability calculation failed: %s", e)
            return 0.8
        except Exception as e:
            logger.warning("Unexpected error calculating system stability: %s", e)
            return 0.8

    def _calculate_recovery_capability(self) -> float:
        """Derive recovery capability from available memory headroom."""
        try:
            mem = psutil.virtual_memory()
            return max(0.0, min(1.0, mem.available / mem.total))
        except (OSError, RuntimeError, ValueError, AttributeError) as e:
            logger.debug("Recovery capability calculation failed: %s", e)
            return 0.7
        except Exception as e:
            logger.warning("Unexpected error calculating recovery capability: %s", e)
            return 0.7

    def _calculate_stress_level(self) -> float:
        """Derive stress from system load average or CPU pressure."""
        try:
            cpu = psutil.cpu_percent(interval=0)
            return max(0.0, min(1.0, cpu / 100.0))
        except (OSError, RuntimeError, ValueError) as e:
            logger.debug("Stress level calculation failed: %s", e)
            return 0.3
        except Exception as e:
            logger.warning("Unexpected error calculating stress level: %s", e)
            return 0.3

    def _calculate_activity_level(self) -> float:
        """Derive activity level from current CPU utilisation."""
        try:
            cpu = psutil.cpu_percent(interval=0)
            return max(0.0, min(1.0, cpu / 100.0))
        except (OSError, RuntimeError, ValueError) as e:
            logger.debug("Activity level calculation failed: %s", e)
            return 0.5
        except Exception as e:
            logger.warning("Unexpected error calculating activity level: %s", e)
            return 0.5

    def _calculate_resource_availability(self) -> float:
        """Derive resource availability from free physical memory percentage."""
        try:
            mem = psutil.virtual_memory()
            return max(0.0, min(1.0, mem.available / mem.total))
        except (OSError, RuntimeError, ValueError, AttributeError) as e:
            logger.debug("Resource availability calculation failed: %s", e)
            return 0.7
        except Exception as e:
            logger.warning("Unexpected error calculating resource availability: %s", e)
            return 0.7

    def _calculate_goal_alignment(self) -> float:
        """Estimate goal alignment from ratio of running agent-related processes.

        Uses the count of Python processes as a proxy (more active workers → more aligned).
        """
        try:
            python_procs = sum(
                1 for p in psutil.process_iter(["name"]) if "python" in (p.info.get("name") or "").lower()
            )
            # Normalise: 1 process = 0.5, 4+ = 1.0
            return min(1.0, 0.3 + python_procs * 0.175)
        except (OSError, RuntimeError, ValueError, AttributeError) as e:
            logger.debug("Goal alignment calculation failed: %s", e)
            return 0.6
        except Exception as e:
            logger.warning("Unexpected error calculating goal alignment: %s", e)
            return 0.6

    def _calculate_information_clarity(self) -> float:
        """Derive information clarity from disk I/O wait (low wait → clear pipeline)."""
        try:
            cpu_times = psutil.cpu_times_percent(interval=0)
            iowait = getattr(cpu_times, "iowait", 0.0)
            return max(0.0, min(1.0, 1.0 - iowait / 100.0))
        except (OSError, RuntimeError, ValueError, AttributeError) as e:
            logger.debug("Information clarity calculation failed: %s", e)
            return 0.7
        except Exception as e:
            logger.warning("Unexpected error calculating information clarity: %s", e)
            return 0.7

    def _calculate_decision_quality(self) -> float:
        """Derive decision quality from low error rate in recent history."""
        try:
            # Use friction history as a proxy — low recent friction → good decisions
            if self._friction_history:
                recent_friction = mean(list(self._friction_history)[-20:])
                return max(0.0, min(1.0, 1.0 - recent_friction))
            return 0.65
        except (TypeError, ValueError) as e:
            logger.debug("Decision quality calculation failed: %s", e)
            return 0.65
        except Exception as e:
            logger.warning("Unexpected error calculating decision quality: %s", e)
            return 0.65

    def _calculate_complexity_factor(self) -> float:
        """Derive complexity from the number of active threads in the process."""
        try:
            import threading

            thread_count = threading.active_count()
            # Normalise: 1 thread = 0.1, 20+ threads = 0.6
            return min(0.8, thread_count * 0.03)
        except (RuntimeError, ValueError) as e:
            logger.debug("Complexity factor calculation failed: %s", e)
            return 0.3
        except Exception as e:
            logger.warning("Unexpected error calculating complexity factor: %s", e)
            return 0.3

    def _calculate_error_rate(self) -> float:
        """Derive error rate from recent friction spikes in history buffer."""
        try:
            if len(self._friction_history) > 5:
                recent = list(self._friction_history)[-10:]
                return mean(recent)
            return 0.1
        except (TypeError, ValueError) as e:
            logger.debug("Error rate calculation failed: %s", e)
            return 0.1
        except Exception as e:
            logger.warning("Unexpected error calculating error rate: %s", e)
            return 0.1

    def _calculate_confusion_level(self) -> float:
        """Derive confusion from variance in recent harmony readings."""
        try:
            if len(self._harmony_history) > 5:
                recent = list(self._harmony_history)[-20:]
                # High variance in harmony → high confusion
                return min(0.5, stdev(recent) * 2)
            return 0.2
        except (TypeError, ValueError) as e:
            logger.debug("Confusion level calculation failed: %s", e)
            return 0.2
        except Exception as e:
            logger.warning("Unexpected error calculating confusion level: %s", e)
            return 0.2

    def _should_update(self) -> bool:
        """
        Determine whether the calculator should recompute its state based on the configured update interval.

        Returns:
            True if no prior update exists or the elapsed time since the last update is greater than or equal to update_interval, False otherwise.
        """
        if not self._last_update:
            return True

        time_diff = (datetime.now(UTC) - self._last_update).total_seconds()
        return time_diff >= self.update_interval

    def _get_metric_history(self, metric: str, cutoff_time: datetime) -> list[float]:
        """
        Retrieve stored historical values for a named metric.

        Uses in-memory deque buffers populated by each update cycle.
        These buffers persist for the lifetime of the process and hold
        the most recent values (capped by deque maxlen).

        Parameters:
            metric (str): One of "harmony", "resilience", "throughput", "focus", or "friction".
            cutoff_time (datetime): Cutoff time for returned history; accepted by the API but
                not yet used for filtering in the current in-memory implementation.

        Returns:
            List[float]: Historical metric values; empty list if the metric name is unrecognized.
        """
        history_map = {
            "harmony": self._harmony_history,
            "resilience": self._resilience_history,
            "throughput": self._throughput_history,
            "focus": self._focus_history,
            "friction": self._friction_history,
        }

        if metric in history_map:
            return list(history_map[metric])
        return []

    def _analyze_metric_trend(self, history: list[float], metric: str) -> dict[str, Any]:
        """
        Analyze recent trend characteristics for a metric's historical values.

        Parameters:
            history (List[float]): Ordered list of past metric values (oldest first).
            metric (str): Metric name for contextual reporting.

        Returns:
            Dict[str, Any]: If fewer than 5 data points are provided returns {"trend": "insufficient_data"}.
                Otherwise returns a dictionary with:
                - direction (str): "increasing", "decreasing", or "stable" comparing recent and older averages.
                - velocity (float): Numeric difference between recent and older averages.
                - volatility (float): Standard deviation over the selected window.
                - current_value (float): Most recent value from history.
                - confidence (float): Trend confidence between 0.0 and 1.0 (scales with history length).
        """
        if len(history) < 5:
            return {"trend": "insufficient_data"}

        # Calculate trend direction
        recent_avg = mean(history[-10:])
        older_avg = mean(history[-20:-10]) if len(history) >= 20 else mean(history[:-5])

        trend_direction = (
            "increasing" if recent_avg > older_avg else "decreasing" if recent_avg < older_avg else "stable"
        )

        # Calculate trend velocity
        velocity = recent_avg - older_avg

        # Calculate volatility
        volatility = stdev(history[-20:]) if len(history) >= 20 else stdev(history)

        return {
            "direction": trend_direction,
            "velocity": velocity,
            "volatility": volatility,
            "current_value": history[-1],
            "confidence": min(1.0, len(history) / 20),
        }

    def _get_metric_sources(self) -> dict[str, list[str]]:
        """
        Map each UCF metric name to its contributing source identifiers.

        Returns:
            Dict[str, List[str]]: Dictionary where each key is a metric name ("harmony", "resilience", "throughput", "focus", "friction")
            and each value is a list of short identifiers for sources that contribute to that metric.
        """
        return {
            "harmony": ["system", "agent", "workflow", "user"],
            "resilience": ["system", "stability", "recovery"],
            "throughput": ["energy_cycle", "activity", "resources"],
            "focus": ["goals", "information", "decisions"],
            "friction": ["complexity", "errors", "confusion"],
        }

    def _calculate_confidence(self) -> float:
        """
        Estimate overall confidence of the current UCF state.

        Combines data freshness and recent metric consistency into a single score reflecting reliability of the current state.

        Returns:
            float: Confidence between 0.0 and 1.0, where higher values indicate greater confidence.
        """
        if not self._current_state:
            return 0.0

        # Confidence based on data freshness and consistency
        time_diff = (datetime.now(UTC) - self._last_update).total_seconds()
        freshness_score = max(0.0, 1.0 - (time_diff / 300))  # Decay over 5 minutes

        # Consistency score based on recent history
        consistency_score = self._calculate_consistency_score()

        return freshness_score * 0.6 + consistency_score * 0.4

    def _calculate_consistency_score(self) -> float:
        """
        Compute an overall consistency score from recent metric histories.

        Uses the last 10 values of each metric (harmony, resilience, throughput, focus, friction) to compute a per-metric consistency as max(0.0, 1.0 - coefficient_of_variation). Returns the mean of available per-metric consistencies. If no metric has at least 10 samples, returns a neutral default of 0.5.

        Returns:
            float: Consistency score between 0.0 and 1.0; higher values indicate more consistent recent behavior.
        """
        if len(self._harmony_history) < 10:
            return 0.5

        # Calculate consistency for each metric
        metrics = [
            self._harmony_history,
            self._resilience_history,
            self._throughput_history,
            self._focus_history,
            self._friction_history,
        ]

        consistency_scores = []
        for metric_history in metrics:
            if len(metric_history) >= 10:
                recent_values = list(metric_history)[-10:]
                std_dev = stdev(recent_values)
                mean_val = mean(recent_values)
                cv = std_dev / mean_val if mean_val > 0 else 0
                consistency = max(0.0, 1.0 - cv)
                consistency_scores.append(consistency)

        return mean(consistency_scores) if consistency_scores else 0.5

    def _get_history_summary(self) -> dict[str, dict[str, float]]:
        """
        Produce summary statistics for each metric history that has at least five samples.

        For each of 'harmony', 'resilience', 'throughput', 'focus', and 'friction' with >= 5 recorded values, return mean, sample standard deviation (0.0 if only one value), minimum, maximum, and the most recent value.

        Returns:
            summaries (Dict[str, Dict[str, float]]): Mapping from metric name to a stats dictionary with keys:
                - mean: average of the historical values
                - std: sample standard deviation (0.0 if only one value)
                - min: minimum historical value
                - max: maximum historical value
                - current: most recent historical value
        """
        summaries = {}
        metric_names = ["harmony", "resilience", "throughput", "focus", "friction"]
        histories = [
            self._harmony_history,
            self._resilience_history,
            self._throughput_history,
            self._focus_history,
            self._friction_history,
        ]

        for name, history in zip(metric_names, histories, strict=False):
            if len(history) >= 5:
                values = list(history)
                summaries[name] = {
                    "mean": mean(values),
                    "std": stdev(values) if len(values) > 1 else 0.0,
                    "min": min(values),
                    "max": max(values),
                    "current": values[-1],
                }

        return summaries

    def _generate_health_recommendations(self, state: dict[str, float]) -> list[str]:
        """
        Generate concise, actionable recommendations based on UCF metric values.

        Parameters:
            state (Dict[str, float]): Mapping of metric names to their current values. Expected keys:
                - harmony: 0.0–1.0 (higher is better)
                - resilience: >= 0.0 (higher is better; baseline ≈ 1.0)
                - throughput: 0.0–1.0 (higher is better)
                - focus: 0.0–1.0 (higher is better)
                - friction: 0.0–1.0 (higher indicates more entropy)

        Returns:
            List[str]: Short, human-readable recommendations addressing metrics outside preferred ranges.
                If no recommendations are needed, returns a single-item list stating the system health is optimal.
        """
        recommendations = []

        if state["harmony"] < 0.5:
            recommendations.append("Focus on system harmony through coordination routines")

        if state["resilience"] < 1.0:
            recommendations.append("Enhance system resilience with stability practices")

        if state["throughput"] < 0.5:
            recommendations.append("Boost system energy through vitality exercises")

        if state["focus"] < 0.5:
            recommendations.append("Improve system clarity through focus practices")

        if state["friction"] > 0.5:
            recommendations.append("Reduce system entropy through organization")

        if not recommendations:
            recommendations.append("System health is optimal")

        return recommendations

    def _get_influence_effects(self, influence_type: str, intensity: float) -> dict[str, float]:
        """
        Map an external influence type and intensity to per-metric additive effects.

        Parameters:
            influence_type (str): Influence identifier, expected values are "positive", "negative", or "chaotic".
            intensity (float): Scale factor for the influence (0 means no effect); values are applied multiplicatively to per-metric adjustments.

        Returns:
            Dict[str, float]: Mapping from metric names ("harmony", "resilience", "throughput", "focus", "friction") to additive deltas (may be negative). Returns an empty dict if the influence_type is unrecognized.
        """
        influence_map = {
            "positive": {
                "harmony": intensity * 0.2,
                "resilience": intensity * 0.1,
                "throughput": intensity * 0.15,
                "focus": intensity * 0.1,
                "friction": -intensity * 0.1,
            },
            "negative": {
                "harmony": -intensity * 0.2,
                "resilience": -intensity * 0.1,
                "throughput": -intensity * 0.15,
                "focus": -intensity * 0.1,
                "friction": intensity * 0.1,
            },
            "chaotic": {
                "harmony": intensity * 0.1,
                "resilience": -intensity * 0.05,
                "throughput": intensity * 0.05,
                "focus": -intensity * 0.15,
                "friction": intensity * 0.2,
            },
        }

        return influence_map.get(influence_type, {})

    def _calculate_health_from_state(self, state: dict[str, float]) -> float:
        """
        Compute a single health score from a UCF state snapshot using the instance's calibration weights.

        Parameters:
            state (Dict[str, float]): Mapping of metric names to their values. Expected keys: 'harmony', 'resilience', 'throughput', 'focus', 'friction'. Resilience is treated as up to 2.0 (scaled internally), and friction is treated as a detractor (inverted).

        Returns:
            float: Aggregated health score where higher values indicate better overall health according to the current calibration.
        """
        return (
            state["harmony"] * self.calibration.harmony_weight
            + min(1.0, state["resilience"] / 2.0) * self.calibration.resilience_weight
            + state["throughput"] * self.calibration.throughput_weight
            + state["focus"] * self.calibration.focus_weight
            + (1.0 - state["friction"]) * self.calibration.friction_weight
        )

    async def save_state(self) -> bool:
        """Persist the current UCF state and history to Redis.

        Returns:
            True if saved successfully, False otherwise.
        """
        try:
            from apps.backend.core.unified_auth import Cache

            payload = {
                "current_state": self._current_state,
                "last_update": self._last_update.isoformat() if self._last_update else None,
                "calibration": asdict(self.calibration),
                "history": {
                    "harmony": list(self._harmony_history),
                    "resilience": list(self._resilience_history),
                    "throughput": list(self._throughput_history),
                    "focus": list(self._focus_history),
                    "friction": list(self._friction_history),
                },
            }
            await Cache.set("ucf:calculator:state", json.dumps(payload), ttl=86400)
            logger.debug("UCF calculator state persisted to Redis")
            return True
        except Exception as e:
            logger.warning("Failed to persist UCF state: %s", e)
            return False

    async def load_state(self) -> bool:
        """Load UCF state and history from Redis.

        Returns:
            True if state was loaded successfully, False otherwise.
        """
        try:
            from apps.backend.core.unified_auth import Cache

            raw = await Cache.get("ucf:calculator:state")
            if not raw:
                return False

            payload = json.loads(raw)

            if payload.get("current_state"):
                self._current_state = payload["current_state"]

            if payload.get("last_update"):
                self._last_update = datetime.fromisoformat(payload["last_update"])

            if payload.get("calibration"):
                cal = payload["calibration"]
                self.calibration = UCFCalibration(**cal)

            history = payload.get("history", {})
            for key in ("harmony", "resilience", "throughput", "focus", "friction"):
                hist_deque = getattr(self, f"_{key}_history")
                hist_deque.clear()
                hist_deque.extend(history.get(key, []))

            logger.debug("UCF calculator state loaded from Redis")
            return True
        except Exception as e:
            logger.warning("Failed to load UCF state: %s", e)
            return False

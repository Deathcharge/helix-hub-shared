"""
System Metrics Service
Implements memoized service for system metrics with proper caching and performance optimization.
"""

import logging
import time
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from apps.backend.services.service_registry import ServiceRegistry

from ..models.system import SystemMetrics

logger = logging.getLogger(__name__)

# Try to import UCFCalculator for real metrics
_ucf_calculator = None
try:
    from ..services.ucf_calculator import UCFCalculator

    _ucf_calculator = UCFCalculator()
    logger.info("UCFCalculator available for system metrics")
except (ImportError, ModuleNotFoundError) as e:
    logger.debug("UCFCalculator not available: %s", e)
    logger.info("UCFCalculator not available; system metrics will return null values")
except Exception as e:
    logger.warning("UCFCalculator initialization failed: %s", e)
    logger.info("UCFCalculator not available; system metrics will return null values")


class SystemMetricsService:
    """Service for managing system metrics with memoization and caching"""

    def __init__(self) -> None:
        """
        Initialize the SystemMetricsService, configuring caching, an in-memory metrics history, and a service registry.

        Sets a 30-second cache TTL, initializes the cache timestamp and cached metrics placeholder, creates a ServiceRegistry instance, and prepares an empty metrics history with a maximum size of 100 entries.
        """
        self._cache_ttl = 30  # 30 seconds cache TTL
        self._cache_time = 0
        self._cached_metrics: SystemMetrics | None = None
        self._service_registry = ServiceRegistry()
        self._metrics_history: list[SystemMetrics] = []
        self._max_history_size = 100

    @lru_cache(maxsize=128)
    def get_cached_metrics(self, timestamp: int) -> SystemMetrics:
        """
        Retrieve the cached SystemMetrics object for the provided timestamp.

        Parameters:
            timestamp (int): Timestamp key used to look up the cached metrics.

        Returns:
            SystemMetrics or None: The cached SystemMetrics matching the timestamp, or `None` if no cached value exists.
        """
        return self._cached_metrics

    async def get_current_metrics(self) -> SystemMetrics:
        """
        Produce current system metrics from UCFCalculator state if available,
        otherwise return metrics with null/unavailable status.

        Returns:
            SystemMetrics: Object with real UCF-derived values when available,
            or null-equivalent values with 'unavailable' status otherwise.
        """
        current_time = time.time()

        # Check if we have valid cached metrics
        if self._cached_metrics and current_time - self._cache_time < self._cache_ttl:
            logger.debug("Returning cached system metrics")
            return self._cached_metrics

        # Try to get real metrics from UCFCalculator
        coherence_level = 0.0
        entanglement_strength = 0.0
        resonance_frequency = 0.0
        field_intensity = 0.0
        status = "unavailable"
        metadata: dict[str, Any] = {}

        if _ucf_calculator is not None:
            try:
                ucf_state = _ucf_calculator.get_state()
                # Map UCF metrics to system metrics
                harmony = ucf_state.get("harmony", 0.0)
                resilience = ucf_state.get("resilience", 0.0)
                throughput = ucf_state.get("throughput", 0.0)
                focus = ucf_state.get("focus", 0.0)

                coherence_level = round(harmony, 3)
                entanglement_strength = round(resilience, 3)
                resonance_frequency = round(throughput * 5000, 2)  # Scale to MHz range
                field_intensity = round(focus, 3)

                # Determine status based on coherence
                if coherence_level > 0.8:
                    status = "stable"
                elif coherence_level > 0.5:
                    status = "unstable"
                else:
                    status = "critical"

                metadata = {
                    "system_field_strength": round(field_intensity * 100, 1),
                    "resonance_stability": round(coherence_level * 100, 1),
                    "entanglement_quality": ("high" if entanglement_strength > 0.8 else "medium"),
                    "source": "ucf_calculator",
                }
            except Exception as e:
                logger.warning("Failed to get UCF state for system metrics: %s", e)
                status = "unavailable"
                metadata = {"source": "error", "error": "Failed to get UCF state"}
        else:
            metadata = {"source": "unavailable"}

        # Create metrics object
        metrics = SystemMetrics(
            coherence_level=coherence_level,
            entanglement_strength=entanglement_strength,
            resonance_frequency=resonance_frequency,
            field_intensity=field_intensity,
            timestamp=int(current_time),
            status=status,
            metadata=metadata,
        )

        # Update cache
        self._cached_metrics = metrics
        self._cache_time = current_time

        # Add to history
        self._metrics_history.append(metrics)
        if len(self._metrics_history) > self._max_history_size:
            self._metrics_history.pop(0)

        logger.info(
            "Generated system metrics: coherence=%s, status=%s, source=%s",
            metrics.coherence_level,
            metrics.status,
            metadata.get("source", "unknown"),
        )
        return metrics

    async def get_metrics_history(self, limit: int = 10) -> list[SystemMetrics]:
        """
        Return the most recent system metrics from the in-memory history.

        Parameters:
            limit (int): Maximum number of recent entries to return.

        Returns:
            List[SystemMetrics]: Up to limit most recent metrics entries ordered chronologically (oldest first). Returns an empty list if no history exists.
        """
        return self._metrics_history[-limit:] if self._metrics_history else []

    async def get_average_metrics(self, hours: int = 1) -> dict[str, float]:
        """
        Compute average system metrics for the past `hours` hours.

        Currently returns the latest metrics as a placeholder for the computed averages.

        Parameters:
                hours (int): Time window in hours over which to compute averages.

        Returns:
                dict: A mapping with keys `avg_coherence_level`, `avg_entanglement_strength`, `avg_resonance_frequency`, and `avg_field_intensity` containing the averaged metric values.
        """
        if not self._metrics_history:
            return {}

        # Compute actual averages from stored history within time window
        cutoff = datetime.now(UTC).timestamp() - (hours * 3600)
        relevant = [m for m in self._metrics_history if getattr(m, "timestamp", 0) >= cutoff]

        if not relevant:
            # Fall back to full history if nothing in window
            relevant = self._metrics_history

        count = len(relevant)
        return {
            "avg_coherence_level": sum(m.coherence_level for m in relevant) / count,
            "avg_entanglement_strength": sum(m.entanglement_strength for m in relevant) / count,
            "avg_resonance_frequency": sum(m.resonance_frequency for m in relevant) / count,
            "avg_field_intensity": sum(m.field_intensity for m in relevant) / count,
        }

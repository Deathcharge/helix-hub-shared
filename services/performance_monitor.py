"""
Performance Monitoring Service for Helix Collective

Comprehensive performance monitoring and optimization service that collects,
analyzes, and reports on system performance metrics across all services.
"""

import asyncio
import json
import logging
import statistics
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

import psutil
import redis
from prometheus_client import Gauge, start_http_server

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Types of performance metrics"""

    RESPONSE_TIME = "response_time"
    THROUGHPUT = "throughput"
    ERROR_RATE = "error_rate"
    MEMORY_USAGE = "memory_usage"
    CPU_USAGE = "cpu_usage"
    DATABASE_QUERY_TIME = "database_query_time"
    CACHE_HIT_RATE = "cache_hit_rate"
    WEBSOCKET_CONNECTIONS = "websocket_connections"


@dataclass
class PerformanceMetric:
    """Performance metric data structure"""

    metric_type: MetricType
    service_name: str
    value: float
    timestamp: datetime
    metadata: dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class PerformanceThresholds:
    """Performance thresholds for different metrics"""

    def __init__(self) -> None:
        self.thresholds = {
            MetricType.RESPONSE_TIME: {
                "warning": 0.5,  # 500ms
                "critical": 1.0,  # 1000ms
            },
            MetricType.THROUGHPUT: {
                "warning": 100,  # 100 req/s
                "critical": 50,  # 50 req/s
            },
            MetricType.ERROR_RATE: {"warning": 1.0, "critical": 5.0},  # 1%  # 5%
            MetricType.MEMORY_USAGE: {"warning": 80.0, "critical": 90.0},  # 80%  # 90%
            MetricType.CPU_USAGE: {"warning": 70.0, "critical": 85.0},  # 70%  # 85%
            MetricType.DATABASE_QUERY_TIME: {
                "warning": 0.1,  # 100ms
                "critical": 0.5,  # 500ms
            },
            MetricType.CACHE_HIT_RATE: {
                "warning": 70.0,  # 70%
                "critical": 50.0,  # 50%
            },
        }


class MetricsCollector:
    """Collects performance metrics from various sources"""

    def __init__(self, redis_client: redis.Redis | None = None) -> None:
        self.redis_client = redis_client
        self.metrics_buffer = deque(maxlen=10000)  # Buffer for recent metrics
        self.service_metrics = defaultdict(deque)

    async def collect_system_metrics(self, service_name: str) -> list[PerformanceMetric]:
        """Collect system-level metrics"""
        metrics = []

        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            metrics.append(
                PerformanceMetric(
                    metric_type=MetricType.CPU_USAGE,
                    service_name=service_name,
                    value=cpu_percent,
                    timestamp=datetime.now(UTC),
                    metadata={"process_count": len(psutil.pids())},
                )
            )

            # Memory usage
            memory = psutil.virtual_memory()
            metrics.append(
                PerformanceMetric(
                    metric_type=MetricType.MEMORY_USAGE,
                    service_name=service_name,
                    value=memory.percent,
                    timestamp=datetime.now(UTC),
                    metadata={
                        "total_gb": round(memory.total / (1024**3), 2),
                        "available_gb": round(memory.available / (1024**3), 2),
                    },
                )
            )

            # Disk usage
            disk = psutil.disk_usage("/")
            metrics.append(
                PerformanceMetric(
                    metric_type=MetricType.MEMORY_USAGE,
                    service_name=f"{service_name}_disk",
                    value=disk.percent,
                    timestamp=datetime.now(UTC),
                    metadata={
                        "total_gb": round(disk.total / (1024**3), 2),
                        "free_gb": round(disk.free / (1024**3), 2),
                    },
                )
            )

            # Network I/O
            network = psutil.net_io_counters()
            metrics.append(
                PerformanceMetric(
                    metric_type=MetricType.THROUGHPUT,
                    service_name=f"{service_name}_network",
                    value=network.bytes_sent + network.bytes_recv,
                    timestamp=datetime.now(UTC),
                    metadata={
                        "bytes_sent": network.bytes_sent,
                        "bytes_recv": network.bytes_recv,
                        "packets_sent": network.packets_sent,
                        "packets_recv": network.packets_recv,
                    },
                )
            )

        except (ValueError, TypeError, KeyError) as e:
            logger.debug("System metrics calculation error for %s: %s", service_name, e)
        except Exception as e:
            logger.error("Failed to collect system metrics for %s: %s", service_name, e)

        return metrics

    async def collect_database_metrics(self, service_name: str) -> list[PerformanceMetric]:
        """
        Collect Redis-derived database performance metrics for a service.

        Returns:
            List[PerformanceMetric]: Collected metrics (memory usage and cache hit rate) for the service's Redis instance. Returns an empty list if no Redis client is configured or if metric collection fails.
        """
        metrics = []

        if not self.redis_client:
            return metrics

        try:
            info = await asyncio.to_thread(self.redis_client.info)

            # Memory usage
            metrics.append(
                PerformanceMetric(
                    metric_type=MetricType.MEMORY_USAGE,
                    service_name=f"{service_name}_redis",
                    value=info.get("used_memory_peak_perc", 0),
                    timestamp=datetime.now(UTC),
                    metadata={
                        "used_memory": info.get("used_memory_human", "0B"),
                        "connected_clients": info.get("connected_clients", 0),
                        "keyspace_hits": info.get("keyspace_hits", 0),
                        "keyspace_misses": info.get("keyspace_misses", 0),
                    },
                )
            )

            # Cache hit rate
            hits = info.get("keyspace_hits", 0)
            misses = info.get("keyspace_misses", 0)
            total_requests = hits + misses
            hit_rate = (hits / total_requests * 100) if total_requests > 0 else 0

            metrics.append(
                PerformanceMetric(
                    metric_type=MetricType.CACHE_HIT_RATE,
                    service_name=f"{service_name}_redis",
                    value=hit_rate,
                    timestamp=datetime.now(UTC),
                    metadata={"total_requests": total_requests, "hit_rate": hit_rate},
                )
            )

        except Exception as e:
            logger.error("Failed to collect database metrics for %s: %s", service_name, e)

        return metrics

    async def collect_api_metrics(
        self, service_name: str, endpoint: str, response_time: float, status_code: int
    ) -> list[PerformanceMetric]:
        """Collect API performance metrics"""
        metrics = []

        # Response time
        metrics.append(
            PerformanceMetric(
                metric_type=MetricType.RESPONSE_TIME,
                service_name=f"{service_name}_{endpoint}",
                value=response_time,
                timestamp=datetime.now(UTC),
                metadata={"endpoint": endpoint, "status_code": status_code},
            )
        )

        # Throughput (calculated over time window)
        # This would typically be calculated in the aggregator

        # Error rate (calculated over time window)
        if status_code >= 400:
            metrics.append(
                PerformanceMetric(
                    metric_type=MetricType.ERROR_RATE,
                    service_name=f"{service_name}_{endpoint}",
                    value=1.0,  # Error occurred
                    timestamp=datetime.now(UTC),
                    metadata={"endpoint": endpoint, "status_code": status_code},
                )
            )

        return metrics

    async def collect_websocket_metrics(
        self, service_name: str, active_connections: int, message_rate: float
    ) -> list[PerformanceMetric]:
        """
        Create a WEBSOCKET_CONNECTIONS PerformanceMetric for a service, capturing current active connections and message throughput.

        Parameters:
            service_name (str): Name of the service reporting the WebSocket metrics.
            active_connections (int): Current number of active WebSocket connections.
            message_rate (float): Messages per second observed for the WebSocket connections.

        Returns:
            List[PerformanceMetric]: A list containing a single `PerformanceMetric` with metric_type `WEBSOCKET_CONNECTIONS`, the provided connection count as `value`, and `metadata` that includes `message_rate` and `peak_connections`.
        """
        metrics = []

        metrics.append(
            PerformanceMetric(
                metric_type=MetricType.WEBSOCKET_CONNECTIONS,
                service_name=service_name,
                value=active_connections,
                timestamp=datetime.now(UTC),
                metadata={
                    "message_rate": message_rate,
                    "peak_connections": active_connections,  # Would track peak over time
                },
            )
        )

        return metrics

    async def store_metrics(self, metrics: list[PerformanceMetric]):
        """
        Add provided PerformanceMetric objects to the in-memory buffers and persist them to Redis when a Redis client is configured.

        Each metric is appended to the cross-service buffer and the per-service deque. When Redis is available, the function stores each metric in a sorted set keyed as "metrics:{service_name}:{metric_type}", sets a TTL of 86400 seconds (24 hours), and trims the sorted set to keep the most recent 1000 entries. Storage failures are logged but do not raise from this function.

        Parameters:
            metrics (List[PerformanceMetric]): Metrics to store and optionally persist.
        """
        for metric in metrics:
            # Add to buffer
            self.metrics_buffer.append(metric)
            self.service_metrics[metric.service_name].append(metric)

            # Store in Redis if available
            if self.redis_client:
                try:
                    metric_data = {
                        "metric_type": metric.metric_type.value,
                        "service_name": metric.service_name,
                        "value": metric.value,
                        "timestamp": metric.timestamp.isoformat(),
                        "metadata": metric.metadata,
                    }

                    # Store in Redis with TTL
                    key = f"metrics:{metric.service_name}:{metric.metric_type.value}"
                    await asyncio.to_thread(
                        self.redis_client.zadd,
                        key,
                        {json.dumps(metric_data): metric.timestamp.timestamp()},
                    )

                    # Set expiration (keep metrics for 24 hours)
                    await asyncio.to_thread(self.redis_client.expire, key, 86400)

                    # Keep only last 1000 entries per metric type
                    await asyncio.to_thread(self.redis_client.zremrangebyrank, key, 0, -1001)

                except Exception as e:
                    logger.error("Failed to store metric in Redis: %s", e)

    def add_metric(self, metric: PerformanceMetric):
        """Add a metric to the buffer"""
        self.metrics_buffer.append(metric)
        self.service_metrics[metric.service_name].append(metric)

    def get_recent_metrics(
        self, service_name: str, metric_type: MetricType, minutes: int = 5
    ) -> list[PerformanceMetric]:
        """Get recent metrics for a service and metric type"""
        cutoff_time = datetime.now(UTC) - timedelta(minutes=minutes)
        recent_metrics = []

        for metric in self.service_metrics[service_name]:
            if metric.metric_type == metric_type and metric.timestamp >= cutoff_time:
                recent_metrics.append(metric)

        return recent_metrics

    def aggregate_metrics(
        self,
        service_name: str,
        metric_type: MetricType,
        window_seconds: int = 300,
    ) -> dict[str, Any]:
        """Aggregate metrics for a service and metric type over a time window"""

        cutoff_time = datetime.now(UTC) - timedelta(seconds=window_seconds)
        relevant_metrics = []

        for metric in self.service_metrics[service_name]:
            if metric.metric_type == metric_type and metric.timestamp >= cutoff_time:
                relevant_metrics.append(metric)

        if not relevant_metrics:
            return {}

        values = [m.value for m in relevant_metrics]

        return {
            "count": len(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "min": min(values),
            "max": max(values),
            "std_dev": statistics.stdev(values) if len(values) > 1 else 0,
        }


class MetricsAggregator:
    """Aggregates and analyzes performance metrics"""

    def __init__(self, thresholds: PerformanceThresholds) -> None:
        self.thresholds = thresholds
        self.alerts = deque(maxlen=1000)

    def calculate_aggregates(
        self,
        metrics: list[PerformanceMetric],
        time_window: timedelta = timedelta(minutes=5),
    ) -> dict[str, Any]:
        """Calculate aggregate metrics over time window"""
        if not metrics:
            return {}

        # Filter metrics by time window
        cutoff_time = datetime.now(UTC) - time_window
        recent_metrics = [m for m in metrics if m.timestamp >= cutoff_time]

        if not recent_metrics:
            return {}

        # Group by metric type
        by_type = defaultdict(list)
        for metric in recent_metrics:
            by_type[metric.metric_type].append(metric)

        aggregates = {}

        for metric_type, metric_list in by_type.items():
            values = [m.value for m in metric_list]

            aggregates[metric_type.value] = {
                "count": len(values),
                "avg": statistics.mean(values),
                "median": statistics.median(values),
                "p95": self._calculate_percentile(values, 95),
                "p99": self._calculate_percentile(values, 99),
                "min": min(values),
                "max": max(values),
                "std_dev": statistics.stdev(values) if len(values) > 1 else 0,
            }

        return aggregates

    def _calculate_percentile(self, values: list[float], percentile: int) -> float:
        """Calculate percentile value"""
        if not values:
            return 0.0

        sorted_values = sorted(values)
        index = int((percentile / 100) * len(sorted_values))
        return sorted_values[min(index, len(sorted_values) - 1)]

    def check_thresholds(self, aggregates: dict[str, Any], service_name: str) -> list[dict[str, Any]]:
        """
        Generate alert entries for metrics whose aggregated averages exceed configured thresholds.

        Parameters:
            aggregates (Dict[str, Any]): Mapping from metric name (the MetricType value) to aggregated statistics.
                Each stats dict is expected to contain an "avg" key with a numeric average value.
            service_name (str): Name of the service to include in produced alert entries.

        Returns:
            List[Dict[str, Any]]: A list of alert dictionaries. Each alert contains:
                - service (str): the service_name provided
                - metric (str): the metric name from the aggregates keys
                - value (float): the observed average value that triggered the alert
                - threshold (float): the threshold value that was exceeded
                - level (str): "warning" or "critical"
                - timestamp (str): ISO-formatted UTC timestamp when the alert was generated
                - message (str): human-readable message describing the threshold breach

        Notes:
            - Metrics whose names do not map to a known MetricType are ignored and a warning is logged.
            - Both warning and critical thresholds are evaluated; a metric may produce multiple alerts if it exceeds multiple configured levels.
        """
        alerts = []

        for metric_name, stats in aggregates.items():
            try:
                thresholds = self.thresholds.thresholds.get(metric_name, {})

                avg_value = stats.get("avg", 0)

                # Check warning threshold
                if "warning" in thresholds and avg_value > thresholds["warning"]:
                    alerts.append(
                        {
                            "service": service_name,
                            "metric": metric_name,
                            "value": avg_value,
                            "threshold": thresholds["warning"],
                            "level": "warning",
                            "timestamp": datetime.now(UTC).isoformat(),
                            "message": (
                                f"{metric_name} exceeded warning threshold: "
                                f"{avg_value:.2f} > {thresholds['warning']:.2f}"
                            ),
                        }
                    )

                # Check critical threshold
                if "critical" in thresholds and avg_value > thresholds["critical"]:
                    alerts.append(
                        {
                            "service": service_name,
                            "metric": metric_name,
                            "value": avg_value,
                            "threshold": thresholds["critical"],
                            "level": "critical",
                            "timestamp": datetime.now(UTC).isoformat(),
                            "message": (
                                f"{metric_name} exceeded critical threshold: "
                                f"{avg_value:.2f} > {thresholds['critical']:.2f}"
                            ),
                        }
                    )

            except ValueError:
                logger.warning("Unknown metric type: %s", metric_name)

        return alerts

    def generate_performance_report(
        self,
        service_name: str,
        metrics: list[PerformanceMetric] = None,
        time_window: timedelta = timedelta(hours=1),
    ) -> dict[str, Any]:
        """Generate comprehensive performance report"""
        if metrics is None:
            metrics = []
        cutoff_time = datetime.now(UTC) - time_window

        # Get metrics for service
        service_metrics = [m for m in metrics if m.service_name.startswith(service_name) and m.timestamp >= cutoff_time]

        # Calculate aggregates
        aggregates = self.calculate_aggregates(service_metrics, time_window)

        # Check thresholds
        alerts = self.check_thresholds(aggregates, service_name)

        # Calculate overall health score
        health_score = self.calculate_health_score(aggregates)

        return {
            "service": service_name,
            "timestamp": datetime.now(UTC).isoformat(),
            "time_window": str(time_window),
            "total_metrics": len(service_metrics),
            "aggregates": aggregates,
            "alerts": alerts,
            "health_score": health_score,
            "recommendations": self.generate_recommendations(aggregates, alerts),
        }

    def calculate_health_score(self, aggregates: dict[str, Any]) -> float:
        """Calculate overall health score (0-100)"""
        if not aggregates:
            return 50.0  # Neutral score if no data

        score = 100.0

        for metric_name, stats in aggregates.items():
            try:
                thresholds = self.thresholds.thresholds.get(metric_name, {})

                avg_value = stats.get("avg", 0)

                # Deduct points based on threshold violations
                if "critical" in thresholds and avg_value > thresholds["critical"]:
                    score -= 30  # Major deduction for critical threshold
                elif "warning" in thresholds and avg_value > thresholds["warning"]:
                    score -= 10  # Minor deduction for warning threshold

                # Additional deductions for high variance
                std_dev = stats.get("std_dev", 0)
                if std_dev > avg_value * 0.5:  # High variance
                    score -= 5

            except ValueError:
                continue

        return max(0.0, min(100.0, score))

    def generate_recommendations(self, aggregates: dict[str, Any], alerts: list[dict[str, Any]]) -> list[str]:
        """Generate performance optimization recommendations"""
        recommendations = []

        for alert in alerts:
            metric = alert["metric"]
            level = alert["level"]

            if metric == "response_time" and level == "critical":
                recommendations.append("Consider implementing caching for slow endpoints")
                recommendations.append("Review database query performance")
                recommendations.append("Consider horizontal scaling")

            elif metric == "error_rate" and level == "critical":
                recommendations.append("Review error handling and logging")
                recommendations.append("Check for resource exhaustion")
                recommendations.append("Review recent code changes")

            elif metric == "memory_usage" and level == "critical":
                recommendations.append("Review memory leaks in application code")
                recommendations.append("Consider increasing memory allocation")
                recommendations.append("Review caching strategy")

            elif metric == "cpu_usage" and level == "critical":
                recommendations.append("Review CPU-intensive operations")
                recommendations.append("Consider optimizing algorithms")
                recommendations.append("Review for infinite loops or blocking operations")

        # General recommendations
        if not recommendations:
            recommendations.append("Performance metrics are within acceptable ranges")
            recommendations.append("Continue monitoring for trends")

        return recommendations


class PerformanceMonitor:
    """Main performance monitoring service"""

    # Class-level Prometheus metrics to avoid duplication
    _response_time_gauge = None
    _error_rate_gauge = None
    _memory_usage_gauge = None
    _cpu_usage_gauge = None
    _cache_hit_rate_gauge = None
    _metrics_initialized = False

    def __init__(self, redis_client: redis.Redis | None = None) -> None:
        self.redis_client = redis_client
        self.metrics_collector = MetricsCollector(redis_client)
        self.metrics_aggregator = MetricsAggregator(PerformanceThresholds())
        self.is_running = False
        self.monitoring_tasks = []

        # Initialize Prometheus metrics once per class
        if not PerformanceMonitor._metrics_initialized:
            PerformanceMonitor._response_time_gauge = Gauge(
                "response_time_seconds",
                "Response time in seconds",
                ["service", "endpoint"],
            )
            PerformanceMonitor._error_rate_gauge = Gauge(
                "error_rate_percent", "Error rate percentage", ["service", "endpoint"]
            )
            PerformanceMonitor._memory_usage_gauge = Gauge(
                "memory_usage_percent", "Memory usage percentage", ["service"]
            )
            PerformanceMonitor._cpu_usage_gauge = Gauge("cpu_usage_percent", "CPU usage percentage", ["service"])
            PerformanceMonitor._cache_hit_rate_gauge = Gauge(
                "cache_hit_rate_percent", "Cache hit rate percentage", ["service"]
            )
            PerformanceMonitor._metrics_initialized = True

        # Instance references to class metrics
        self.response_time_gauge = PerformanceMonitor._response_time_gauge
        self.error_rate_gauge = PerformanceMonitor._error_rate_gauge
        self.memory_usage_gauge = PerformanceMonitor._memory_usage_gauge
        self.cpu_usage_gauge = PerformanceMonitor._cpu_usage_gauge
        self.cache_hit_rate_gauge = PerformanceMonitor._cache_hit_rate_gauge

    async def start(self, services: list[str] = None, interval: int = 30):
        """Start performance monitoring with default services"""
        if services is None:
            services = ["test_service"]
        await self.start_monitoring(services, interval)

    async def record_metric(
        self,
        metric_type: MetricType,
        service_name: str,
        value: float,
        metadata: dict[str, Any] | None = None,
    ):
        """Record a performance metric"""
        metric = PerformanceMetric(
            metric_type=metric_type,
            service_name=service_name,
            value=value,
            timestamp=datetime.now(UTC),
            metadata=metadata or {},
        )

        # Add to collector
        self.metrics_collector.add_metric(metric)

        # Check thresholds and generate alerts
        aggregates = self.metrics_aggregator.calculate_aggregates([metric])
        alerts = self.metrics_aggregator.check_thresholds(aggregates, service_name)
        for alert in alerts:
            self.metrics_aggregator.alerts.append(alert)

        # Update Prometheus metrics
        if metric_type == MetricType.RESPONSE_TIME:
            self.response_time_gauge.labels(
                service=service_name,
                endpoint=metadata.get("endpoint", "") if metadata else "",
            ).set(value)
        elif metric_type == MetricType.ERROR_RATE:
            self.error_rate_gauge.labels(
                service=service_name,
                endpoint=metadata.get("endpoint", "") if metadata else "",
            ).set(value)
        elif metric_type == MetricType.MEMORY_USAGE:
            self.memory_usage_gauge.labels(service=service_name).set(value)
        elif metric_type == MetricType.CPU_USAGE:
            self.cpu_usage_gauge.labels(service=service_name).set(value)
        elif metric_type == MetricType.CACHE_HIT_RATE:
            self.cache_hit_rate_gauge.labels(service=service_name).set(value)

    def get_metrics(
        self, service_name: str = None, metric_type: MetricType = None, minutes: int = 5
    ) -> list[PerformanceMetric]:
        """Get metrics with optional filtering"""
        if service_name and metric_type:
            return self.metrics_collector.get_recent_metrics(service_name, metric_type, minutes)
        elif service_name:
            # Return all metrics for this service
            all_metrics = []
            for m_type in MetricType:
                all_metrics.extend(self.metrics_collector.get_recent_metrics(service_name, m_type, minutes))
            return all_metrics
        else:
            # Return all metrics
            all_metrics = []
            for svc_name in self.metrics_collector.service_metrics.keys():
                for m_type in MetricType:
                    all_metrics.extend(self.metrics_collector.get_recent_metrics(svc_name, m_type, minutes))
            return all_metrics

    def get_metrics_by_type(
        self, metric_type: MetricType, service_name: str = None, minutes: int = 5
    ) -> list[PerformanceMetric]:
        """Get metrics by type"""
        if service_name:
            return self.metrics_collector.get_recent_metrics(service_name, metric_type, minutes)
        else:
            # Return metrics from all services
            all_metrics = []
            for svc_name in self.metrics_collector.service_metrics.keys():
                all_metrics.extend(self.metrics_collector.get_recent_metrics(svc_name, metric_type, minutes))
            return all_metrics

    async def stop(self):
        """Stop performance monitoring"""
        await self.stop_monitoring()

    def get_alerts(self) -> list[dict[str, Any]]:
        """Get current alerts"""
        return list(self.metrics_aggregator.alerts)

    async def start_monitoring(self, services: list[str], interval: int = 30):
        """Start performance monitoring for specified services"""
        self.is_running = True
        logger.info("Starting performance monitoring for services: %s", services)

        # Start Prometheus metrics server
        start_http_server(8004)
        logger.info("Prometheus metrics server started on port 8004")

        # Start monitoring tasks
        for service in services:
            task = asyncio.create_task(self._monitor_service(service, interval))
            self.monitoring_tasks.append(task)

        # Start alert processing
        alert_task = asyncio.create_task(self._process_alerts())
        self.monitoring_tasks.append(alert_task)

        logger.info("Performance monitoring started successfully")

    async def stop_monitoring(self):
        """Stop performance monitoring"""
        self.is_running = False

        # Cancel all monitoring tasks
        for task in self.monitoring_tasks:
            task.cancel()

        # Wait for tasks to complete
        await asyncio.gather(*self.monitoring_tasks, return_exceptions=True)

        logger.info("Performance monitoring stopped")

    async def _monitor_service(self, service_name: str, interval: int):
        """
        Continuously collect, store, and export runtime and database metrics for the given service.

        Parameters:
            service_name (str): Name of the service to monitor.
            interval (int): Polling interval in seconds between metric collection cycles.
        """
        while self.is_running:
            try:
                system_metrics = await self.metrics_collector.collect_system_metrics(service_name)

                # Collect database metrics
                db_metrics = await self.metrics_collector.collect_database_metrics(service_name)

                # Combine metrics
                all_metrics = system_metrics + db_metrics

                # Store metrics
                await self.metrics_collector.store_metrics(all_metrics)

                # Update Prometheus metrics
                await self._update_prometheus_metrics(all_metrics)

                logger.debug("Collected %d metrics for %s", len(all_metrics), service_name)

            except Exception as e:
                logger.error("Error monitoring service %s: %s", service_name, e)

            await asyncio.sleep(interval)

    async def _update_prometheus_metrics(self, metrics: list[PerformanceMetric]):
        """Update Prometheus metrics"""
        for metric in metrics:
            if metric.metric_type == MetricType.RESPONSE_TIME:
                self.response_time_gauge.labels(
                    service=metric.service_name,
                    endpoint=metric.metadata.get("endpoint", "unknown"),
                ).set(metric.value)

            elif metric.metric_type == MetricType.ERROR_RATE:
                self.error_rate_gauge.labels(
                    service=metric.service_name,
                    endpoint=metric.metadata.get("endpoint", "unknown"),
                ).set(metric.value)

            elif metric.metric_type == MetricType.MEMORY_USAGE:
                self.memory_usage_gauge.labels(service=metric.service_name).set(metric.value)

            elif metric.metric_type == MetricType.CPU_USAGE:
                self.cpu_usage_gauge.labels(service=metric.service_name).set(metric.value)

            elif metric.metric_type == MetricType.CACHE_HIT_RATE:
                self.cache_hit_rate_gauge.labels(service=metric.service_name).set(metric.value)
        """Get metrics with optional filtering"""

    def calculate_statistics(self, service_name: str, metric_type: MetricType, minutes: int = 5) -> dict[str, Any]:
        """Calculate statistics for a metric type"""
        metrics = self.metrics_collector.get_recent_metrics(service_name, metric_type, minutes)

        if not metrics:
            return {}

        values = [m.value for m in metrics]

        return {
            "count": len(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "min": min(values),
            "max": max(values),
            "std_dev": statistics.stdev(values) if len(values) > 1 else 0,
        }

    def get_optimization_recommendations(self, service_name: str, metric_type: MetricType = None) -> list[str]:
        """Get optimization recommendations based on current metrics"""
        recommendations = []

        # Get recent metrics
        if metric_type:
            metrics = self.metrics_collector.get_recent_metrics(service_name, metric_type, 10)
        else:
            # Check all metric types
            metrics = []
            for m_type in MetricType:
                metrics.extend(self.metrics_collector.get_recent_metrics(service_name, m_type, 10))

        if not metrics:
            return ["No recent metrics available for analysis"]

        # Analyze metrics and provide recommendations
        for metric in metrics[-5:]:  # Check last 5 metrics
            if metric.metric_type == MetricType.RESPONSE_TIME and metric.value > 1.0:
                recommendations.append("High response time detected - consider optimizing database queries")
            elif metric.metric_type == MetricType.ERROR_RATE and metric.value > 5.0:
                recommendations.append("High error rate detected - review error handling and logging")
            elif metric.metric_type == MetricType.MEMORY_USAGE and metric.value > 85.0:
                recommendations.append("High memory usage - consider memory optimization or scaling")
            elif metric.metric_type == MetricType.CPU_USAGE and metric.value > 80.0:
                recommendations.append("High CPU usage - review CPU-intensive operations")

        if not recommendations:
            recommendations.append("Performance metrics are within acceptable ranges")

        return recommendations

    async def _process_alerts(self):
        """Process and handle performance alerts"""
        while self.is_running:
            try:
                services = set(m.service_name for m in self.metrics_collector.metrics_buffer)

                for service in services:
                    report = self.metrics_aggregator.generate_performance_report(service)

                    # Log critical alerts
                    critical_alerts = [a for a in report["alerts"] if a["level"] == "critical"]
                    for alert in critical_alerts:
                        logger.critical("CRITICAL ALERT: %s", alert.get("message"))

                    # Log warning alerts
                    warning_alerts = [a for a in report["alerts"] if a["level"] == "warning"]
                    for alert in warning_alerts:
                        logger.warning("WARNING: %s", alert.get("message"))

            except Exception as e:
                logger.error("Error processing alerts: %s", e)

            await asyncio.sleep(60)  # Check alerts every minute

    async def get_performance_report(
        self, service_name: str, time_window: timedelta = timedelta(hours=1)
    ) -> dict[str, Any]:
        """Get performance report for a specific service"""
        return self.metrics_aggregator.generate_performance_report(service_name, time_window)

    async def get_system_health(self) -> dict[str, Any]:
        """Get overall system health status"""
        services = set(m.service_name for m in self.metrics_collector.metrics_buffer)

        health_status = {
            "timestamp": datetime.now(UTC).isoformat(),
            "services": {},
            "overall_health_score": 0.0,
            "total_alerts": 0,
            "critical_alerts": 0,
        }

        total_score = 0.0
        total_services = len(services)

        for service in services:
            report = await self.get_performance_report(service)

            health_status["services"][service] = {
                "health_score": report["health_score"],
                "total_alerts": len(report["alerts"]),
                "critical_alerts": len([a for a in report["alerts"] if a["level"] == "critical"]),
                "recommendations": report["recommendations"][:3],  # Top 3 recommendations
            }

            total_score += report["health_score"]
            health_status["total_alerts"] += len(report["alerts"])
            health_status["critical_alerts"] += len([a for a in report["alerts"] if a["level"] == "critical"])

        health_status["overall_health_score"] = total_score / total_services if total_services > 0 else 50.0

        return health_status

    async def optimize_database_queries(self, service_name: str) -> list[dict[str, Any]]:
        """Analyze and suggest database query optimizations.

        Returns an empty list until connected to a slow-query log or
        database performance monitoring backend.
        """
        # Requires slow-query log integration to provide real suggestions
        logger.debug(
            "Database optimization requested for %s - no slow-query log configured",
            service_name,
        )
        return []


# Global performance monitor instance
performance_monitor = PerformanceMonitor()


async def main():
    """
    Start the performance monitor for a predefined set of services and run continuous health checks.

    Starts monitoring for core_api, websocket_service, integration_hub, and frontend_service with a 30‑second collection interval, then enters a loop that sleeps 60 seconds and logs the overall system health score each minute. Handles KeyboardInterrupt by stopping monitoring and performing a graceful shutdown.
    """
    try:
        services = [
            "core_api",
            "websocket_service",
            "integration_hub",
            "frontend_service",
        ]
        await performance_monitor.start_monitoring(services, interval=30)

        # Keep running
        while True:
            await asyncio.sleep(60)

            # Get system health every minute
            health = await performance_monitor.get_system_health()
            logger.info("System health: %.1f/100", health.get("overall_health_score", 0.0))

    except KeyboardInterrupt:
        logger.info("Stopping performance monitoring...")
        await performance_monitor.stop_monitoring()


# ============================================================================
# OPERATION TIMING UTILITIES (Extracted from system_enhancement_utils.py)
# ============================================================================

import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field


@dataclass
class OperationMetrics:
    """Operation timing metrics"""

    operation_name: str
    start_time: float
    end_time: float | None = None
    duration: float | None = None
    success: bool = False
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def complete(self, success: bool = True, error_message: str | None = None) -> None:
        """Mark operation as complete"""
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
        self.success = success
        if error_message:
            self.error_message = error_message


@dataclass
class OperationTracker:
    """Tracks operation timing metrics"""

    operations: int = 0
    total_duration: float = 0.0
    successful_operations: int = 0
    failed_operations: int = 0
    operation_history: list[OperationMetrics] = field(default_factory=list)

    def record_operation(self, metrics: OperationMetrics) -> None:
        """Record a completed operation"""
        self.operations += 1
        self.operation_history.append(metrics)

        if metrics.duration:
            self.total_duration += metrics.duration

        if metrics.success:
            self.successful_operations += 1
        else:
            self.failed_operations += 1

    def get_summary(self) -> dict[str, Any]:
        """Get operation summary"""
        if self.operations == 0:
            return {
                "total_operations": 0,
                "success_rate": 0.0,
                "average_duration": 0.0,
                "total_duration": 0.0,
            }

        return {
            "total_operations": self.operations,
            "success_rate": round(self.successful_operations / self.operations, 3),
            "average_duration": round(self.total_duration / self.operations, 3),
            "total_duration": round(self.total_duration, 3),
            "failed_operations": self.failed_operations,
        }

    def reset(self) -> None:
        """Reset all metrics"""
        self.operations = 0
        self.total_duration = 0.0
        self.successful_operations = 0
        self.failed_operations = 0
        self.operation_history.clear()


class OperationTimer:
    """
    Operation timing utility for agent operations

    Provides context managers and decorators for timing operations
    """

    def __init__(self) -> None:
        self.tracker = OperationTracker()
        self.active_operations: dict[str, OperationMetrics] = {}

    @asynccontextmanager
    async def track_operation(self, operation_name: str, metadata: dict[str, Any] | None = None):
        """
        Context manager to track operation performance

        Usage:
            async with timer.track_operation("agent_task"):
                # Your operation here
                pass
        """
        operation_id = f"{operation_name}_{time.time()}"
        metrics = OperationMetrics(
            operation_name=operation_name,
            start_time=time.time(),
            metadata=metadata or {},
        )

        self.active_operations[operation_id] = metrics

        try:
            yield metrics
            metrics.complete(success=True)
        except Exception as e:
            error_msg = str(e)
            metrics.complete(success=False, error_message=error_msg)
            logger.error("Operation %s failed: %s", operation_name, error_msg)
            raise
        finally:
            self.tracker.record_operation(metrics)
            self.active_operations.pop(operation_id, None)

    async def time_operation(
        self,
        operation_name: str,
        operation_func,
        *args,
        metadata: dict[str, Any] | None = None,
        **kwargs,
    ) -> Any:
        """
        Time an operation and record metrics

        Args:
            operation_name: Name of the operation
            operation_func: Async function to time
            *args: Arguments for the function
            metadata: Additional metadata to record
            **kwargs: Keyword arguments for the function

        Returns:
            Result of the operation
        """
        async with self.track_operation(operation_name, metadata):
            result = await operation_func(*args, **kwargs)
            return result

    def get_operation_report(self) -> dict[str, Any]:
        """Get comprehensive operation report"""
        summary = self.tracker.get_summary()

        # Add recent operations
        recent_ops = self.tracker.operation_history[-10:]  # Last 10 operations

        return {
            "summary": summary,
            "recent_operations": [
                {
                    "name": op.operation_name,
                    "duration": op.duration,
                    "success": op.success,
                    "error": op.error_message,
                    "metadata": op.metadata,
                }
                for op in recent_ops
            ],
            "active_operations": len(self.active_operations),
        }

    def get_operation_stats(self, operation_name: str) -> dict[str, Any]:
        """Get statistics for a specific operation type"""
        ops = [op for op in self.tracker.operation_history if op.operation_name == operation_name]

        if not ops:
            return {"operation": operation_name, "count": 0}

        durations = [op.duration for op in ops if op.duration]
        successful = [op for op in ops if op.success]

        return {
            "operation": operation_name,
            "count": len(ops),
            "success_rate": len(successful) / len(ops) if ops else 0,
            "average_duration": sum(durations) / len(durations) if durations else 0,
            "min_duration": min(durations) if durations else 0,
            "max_duration": max(durations) if durations else 0,
        }


# Global operation timer instance
operation_timer = OperationTimer()


async def monitor_agent_operation(operation_name: str, agent_func, *args, **kwargs) -> Any:
    """
    Convenience function to monitor agent operations

    Args:
        operation_name: Name of the operation
        agent_func: Agent function to monitor
        *args: Arguments for the function
        **kwargs: Keyword arguments for the function

    Returns:
        Result of the agent operation
    """
    return await operation_timer.time_operation(operation_name, agent_func, *args, **kwargs)


if __name__ == "__main__":
    asyncio.run(main())

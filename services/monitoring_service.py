"""
🌀 Helix Collective - Monitoring & Alerting Service
Real-time system monitoring, metrics collection, and alerting

NOTE: LEGACY — superseded by apps/backend/routes/monitoring_endpoints.py which has
circuit breakers, retry policies, advanced health checks, and is already registered
in router_registry. This file is retained for reference but is NOT wired to the app.
"""

import asyncio
import logging
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from apps.backend.utils.database_helpers import get_database_helpers

logger = logging.getLogger(__name__)

# Auth dependency — fail closed if import fails
try:
    from apps.backend.core.unified_auth import get_current_user
except ImportError:
    logger.warning("Could not import get_current_user for monitoring service")

    async def get_current_user():
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="Auth service unavailable")


# ============================================================================
# MODELS
# ============================================================================


class Metric(BaseModel):
    """System metric"""

    name: str
    value: float
    timestamp: datetime
    tags: dict[str, str] = {}
    unit: str = ""


class Alert(BaseModel):
    """System alert"""

    id: str
    severity: str  # critical, warning, info
    title: str
    message: str
    service: str
    timestamp: datetime
    acknowledged: bool = False
    resolved: bool = False


class HealthCheck(BaseModel):
    """Service health check result"""

    service: str
    status: str  # healthy, degraded, down
    response_time_ms: float
    timestamp: datetime
    details: dict[str, Any] = {}


# ============================================================================
# MONITORING SERVICE
# ============================================================================


class MonitoringService:
    """Comprehensive monitoring and alerting service"""

    def __init__(self) -> None:
        self.router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])
        self.metrics_store = defaultdict(list)
        self.alerts = []
        self.health_checks = {}
        self._setup_routes()

        # Start background monitoring tasks
        self.monitoring_active = False

    def _setup_routes(self):
        """Setup monitoring routes"""

        @self.router.post("/metrics")
        async def record_metric(metric: Metric, user=Depends(get_current_user)):
            """Record a system metric"""
            # Store in memory
            self.metrics_store[metric.name].append(metric)

            # Keep only last 1000 metrics per type in memory
            if len(self.metrics_store[metric.name]) > 1000:
                self.metrics_store[metric.name] = self.metrics_store[metric.name][-1000:]

            # Persist to database
            try:

                db_helpers = await get_database_helpers()
                if db_helpers:
                    await db_helpers.record_metric(
                        name=metric.name,
                        value=metric.value,
                        tags=metric.tags,
                        unit=metric.unit,
                    )
            except (ConnectionError, TimeoutError) as e:
                logger.debug("Database connection error persisting metric: %s", e)
            except Exception as e:
                logger.warning("Failed to persist metric to database: %s", e)

            # Check for alert conditions
            await self._check_metric_thresholds(metric)

            return {"status": "recorded"}

        @self.router.get("/metrics/{metric_name}")
        async def get_metrics(
            metric_name: str, since: datetime | None = None, limit: int = 100, user=Depends(get_current_user)
        ) -> list[Metric]:
            """Get historical metrics"""
            try:
                db_helpers = await get_database_helpers()
                if db_helpers:
                    # Fetch from database
                    db_metrics = await db_helpers.get_recent_metrics(metric_name, limit=limit)

                    if db_metrics:
                        return [
                            Metric(
                                name=m["name"],
                                value=m["value"],
                                timestamp=m["timestamp"],
                                tags=m.get("tags", {}),
                                unit=m.get("unit", ""),
                            )
                            for m in db_metrics
                        ]
            except Exception as e:
                logger.warning("Failed to fetch metrics from database: %s", e)

            # Fallback to in-memory store
            metrics = self.metrics_store.get(metric_name, [])

            if since:
                metrics = [m for m in metrics if m.timestamp >= since]

            return metrics[-limit:]

        @self.router.get("/metrics/summary/all")
        async def get_metrics_summary(user=Depends(get_current_user)) -> dict[str, Any]:
            """Get summary of all metrics"""
            summary = {}

            for metric_name, metrics in self.metrics_store.items():
                if not metrics:
                    continue

                recent = metrics[-10:]
                values = [m.value for m in recent]

                summary[metric_name] = {
                    "current": values[-1] if values else 0,
                    "avg": sum(values) / len(values) if values else 0,
                    "min": min(values) if values else 0,
                    "max": max(values) if values else 0,
                    "count": len(metrics),
                }

            return summary

        @self.router.get("/health")
        async def get_health_status() -> dict[str, HealthCheck]:
            """Get health status of all services"""
            # Perform health checks
            await self._perform_health_checks()
            return self.health_checks

        @self.router.get("/alerts")
        async def get_alerts(
            severity: str | None = None, resolved: bool | None = None, user=Depends(get_current_user)
        ) -> list[Alert]:
            """Get system alerts"""
            try:
                db_helpers = await get_database_helpers()
                if db_helpers:
                    # Fetch from database
                    if resolved is False:
                        db_alerts = await db_helpers.get_unresolved_alerts()
                    else:
                        # Get all alerts logic would go here
                        db_alerts = await db_helpers.get_unresolved_alerts()

                    if db_alerts:
                        return [
                            Alert(
                                id=a["id"],
                                severity=a["severity"],
                                title=a["title"],
                                message=a["message"],
                                service=a["service"],
                                timestamp=a["timestamp"],
                                acknowledged=a.get("acknowledged", False),
                                resolved=a.get("resolved", False),
                            )
                            for a in db_alerts
                            if (severity is None or a["severity"] == severity)
                        ]
            except Exception as e:
                logger.warning("Failed to fetch alerts from database: %s", e)

            # Fallback to in-memory store
            filtered = self.alerts

            if severity:
                filtered = [a for a in filtered if a.severity == severity]

            if resolved is not None:
                filtered = [a for a in filtered if a.resolved == resolved]

            return sorted(filtered, key=lambda x: x.timestamp, reverse=True)

        @self.router.post("/alerts/{alert_id}/acknowledge")
        async def acknowledge_alert(alert_id: str, user=Depends(get_current_user)):
            """Acknowledge an alert"""
            try:
                db_helpers = await get_database_helpers()
                if db_helpers:
                    await db_helpers.acknowledge_alert(alert_id, "system")
                    logger.info("Alert acknowledged: %s", alert_id)
            except Exception as e:
                logger.warning("Failed to acknowledge alert in database: %s", e)

            # Also update in-memory store
            for alert in self.alerts:
                if alert.id == alert_id:
                    alert.acknowledged = True
                    return {"status": "acknowledged"}

            return {"status": "acknowledged"}

        @self.router.post("/alerts/{alert_id}/resolve")
        async def resolve_alert(alert_id: str, user=Depends(get_current_user)):
            """Resolve an alert"""
            try:
                db_helpers = await get_database_helpers()
                if db_helpers:
                    await db_helpers.resolve_alert(alert_id, "system")
                    logger.info("Alert resolved: %s", alert_id)
            except Exception as e:
                logger.warning("Failed to resolve alert in database: %s", e)

            # Also update in-memory store
            for alert in self.alerts:
                if alert.id == alert_id:
                    alert.resolved = True
                    return {"status": "resolved"}

            return {"status": "resolved"}

        @self.router.get("/stats/performance")
        async def get_performance_stats(user=Depends(get_current_user)) -> dict[str, Any]:
            """Get live performance statistics from psutil."""
            import psutil

            cpu = psutil.cpu_percent(interval=0)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")

            # Derive response-time percentiles from stored metrics if available
            rt_metrics = [m.value for m in self.metrics_store.get("api_response_time_ms", [])]
            if len(rt_metrics) >= 3:
                rt_sorted = sorted(rt_metrics)
                n = len(rt_sorted)
                p50 = rt_sorted[int(n * 0.5)]
                p95 = rt_sorted[int(n * 0.95)]
                p99 = rt_sorted[min(int(n * 0.99), n - 1)]
            else:
                p50, p95, p99 = 0.0, 0.0, 0.0

            return {
                "api_response_time": {
                    "p50": round(p50, 1),
                    "p95": round(p95, 1),
                    "p99": round(p99, 1),
                },
                "throughput_rps": len(rt_metrics),
                "error_rate": 0.0,
                "active_connections": sum(len(v) for v in self.metrics_store.values()),
                "cpu_usage_percent": round(cpu, 1),
                "memory_usage_percent": round(mem.percent, 1),
                "disk_usage_percent": round(disk.percent, 1),
            }

    async def _check_metric_thresholds(self, metric: Metric):
        """Check if metric exceeds thresholds and create alerts"""
        # Define thresholds
        thresholds = {
            "api_response_time_ms": {"warning": 200, "critical": 500},
            "error_rate": {"warning": 0.05, "critical": 0.10},
            "cpu_usage_percent": {"warning": 80, "critical": 95},
            "memory_usage_percent": {"warning": 85, "critical": 95},
        }

        if metric.name in thresholds:
            threshold = thresholds[metric.name]

            if metric.value >= threshold.get("critical", float("inf")):
                await self._create_alert(
                    severity="critical",
                    title=f"Critical: {metric.name}",
                    message=f"{metric.name} is {metric.value}{metric.unit} (threshold: {threshold['critical']})",
                    service=metric.tags.get("service", "unknown"),
                )
            elif metric.value >= threshold.get("warning", float("inf")):
                await self._create_alert(
                    severity="warning",
                    title=f"Warning: {metric.name}",
                    message=f"{metric.name} is {metric.value}{metric.unit} (threshold: {threshold['warning']})",
                    service=metric.tags.get("service", "unknown"),
                )

    async def _create_alert(self, severity: str, title: str, message: str, service: str):
        """Create a new alert"""
        # Check if similar alert already exists
        similar = [
            a
            for a in self.alerts
            if a.title == title
            and not a.resolved
            and (datetime.now(UTC) - a.timestamp) < timedelta(minutes=15)
        ]

        if similar:
            return  # Don't create duplicate alerts within 15 minutes

        alert_id = f"alert_{int(time.time())}_{len(self.alerts)}"

        alert = Alert(
            id=alert_id,
            severity=severity,
            title=title,
            message=message,
            service=service,
            timestamp=datetime.now(UTC),
        )

        self.alerts.append(alert)
        logger.warning("Alert created: [%s] %s - %s", severity.upper(), title, message)

        # Persist to database
        try:
            db_helpers = await get_database_helpers()
            if db_helpers:
                await db_helpers.create_alert(
                    alert_id=alert_id,
                    severity=severity,
                    title=title,
                    message=message,
                    service=service,
                )
        except Exception as e:
            logger.warning("Failed to persist alert to database: %s", e)

        # Keep only last 1000 alerts in memory
        if len(self.alerts) > 1000:
            self.alerts = self.alerts[-1000:]

    async def _perform_health_checks(self):
        """Perform health checks on all services"""
        services = [
            "core_api",
            "websocket",
            "integration_hub",
            "frontend",
            "database",
            "redis",
        ]

        for service in services:
            start = time.time()

            try:
                status = "healthy"
                details = {}

                if service == "database":
                    # Actually ping the database
                    try:
                        from apps.backend.core.unified_auth import Database

                        pool = await Database.connect()
                        async with pool.acquire() as conn:
                            row = await conn.fetchval("SELECT 1")
                            pool_size = pool.get_size()
                            pool_free = pool.get_idle_size()
                        details = {
                            "connections": pool_size,
                            "idle_connections": pool_free,
                            "ping": "ok" if row == 1 else "unexpected",
                        }
                    except Exception as db_err:
                        status = "degraded"
                        logger.warning("Database health check failed: %s", db_err)
                        details = {"error": "Database connection failed"}
                elif service == "redis":
                    # Actually ping Redis
                    try:
                        from apps.backend.core.redis_client import get_redis

                        r = await get_redis()
                        if r:
                            await r.ping()
                            info = await r.info(section="clients")
                            mem_info = await r.info(section="memory")
                            details = {
                                "connected_clients": info.get("connected_clients", 0),
                                "memory_used_mb": round(
                                    mem_info.get("used_memory", 0) / (1024 * 1024),
                                    1,
                                ),
                                "ping": "ok",
                            }
                        else:
                            status = "degraded"
                            details = {"error": "Redis client unavailable"}
                    except Exception as redis_err:
                        status = "degraded"
                        logger.warning("Redis health check failed: %s", redis_err)
                        details = {"error": "Redis connection failed"}

                response_time = (time.time() - start) * 1000

                health_check = HealthCheck(
                    service=service,
                    status=status,
                    response_time_ms=response_time,
                    timestamp=datetime.now(UTC),
                    details=details,
                )

                self.health_checks[service] = health_check

                # Persist to database
                try:
                    db_helpers = await get_database_helpers()
                    if db_helpers:
                        await db_helpers.record_health_check(
                            service=service,
                            status=status,
                            response_time_ms=response_time,
                            details=details,
                        )
                except Exception as e:
                    logger.warning("Failed to persist health check to database: %s", e)

            except Exception as e:
                logger.error("Health check failed for %s: %s", service, e)
                self.health_checks[service] = HealthCheck(
                    service=service,
                    status="down",
                    response_time_ms=0,
                    timestamp=datetime.now(UTC),
                    details={"error": "Health check failed"},
                )

    async def start_monitoring(self):
        """Start background monitoring tasks"""
        if self.monitoring_active:
            return

        self.monitoring_active = True
        logger.info("🔍 Starting monitoring service")

        # Start monitoring loops
        asyncio.create_task(self._monitor_system_metrics())
        asyncio.create_task(self._monitor_service_health())

    async def _monitor_system_metrics(self):
        """Background task to collect system metrics"""
        while self.monitoring_active:
            try:
                import psutil

                # CPU metrics
                cpu_percent = psutil.cpu_percent(interval=1)
                await self.record_metric(
                    Metric(
                        name="cpu_usage_percent",
                        value=cpu_percent,
                        timestamp=datetime.now(UTC),
                        unit="%",
                    )
                )

                # Memory metrics
                memory = psutil.virtual_memory()
                await self.record_metric(
                    Metric(
                        name="memory_usage_percent",
                        value=memory.percent,
                        timestamp=datetime.now(UTC),
                        unit="%",
                    )
                )

                # Disk metrics
                disk = psutil.disk_usage("/")
                await self.record_metric(
                    Metric(
                        name="disk_usage_percent",
                        value=disk.percent,
                        timestamp=datetime.now(UTC),
                        unit="%",
                    )
                )

            except ImportError:
                logger.warning("psutil not available, skipping system metrics")
            except Exception as e:
                logger.error("Error collecting system metrics: %s", e)

            await asyncio.sleep(60)  # Collect every minute

    async def _monitor_service_health(self):
        """Background task to monitor service health"""
        while self.monitoring_active:
            try:
                await self._check_service_health()
            except Exception as e:
                logger.error("Error during health check: %s", e)

            await asyncio.sleep(30)  # Check every 30 seconds


# ============================================================================
# INITIALIZATION
# ============================================================================

monitoring_service = MonitoringService()

# Export router for FastAPI app
router = monitoring_service.router


# Helper function to record metrics from other services
async def record_metric(name: str, value: float, tags: dict[str, str] = None, unit: str = ""):
    """Helper to record a metric"""
    metric = Metric(
        name=name,
        value=value,
        timestamp=datetime.now(UTC),
        tags=tags or {},
        unit=unit,
    )
    monitoring_service.metrics_store[name].append(metric)
    await monitoring_service._check_metric_thresholds(metric)

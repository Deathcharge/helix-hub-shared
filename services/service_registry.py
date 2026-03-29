"""
🌀 Helix Collective - Service Registry
Central registry for service discovery, health monitoring, and inter-service communication.

Supports:
- Service discovery for both monolith and 4-service architecture
- Circuit breaker pattern for fault tolerance
- Load balancing between mono and 4-service
- Redis pub/sub for inter-service messaging
"""

import asyncio
import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx
import redis

logger = logging.getLogger(__name__)


class ServiceStatus(Enum):
    """Service health status"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


class CircuitState(Enum):
    """Circuit breaker states"""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreaker:
    """Circuit breaker for fault tolerance"""

    failure_threshold: int = 5
    recovery_timeout: float = 30.0  # seconds
    half_open_max_calls: int = 3

    state: CircuitState = field(default=CircuitState.CLOSED)
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0.0
    half_open_calls: int = 0

    def record_success(self):
        """Record a successful call"""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.half_open_max_calls:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                logger.info("🔌 Circuit breaker CLOSED (service recovered)")
        else:
            self.failure_count = 0

    def record_failure(self):
        """Record a failed call"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            self.half_open_calls = 0
            logger.warning("🔌 Circuit breaker OPEN (failed during half-open)")
        elif self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning("🔌 Circuit breaker OPEN (threshold reached)")

    def can_execute(self) -> bool:
        """Check if a call can be made"""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                self.success_count = 0
                logger.info("🔌 Circuit breaker HALF-OPEN (testing recovery)")
                return True
            return False

        # Half-open state
        if self.half_open_calls < self.half_open_max_calls:
            self.half_open_calls += 1
            return True
        return False


class ServiceRegistry:
    """Central registry for service discovery, health monitoring, and load balancing"""

    def __init__(self) -> None:
        """Initialize service registry with environment-based configuration"""
        # Architecture mode: "mono", "distributed", or "hybrid"
        self.mode = os.getenv("HELIX_ARCHITECTURE_MODE", "hybrid")

        self.services = {
            # ============================================
            # MONOLITH (Primary - Production Ready)
            # ============================================
            "monolith": {
                "name": "Helix Monolith",
                "url": os.getenv("MONOLITH_URL", "http://localhost:8000"),
                "health_endpoint": "/health",
                "status": "unknown",
                "last_check": None,
                "response_time_ms": None,
                "priority": 1,  # Higher priority = preferred
                "architecture": "monolith",
                "capabilities": [
                    "api",
                    "websocket",
                    "voice",
                    "spirals",
                    "mcp",
                    "discord",
                    "agents",
                    "coordination",
                    "analytics",
                ],
            },
            # ============================================
            # 4-SERVICE ARCHITECTURE (Distributed)
            # ============================================
            "core_api": {
                "name": "Core API",
                "url": os.getenv("CORE_API_URL", "http://localhost:8001"),
                "health_endpoint": "/health/core",
                "status": "unknown",
                "last_check": None,
                "response_time_ms": None,
                "priority": 2,
                "architecture": "distributed",
                "capabilities": ["api", "agents", "coordination", "analytics"],
            },
            "websocket": {
                "name": "WebSocket Service",
                "url": os.getenv("WEBSOCKET_URL", "http://localhost:8002"),
                "health_endpoint": "/health/websocket",
                "status": "unknown",
                "last_check": None,
                "response_time_ms": None,
                "priority": 2,
                "architecture": "distributed",
                "capabilities": ["websocket", "resonance", "realtime"],
            },
            "integration_hub": {
                "name": "Integration Hub",
                "url": os.getenv("INTEGRATION_HUB_URL", "http://localhost:8003"),
                "health_endpoint": "/health/integration",
                "status": "unknown",
                "last_check": None,
                "response_time_ms": None,
                "priority": 2,
                "architecture": "distributed",
                "capabilities": ["voice", "discord", "zapier", "forum", "spirals"],
            },
            "frontend": {
                "name": "Frontend Service",
                "url": os.getenv("FRONTEND_URL", "http://localhost:3000"),
                "health_endpoint": "/api/health",
                "status": "unknown",
                "last_check": None,
                "response_time_ms": None,
                "priority": 2,
                "architecture": "distributed",
                "capabilities": ["web", "ui"],
            },
        }

        # Circuit breakers for each service
        self.circuit_breakers: dict[str, CircuitBreaker] = {name: CircuitBreaker() for name in self.services}

        # Request counters for load balancing
        self.request_counts: dict[str, int] = dict.fromkeys(self.services, 0)

        # Redis client for pub/sub (initialized lazily)
        self._redis = None
        self._pubsub = None
        self._message_handlers: dict[str, list[Callable]] = {}

        logger.info("🔍 Service Registry initialized (mode: %s)", self.mode)
        logger.info("   Services registered: %d", len(self.services))
        for name, config in self.services.items():
            logger.info("   - %s: %s [%s]", name, config["url"], config["architecture"])

    def get_service_url(self, service_name: str) -> str | None:
        """Get URL for a service"""
        service = self.services.get(service_name)
        return service["url"] if service else None

    def get_service_config(self, service_name: str) -> dict[str, Any] | None:
        """Get full configuration for a service"""
        return self.services.get(service_name)

    async def check_service_health(self, service_name: str) -> dict[str, Any]:
        """Check health of a specific service"""
        if service_name not in self.services:
            return {
                "status": "not_found",
                "error": f"Service {service_name} not registered",
            }

        config = self.services[service_name]
        start_time = time.time()

        try:
            url = f"{config['url']}{config['health_endpoint']}"
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url)

            response_time_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                config["status"] = "healthy"
                config["response_time_ms"] = response_time_ms
                config["last_check"] = time.time()
                logger.debug("✅ %s healthy (%dms)", service_name, response_time_ms)
            else:
                config["status"] = "degraded"
                config["response_time_ms"] = response_time_ms
                config["last_check"] = time.time()
                logger.warning("⚠️ %s degraded (status: %d)", service_name, response.status_code)

        except httpx.TimeoutException:
            config["status"] = "timeout"
            config["response_time_ms"] = None
            config["last_check"] = time.time()
            logger.warning("⏱️ %s timeout", service_name)

        except httpx.ConnectError:
            config["status"] = "offline"
            config["response_time_ms"] = None
            config["last_check"] = time.time()
            logger.warning("❌ %s offline (cannot connect)", service_name)

        except Exception as e:
            config["status"] = "error"
            config["response_time_ms"] = None
            config["last_check"] = time.time()
            logger.error("❌ %s error: %s", service_name, str(e))

        return {
            "service": service_name,
            "status": config["status"],
            "response_time_ms": config["response_time_ms"],
            "last_check": config["last_check"],
        }

    async def health_check_all(self) -> dict[str, Any]:
        """Check health of all services in parallel"""
        logger.info("🔍 Checking health of all services...")

        tasks = []
        for service_name in self.services.keys():
            tasks.append(self.check_service_health(service_name))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Count statuses
        healthy_count = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "healthy")
        total_count = len(self.services)

        overall_status = "healthy" if healthy_count == total_count else "degraded" if healthy_count > 0 else "critical"

        summary = {
            "overall_status": overall_status,
            "healthy_services": healthy_count,
            "total_services": total_count,
            "services": {r["service"]: r for r in results if isinstance(r, dict)},
            "timestamp": time.time(),
        }

        logger.info(
            "📊 Health check complete: %d/%d services healthy (status: %s)",
            healthy_count,
            total_count,
            overall_status,
        )

        return summary

    def get_all_services(self) -> dict[str, dict[str, Any]]:
        """Get all registered services"""
        return self.services.copy()

    def is_service_healthy(self, service_name: str) -> bool:
        """Check if a service is currently healthy"""
        service = self.services.get(service_name)
        return service is not None and service.get("status") == "healthy"

    # ========================================================================
    # LOAD BALANCING
    # ========================================================================

    def get_service_for_capability(self, capability: str) -> str | None:
        """
        Get the best service for a given capability using load balancing.

        Priority order:
        1. Healthy services with the capability
        2. Higher priority services (monolith=1, distributed=2)
        3. Lower request count (round-robin-ish)
        """
        candidates = []

        for name, config in self.services.items():
            # Check if service has the capability
            if capability not in config.get("capabilities", []):
                continue

            # Check circuit breaker
            breaker = self.circuit_breakers.get(name)
            if breaker and not breaker.can_execute():
                logger.debug("⚡ %s circuit breaker OPEN, skipping", name)
                continue

            # Check health status
            if config.get("status") == "healthy":
                candidates.append((name, config))

        if not candidates:
            # Fallback: try any service with the capability regardless of health
            for name, config in self.services.items():
                if capability in config.get("capabilities", []):
                    breaker = self.circuit_breakers.get(name)
                    if breaker and breaker.can_execute():
                        candidates.append((name, config))

        if not candidates:
            logger.warning("❌ No service available for capability: %s", capability)
            return None

        # Sort by priority (lower is better), then by request count
        candidates.sort(key=lambda x: (x[1].get("priority", 99), self.request_counts.get(x[0], 0)))

        selected = candidates[0][0]
        self.request_counts[selected] = self.request_counts.get(selected, 0) + 1

        logger.debug("🎯 Selected %s for capability '%s'", selected, capability)
        return selected

    def get_best_api_service(self) -> str:
        """Get the best service for API requests (load balanced)"""
        service = self.get_service_for_capability("api")
        return service or "monolith"  # Fallback to monolith

    def get_best_websocket_service(self) -> str:
        """Get the best service for WebSocket connections"""
        service = self.get_service_for_capability("websocket")
        return service or "monolith"

    def record_request_result(self, service_name: str, success: bool):
        """Record the result of a request for circuit breaker tracking"""
        breaker = self.circuit_breakers.get(service_name)
        if breaker:
            if success:
                breaker.record_success()
            else:
                breaker.record_failure()

    # ========================================================================
    # INTER-SERVICE COMMUNICATION (Redis Pub/Sub)
    # ========================================================================

    async def connect_redis(self):
        """Initialize Redis connection for pub/sub"""
        if self._redis:
            return

        try:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
            self._redis = redis.from_url(redis_url)
            self._pubsub = self._redis.pubsub()
            logger.info("🔗 Redis connected for inter-service messaging")
        except Exception as e:
            logger.warning("⚠️ Redis connection failed: %s", e)
            self._redis = None

    async def publish_event(self, channel: str, event: dict[str, Any]):
        """
        Publish an event to other services via Redis pub/sub.

        Channels:
        - helix:service:health - Health status updates
        - helix:service:discovery - Service registration/deregistration
        - helix:agents:status - Agent status changes
        - helix:coordination:update - UCF metric updates
        - helix:task:dispatch - Task distribution
        """
        if not self._redis:
            await self.connect_redis()

        if not self._redis:
            logger.debug("Redis not available, skipping publish")
            return

        try:
            message = json.dumps(
                {
                    "source": os.getenv("SERVICE_NAME", "unknown"),
                    "timestamp": time.time(),
                    "event": event,
                }
            )
            await self._redis.publish(channel, message)
            logger.debug("📤 Published to %s: %s", channel, event.get("type", "unknown"))
        except Exception as e:
            logger.error("Failed to publish event: %s", e)

    async def subscribe(self, channel: str, handler: Callable):
        """Subscribe to a channel and register a handler"""
        if not self._redis:
            await self.connect_redis()

        if not self._redis:
            logger.warning("Redis not available, cannot subscribe")
            return

        if channel not in self._message_handlers:
            self._message_handlers[channel] = []
            await self._pubsub.subscribe(channel)
            logger.info("📥 Subscribed to channel: %s", channel)

        self._message_handlers[channel].append(handler)

    async def start_message_listener(self):
        """Start listening for messages on subscribed channels"""
        if not self._pubsub:
            return

        logger.info("👂 Starting inter-service message listener")

        async for message in self._pubsub.listen():
            if message["type"] == "message":
                channel = message["channel"]
                if isinstance(channel, bytes):
                    channel = channel.decode()

                try:
                    data = json.loads(message["data"])
                    handlers = self._message_handlers.get(channel, [])
                    for handler in handlers:
                        try:
                            if asyncio.iscoroutinefunction(handler):
                                await handler(data)
                            else:
                                handler(data)
                        except Exception as e:
                            logger.error("Handler error for %s: %s", channel, e)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON in message on %s", channel)

    # ========================================================================
    # SERVICE-TO-SERVICE CALLS
    # ========================================================================

    async def call_service(
        self,
        service_name: str,
        endpoint: str,
        method: str = "GET",
        data: dict | None = None,
        timeout: float = 5.0,
    ) -> dict[str, Any] | None:
        """
        Make a request to another service with circuit breaker protection.

        Returns the response data or None if the request failed.
        """
        config = self.services.get(service_name)
        if not config:
            logger.error("Unknown service: %s", service_name)
            return None

        breaker = self.circuit_breakers.get(service_name)
        if breaker and not breaker.can_execute():
            logger.warning("Circuit breaker OPEN for %s", service_name)
            return None

        url = f"{config['url']}{endpoint}"
        start_time = time.time()

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if method.upper() == "GET":
                    response = await client.get(url)
                elif method.upper() == "POST":
                    response = await client.post(url, json=data)
                elif method.upper() == "PUT":
                    response = await client.put(url, json=data)
                elif method.upper() == "DELETE":
                    response = await client.delete(url)
                else:
                    logger.error("Unsupported method: %s", method)
                    return None

            elapsed_ms = int((time.time() - start_time) * 1000)

            if response.status_code < 400:
                self.record_request_result(service_name, True)
                logger.debug(
                    "✅ %s %s -> %d (%dms)",
                    method,
                    url,
                    response.status_code,
                    elapsed_ms,
                )
                return response.json()
            else:
                self.record_request_result(service_name, False)
                logger.warning(
                    "⚠️ %s %s -> %d (%dms)",
                    method,
                    url,
                    response.status_code,
                    elapsed_ms,
                )
                return None

        except httpx.TimeoutException:
            self.record_request_result(service_name, False)
            logger.warning("⏱️ Timeout calling %s", url)
            return None

        except httpx.ConnectError:
            self.record_request_result(service_name, False)
            logger.warning("❌ Cannot connect to %s", url)
            return None

        except Exception as e:
            self.record_request_result(service_name, False)
            logger.error("Error calling %s: %s", url, e)
            return None

    # ========================================================================
    # HYBRID MODE HELPERS
    # ========================================================================

    def get_architecture_status(self) -> dict[str, Any]:
        """Get the status of both architectures"""
        mono_healthy = self.is_service_healthy("monolith")
        distributed_services = ["core_api", "websocket", "integration_hub", "frontend"]
        distributed_healthy = sum(1 for s in distributed_services if self.is_service_healthy(s))

        return {
            "mode": self.mode,
            "monolith": {
                "healthy": mono_healthy,
                "url": self.services["monolith"]["url"],
                "status": self.services["monolith"]["status"],
            },
            "distributed": {
                "healthy_services": distributed_healthy,
                "total_services": len(distributed_services),
                "services": {
                    s: {
                        "healthy": self.is_service_healthy(s),
                        "url": self.services[s]["url"],
                        "status": self.services[s]["status"],
                    }
                    for s in distributed_services
                },
            },
            "recommended_target": (
                "monolith" if mono_healthy else ("distributed" if distributed_healthy >= 2 else "none")
            ),
            "circuit_breakers": {
                name: {
                    "state": breaker.state.value,
                    "failures": breaker.failure_count,
                }
                for name, breaker in self.circuit_breakers.items()
            },
        }


# Global service registry instance
registry = ServiceRegistry()


# ============================================================================
# INTER-SERVICE MESSAGE TYPES
# ============================================================================


class ServiceEvent:
    """Standard event types for inter-service communication"""

    # Health events
    HEALTH_UPDATE = "health_update"
    SERVICE_ONLINE = "service_online"
    SERVICE_OFFLINE = "service_offline"

    # Agent events
    AGENT_STATUS_CHANGE = "agent_status_change"
    AGENT_TASK_COMPLETE = "agent_task_complete"
    AGENT_ERROR = "agent_error"

    # Coordination events
    UCF_UPDATE = "ucf_update"
    RESONANCE_PEAK = "resonance_peak"
    CYCLE_TRIGGERED = "cycle_triggered"

    # Task events
    TASK_DISPATCH = "task_dispatch"
    TASK_RESULT = "task_result"
    TASK_FAILED = "task_failed"


async def broadcast_health_update(service_name: str, status: str):
    """Broadcast a health status update to all services"""
    await registry.publish_event(
        "helix:service:health",
        {
            "type": ServiceEvent.HEALTH_UPDATE,
            "service": service_name,
            "status": status,
        },
    )


async def broadcast_agent_status(agent_id: str, status: dict[str, Any]):
    """Broadcast agent status change to all services"""
    await registry.publish_event(
        "helix:agents:status",
        {
            "type": ServiceEvent.AGENT_STATUS_CHANGE,
            "agent_id": agent_id,
            "status": status,
        },
    )


async def dispatch_task(task: dict[str, Any], target_capability: str = "api"):
    """Dispatch a task to the best available service"""
    service = registry.get_service_for_capability(target_capability)
    if service:
        await registry.publish_event(
            "helix:task:dispatch",
            {
                "type": ServiceEvent.TASK_DISPATCH,
                "target_service": service,
                "task": task,
            },
        )

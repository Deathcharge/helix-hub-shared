"""
🌀 Helix Collective - Internal HTTP Client
HTTP client for secure inter-service communication with circuit breaker

Usage:
    from apps.backend.services.internal_client import InternalHTTPClient
    client = InternalHTTPClient(service_name="core-api")
    response = await client.get("websocket-service", "/api/health")

Requires service URLs in the service registry (service_registry.py).
"""

import logging
import time
import uuid
from enum import Enum
from typing import Any

import httpx

from apps.backend.services.service_registry import registry

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states"""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Circuit tripped, rejecting requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """Circuit breaker for fault tolerance"""

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout_seconds: int = 30,
        half_open_max_calls: int = 3,
    ):
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.half_open_max_calls = half_open_max_calls

        self.failure_count = 0
        self.state = CircuitState.CLOSED
        self.last_failure_time = None
        self.half_open_calls = 0

    def call_succeeded(self):
        """Record successful call"""
        if self.state == CircuitState.HALF_OPEN:
            logger.info("🔄 Circuit breaker: Service recovered, closing circuit")
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.half_open_calls = 0
        elif self.state == CircuitState.CLOSED:
            self.failure_count = max(0, self.failure_count - 1)

    def call_failed(self):
        """Record failed call"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            logger.warning("🔴 Circuit breaker: Half-open test failed, reopening circuit")
            self.state = CircuitState.OPEN
            self.half_open_calls = 0
        elif self.failure_count >= self.failure_threshold:
            logger.error(
                "🔴 Circuit breaker: Threshold reached (%d failures), opening circuit",
                self.failure_count,
            )
            self.state = CircuitState.OPEN

    def can_execute(self) -> bool:
        """Check if call should be allowed"""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if timeout has elapsed
            if self.last_failure_time and time.time() - self.last_failure_time > self.timeout_seconds:
                logger.info("🟡 Circuit breaker: Timeout elapsed, entering half-open state")
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            # Allow limited calls in half-open state
            if self.half_open_calls < self.half_open_max_calls:
                self.half_open_calls += 1
                return True
            return False

        return False


class InternalHTTPClient:
    """HTTP client for inter-service communication with circuit breaker"""

    def __init__(self, service_name: str = "unknown") -> None:
        """Initialize internal HTTP client

        Args:
            service_name: Name of the calling service (for logging/tracing)
        """
        self.service_name = service_name
        self.client = httpx.AsyncClient(timeout=10.0)
        self.circuit_breakers: dict[str, CircuitBreaker] = {}
        logger.info("🔌 Internal HTTP client initialized for %s", service_name)

    def _get_circuit_breaker(self, service_name: str) -> CircuitBreaker:
        """Get or create circuit breaker for a service"""
        if service_name not in self.circuit_breakers:
            self.circuit_breakers[service_name] = CircuitBreaker()
        return self.circuit_breakers[service_name]

    async def call_service(
        self,
        service_name: str,
        endpoint: str,
        method: str = "GET",
        request_id: str | None = None,
        **kwargs,
    ) -> httpx.Response:
        """Call another internal service with circuit breaker protection

        Args:
            service_name: Name of the service to call
            endpoint: API endpoint path
            method: HTTP method (GET, POST, PUT, DELETE)
            request_id: Optional request ID for tracing
            **kwargs: Additional arguments passed to httpx request

        Returns:
            httpx.Response object

        Raises:
            ServiceNotFoundError: If service not registered
            CircuitBreakerOpenError: If circuit breaker is open
            httpx exceptions for other failures
        """
        # Get circuit breaker
        circuit_breaker = self._get_circuit_breaker(service_name)

        # Check circuit breaker
        if not circuit_breaker.can_execute():
            logger.warning(
                "🔴 Circuit breaker OPEN for %s, rejecting call to %s",
                service_name,
                endpoint,
            )
            raise CircuitBreakerOpenError(f"Circuit breaker is open for {service_name}")

        # Get service URL from registry
        service_url = registry.get_service_url(service_name)
        if not service_url:
            logger.error("❌ Service %s not found in registry", service_name)
            raise ServiceNotFoundError(f"Service {service_name} not found in registry")

        # Generate request ID if not provided
        if not request_id:
            request_id = str(uuid.uuid4())

        # Build full URL
        url = f"{service_url}{endpoint}"

        # Add tracing headers
        if "headers" not in kwargs:
            kwargs["headers"] = {}
        kwargs["headers"]["X-Request-ID"] = request_id
        kwargs["headers"]["X-Source-Service"] = self.service_name

        # Log request
        logger.info(
            "🔌 [%s] %s → %s %s",
            request_id[:8],
            self.service_name,
            method,
            url,
        )

        start_time = time.time()

        try:
            response = await self.client.request(method, url, **kwargs)

            # Record success
            circuit_breaker.call_succeeded()

            # Log response
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "✅ [%s] %s responded: %d (%dms)",
                request_id[:8],
                service_name,
                response.status_code,
                elapsed_ms,
            )

            return response

        except httpx.TimeoutException:
            circuit_breaker.call_failed()
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "⏱️ [%s] Timeout calling %s%s (%dms)",
                request_id[:8],
                service_name,
                endpoint,
                elapsed_ms,
            )
            raise

        except httpx.ConnectError as e:
            circuit_breaker.call_failed()
            logger.error(
                "❌ [%s] Cannot connect to %s: %s",
                request_id[:8],
                service_name,
                str(e),
            )
            raise

        except Exception as e:
            circuit_breaker.call_failed()
            logger.error(
                "❌ [%s] Error calling %s%s: %s",
                request_id[:8],
                service_name,
                endpoint,
                str(e),
            )
            raise

    async def get(self, service_name: str, endpoint: str, **kwargs) -> httpx.Response:
        """GET request to another service"""
        return await self.call_service(service_name, endpoint, "GET", **kwargs)

    async def post(self, service_name: str, endpoint: str, **kwargs) -> httpx.Response:
        """POST request to another service"""
        return await self.call_service(service_name, endpoint, "POST", **kwargs)

    async def put(self, service_name: str, endpoint: str, **kwargs) -> httpx.Response:
        """PUT request to another service"""
        return await self.call_service(service_name, endpoint, "PUT", **kwargs)

    async def delete(self, service_name: str, endpoint: str, **kwargs) -> httpx.Response:
        """DELETE request to another service"""
        return await self.call_service(service_name, endpoint, "DELETE", **kwargs)

    def get_circuit_status(self, service_name: str) -> dict[str, Any]:
        """Get circuit breaker status for a service"""
        circuit_breaker = self._get_circuit_breaker(service_name)
        return {
            "service": service_name,
            "state": circuit_breaker.state.value,
            "failure_count": circuit_breaker.failure_count,
            "last_failure_time": circuit_breaker.last_failure_time,
        }

    def get_all_circuit_status(self) -> dict[str, dict[str, Any]]:
        """Get status of all circuit breakers"""
        return {service_name: self.get_circuit_status(service_name) for service_name in self.circuit_breakers.keys()}

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()


class ServiceNotFoundError(Exception):
    """Raised when service is not found in registry"""


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open"""

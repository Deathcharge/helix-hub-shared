"""
Helix Collective - Backend Services Package

Provides access to the hybrid architecture services:
- Core API: Main API endpoints and business logic
- WebSocket Service: Real-time coordination streaming
- Integration Hub: External integrations and webhooks
- API Gateway: Load balancing and intelligent routing
- Service Registry: Service discovery and health monitoring
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

from .service_registry import (
    CircuitBreaker,
    CircuitState,
    ServiceEvent,
    ServiceRegistry,
    broadcast_health_update,
    registry,
)

if TYPE_CHECKING:
    from fastapi import FastAPI


# Data hygiene for text preprocessing
try:
    from .data_hygiene import DataHygiene
except ImportError as e:
    logger.debug("DataHygiene module not available: %s", e)


# Lazy imports to avoid circular dependencies
def get_core_api() -> FastAPI:
    """Get the Core API FastAPI app"""
    from .core_api import app

    return app


def get_websocket_service() -> FastAPI:
    """Get the WebSocket Service FastAPI app"""
    from .websocket_service import app

    return app


def get_integration_hub() -> FastAPI:
    """Get the Integration Hub FastAPI app"""
    from .integration_hub import app

    return app


def get_api_gateway() -> FastAPI:
    """Get the API Gateway FastAPI app"""
    from .api_gateway import app

    return app


__all__ = [
    # Service Registry
    "ServiceRegistry",
    "registry",
    "CircuitBreaker",
    "CircuitState",
    "ServiceEvent",
    "broadcast_health_update",
    # Lazy app getters
    "get_core_api",
    "get_websocket_service",
    "get_integration_hub",
    "get_api_gateway",
]

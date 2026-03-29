"""
🌀 Coordination Metrics WebSocket Service
Real-time UCF metrics broadcasting for live dashboard updates

Provides WebSocket endpoint for streaming coordination field metrics
to connected frontend clients with 1-second update intervals.
"""

import asyncio
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from apps.backend.services.ucf_calculator import UCFCalculator

# Auth import — fail closed if unavailable
try:
    from apps.backend.core.auth import AuthManager

    _auth_available = True
except ImportError:
    _auth_available = False

logger = logging.getLogger(__name__)


# Global connection manager for metrics broadcasting
class MetricsConnectionManager:
    """Manage active WebSocket connections for metrics broadcasting."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self.ucf_calculator = UCFCalculator()

    async def connect(self, websocket: WebSocket, client_id: str):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("📊 Metrics WebSocket connected: %s", client_id)

    async def disconnect(self, websocket: WebSocket, client_id: str):
        """Remove a disconnected WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("📊 Metrics WebSocket disconnected: %s", client_id)

    async def broadcast_metrics(self):
        """Broadcast current UCF metrics to all connected clients."""
        try:
            metrics = self.ucf_calculator.get_detailed_state()

            message = {
                "type": "metrics_update",
                "timestamp": datetime.now(UTC).isoformat(),
                "throughput": metrics.get("throughput", 0.0),
                "focus": metrics.get("focus", 0.0),
                "friction": metrics.get("friction", 0.0),
                "harmony": metrics.get("harmony", 0.0),
                "resilience": metrics.get("resilience", 0.0),
                "performance_score": metrics.get("performance_score", 1),
                "field_stability": metrics.get("field_stability", 0.0),
                "system_coherence": metrics.get("system_coherence", 0.0),
            }

            # Send to all connected clients
            disconnected_clients = []
            for connection in self.active_connections:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error("Failed to send metrics to client: %s", e)
                    disconnected_clients.append(connection)

            # Clean up disconnected clients
            for client in disconnected_clients:
                await self.disconnect(client, "unknown")

        except Exception as e:
            logger.error("Error broadcasting metrics: %s", e)


# Global manager instance
manager = MetricsConnectionManager()

# Create router for the metrics endpoints
router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.websocket("/ws/{client_id}")
async def websocket_metrics_endpoint(websocket: WebSocket, client_id: str, token: str = Query(None)):
    """
    WebSocket endpoint for real-time coordination metrics streaming.

    Broadcasts UCF metrics every second to connected dashboard clients.
    Requires JWT token via ?token= query parameter.
    """
    # Validate JWT token before accepting connection
    if _auth_available:
        # Also check httpOnly cookie if no query token
        cookie_token = websocket.cookies.get("helix_auth_token")
        effective_token = token or cookie_token
        if not effective_token:
            await websocket.close(code=1008, reason="Authentication required — missing token parameter")
            return
        try:
            AuthManager.verify_token(effective_token)
        except (ValueError, TypeError, KeyError) as e:
            logger.debug("Token verification validation error: %s", e)
            await websocket.close(code=1008, reason="Invalid or expired token")
            return
        except Exception as e:
            logger.warning("Token verification failed: %s", e)
            await websocket.close(code=1008, reason="Invalid or expired token")
            return
    else:
        logger.error("Auth module unavailable — rejecting metrics WS connection")
        await websocket.close(code=1013, reason="Authentication service unavailable")
        return

    await manager.connect(websocket, client_id)

    try:
        await manager.broadcast_metrics()

        # Main broadcast loop - send metrics every 1 second
        while True:
            await manager.broadcast_metrics()
            await asyncio.sleep(1)  # Update every 1 second

    except WebSocketDisconnect:
        logger.info("📊 Metrics client disconnected: %s", client_id)
    except Exception as e:
        logger.error("Metrics WebSocket error for %s: %s", client_id, e)
    finally:
        await manager.disconnect(websocket, client_id)


@router.get("/current")
async def get_current_metrics():
    """
    REST endpoint for current coordination metrics.
    Useful for initial page loads or API consumers.
    """
    try:
        metrics = manager.ucf_calculator.get_detailed_state()
        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "metrics": {
                "throughput": metrics.get("throughput", 0.0),
                "focus": metrics.get("focus", 0.0),
                "friction": metrics.get("friction", 0.0),
                "harmony": metrics.get("harmony", 0.0),
                "resilience": metrics.get("resilience", 0.0),
                "performance_score": metrics.get("performance_score", 1),
                "field_stability": metrics.get("field_stability", 0.0),
                "system_coherence": metrics.get("system_coherence", 0.0),
            },
        }
    except Exception as e:
        logger.error("Error getting current metrics: %s", e)
        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "error": "Failed to retrieve metrics",
            "metrics": {},
        }


@router.get("/health")
async def metrics_service_health():
    """Health check for the metrics service."""
    return {
        "status": "healthy",
        "service": "coordination_metrics",
        "active_connections": len(manager.active_connections),
        "timestamp": datetime.now(UTC).isoformat(),
    }

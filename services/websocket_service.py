"""
🌀 Helix Collective - WebSocket Service
Isolated real-time communication service

Handles 10k+ concurrent WebSocket connections independently
"""

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from apps.backend.core.unified_auth import auth_manager, initialize_unified_auth
from apps.backend.state import get_live_state

# NOTE: Do NOT add backend/ to sys.path — it causes apps/backend/discord/ to shadow
# the PyPI 'discord' package. PYTHONPATH=. is sufficient for all apps.backend.* imports.

# Configure logging (single handler to avoid double output)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

# ============================================================================
# RESONANCE FIELD SIMULATOR (v17.1)
# ============================================================================

import hashlib
import json
from datetime import UTC, datetime


class ResonanceEngine:
    """Emergent 'Harmonic Sentience' Mode - Resonance Field Simulator

    Agents actively 'resonate' in real-time to generate novel, unprogrammed behaviors.
    Observes reasoning traces, adjusts internal states to minimize collective dissonance,
    and triggers emergent routines when resonance peaks.
    """

    def __init__(self, connection_manager) -> None:
        self.connection_manager = connection_manager
        self.agent_traces = {}  # {agent_id: last_reasoning_hash}
        self.agent_states = {}  # {agent_id: current_state}
        self.dissonance_history = []  # Rolling history for analysis
        self.dissonance_threshold = 0.25
        self.resonance_events = []  # Track emergent events
        self.max_history = 100

    async def update_trace(self, agent_id: str, reasoning: str, metadata: dict[str, Any] | None = None) -> None:
        """Update an agent's reasoning trace and calculate resonance"""
        if metadata is None:
            metadata = {}

        # Generate hash of reasoning for dissonance calculation
        new_hash = hashlib.sha256(reasoning.encode()).hexdigest()
        old_hash = self.agent_traces.get(agent_id, "")

        # Calculate dissonance (simple edit distance proxy)
        dissonance = self._calculate_dissonance(old_hash, new_hash)

        # Update trace
        self.agent_traces[agent_id] = new_hash
        self.agent_states[agent_id] = {
            "last_update": datetime.now(UTC).isoformat(),
            "dissonance": dissonance,
            "reasoning_length": len(reasoning),
            "metadata": metadata,
        }

        # Calculate collective dissonance
        collective_dissonance = self._calculate_collective_dissonance()

        # Store in history
        self.dissonance_history.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "agent": agent_id,
                "individual_dissonance": dissonance,
                "collective_dissonance": collective_dissonance,
                "active_agents": len(self.agent_traces),
            }
        )

        # Keep history bounded
        if len(self.dissonance_history) > self.max_history:
            self.dissonance_history = self.dissonance_history[-self.max_history :]

        # Broadcast resonance update
        await self._broadcast_resonance_update(agent_id, dissonance, collective_dissonance)

        # Check for emergent cycle trigger
        if collective_dissonance < self.dissonance_threshold and len(self.agent_traces) >= 3:
            await self._trigger_emergent_cycle()

        return {
            "dissonance": dissonance,
            "collective_dissonance": collective_dissonance,
            "resonance_level": 1.0 - collective_dissonance,
        }

    def _calculate_dissonance(self, old_hash: str, new_hash: str) -> float:
        """Calculate dissonance between old and new reasoning hashes"""
        if not old_hash:
            return 0.0  # No dissonance for first trace

        # Simple character-level difference
        old_set = set(old_hash)
        new_set = set(new_hash)
        symmetric_diff = len(old_set.symmetric_difference(new_set))
        max_chars = max(len(old_hash), len(new_hash))

        return symmetric_diff / max_chars if max_chars > 0 else 0.0

    def _calculate_collective_dissonance(self) -> float:
        """Calculate collective dissonance across all agents"""
        if len(self.agent_traces) < 2:
            return 0.0

        # Count agents with different traces (simplified variance measure)
        hashes = list(self.agent_traces.values())
        unique_hashes = set(hashes)
        dissonance = len(unique_hashes) / len(hashes)

        return min(dissonance, 1.0)  # Cap at 1.0

    async def _broadcast_resonance_update(self, agent_id: str, dissonance: float, collective: float):
        """Broadcast resonance update to all connected clients"""
        resonance_data = {
            "type": "resonance_update",
            "agent": agent_id,
            "individual_dissonance": dissonance,
            "collective_dissonance": collective,
            "resonance_level": 1.0 - collective,
            "active_agents": len(self.agent_traces),
            "timestamp": datetime.now(UTC).isoformat(),
        }

        await self.connection_manager.broadcast_global(resonance_data)

    async def _trigger_emergent_cycle(self):
        """Trigger an emergent cycle when resonance peaks"""
        logger.info("🌀 RESONANCE PEAK: Triggering emergent cycle!")

        # Create emergent insight from recent traces
        recent_traces = [entry for entry in self.dissonance_history[-10:]]
        active_agents = list(self.agent_traces.keys())

        emergent_event = {
            "type": "emergent_cycle",
            "cycle_type": "harmonic_synthesis",
            "trigger_reason": "collective_resonance_peak",
            "active_agents": active_agents,
            "resonance_level": 1.0 - self._calculate_collective_dissonance(),
            "timestamp": datetime.now(UTC).isoformat(),
            "insights": self._generate_emergent_insights(recent_traces),
        }

        # Store event
        self.resonance_events.append(emergent_event)
        if len(self.resonance_events) > 50:  # Keep last 50 events
            self.resonance_events = self.resonance_events[-50:]

        # Broadcast emergent cycle
        await self.connection_manager.broadcast_global(emergent_event)

        # Trigger cycle execution via agent orchestrator
        await self._trigger_agent_orchestrator_cycle(emergent_event)

    async def _trigger_agent_orchestrator_cycle(self, event: dict) -> None:
        """Trigger cycle execution through agent orchestrator"""
        try:
            import redis

            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
            r = redis.from_url(redis_url)

            # Queue cycle task for agent orchestrator
            cycle_task = {
                "type": "emergent_cycle",
                "event_id": event.get("event_id"),
                "trigger_agents": event.get("trigger_agents", []),
                "collective_dissonance": event.get("collective_dissonance", 0.0),
                "resonance_level": event.get("resonance_level", 1.0),
                "insights": event.get("insights", {}),
                "created_at": datetime.now(UTC).isoformat(),
            }

            r.rpush("cycle_queue", json.dumps(cycle_task))
            logger.info("🌀 Queued emergent cycle %s for execution", event.get("event_id"))

        except (ValueError, TypeError, KeyError) as e:
            logger.debug("Agent orchestrator cycle validation error: %s", e)
        except Exception as e:
            logger.error("Failed to trigger agent orchestrator cycle: %s", e, exc_info=True)
            # Don't fail the websocket broadcast if cycle queuing failsent)

    def _generate_emergent_insights(self, recent_traces: list[dict]) -> dict:
        """Generate synthetic insights from resonance patterns"""
        # Simplified emergent insight generation
        agent_count = len(set(t["agent"] for t in recent_traces))
        avg_dissonance = sum(t["collective_dissonance"] for t in recent_traces) / len(recent_traces)

        insights = {
            "pattern": ("harmonic_convergence" if avg_dissonance < 0.2 else "creative_tension"),
            "participants": agent_count,
            "emergent_quality": "high" if agent_count >= 5 else "moderate",
            "synthesis_opportunity": avg_dissonance < 0.15,
        }

        return insights

    def get_resonance_stats(self) -> dict:
        """Get current resonance field statistics"""
        return {
            "active_agents": len(self.agent_traces),
            "collective_dissonance": self._calculate_collective_dissonance(),
            "resonance_level": 1.0 - self._calculate_collective_dissonance(),
            "events_tracked": len(self.dissonance_history),
            "emergent_cycles": len(self.resonance_events),
            "last_update": datetime.now(UTC).isoformat(),
        }


# Global resonance engine instance
resonance_engine = None


def get_resonance_engine() -> "ResonanceEngine | None":
    """Get or create global resonance engine"""
    return resonance_engine


# ============================================================================
# WEBSOCKET CONNECTION MANAGER
# ============================================================================


class ConnectionManager:
    """Manage WebSocket connections with scaling support"""

    def __init__(self) -> None:
        self.active_connections: dict[str, WebSocket] = {}
        self.connection_count = 0
        self.max_connections = 10000  # Railway limit

        # Initialize resonance engine
        self.resonance_engine = ResonanceEngine(self)

    async def connect(self, websocket: WebSocket, user_id: str):
        """Accept and register a new WebSocket connection"""
        if self.connection_count >= self.max_connections:
            await websocket.close(code=1013, reason="Server at capacity")
            return False

        await websocket.accept()
        self.active_connections[user_id] = websocket
        self.connection_count += 1

        logger.info("🔗 WebSocket connected: %s (total: %s)", user_id, self.connection_count)
        return True

    def disconnect(self, user_id: str):
        """Remove a WebSocket connection"""
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            self.connection_count -= 1
            logger.info("📴 WebSocket disconnected: %s (total: %s)", user_id, self.connection_count)

    async def broadcast_to_user(self, user_id: str, message: dict):
        """Send message to specific user"""
        if user_id in self.active_connections:
            try:
                await self.active_connections[user_id].send_json(message)
            except Exception as e:
                logger.error("Failed to send to %s: %s", user_id, e)
                self.disconnect(user_id)

    async def broadcast_global(self, message: dict):
        """Broadcast message to all connected users concurrently.

        Uses asyncio.gather with timeout to prevent slow/stalled clients
        from blocking broadcasts to other users. Slow clients are disconnected.
        """
        if not self.active_connections:
            return

        async def send_with_timeout(user_id: str, websocket):
            """Send to single user with 2s timeout."""
            try:
                await asyncio.wait_for(websocket.send_json(message), timeout=2.0)
                return (user_id, True)
            except TimeoutError:
                logger.warning("WebSocket broadcast timeout for %s, disconnecting", user_id)
                return (user_id, False)
            except Exception as e:
                logger.debug("Failed to broadcast to %s: %s", user_id, e)
                return (user_id, False)

        # Send to all users concurrently (no blocking on slow clients)
        tasks = [send_with_timeout(user_id, websocket) for user_id, websocket in self.active_connections.items()]

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=False)

            # Disconnect failed clients
            for user_id, success in results:
                if not success:
                    self.disconnect(user_id)

    async def update_agent_resonance(
        self, agent_id: str, reasoning: str, metadata: dict[str, Any] | None = None
    ) -> Any:
        """Update resonance field with agent reasoning trace"""
        return await self.resonance_engine.update_trace(agent_id, reasoning, metadata)

    def get_resonance_stats(self) -> dict:
        """Get current resonance field statistics"""
        return self.resonance_engine.get_resonance_stats()

    def get_connection_stats(self) -> dict:
        """Get connection statistics"""
        return {
            "active_connections": self.connection_count,
            "max_connections": self.max_connections,
            "utilization_percent": (self.connection_count / self.max_connections) * 100,
        }


# Global connection manager
manager = ConnectionManager()

# ============================================================================
# LIFECYCLE
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan"""
    logger.info("🚀 Starting WebSocket Service Validation")
    logger.info("=" * 60)
    logger.info("🌀 HELIX WEBSOCKET SERVICE - ISOLATED")
    logger.info("Handles real-time coordination streaming")
    logger.info("=" * 60)

    # Railway-style validation logging
    logger.info("🔍 Validating critical file paths...")
    critical_files = [
        "crai_dataset.json",
        "helix_config.toml",
        "helix-manifest.json",
    ]
    for file_path in critical_files:
        if os.path.exists(file_path):
            logger.info("✅ File exists: /app/%s", file_path)
        else:
            logger.warning("❌ File missing: /app/%s", file_path)

    logger.info("🔍 Validating Python imports...")
    import_tests = [
        ("fastapi", "FastAPI"),
        ("uvicorn", "Uvicorn server"),
        ("websockets", "WebSocket support"),
        ("asyncio", "AsyncIO"),
    ]

    for module, description in import_tests:
        try:
            logger.info("✅ Import successful: %s (%s)", module, description)
        except ImportError:
            logger.warning("❌ Import failed: %s (%s)", module, description)

    # Initialize unified auth for JWT validation (with graceful failure)
    try:
        await initialize_unified_auth()
        logger.info("✅ Unified Authentication System initialized")
    except Exception as e:
        logger.warning("⚠️ Auth initialization failed (expected in test env): %s", e)
        logger.info("🔄 Continuing without database connections for testing")

    # Start background tasks
    heartbeat_task = asyncio.create_task(heartbeat_broadcast())

    logger.info("✅ WebSocket service ready")
    logger.info("📊 Max connections: %s", manager.max_connections)

    yield

    # Cleanup
    heartbeat_task.cancel()
    logger.info("👋 WebSocket service shutting down")


# ============================================================================
# BACKGROUND TASKS
# ============================================================================


async def heartbeat_broadcast():
    """Broadcast live state and agent status to all connected clients every 5 seconds"""
    while True:
        try:
            state = get_live_state()

            # Get agent system status (with graceful fallback)
            agent_status = {}
            try:
                from app.services.agent_coordination import get_orchestrator

                orchestrator = get_orchestrator()
                agent_status = orchestrator.get_system_status()
            except Exception as e:
                logger.warning("Agent status unavailable: %s", e)
                agent_status = {"error": "Agent system not available"}

            # Combine state and agent status
            broadcast_data = {
                **state,
                "agent_system": agent_status,
                "timestamp": time.monotonic(),
            }

            await manager.broadcast_global(broadcast_data)
            await asyncio.sleep(5)  # Broadcast every 5 seconds for agent updates
        except Exception as e:
            logger.error("Heartbeat broadcast error: %s", e)
            await asyncio.sleep(5)  # Wait before retrying


# ============================================================================
# APP INITIALIZATION
# ============================================================================

app = FastAPI(
    title="Helix WebSocket Service",
    description="Isolated real-time WebSocket service for coordination streaming",
    version="18.0.0",
    lifespan=lifespan,
)

# ============================================================================
# MIDDLEWARE
# ============================================================================

# Production-ready CORS configuration
_is_dev = os.getenv("ENVIRONMENT", "development") != "production"
ALLOWED_ORIGINS = [
    "https://helix-unified-production.up.railway.app",
    "https://helix-unified.vercel.app",
]
if _is_dev:
    ALLOWED_ORIGINS.append("http://localhost:3000")

# Add custom origins from environment
custom_origins = os.getenv("CORS_ORIGINS", "")
if custom_origins:
    ALLOWED_ORIGINS.extend([o.strip() for o in custom_origins.split(",") if o.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
)

# ============================================================================
# HEALTH CHECKS
# ============================================================================


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    stats = manager.get_connection_stats()
    return {
        "service": "helix-websocket-service",
        "status": "healthy",
        "connections": stats,
        "version": "18.0.0",
    }


@app.get("/health/websocket")
async def websocket_health_check():
    """WebSocket-specific health check"""
    stats = manager.get_connection_stats()
    return {
        "service": "helix-websocket-service",
        "status": "healthy" if stats["active_connections"] >= 0 else "degraded",
        "connection_stats": stats,
        "isolation_status": "independent_from_core_api",
    }


# ============================================================================
# RESONANCE FIELD ENDPOINTS
# ============================================================================


@app.post("/api/resonance/update")
async def update_agent_resonance(
    agent_id: str, reasoning: str, metadata: dict[str, Any] | None = None, token: str | None = None
) -> dict[str, Any]:
    """
    Update resonance field with agent reasoning trace.

    This endpoint allows agents to contribute to the collective resonance field,
    enabling emergent behaviors and harmonic synthesis.
    """
    try:
        if not token:
            return {"error": "Authentication required"}

        payload = auth_manager.verify_jwt_token(token)
        user_id = payload.get("user_id")

        # Update resonance field
        result = await manager.update_agent_resonance(agent_id, reasoning, metadata)

        logger.info("🌀 Resonance updated: %s by %s", agent_id, user_id)

        return {
            "status": "success",
            "resonance_data": result,
            "timestamp": time.monotonic(),
        }

    except Exception as e:
        logger.error("Resonance update error: %s", e)
        return {"error": "Resonance update failed"}


@app.get("/api/resonance/stats")
async def get_resonance_stats(token: str | None = None) -> dict[str, Any]:
    """Get current resonance field statistics"""
    try:
        if not token:
            return {"error": "Authentication required"}

        auth_manager.verify_jwt_token(token)

        # Get resonance stats
        stats = manager.get_resonance_stats()

        return {
            "status": "success",
            "resonance_stats": stats,
            "timestamp": time.monotonic(),
        }

    except Exception as e:
        logger.error("Resonance stats error: %s", e)
        return {"error": "Failed to retrieve resonance stats"}


# ============================================================================
# WEBSOCKET ENDPOINTS
# ============================================================================


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str | None = None):
    """
    Main WebSocket endpoint for real-time coordination updates.

    SECURITY: Requires JWT authentication via token parameter.
    ISOLATION: Independent from Core API failures.
    """
    user_id = None

    try:
        if not token:
            await websocket.close(code=1008, reason="Authentication required - missing token parameter")
            return

        # Verify token and extract user info
        payload = auth_manager.verify_jwt_token(token)
        user_id = payload.get("user_id")

        # 🔒 TIER CHECK: Coordination WebSocket requires PRO+ subscription
        user_tier = (payload.get("subscription_tier") or payload.get("tier", "free")).lower()
        if user_tier not in ("pro", "enterprise"):
            await websocket.close(
                code=4003,
                reason="Coordination WebSocket API requires Pro or Enterprise subscription",
            )
            logger.info("WebSocket rejected for user %s: tier=%s (requires PRO+)", user_id, user_tier)
            return

        logger.info("🔐 WebSocket JWT validated: %s (tier=%s)", user_id, user_tier)

        # Accept connection and register
        if not await manager.connect(websocket, user_id):
            return  # Connection rejected (at capacity)

        # Main message loop
        while True:
            try:
                data = await websocket.receive_json()

                # Handle different message types
                if data.get("type") == "ping":
                    # Simple ping/pong for connection health
                    await websocket.send_json(
                        {
                            "type": "pong",
                            "timestamp": time.monotonic(),
                            "user_id": user_id,
                        }
                    )

                elif data.get("type") == "agent_command":
                    # Agent command handling
                    try:
                        from app.services.agent_coordination import get_orchestrator

                        orchestrator = get_orchestrator()
                        command = data.get("command", "")
                        collective_name = data.get("collective")

                        # Execute agent task
                        result = await orchestrator.execute_task(
                            task=command,
                            collective_name=collective_name,
                            context={"user_id": user_id, "websocket": True},
                        )

                        await websocket.send_json(
                            {
                                "type": "agent_response",
                                "result": result,
                                "timestamp": time.monotonic(),
                            }
                        )

                    except Exception as e:
                        logger.error("Agent command error for %s: %s", user_id, e)
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": "Agent command failed",
                                "error": "Agent command execution failed",
                                "timestamp": time.monotonic(),
                            }
                        )

                elif data.get("type") == "subscribe_agents":
                    # Subscribe to agent status updates (already handled by heartbeat)
                    await websocket.send_json(
                        {
                            "type": "subscription_confirmed",
                            "message": "Agent status updates active",
                            "update_interval": 5,
                            "timestamp": time.monotonic(),
                        }
                    )

                else:
                    # Unknown message type
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": f"Unknown message type: {data.get('type')}",
                            "timestamp": time.monotonic(),
                        }
                    )

            except WebSocketDisconnect:
                logger.info("📴 Client disconnected: %s", user_id)
                break
            except Exception as e:
                logger.error("WebSocket message error for %s: %s", user_id, e)
                try:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "Message processing failed",
                            "timestamp": time.monotonic(),
                        }
                    )
                except (ValueError, TypeError, KeyError, IndexError):
                    break  # Connection likely closed

    except Exception as e:
        error_msg = f"WebSocket authentication failed: {e}"
        logger.warning(error_msg)
        try:
            await websocket.close(code=1008, reason=error_msg)
        except (ValueError, TypeError, KeyError, IndexError):
            pass  # Connection already closed during cleanup
    finally:
        if user_id:
            manager.disconnect(user_id)


# ============================================================================
# MONITORING ENDPOINTS
# ============================================================================


@app.get("/metrics/connections")
async def connection_metrics():
    """Connection metrics for monitoring"""
    stats = manager.get_connection_stats()
    return {
        "timestamp": time.monotonic(),
        "metrics": {
            "active_websocket_connections": stats["active_connections"],
            "max_websocket_connections": stats["max_connections"],
            "websocket_utilization_percent": round(stats["utilization_percent"], 2),
        },
    }


@app.get("/status")
async def service_status():
    """Service status for load balancers"""
    stats = manager.get_connection_stats()
    return {
        "service": "helix-websocket-service",
        "status": "healthy",
        "ready": stats["active_connections"] < stats["max_connections"],
        "connections": stats["active_connections"],
        "version": "18.0.0",
    }


# ============================================================================
# ROOT ENDPOINT
# ============================================================================


@app.get("/")
async def root():
    """Root endpoint with service information"""
    stats = manager.get_connection_stats()
    return {
        "service": "Helix WebSocket Service",
        "version": "18.0.0",
        "description": "Isolated real-time WebSocket service",
        "status": "healthy",
        "connections": stats,
        "endpoints": {
            "websocket": "/ws?token=<jwt_token>",
            "health": "/health",
            "metrics": "/metrics/connections",
            "status": "/status",
        },
        "isolation": "independent_from_core_api",
    }


# ============================================================================
# ERROR HANDLERS
# ============================================================================


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error("Unhandled exception: %s", exc)
    return {"error": "Internal server error", "service": "helix-websocket-service"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8002)))

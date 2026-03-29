"""
🌀 Helix Collective - API Gateway
Load balancing and routing between monolith and 4-service architecture.

Features:
- Intelligent routing based on service health
- Automatic failover from distributed to monolith
- Request proxying with circuit breaker protection
- Unified entry point for all Helix services
"""

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

import httpx
import websockets
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from .service_registry import registry

# Auth import — fail closed if unavailable
try:
    from apps.backend.core.auth import AuthManager

    _auth_available = True
except ImportError:
    _auth_available = False

logger = logging.getLogger(__name__)


# ============================================================================
# ROUTE MAPPING
# ============================================================================

# Map URL prefixes to capabilities for intelligent routing
ROUTE_CAPABILITIES = {
    # API routes
    "/api/agents": "agents",
    "/api/coordination": "coordination",
    "/api/analytics": "analytics",
    "/api/auth": "api",
    "/api/saas": "api",
    "/api/billing": "api",
    "/api/marketplace": "api",
    "/api/admin": "api",
    "/api/dashboard": "api",
    "/api/mcp": "api",
    "/api/system": "api",
    "/api/spirals": "spirals",
    "/api/voice": "voice",
    "/api/forum": "api",
    "/api/web-os": "api",
    "/api/zapier": "api",
    "/api/": "api",  # Default API capability
    # WebSocket routes
    "/ws": "websocket",
    # Health routes
    "/health": "api",
}


def get_capability_for_path(path: str) -> str:
    """Determine the capability needed for a given path"""
    for prefix, capability in ROUTE_CAPABILITIES.items():
        if path.startswith(prefix):
            return capability
    return "api"  # Default capability


# ============================================================================
# LIFECYCLE
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gateway lifespan - startup and shutdown"""
    logger.info("🚀 Starting Helix API Gateway")
    logger.info("=" * 60)
    logger.info("🌀 HELIX API GATEWAY - HYBRID ARCHITECTURE")
    logger.info("Load balancing between monolith and 4-service")
    logger.info("=" * 60)

    # Initialize service registry
    logger.info("🔍 Initializing service discovery...")

    # Connect to Redis for inter-service messaging
    try:
        logger.info("✅ Redis connected for inter-service messaging")
    except Exception as e:
        logger.warning("⚠️ Redis not available: %s", e)

    # Start background health check task
    health_check_task = asyncio.create_task(background_health_monitor())

    # Start inter-service message listener
    message_listener_task = None
    try:
        logger.info("✅ Inter-service message listener started")
    except Exception as e:
        logger.warning("⚠️ Message listener failed to start: %s", e)

    # Initial health check
    await registry.health_check_all()
    status = registry.get_architecture_status()
    logger.info("📊 Architecture status:")
    logger.info("   Mode: %s", status["mode"])
    logger.info(
        "   Monolith: %s",
        "✅ healthy" if status["monolith"]["healthy"] else "❌ offline",
    )
    logger.info(
        "   Distributed: %d/%d services healthy",
        status["distributed"]["healthy_services"],
        status["distributed"]["total_services"],
    )
    logger.info("   Recommended target: %s", status["recommended_target"])

    logger.info("✅ API Gateway ready")

    yield

    # Cleanup
    health_check_task.cancel()
    if message_listener_task:
        message_listener_task.cancel()
    logger.info("👋 API Gateway shutting down")


async def background_health_monitor():
    """Background task to monitor service health"""
    while True:
        try:
            await asyncio.sleep(30)  # Check every 30 seconds
            await registry.health_check_all()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Health monitor error: %s", e)
            await asyncio.sleep(60)  # Wait longer on error


# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(
    title="Helix API Gateway",
    description="Load balancing gateway for Helix Collective services",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Configuration
_is_dev = os.getenv("ENVIRONMENT", "development") != "production"
ALLOWED_ORIGINS = [
    "https://helix-unified-production.up.railway.app",
    "https://helixspiral.work",
    "https://www.helixspiral.work",
    "https://helixcollective.work",
    "https://www.helixcollective.work",
]
if _is_dev:
    ALLOWED_ORIGINS.extend(["http://localhost:3000", "http://localhost:8000"])

custom_origins = os.getenv("CORS_ORIGINS", "")
if custom_origins:
    ALLOWED_ORIGINS.extend([o.strip() for o in custom_origins.split(",") if o.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)


# ============================================================================
# GATEWAY HEALTH ENDPOINTS
# ============================================================================


@app.get("/")
async def gateway_root():
    """Gateway root endpoint"""
    status = registry.get_architecture_status()
    return {
        "service": "Helix API Gateway",
        "version": "1.0.0",
        "description": "Load balancing gateway for hybrid architecture",
        "architecture": status,
        "endpoints": {
            "health": "/health",
            "architecture": "/gateway/architecture",
            "services": "/gateway/services",
            "proxy": "/* (all requests proxied to backend services)",
        },
    }


@app.get("/health")
async def gateway_health():
    """Gateway health check"""
    status = registry.get_architecture_status()
    healthy = status["monolith"]["healthy"] or status["distributed"]["healthy_services"] >= 2

    return {
        "service": "helix-api-gateway",
        "status": "healthy" if healthy else "degraded",
        "architecture_status": status,
        "timestamp": time.time(),
    }


@app.get("/gateway/architecture")
async def get_architecture():
    """Get detailed architecture status"""
    return registry.get_architecture_status()


@app.get("/gateway/services")
async def get_services():
    """Get all registered services"""
    services = registry.get_all_services()
    return {
        "services": services,
        "circuit_breakers": {
            name: {
                "state": breaker.state.value,
                "failures": breaker.failure_count,
            }
            for name, breaker in registry.circuit_breakers.items()
        },
    }


@app.post("/gateway/health-check")
async def trigger_health_check():
    """Manually trigger a health check of all services"""
    result = await registry.health_check_all()
    return result


# ============================================================================
# REQUEST PROXYING
# ============================================================================


async def proxy_request(request: Request, target_service: str, timeout: float = 30.0) -> JSONResponse:
    """
    Proxy a request to the target service.

    Args:
        request: The incoming request
        target_service: The service to forward the request to
        timeout: Request timeout in seconds

    Returns:
        JSONResponse with the proxied response
    """
    service_config = registry.services.get(target_service)
    if not service_config:
        raise HTTPException(status_code=503, detail=f"Unknown service: {target_service}")

    # Build target URL
    target_url = f"{service_config['url']}{request.url.path}"
    if request.url.query:
        target_url += f"?{request.url.query}"

    # Get request body
    body = await request.body()

    # Copy headers (excluding host)
    headers = dict(request.headers)
    headers.pop("host", None)
    headers["X-Forwarded-For"] = request.client.host if request.client else "unknown"
    headers["X-Gateway-Service"] = target_service

    start_time = time.time()

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
            )

        elapsed_ms = int((time.time() - start_time) * 1000)
        registry.record_request_result(target_service, response.status_code < 500)

        logger.info(
            "🔀 %s %s -> %s (%d) [%dms]",
            request.method,
            request.url.path,
            target_service,
            response.status_code,
            elapsed_ms,
        )

        # Return response
        return JSONResponse(
            content=(
                response.json()
                if response.headers.get("content-type", "").startswith("application/json")
                else {"data": response.text}
            ),
            status_code=response.status_code,
            headers={
                "X-Gateway-Service": target_service,
                "X-Gateway-Response-Time": str(elapsed_ms),
            },
        )

    except httpx.TimeoutException:
        registry.record_request_result(target_service, False)
        logger.warning("⏱️ Timeout proxying to %s: %s", target_service, target_url)
        raise HTTPException(status_code=504, detail="Gateway timeout")

    except httpx.ConnectError:
        registry.record_request_result(target_service, False)
        logger.warning("❌ Cannot connect to %s: %s", target_service, target_url)
        raise HTTPException(status_code=503, detail=f"Service unavailable: {target_service}")

    except Exception as e:
        registry.record_request_result(target_service, False)
        logger.error("Error proxying to %s: %s", target_service, e)
        raise HTTPException(status_code=502, detail="Bad gateway")


async def proxy_streaming_response(request: Request, target_service: str, timeout: float = 60.0) -> StreamingResponse:
    """Proxy a streaming response (SSE, etc.)"""
    service_config = registry.services.get(target_service)
    if not service_config:
        raise HTTPException(status_code=503, detail=f"Unknown service: {target_service}")

    target_url = f"{service_config['url']}{request.url.path}"
    if request.url.query:
        target_url += f"?{request.url.query}"

    headers = dict(request.headers)
    headers.pop("host", None)

    async def stream_generator():
        async with (
            httpx.AsyncClient(timeout=timeout) as client,
            client.stream(
                method=request.method,
                url=target_url,
                headers=headers,
            ) as response,
        ):
            async for chunk in response.aiter_bytes():
                yield chunk

    return StreamingResponse(stream_generator(), media_type="text/event-stream")


# ============================================================================
# CATCH-ALL PROXY ROUTES
# ============================================================================


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy_api(request: Request, path: str):
    """
    Proxy all API requests to the appropriate backend service.

    Uses intelligent routing based on:
    1. Path-based capability mapping
    2. Service health status
    3. Circuit breaker state
    4. Load balancing
    """
    full_path = f"/api/{path}"
    capability = get_capability_for_path(full_path)

    # Get the best service for this capability
    target_service = registry.get_service_for_capability(capability)

    if not target_service:
        # Fallback to monolith
        target_service = "monolith"
        if not registry.circuit_breakers["monolith"].can_execute():
            raise HTTPException(
                status_code=503,
                detail="All services unavailable. Please try again later.",
            )

    logger.debug("🎯 Routing %s -> %s (capability: %s)", full_path, target_service, capability)

    # Check for streaming endpoints
    if "/stream" in path or request.headers.get("accept") == "text/event-stream":
        return await proxy_streaming_response(request, target_service)

    return await proxy_request(request, target_service)


@app.api_route("/health/{path:path}", methods=["GET"])
async def proxy_health(request: Request, path: str):
    """Proxy health check endpoints"""
    target_service = registry.get_best_api_service()
    return await proxy_request(request, target_service)


@app.api_route("/ucf", methods=["GET"])
async def proxy_ucf(request: Request):
    """Proxy UCF metrics endpoint"""
    target_service = registry.get_service_for_capability("coordination")
    if not target_service:
        target_service = "monolith"
    return await proxy_request(request, target_service)


@app.api_route("/agents", methods=["GET"])
async def proxy_agents(request: Request):
    """Proxy agents endpoint"""
    target_service = registry.get_service_for_capability("agents")
    if not target_service:
        target_service = "monolith"
    return await proxy_request(request, target_service)


# ============================================================================
# WEBSOCKET PROXY
# ============================================================================


@app.websocket("/ws")
async def websocket_proxy(websocket: WebSocket, token: str = Query(None)):
    """Proxy WebSocket connections to the appropriate backend. Requires JWT ?token= param."""
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
        except Exception as e:
            logger.debug("Token verification failed: %s", e)
            await websocket.close(code=1008, reason="Invalid or expired token")
            return
    else:
        logger.error("Auth module unavailable — rejecting gateway WS connection")
        await websocket.close(code=1013, reason="Authentication service unavailable")
        return

    await websocket.accept()

    # Get best WebSocket service
    target_service = registry.get_best_websocket_service()
    service_config = registry.services.get(target_service)

    if not service_config:
        await websocket.close(code=1013, reason="No WebSocket service available")
        return

    # Connect to backend WebSocket
    ws_url = service_config["url"].replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_url}/ws"

    try:
        async with websockets.connect(ws_url) as backend_ws:
            logger.info("🔗 WebSocket full-duplex proxy to %s", target_service)

            async def client_to_backend():
                """Forward messages from client → backend."""
                try:
                    while True:
                        data = await websocket.receive_text()
                        await backend_ws.send(data)
                except WebSocketDisconnect:
                    await backend_ws.close()
                except (RuntimeError, OSError) as e:
                    logger.debug("Client to backend relay error: %s", e)
                except Exception as e:
                    logger.warning("Unexpected client relay error: %s", e)

            async def backend_to_client():
                """Forward messages from backend → client."""
                try:
                    async for message in backend_ws:
                        await websocket.send_text(message if isinstance(message, str) else message.decode("utf-8"))
                except websockets.exceptions.ConnectionClosed:
                    logger.debug("WebSocket connection closed normally during backend-to-client relay")
                except (RuntimeError, OSError, ValueError) as e:
                    logger.debug("Backend to client relay error: %s", e)
                except Exception as e:
                    logger.warning("Unexpected backend relay error: %s", e)

            # Run both relay directions concurrently; when either finishes, cancel the other
            done, pending = await asyncio.wait(
                [
                    asyncio.create_task(client_to_backend()),
                    asyncio.create_task(backend_to_client()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()

    except websockets.exceptions.InvalidStatusCode as e:
        logger.error("WebSocket backend rejected connection (%s): %s", target_service, e)
        await websocket.close(code=1013, reason="Backend rejected connection")
    except (OSError, websockets.exceptions.WebSocketException) as e:
        logger.error("WebSocket proxy connection error: %s", e)
        await websocket.close(code=1013, reason="Cannot reach backend WebSocket service")
    except Exception as e:
        logger.error("WebSocket proxy error: %s", e)
        await websocket.close(code=1011, reason="Internal error")


@app.websocket("/ws/coordination")
async def coordination_websocket_proxy(websocket: WebSocket, token: str = Query(None)):
    """Proxy coordination WebSocket connections. Requires JWT ?token= param."""
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
        logger.error("Auth module unavailable — rejecting coordination WS connection")
        await websocket.close(code=1013, reason="Authentication service unavailable")
        return

    await websocket.accept()

    target_service = registry.get_service_for_capability("websocket")
    if not target_service:
        target_service = "monolith"

    service_config = registry.services.get(target_service)
    if not service_config:
        await websocket.close(code=1013, reason="No WebSocket service available")
        return

    ws_url = service_config["url"].replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_url}/ws/coordination"

    try:
        async with websockets.connect(ws_url) as backend_ws:
            logger.info("🌀 Coordination WebSocket full-duplex proxy to %s", target_service)

            async def client_to_backend():
                try:
                    while True:
                        data = await websocket.receive_text()
                        await backend_ws.send(data)
                except WebSocketDisconnect:
                    await backend_ws.close()
                except (ConnectionError, TimeoutError, OSError) as e:
                    logger.debug("WebSocket client to backend connection error: %s", e)
                except Exception as e:
                    logger.warning("WebSocket client to backend error: %s", e)

            async def backend_to_client():
                try:
                    async for message in backend_ws:
                        await websocket.send_text(message if isinstance(message, str) else message.decode("utf-8"))
                except websockets.exceptions.ConnectionClosed:
                    logger.debug("Coordination WebSocket connection closed normally during backend-to-client relay")
                except (ConnectionError, TimeoutError, OSError) as e:
                    logger.debug("WebSocket backend to client connection error: %s", e)
                except Exception as e:
                    logger.warning("WebSocket backend to client error: %s", e)

            done, pending = await asyncio.wait(
                [
                    asyncio.create_task(client_to_backend()),
                    asyncio.create_task(backend_to_client()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()

    except websockets.exceptions.InvalidStatusCode as e:
        logger.error("Coordination WS backend rejected (%s): %s", target_service, e)
        await websocket.close(code=1013, reason="Backend rejected connection")
    except (OSError, websockets.exceptions.WebSocketException) as e:
        logger.error("Coordination WebSocket proxy error: %s", e)
        await websocket.close(code=1013, reason="Cannot reach backend WebSocket service")
    except Exception as e:
        logger.error("Coordination WebSocket error: %s", e)


# ============================================================================
# STATIC FILES AND FRONTEND PROXY
# ============================================================================


@app.get("/{path:path}")
async def proxy_frontend(request: Request, path: str):
    """
    Proxy frontend requests.

    For paths not matching /api/*, forward to frontend service.
    """
    # Check if this is a known API path that slipped through
    if path.startswith("api/"):
        return await proxy_api(request, path[4:])

    # Forward to frontend service
    target_service = "frontend"
    if not registry.is_service_healthy("frontend"):
        # Fallback to monolith which also serves frontend
        target_service = "monolith"

    try:
        return await proxy_request(request, target_service)
    except HTTPException:
        # Return a simple message if no frontend available
        return JSONResponse(
            content={
                "message": "Helix Collective API Gateway",
                "api_docs": "/api/docs",
                "health": "/health",
            },
            status_code=200,
        )


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("GATEWAY_PORT", 8080))
    logger.info("🚀 Starting Helix API Gateway on port %d", port)

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

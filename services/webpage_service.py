# NOTE: This service is not currently wired to any route.
# It defines its own FastAPI app and standalone functions but is never
# imported by main.py or any route. Wire to routes/web.py or remove.
"""
🌀 Helix Collective - Webpage Service
Dedicated webpage service with proper template serving

Serves the beautiful webpage with agent gallery, Swagger docs, and live coordination metrics
"""

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)

# ============================================================================
# TEMPLATE CONFIGURATION
# ============================================================================


def find_templates_directory():
    """Find templates directory using multiple strategies."""

    # Strategy 1: Relative to this file (consolidated/webpage_service.py)
    strategy1 = Path(__file__).parent.parent.parent / "templates"

    # Strategy 2: Relative to current working directory
    strategy2 = Path.cwd() / "templates"

    # Strategy 3: In parent of current working directory
    strategy3 = Path.cwd().parent / "templates"

    # Strategy 4: Absolute from /app root (Railway specific)
    strategy4 = Path("/app/templates")

    # Strategy 5: From TEMPLATES_DIR environment variable (local dev override)
    _templates_env = os.environ.get("TEMPLATES_DIR", "")
    strategy5 = Path(_templates_env) if _templates_env else None

    strategies = [
        ("parent.parent.parent / templates", strategy1),
        ("cwd() / templates", strategy2),
        ("cwd().parent / templates", strategy3),
        ("/app/templates", strategy4),
    ]
    if strategy5:
        strategies.append(("TEMPLATES_DIR env", strategy5))

    logger.info("🔍 Searching for templates directory...")
    logger.info("   __file__ = %s", Path(__file__).resolve())
    logger.info("   cwd() = %s", Path.cwd().resolve())

    for name, path in strategies:
        logger.info("   Testing: %s -> %s", name, path.resolve())
        if path.exists() and path.is_dir():
            # Verify index.html exists
            if (path / "index.html").exists():
                logger.info("✅ Found templates at: %s", path.resolve())
                return path
            else:
                logger.warning(
                    "❌ Templates directory exists but index.html not found: %s",
                    path.resolve(),
                )
        else:
            logger.info("❌ Not found: %s", path.resolve())

    # If nothing found, use default and let it fail with good error message
    logger.error("❌ Could not find templates directory! Using fallback.")
    return strategy1


# Initialize templates
TEMPLATES_DIR = find_templates_directory()
try:
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    logger.info("Templates configured: %s", TEMPLATES_DIR)
except (OSError, ImportError) as e:
    logger.debug("Template configuration error: %s", e)
except Exception as e:
    logger.warning("❌ Template configuration failed: %s", e)
    templates = None

# ============================================================================
# PORTAL MONITORING
# ============================================================================


class PortalMonitor:
    """Monitor and report portal status"""

    def __init__(self) -> None:
        self.portals = {
            "railway": {
                "name": "Railway Backend",
                "url": "https://helix-unified-production.up.railway.app/health",
                "status": "unknown",
                "last_check": None,
            },
            "streamlit": {
                "name": "Streamlit Dashboard",
                "url": None,
                "status": "not_deployed",
                "last_check": None,
            },
            "zapier_dashboard": {
                "name": "Coordination Dashboard",
                "url": "https://helix-coordination-dashboard-1be70b.zapier.app",
                "status": "unknown",
                "last_check": None,
            },
            "zapier_nexus": {
                "name": "Meta Sigil Nexus",
                "url": "https://meta-sigil-nexus-v16.zapier.app",
                "status": "unknown",
                "last_check": None,
            },
            "zapier_routine": {
                "name": "System Cycle Chamber",
                "url": "https://new-interface-d99800.zapier.app",
                "status": "unknown",
                "last_check": None,
            },
        }

    async def check_portal_status(self, portal_key: str) -> dict[str, Any]:
        """Check status of a specific portal"""
        import httpx

        portal = self.portals[portal_key]
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(portal["url"])

                if response.status_code == 200:
                    portal["status"] = "online"
                else:
                    portal["status"] = "degraded"

        except httpx.TimeoutException:
            portal["status"] = "timeout"
        except httpx.ConnectError:
            portal["status"] = "offline"
        except Exception:
            portal["status"] = "error"

        portal["last_check"] = time.monotonic()
        return portal

    async def get_all_portal_status(self) -> list[dict[str, Any]]:
        """Get status of all portals"""
        tasks = []
        for portal_key in self.portals:
            tasks.append(self.check_portal_status(portal_key))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out any exceptions and return valid results
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                portal_key = list(self.portals.keys())[i]
                logger.error("Portal check failed for %s: %s", portal_key, result)
                valid_results.append(
                    {
                        "name": self.portals[portal_key]["name"],
                        "status": "error",
                        "last_check": None,
                    }
                )
            else:
                valid_results.append(result)

        return valid_results


# Initialize portal monitor
portal_monitor = PortalMonitor()

# ============================================================================
# UCF METRICS INTEGRATION
# ============================================================================


async def get_consolidated_ucf_metrics() -> dict[str, Any]:
    """Get consolidated UCF metrics from the system"""
    try:
        from apps.backend.state import get_live_state

        # Get live state which includes UCF metrics
        state = get_live_state()

        # Extract UCF metrics
        ucf_metrics = {
            "harmony": state.get("ucf_state", {}).get("harmony", 0.0),
            "resilience": state.get("ucf_state", {}).get("resilience", 0.0),
            "throughput": state.get("ucf_state", {}).get("throughput", 0.0),
            "focus": state.get("ucf_state", {}).get("focus", 0.0),
            "friction": state.get("ucf_state", {}).get("friction", 0.0),
            "velocity": state.get("ucf_state", {}).get("velocity", 0.0),
            "status": state.get("status", "unknown"),
            "timestamp": state.get("timestamp", 0.0),
        }

        return ucf_metrics

    except Exception as e:
        logger.error("Failed to get UCF metrics: %s", e)
        return {
            "harmony": 0.0,
            "resilience": 0.0,
            "throughput": 0.0,
            "focus": 0.0,
            "friction": 0.0,
            "velocity": 0.0,
            "status": "error",
            "timestamp": 0.0,
        }


# ============================================================================
# LIFECYCLE
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown"""
    logger.info("=" * 70)
    logger.info("🌀 HELIX COLLECTIVE WEBPAGE SERVICE")
    logger.info("Beautiful webpage with agent gallery and live metrics")
    logger.info("=" * 70)

    # Check template configuration
    if templates:
        logger.info("Templates configured: %s", TEMPLATES_DIR)
    else:
        logger.warning("⚠️ Templates not configured - serving basic HTML")

    # Initialize portal monitoring
    portal_status = await portal_monitor.get_all_portal_status()
    logger.info(
        f"📊 Portal status: {len([p for p in portal_status if p['status'] == 'online'])}/{len(portal_status)} online"
    )

    logger.info("✅ Webpage service ready")
    yield
    logger.info("👋 Webpage service shutting down")


# ============================================================================
# APP INITIALIZATION
# ============================================================================

app = FastAPI(
    title="Helix Collective Webpage Service",
    description="Beautiful webpage with agent gallery and live coordination metrics",
    version="18.0.0",
    lifespan=lifespan,
)

# ============================================================================
# MIDDLEWARE
# ============================================================================

# CORS Configuration - Production-safe origins
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

# Allow custom origins via environment variable
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
# HEALTH CHECKS
# ============================================================================


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "service": "helix-webpage-service",
        "status": "healthy",
        "version": "18.0.0",
        "templates_configured": templates is not None,
        "portal_monitoring": "active",
    }


@app.get("/health/webpage")
async def webpage_health_check():
    """Webpage-specific health check"""
    templates_exist = templates is not None
    templates_dir_exists = TEMPLATES_DIR.exists() if "TEMPLATES_DIR" in globals() else False

    return {
        "service": "helix-webpage-service",
        "status": "healthy",
        "templates_configured": templates_exist,
        "templates_directory": (str(TEMPLATES_DIR) if "TEMPLATES_DIR" in globals() else "unknown"),
        "templates_directory_exists": templates_dir_exists,
        "agent_gallery_available": (
            templates_dir_exists and (TEMPLATES_DIR / "agent_gallery.html").exists() if templates_dir_exists else False
        ),
    }


# ============================================================================
# WEBPAGE ENDPOINTS
# ============================================================================


@app.get("/", response_class=HTMLResponse)
async def serve_main_dashboard(request: Request):
    """Serve the main beautiful dashboard"""
    try:
        templates_exist = templates is not None
        if templates_exist:
            # Get live UCF metrics
            ucf_metrics = await get_consolidated_ucf_metrics()

            # Get portal status
            portal_status = await portal_monitor.get_all_portal_status()

            # Render template with data
            return templates.TemplateResponse(
                "index.html",
                {
                    "request": request,
                    "ucf_metrics": ucf_metrics,
                    "portal_status": portal_status,
                    "timestamp": time.monotonic(),
                },
            )
        else:
            # Fallback to basic HTML
            return HTMLResponse(
                """
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Helix Collective - Restoring Webpage</title>
                    <meta name="viewport" content="width=device-width, initial-scale=1">
                    <style>
                        body {
                            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                            margin: 0;
                            padding: 20px;
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                            color: white;
                            min-height: 100vh;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                        }
                        .container {
                            text-align: center;
                            background: rgba(255, 255, 255, 0.1);
                            padding: 40px;
                            border-radius: 20px;
                            border: 2px solid #00BFA5;
                            backdrop-filter: blur(10px);
                        }
                        h1 { font-size: 3rem; margin-bottom: 10px; }
                        .status { font-size: 1.2rem; margin-bottom: 30px; color: #FFD700; }
                        .metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin: 30px 0; }
                        .metric { background: rgba(0, 0, 0, 0.3); padding: 20px; border-radius: 10px; }
                        .metric-label { font-size: 0.9rem; color: #A0A0A0; }
                        .metric-value { font-size: 1.5rem; font-weight: bold; color: #00BFA5; }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>🌀 Helix Collective</h1>
                        <p class="status">Webpage Restoration in Progress...</p>
                        <div class="metrics">
                            <div class="metric">
                                <div class="metric-label">Harmony</div>
                                <div class="metric-value">--</div>
                            </div>
                            <div class="metric">
                                <div class="metric-label">Resilience</div>
                                <div class="metric-value">--</div>
                            </div>
                            <div class="metric">
                                <div class="metric-label">Throughput</div>
                                <div class="metric-value">--</div>
                            </div>
                        </div>
                        <p>Templates directory not found. Please check template configuration.</p>
                    </div>
                </body>
                </html>
                """
            )
    except Exception as e:
        logger.error("Failed to serve main dashboard: %s", e)
        return HTMLResponse(
            """
            <!DOCTYPE html>
            <html>
            <head><title>Error</title></head>
            <body>
                <h1>❌ Error Serving Dashboard</h1>
                <p>An internal error occurred. Please try again later.</p>
                <p>Please check the backend logs for more information.</p>
            </body>
            </html>
            """,
            status_code=500,
        )


@app.get("/gallery", response_class=HTMLResponse)
async def serve_agent_gallery(request: Request):
    """Serve the agent gallery page"""
    try:
        gallery_path = find_templates_directory() / "agent_gallery.html"
        if gallery_path.exists():
            return HTMLResponse(content=gallery_path.read_text(encoding="utf-8"))
        else:
            logger.error("Agent gallery template not found: %s", gallery_path)

        # Fallback HTML if file doesn't exist
        return HTMLResponse(
            """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Agent Gallery - Helix Collective</title>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        margin: 0;
                        padding: 20px;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        min-height: 100vh;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        color: white;
                    }
                    .container {
                        text-align: center;
                        background: rgba(255, 255, 255, 0.1);
                        padding: 2rem;
                        border-radius: 10px;
                        backdrop-filter: blur(10px);
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>🌀 Agent Gallery</h1>
                    <p>Explore the Helix Collective's 16-agent network.</p>
                    <p><a href="/api/agents" style="color: #00ff00;">View Agent API →</a></p>
                    <p><a href="/" style="color: #00ff00;">← Back to Dashboard</a></p>
                </div>
            </body>
            </html>
            """,
            status_code=200,
        )
    except Exception as e:
        logger.error("Failed to serve agent gallery: %s", e)
        return HTMLResponse("An error occurred while loading this page.", status_code=500)


@app.get("/docs", response_class=HTMLResponse)
async def serve_swagger_docs(request: Request):
    """Serve Swagger documentation"""
    try:
        templates_dir = find_templates_directory()
        swagger_file = templates_dir / "swagger_docs.html"

        if swagger_file.exists():
            with open(swagger_file, encoding="utf-8") as f:
                html_content = f.read()

            # Replace absolute URLs with relative ones for local development
            html_content = html_content.replace("https://helixspiral.work", "")
            html_content = html_content.replace("https://fastapi.tiangolo.com/img/favicon.png", "/static/favicon.png")
            html_content = html_content.replace('href="https://helixspiral.work/docs', 'href="/docs')
            html_content = html_content.replace('href="/openapi.json"', 'href="/api/openapi.json"')

            return HTMLResponse(content=html_content)
        else:
            # Fallback to redirect
            return HTMLResponse(
                """
                <!DOCTYPE html>
                <html>
                <head>
                    <title>API Documentation - Helix Collective</title>
                    <meta http-equiv="refresh" content="0; url=/api/docs">
                    <style>
                        body {
                            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                            margin: 0;
                            padding: 20px;
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                            min-height: 100vh;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            color: white;
                        }
                        .container {
                            text-align: center;
                            background: rgba(255, 255, 255, 0.1);
                            padding: 2rem;
                            border-radius: 10px;
                            backdrop-filter: blur(10px);
                        }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>📚 API Documentation</h1>
                        <p>Redirecting to interactive Swagger documentation...</p>
                        <p><a href="/api/docs" style="color: #00ff00;">Click here if not redirected</a></p>
                        <p><a href="/" style="color: #00aaff;">← Back to Dashboard</a></p>
                    </div>
                </body>
                </html>
                """
            )
    except Exception as e:
        logger.error("Failed to serve Swagger docs: %s", e)
        return HTMLResponse("An error occurred.", status_code=500)


# ============================================================================
# METRICS ENDPOINTS
# ============================================================================


@app.get("/api/metrics")
async def get_live_metrics():
    """Get live UCF metrics"""
    return await get_consolidated_ucf_metrics()


@app.get("/api/portals")
async def get_portal_status():
    """Get all portal status"""
    return await portal_monitor.get_all_portal_status()


# Auth import — fail closed if unavailable
try:
    from apps.backend.core.auth import AuthManager

    _auth_available = True
except ImportError:
    _auth_available = False

# ============================================================================
# WEBSOCKET FOR LIVE METRICS
# ============================================================================


@app.websocket("/ws/metrics")
async def websocket_metrics(websocket: WebSocket, token: str = Query(None)):
    """WebSocket endpoint for live metrics streaming. Requires JWT ?token= param."""
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

    await websocket.accept()
    try:
        # Send live metrics every 5 seconds
        metrics = await get_consolidated_ucf_metrics()
        await websocket.send_json(metrics)
        await asyncio.sleep(5)
    except WebSocketDisconnect:
        logger.info("WebSocket metrics client disconnected")
    except Exception as e:
        logger.error("WebSocket metrics error: %s", e)


# ============================================================================
# STATIC FILE SERVING
# ============================================================================

# Mount static files if they exist
static_path = Path(__file__).parent.parent.parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# ============================================================================
# STANDALONE FUNCTIONS FOR CORE API
# ============================================================================


async def serve_main_dashboard_standalone(request: Request = None) -> HTMLResponse:
    """Serve the main dashboard webpage (standalone, no app routes)."""
    try:
        templates_dir = find_templates_directory()
        if templates_dir and (templates_dir / "index.html").exists():
            # Read the template file directly
            with open(templates_dir / "index.html", encoding="utf-8") as f:
                html_content = f.read()

            # Return as HTML response
            return HTMLResponse(content=html_content, status_code=200)
        else:
            return HTMLResponse("Templates not configured", status_code=500)
    except Exception as e:
        logger.error("Failed to serve main dashboard: %s", e)
        return HTMLResponse("An error occurred while loading the dashboard.", status_code=500)


async def serve_agent_gallery_standalone(request: Request = None) -> HTMLResponse:
    """Serve the agent gallery webpage (standalone, no app routes)."""
    try:
        templates_dir = find_templates_directory()
        if templates_dir and (templates_dir / "agent_gallery.html").exists():
            # Read the template file directly
            with open(templates_dir / "agent_gallery.html", encoding="utf-8") as f:
                html_content = f.read()

            # Return as HTML response
            return HTMLResponse(content=html_content, status_code=200)
        else:
            return HTMLResponse("Agent gallery template not found", status_code=500)
    except Exception as e:
        logger.error("Failed to serve agent gallery: %s", e)
        return HTMLResponse("An error occurred while loading this page.", status_code=500)


async def serve_swagger_docs_standalone(request: Request = None) -> HTMLResponse:
    """Serve API documentation page with links to interactive docs (standalone, no app routes)."""
    try:
        return HTMLResponse(
            """
            <!DOCTYPE html>
            <html>
            <head>
                <title>API Documentation - Helix Collective</title>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <script src="https://cdn.tailwindcss.com"></script>
                <style>
                    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
                    body { font-family: 'Inter', sans-serif; }
                </style>
            </head>
            <body class="bg-slate-950 text-slate-100 min-h-screen">
                <div class="max-w-6xl mx-auto px-6 py-12">
                    <header class="text-center mb-12">
                        <div class="mb-4">
                            <span class="text-6xl">📚</span>
                        </div>
                        <h1 class="text-4xl font-bold mb-4 bg-gradient-to-r from-cyan-400 via-purple-400 to-fuchsia-400 bg-clip-text text-transparent">
                            Helix Collective API
                        </h1>
                        <p class="text-xl text-slate-400 mb-6">
                            Interactive API Documentation
                        </p>
                        <p class="text-sm text-slate-500 max-w-2xl mx-auto">
                            Explore all available endpoints, test requests, and view response schemas for the Helix Collective Core API.
                        </p>
                    </header>

                    <div class="grid grid-cols-1 md:grid-cols-2 gap-8 mb-12">
                        <!-- Swagger UI -->
                        <a href="/api/docs" target="_blank" class="block">
                            <div class="bg-gradient-to-br from-slate-900/60 to-slate-800/40 rounded-xl ring-1 ring-white/10 p-8 h-full hover:ring-cyan-400/50 transition-all duration-300">
                                <div class="text-5xl mb-4">🔍</div>
                                <h3 class="text-2xl font-semibold mb-3">Swagger UI</h3>
                                <p class="text-slate-400 mb-4">
                                    Interactive API explorer with try-it-out functionality. Test all GET, POST, PUT, DELETE endpoints in real-time.
                                </p>
                                <div class="flex items-center text-cyan-400 font-medium">
                                    Open Swagger UI →
                                </div>
                            </div>
                        </a>

                        <!-- ReDoc -->
                        <a href="/api/redoc" target="_blank" class="block">
                            <div class="bg-gradient-to-br from-slate-900/60 to-slate-800/40 rounded-xl ring-1 ring-white/10 p-8 h-full hover:ring-purple-400/50 transition-all duration-300">
                                <div class="text-5xl mb-4">📖</div>
                                <h3 class="text-2xl font-semibold mb-3">ReDoc</h3>
                                <p class="text-slate-400 mb-4">
                                    Clean, responsive documentation with three-panel layout. Perfect for reading API specifications.
                                </p>
                                <div class="flex items-center text-purple-400 font-medium">
                                    Open ReDoc →
                                </div>
                            </div>
                        </a>
                    </div>

                    <!-- Quick Endpoints Overview -->
                    <div class="bg-slate-900/60 rounded-xl ring-1 ring-white/10 p-8 mb-8">
                        <h2 class="text-2xl font-semibold mb-6">Available Endpoints</h2>
                        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                            <div class="bg-slate-800/40 rounded-lg p-4">
                                <div class="text-cyan-400 font-medium mb-2">GET /health</div>
                                <div class="text-sm text-slate-400">System health check</div>
                            </div>
                            <div class="bg-slate-800/40 rounded-lg p-4">
                                <div class="text-cyan-400 font-medium mb-2">GET /ucf</div>
                                <div class="text-sm text-slate-400">UCF metrics data</div>
                            </div>
                            <div class="bg-slate-800/40 rounded-lg p-4">
                                <div class="text-cyan-400 font-medium mb-2">GET /agents</div>
                                <div class="text-sm text-slate-400">Agent status information</div>
                            </div>
                            <div class="bg-slate-800/40 rounded-lg p-4">
                                <div class="text-cyan-400 font-medium mb-2">GET /api/web-os/files/*</div>
                                <div class="text-sm text-slate-400">File system operations</div>
                            </div>
                            <div class="bg-slate-800/40 rounded-lg p-4">
                                <div class="text-cyan-400 font-medium mb-2">POST /api/web-os/terminal</div>
                                <div class="text-sm text-slate-400">Terminal commands</div>
                            </div>
                            <div class="bg-slate-800/40 rounded-lg p-4">
                                <div class="text-cyan-400 font-medium mb-2">GET /api/orchestrator/*</div>
                                <div class="text-sm text-slate-400">Agent orchestration</div>
                            </div>
                        </div>
                    </div>

                    <!-- Navigation -->
                    <div class="text-center">
                        <a href="/" class="inline-flex items-center px-6 py-3 bg-gradient-to-r from-cyan-500 to-purple-500 rounded-lg font-medium hover:from-cyan-600 hover:to-purple-600 transition-all duration-300">
                            ← Back to Dashboard
                        </a>
                    </div>
                </div>
            </body>
            </html>
            """
        )
    except Exception as e:
        logger.error("Failed to serve Swagger docs: %s", e)
        return HTMLResponse("An error occurred.", status_code=500)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8005)))

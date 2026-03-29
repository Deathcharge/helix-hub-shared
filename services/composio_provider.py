"""
Composio Integration Provider
==============================
Wraps Composio's REST API to provide runtime tool discovery (250k+ API tools)
via a single API key. Uses aiohttp directly to avoid SDK dependency.

Composio REST API base: https://backend.composio.dev/api/v2
Auth: X-API-Key header
"""

import hashlib
import json
import logging
import os
import time
from typing import Any

import aiohttp

from apps.backend.agent_capabilities.tool_framework import (
    ParameterType,
    Tool,
    ToolParameter,
    ToolResult,
    get_tool_registry,
)
from apps.backend.core.redis_client import get_redis

logger = logging.getLogger(__name__)

COMPOSIO_API_BASE = "https://backend.composio.dev/api/v2"
CACHE_TTL_SECONDS = 300  # 5 minutes
CACHE_KEY_PREFIX = "helix:composio:tools:"
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=30)


class ComposioProvider:
    """
    Provides access to Composio's 250k+ API tools via their REST API.

    Lazily initializes an aiohttp session. All methods gracefully handle
    the case where COMPOSIO_API_KEY is not configured.
    """

    def __init__(self) -> None:
        self._api_key: str | None = os.getenv("COMPOSIO_API_KEY")
        self._session: aiohttp.ClientSession | None = None

    @property
    def is_configured(self) -> bool:
        """Whether the Composio API key is set."""
        return bool(self._api_key)

    async def _get_session(self) -> aiohttp.ClientSession | None:
        """Lazy-init the aiohttp session. Returns None if not configured."""
        if not self._api_key:
            logger.debug("Composio API key not set, skipping request")
            return None
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                base_url=COMPOSIO_API_BASE,
                headers={
                    "X-API-Key": self._api_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=HTTP_TIMEOUT,
            )
        return self._session

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """
        Make an authenticated request to the Composio API.
        Returns the parsed JSON response, or None on failure.
        """
        session = await self._get_session()
        if session is None:
            return None

        try:
            async with session.request(method, path, params=params, json=json_body) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    logger.warning(
                        "Composio API error: %s %s returned %d: %s",
                        method,
                        path,
                        resp.status,
                        body[:500],
                    )
                    return None
                return await resp.json()
        except aiohttp.ClientError as e:
            logger.warning("Composio HTTP client error for %s %s: %s", method, path, e)
            return None
        except Exception as e:
            logger.warning("Unexpected error calling Composio %s %s: %s", method, path, e)
            return None

    # ------------------------------------------------------------------
    # Tool search
    # ------------------------------------------------------------------

    async def search_tools(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """
        Search Composio's tool catalog.

        Results are cached in Redis for 5 minutes keyed by the MD5 of the
        query string. Returns a list of tool dicts with id, name,
        description, and parameters.
        """
        if not self.is_configured:
            logger.debug("Composio not configured, returning empty tool list")
            return []

        # --- Redis cache check ---
        cache_key = self._cache_key(query)
        cached = await self._get_cached(cache_key)
        if cached is not None:
            return cached

        # --- HTTP request ---
        data = await self._request(
            "GET",
            "/actions",
            params={"query": query, "limit": str(limit)},
        )
        if data is None:
            return []

        items = data.get("items", data) if isinstance(data, dict) else data
        if not isinstance(items, list):
            logger.warning("Unexpected Composio search response shape: %s", type(items))
            return []

        tools: list[dict[str, Any]] = []
        for item in items[:limit]:
            if not isinstance(item, dict):
                continue
            tool_entry = {
                "id": item.get("appName", "") + "/" + item.get("name", item.get("id", "")),
                "name": item.get("displayName", item.get("name", "")),
                "description": item.get("description", ""),
                "parameters": item.get("parameters", []),
            }
            tools.append(tool_entry)

        # --- Cache result ---
        await self._set_cached(cache_key, tools)

        return tools

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    async def execute_tool(
        self,
        tool_id: str,
        params: dict[str, Any],
        user_id: str,
        entity_id: str | None = None,
    ) -> ToolResult:
        """
        Execute a Composio tool by ID.

        Returns a ToolResult from the Helix tool framework.
        """
        if not self.is_configured:
            return ToolResult(
                success=False,
                output=None,
                error="Composio integration is not configured (COMPOSIO_API_KEY not set)",
            )

        start_ms = time.monotonic()

        entity = entity_id or f"helix_user_{user_id}"
        body: dict[str, Any] = {
            "actionName": tool_id,
            "input": params,
            "entityId": entity,
        }

        data = await self._request("POST", "/actions/execute", json_body=body)
        elapsed_ms = (time.monotonic() - start_ms) * 1000

        if data is None:
            return ToolResult(
                success=False,
                output=None,
                error="Composio tool execution failed — no response from API",
                execution_time_ms=elapsed_ms,
            )

        # Composio wraps results differently depending on the action
        execution_output = data.get("response_data", data.get("data", data))
        error_msg = data.get("error")

        if error_msg:
            return ToolResult(
                success=False,
                output=execution_output,
                error=str(error_msg),
                execution_time_ms=elapsed_ms,
                metadata={"composio_tool_id": tool_id, "entity_id": entity},
            )

        return ToolResult(
            success=True,
            output=execution_output,
            execution_time_ms=elapsed_ms,
            metadata={"composio_tool_id": tool_id, "entity_id": entity},
        )

    # ------------------------------------------------------------------
    # Connections
    # ------------------------------------------------------------------

    async def get_connections(self, user_id: str) -> list[dict[str, Any]]:
        """List a user's connected apps in Composio."""
        if not self.is_configured:
            return []

        entity_id = f"helix_user_{user_id}"
        data = await self._request(
            "GET",
            "/connectedAccounts",
            params={"user_entity_id": entity_id},
        )
        if data is None:
            return []

        items = data.get("items", data) if isinstance(data, dict) else data
        if not isinstance(items, list):
            logger.warning("Unexpected Composio connections response shape: %s", type(items))
            return []

        connections: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            connections.append(
                {
                    "id": item.get("id", ""),
                    "app_name": item.get("appName", ""),
                    "status": item.get("status", "unknown"),
                    "created_at": item.get("createdAt"),
                }
            )
        return connections

    async def initiate_connection(self, user_id: str, app_name: str) -> str | None:
        """
        Start an OAuth flow for the given app.
        Returns the redirect URL for the user, or None on failure.
        """
        if not self.is_configured:
            logger.debug(
                "Composio not configured, cannot initiate connection for %s",
                app_name,
            )
            return None

        entity_id = f"helix_user_{user_id}"
        body = {
            "integrationId": app_name,
            "userEntity": entity_id,
        }
        data = await self._request("POST", "/connectedAccounts", json_body=body)
        if data is None:
            return None

        redirect_url = data.get("redirectUrl", data.get("connectionUrl"))
        if not redirect_url:
            logger.warning(
                "Composio connection response missing redirect URL: %s",
                list(data.keys()),
            )
            return None
        return str(redirect_url)

    # ------------------------------------------------------------------
    # Health / status
    # ------------------------------------------------------------------

    async def get_status(self) -> dict[str, Any]:
        """
        Health check: is Composio configured and reachable?
        """
        if not self.is_configured:
            return {
                "configured": False,
                "reachable": False,
                "message": "COMPOSIO_API_KEY not set",
            }

        # Light-weight probe: list a single action
        data = await self._request("GET", "/actions", params={"limit": "1"})
        reachable = data is not None

        return {
            "configured": True,
            "reachable": reachable,
            "message": "ok" if reachable else "Composio API unreachable",
        }

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # ------------------------------------------------------------------
    # Redis cache helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _cache_key(query: str) -> str:
        digest = hashlib.md5(query.encode("utf-8")).hexdigest()
        return f"{CACHE_KEY_PREFIX}{digest}"

    @staticmethod
    async def _get_cached(key: str) -> list[dict[str, Any]] | None:
        try:
            r = await get_redis()
            if r is None:
                return None
            raw = await r.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as e:
            logger.warning("Redis cache read error for %s: %s", key, e)
            return None

    @staticmethod
    async def _set_cached(key: str, value: list[dict[str, Any]]) -> None:
        try:
            r = await get_redis()
            if r is None:
                return
            await r.set(key, json.dumps(value), ex=CACHE_TTL_SECONDS)
        except Exception as e:
            logger.warning("Redis cache write error for %s: %s", key, e)


# ======================================================================
# Singleton accessor
# ======================================================================

_composio_provider: ComposioProvider | None = None


def get_composio_provider() -> ComposioProvider:
    """Return the module-level ComposioProvider singleton."""
    global _composio_provider
    if _composio_provider is None:
        _composio_provider = ComposioProvider()
    return _composio_provider


# ======================================================================
# Meta-tool registration
# ======================================================================


def register_composio_meta_tools(registry=None) -> None:
    """
    Register three Composio meta-tools in the Helix ToolRegistry so that
    agents can discover and invoke Composio tools at runtime.

    1. composio_search_tools  - search the Composio catalog
    2. composio_execute_tool  - execute a specific Composio tool
    3. composio_list_connections - list the user's connected apps
    """
    if registry is None:
        registry = get_tool_registry()

    provider = get_composio_provider()

    # ---- 1. composio_search_tools ----

    async def _handle_search_tools(params: dict[str, Any], context: dict[str, Any] | None = None) -> ToolResult:
        query = params.get("query", "")
        limit = params.get("limit", 10)
        if not query:
            return ToolResult(
                success=False,
                output=None,
                error="'query' parameter is required",
            )
        try:
            tools = await provider.search_tools(query, limit=limit)
            return ToolResult(success=True, output=tools)
        except Exception as e:
            logger.warning("composio_search_tools handler error: %s", e)
            return ToolResult(success=False, output=None, error=str(e))

    search_tool = Tool(
        name="composio_search_tools",
        description=(
            "Search Composio's catalog of 250k+ API tools. Returns matching "
            "tools with their IDs, names, descriptions, and parameter schemas."
        ),
        parameters=[
            ToolParameter(
                name="query",
                type=ParameterType.STRING,
                description="Search query describing the desired tool or action",
                required=True,
            ),
            ToolParameter(
                name="limit",
                type=ParameterType.INTEGER,
                description="Maximum number of results to return",
                required=False,
                default=10,
                min_value=1,
                max_value=50,
            ),
        ],
        handler=_handle_search_tools,
        category="integrations",
        tags=["composio", "tools", "search"],
        timeout_seconds=30,
    )
    registry.register(search_tool)

    # ---- 2. composio_execute_tool ----

    async def _handle_execute_tool(params: dict[str, Any], context: dict[str, Any] | None = None) -> ToolResult:
        tool_id = params.get("tool_id", "")
        parameters = params.get("parameters", {})
        if not tool_id:
            return ToolResult(
                success=False,
                output=None,
                error="'tool_id' parameter is required",
            )
        user_id = (context or {}).get("user_id", "anonymous")
        entity_id = (context or {}).get("entity_id")
        try:
            return await provider.execute_tool(tool_id, parameters, user_id=user_id, entity_id=entity_id)
        except Exception as e:
            logger.warning("composio_execute_tool handler error: %s", e)
            return ToolResult(success=False, output=None, error=str(e))

    execute_tool = Tool(
        name="composio_execute_tool",
        description=(
            "Execute a Composio tool by its ID with the given parameters. "
            "Use composio_search_tools first to discover available tool IDs."
        ),
        parameters=[
            ToolParameter(
                name="tool_id",
                type=ParameterType.STRING,
                description="The Composio tool ID to execute (e.g. 'github/GITHUB_CREATE_ISSUE')",
                required=True,
            ),
            ToolParameter(
                name="parameters",
                type=ParameterType.OBJECT,
                description="Parameters to pass to the Composio tool",
                required=False,
                default={},
            ),
        ],
        handler=_handle_execute_tool,
        category="integrations",
        tags=["composio", "tools", "execute"],
        timeout_seconds=60,
    )
    registry.register(execute_tool)

    # ---- 3. composio_list_connections ----

    async def _handle_list_connections(params: dict[str, Any], context: dict[str, Any] | None = None) -> ToolResult:
        user_id = (context or {}).get("user_id", "anonymous")
        try:
            connections = await provider.get_connections(user_id)
            return ToolResult(success=True, output=connections)
        except Exception as e:
            logger.warning("composio_list_connections handler error: %s", e)
            return ToolResult(success=False, output=None, error=str(e))

    list_connections_tool = Tool(
        name="composio_list_connections",
        description=(
            "List the current user's connected apps in Composio. "
            "Shows which third-party services are authorized for tool execution."
        ),
        parameters=[],
        handler=_handle_list_connections,
        category="integrations",
        tags=["composio", "connections", "oauth"],
        timeout_seconds=15,
    )
    registry.register(list_connections_tool)

    logger.info("Registered 3 Composio meta-tools in ToolRegistry")

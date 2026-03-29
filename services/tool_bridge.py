"""
Unified Tool Bridge
===================
Bridges the separate tool/node registries into a single ToolRegistry.

Strategy: ADDITIVE ONLY. Existing registries keep working as-is.
This module creates Tool wrappers that delegate to the original handlers,
and registers them in the global ToolRegistry under namespaced names.

Naming convention:
  - ToolRegistry built-in tools: "calculator", "format_json" (unchanged)
  - Spiral nodes: "spiral:postgresql", "spiral:slack"
  - Integration actions: "integration:slack:send_message"
  - MCP tools: "mcp:memory:store_memory"
  - Composio: "composio:search_tools" (registered via composio_provider.py)
"""

import logging
import time

from apps.backend.agent_capabilities.tool_framework import ParameterType, Tool, ToolParameter

logger = logging.getLogger(__name__)

# Lazy module-level imports for testability (allows patch('services.tool_bridge.X'))
try:
    from apps.backend.helix_spirals.additional_integrations import get_all_nodes
except ImportError as e:
    logger.debug("Spiral nodes not available: %s", e)
    get_all_nodes = None  # type: ignore[assignment]

try:
    from apps.backend.helix_spirals.integrations.base import INTEGRATION_REGISTRY
except ImportError as e:
    logger.debug("Integration registry not available: %s", e)
    INTEGRATION_REGISTRY = {}  # type: ignore[assignment]

try:
    from apps.backend.routes.mcp_gateway import MCP_SERVERS
except ImportError as e:
    logger.debug("MCP servers not available: %s", e)
    MCP_SERVERS = {}  # type: ignore[assignment]


# ============================================================================
# Spiral Node → Tool Adapter
# ============================================================================


class SpiralNodeToolAdapter:
    """Wraps BaseNode subclasses from integration_nodes / additional_integrations into Tools."""

    @staticmethod
    def adapt(node_type: str, node_class: type) -> Tool | None:
        """Create a Tool from a spiral node class."""
        try:
            description = getattr(node_class, "description", "") or f"{node_type} spiral node"
            category_attr = getattr(node_class, "category", None)
            category = category_attr.value if hasattr(category_attr, "value") else "spiral"
            icon = getattr(node_class, "icon", "⚙️")

            # Build a generic handler that wraps node execution
            async def handler(config: str = "{}", input_data: str = "{}") -> str:
                import json

                try:
                    from apps.backend.helix_spirals.integration_nodes import NodeConfig

                    config_dict = json.loads(config) if isinstance(config, str) else config
                    input_dict = json.loads(input_data) if isinstance(input_data, str) else input_data

                    node_config = NodeConfig(
                        id=f"tool_{node_type}_{int(time.time())}",
                        type=node_type,
                        name=node_type,
                        config=config_dict,
                    )
                    node = node_class(node_config)
                    result = await node.execute(input_dict, {})
                    return json.dumps(result.data) if result.success else f"Error: {result.error}"
                except Exception as e:
                    return f"Error: {e}"

            return Tool(
                name=f"spiral:{node_type}",
                description=f"[{icon}] {description}",
                parameters=[
                    ToolParameter(
                        name="config",
                        type=ParameterType.STRING,
                        description="JSON configuration object for the node (connection strings, API keys, etc.)",
                        required=False,
                        default="{}",
                    ),
                    ToolParameter(
                        name="input_data",
                        type=ParameterType.STRING,
                        description="JSON input data to process",
                        required=False,
                        default="{}",
                    ),
                ],
                handler=handler,
                category=f"spiral:{category}",
                tags=[category, "spiral", node_type],
                timeout_seconds=60,
            )
        except Exception as e:
            logger.warning("Failed to adapt spiral node '%s': %s", node_type, e)
            return None


# ============================================================================
# Integration → Tool Adapter
# ============================================================================


class IntegrationToolAdapter:
    """Wraps INTEGRATION_REGISTRY entries into Tools (one tool per action)."""

    @staticmethod
    def adapt(integration_key: str, integration_info: dict) -> list[Tool]:
        """Create one Tool per action in an integration.

        Returns an empty list for integrations backed by GenericIntegration
        (stub connectors awaiting full implementation) so they don't appear
        in the tool registry as callable tools.  These integrations are still
        discoverable via the Zapier / MCP hub.
        """
        tools = []
        try:
            actions = integration_info.get("actions", [])
            description = integration_info.get("description", f"{integration_key} integration")
            auth_type = integration_info.get("auth_type", "api_key")
            integration_class = integration_info.get("class")

            # Skip stub integrations — they raise NotImplementedError at runtime
            try:
                from apps.backend.helix_spirals.integrations.base import GenericIntegration

                if integration_class is GenericIntegration:
                    logger.debug(
                        "Skipping tool registration for stub integration '%s' (GenericIntegration)",
                        integration_key,
                    )
                    return []
            except ImportError as e:
                logger.debug("Could not import GenericIntegration base class: %s", e)

            for action in actions:
                action_name = action if isinstance(action, str) else str(action)

                async def handler(
                    action_params: str = "{}",
                    access_token: str = "",
                    _key: str = integration_key,
                    _action: str = action_name,
                    _cls: type = integration_class,
                ) -> str:
                    import json

                    try:
                        params = json.loads(action_params) if isinstance(action_params, str) else action_params
                        if _cls is None:
                            return f"Error: Integration class not available for {_key}"
                        instance = _cls(access_token=access_token)
                        result = await instance.execute(_action, params)
                        return json.dumps(result) if isinstance(result, dict | list) else str(result)
                    except NotImplementedError:
                        return f"Error: {_key}.{_action} is not yet implemented. Consider using Composio for this integration."
                    except Exception as e:
                        return f"Error: {e}"

                tools.append(
                    Tool(
                        name=f"integration:{integration_key}:{action_name}",
                        description=f"{description} — {action_name.replace('_', ' ')} (auth: {auth_type})",
                        parameters=[
                            ToolParameter(
                                name="action_params",
                                type=ParameterType.STRING,
                                description=f"JSON parameters for the {action_name} action",
                                required=False,
                                default="{}",
                            ),
                            ToolParameter(
                                name="access_token",
                                type=ParameterType.STRING,
                                description=f"OAuth/API token for {integration_key}",
                                required=False,
                                default="",
                            ),
                        ],
                        handler=handler,
                        category=f"integration:{integration_key}",
                        tags=["integration", integration_key, action_name],
                        timeout_seconds=30,
                    )
                )

        except Exception as e:
            logger.warning("Failed to adapt integration '%s': %s", integration_key, e)

        return tools


# ============================================================================
# MCP Server → Tool Adapter
# ============================================================================


class MCPToolAdapter:
    """Wraps MCP_SERVERS static tool definitions into placeholder Tools."""

    @staticmethod
    def adapt(server_name: str, tool_names: list[str]) -> list[Tool]:
        """Create placeholder Tools for MCP server tools."""
        tools = []
        for tool_name in tool_names:

            async def handler(
                params: str = "{}",
                _server: str = server_name,
                _tool: str = tool_name,
            ) -> str:
                try:
                    from apps.backend.integrations.mcp_client import get_mcp_client

                    client = get_mcp_client()
                    import json

                    result = await client.call_tool(_tool, json.loads(params))
                    return str(result)
                except ImportError:
                    return f"Error: MCP client not available for {_server}:{_tool}"
                except Exception as e:
                    return f"Error: {e}"

            tools.append(
                Tool(
                    name=f"mcp:{server_name}:{tool_name}",
                    description=f"MCP {server_name} server — {tool_name.replace('_', ' ')}",
                    parameters=[
                        ToolParameter(
                            name="params",
                            type=ParameterType.STRING,
                            description=f"JSON parameters for {tool_name}",
                            required=False,
                            default="{}",
                        ),
                    ],
                    handler=handler,
                    category=f"mcp:{server_name}",
                    tags=["mcp", server_name, tool_name],
                    timeout_seconds=30,
                )
            )
        return tools


# ============================================================================
# Main Bridge Registration
# ============================================================================


def register_all_bridges(registry) -> dict[str, int]:
    """
    Register all bridge tools into the unified ToolRegistry.

    Each section is wrapped in try/except so one registry failing
    doesn't block others. Returns stats dict with counts per source.
    """
    stats = {
        "spiral_nodes": 0,
        "integrations": 0,
        "mcp_tools": 0,
    }

    # 1. Spiral nodes (integration + additional + advanced)
    try:
        if get_all_nodes is not None:
            all_nodes = get_all_nodes()
            for node_type, node_class in all_nodes.items():
                tool = SpiralNodeToolAdapter.adapt(node_type, node_class)
                if tool:
                    try:
                        registry.register(tool)
                        stats["spiral_nodes"] += 1
                    except Exception as e:
                        logger.debug("Skipping duplicate spiral tool '%s': %s", node_type, e)
        else:
            logger.debug("Spiral nodes not available, skipping")
    except Exception as e:
        logger.warning("Failed to bridge spiral nodes: %s", e)

    # 2. Integrations
    try:
        for key, info in INTEGRATION_REGISTRY.items():
            integration_tools = IntegrationToolAdapter.adapt(key, info)
            for tool in integration_tools:
                try:
                    registry.register(tool)
                    stats["integrations"] += 1
                except Exception as e:
                    logger.debug("Skipping duplicate integration tool '%s': %s", tool.name, e)
    except Exception as e:
        logger.warning("Failed to bridge integrations: %s", e)

    # 3. MCP server tools
    try:
        for server_name, tool_names in MCP_SERVERS.items():
            mcp_tools = MCPToolAdapter.adapt(server_name, tool_names)
            for tool in mcp_tools:
                try:
                    registry.register(tool)
                    stats["mcp_tools"] += 1
                except Exception as e:
                    logger.debug("Skipping duplicate MCP tool '%s': %s", tool.name, e)
    except Exception as e:
        logger.warning("Failed to bridge MCP tools: %s", e)

    total = sum(stats.values())
    logger.info(
        "Tool bridge: registered %d tools (spiral=%d, integration=%d, mcp=%d)",
        total,
        stats["spiral_nodes"],
        stats["integrations"],
        stats["mcp_tools"],
    )

    return stats

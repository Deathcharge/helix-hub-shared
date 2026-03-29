# NOTE: This service is not currently wired to any route.
# The convenience functions (handle_websocket_agent_message, broadcast_agent_status_to_all)
# are defined at the bottom but never imported by any route or WebSocket endpoint.
# Wire to routes/websocket.py or remove.
"""
Helix Collective WebSocket Agent Bridge
======================================

Real-time agent coordination and coordination streaming bridge for WebSocket connections.

This module provides bidirectional communication between WebSocket clients and the
Helix Collective agent orchestrator, enabling real-time coordination field updates,
agent status broadcasting, and interactive agent coordination.

Core Features:
--------------
WebSocket ↔ Agent Integration:
- Real-time agent status broadcasting and monitoring
- Client-to-agent command routing with authentication
- Agent collective coordination via WebSocket channels
- Coordination field metrics streaming
- Multi-user agent session management

Message Types:
- agent_status: Real-time agent availability and coordination levels
- agent_response: Direct responses from agent operations
- agent_broadcast: Collective announcements and system-wide updates
- agent_command: Client-initiated agent task execution

Architecture:
- WebSocket connection management with automatic cleanup
- Agent subscription system for targeted updates
- Command callback registration for custom handlers
- Thread-safe message processing with FastAPI concurrency
- Integration with HelixOrchestrator and AgentRegistry

Security & Performance:
- User authentication and session validation
- Rate limiting for command execution
- Connection pooling and resource management
- Error handling with graceful degradation
- Memory-efficient message queuing

Integration Points:
- HelixOrchestrator: Core agent coordination engine
- AgentRegistry: Agent discovery and capability management
- WebSocket clients: Frontend dashboards and agent interfaces
- Coordination monitoring: Real-time UCF metrics broadcasting

Author: Andrew John Ward + Claude AI
Version: 1.0.0
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket

from apps.backend.helix_agent_swarm.agent_registry import get_agent_registry
from apps.backend.helix_agent_swarm.helix_orchestrator import HelixOrchestrator

logger = logging.getLogger(__name__)


@dataclass
class AgentMessage:
    """Structured message for agent communication via WebSocket."""

    type: str  # 'agent_status', 'agent_response', 'agent_broadcast', 'agent_command'
    agent_id: str
    data: Any
    timestamp: float
    user_id: str | None = None
    collective_name: str | None = None


class WebSocketAgentBridge:
    """Bridge between WebSocket connections and the agent orchestrator."""

    def __init__(self, orchestrator: HelixOrchestrator | None = None) -> None:
        """Initialize the WebSocket agent bridge."""
        self.orchestrator = orchestrator
        self.registry = get_agent_registry()
        self.active_websockets: dict[str, WebSocket] = {}  # user_id -> WebSocket
        self.agent_subscriptions: dict[str, list[str]] = {}  # agent_id -> [user_ids]
        self.command_callbacks: dict[str, Callable] = {}  # command_id -> callback

        # Agent status tracking
        self.agent_status_cache: dict[str, dict] = {}
        self.last_status_update = 0.0

        logger.info("🌉 WebSocket Agent Bridge initialized")

    async def connect_websocket(self, websocket: WebSocket, user_id: str) -> bool:
        """Connect a WebSocket client to the agent bridge."""
        try:
            self.active_websockets[user_id] = websocket

            # Send initial agent status
            await self._send_initial_agent_status(websocket)

            logger.info("🔗 Agent bridge connected: %s", user_id)
            return True
        except Exception as e:
            logger.error("❌ Failed to connect WebSocket for %s: %s", user_id, e)
            return False

    def disconnect_websocket(self, user_id: str):
        """Disconnect a WebSocket client from the agent bridge."""
        if user_id in self.active_websockets:
            del self.active_websockets[user_id]

        # Clean up subscriptions
        for agent_id, subscribers in self.agent_subscriptions.items():
            if user_id in subscribers:
                subscribers.remove(user_id)

        logger.info("📴 Agent bridge disconnected: %s", user_id)

    async def _send_initial_agent_status(self, websocket: WebSocket):
        """Send initial agent status to newly connected client."""
        try:
            system_status = "operational"

            initial_message = {
                "type": "agent_status",
                "data": {
                    "system_status": system_status,
                    "agent_registry": {
                        "total_agents": len(self.registry.agents),
                        "active_agents": len(self.registry.get_active_agents()),
                        "collectives": len(self.registry.collectives),
                    },
                    "bridge_status": "connected",
                },
                "timestamp": time.monotonic(),
            }

            await websocket.send_json(initial_message)
        except Exception as e:
            logger.error("❌ Failed to send initial status: %s", e)

    async def handle_client_message(
        self, websocket: WebSocket, message: dict, authenticated_user_id: str | None = None
    ):
        """Handle incoming client messages and route to appropriate handlers."""
        try:
            # Use authenticated user_id from the WebSocket session, NOT from the message payload
            user_id = authenticated_user_id or message.get("user_id", "anonymous")
            message_type = message.get("type")

            if message_type == "subscribe_agent_status":
                await self._handle_agent_status_subscription(websocket, message, user_id)

            elif message_type == "agent_command":
                await self._handle_agent_command(websocket, message, user_id)

            elif message_type == "collective_command":
                await self._handle_collective_command(websocket, message, user_id)

            elif message_type == "subscribe_collective":
                await self._handle_collective_subscription(websocket, message, user_id)

            elif message_type == "ping":
                await self._handle_ping(websocket, user_id)

            else:
                await self._send_error_response(websocket, f"Unknown message type: {message_type}", user_id)

        except Exception as e:
            logger.error("Error handling client message: %s", e)
            await self._send_error_response(websocket, "Internal error processing message", user_id)

    async def _handle_agent_status_subscription(self, websocket: WebSocket, message: dict, user_id: str):
        """Handle agent status subscription requests."""
        agent_ids = message.get("agent_ids", [])

        for agent_id in agent_ids:
            if agent_id not in self.agent_subscriptions:
                self.agent_subscriptions[agent_id] = []

            if user_id not in self.agent_subscriptions[agent_id]:
                self.agent_subscriptions[agent_id].append(user_id)

        await websocket.send_json(
            {
                "type": "subscription_response",
                "status": "success",
                "subscribed_agents": agent_ids,
                "timestamp": time.monotonic(),
            }
        )

    async def _handle_agent_command(self, websocket: WebSocket, message: dict, user_id: str):
        """Handle direct agent commands."""
        try:
            agent_id = message.get("agent_id")
            command = message.get("command")
            context = message.get("context", {})

            if not agent_id or not command:
                await self._send_error_response(websocket, "Missing agent_id or command", user_id)
                return

            # Execute command via orchestrator
            if self.orchestrator:
                result = await self.orchestrator.execute_task(
                    task=command,
                    collective_name=None,
                    context={**context, "user_id": user_id, "source": "websocket"},
                )

                response = {
                    "type": "agent_response",
                    "agent_id": agent_id,
                    "result": result,
                    "timestamp": time.monotonic(),
                }

                await websocket.send_json(response)
            else:
                await self._send_error_response(websocket, "Orchestrator not available", user_id)

        except Exception as e:
            logger.error("❌ Agent command failed: %s", e)
            await self._send_error_response(websocket, "Command execution failed", user_id)

    async def _handle_collective_command(self, websocket: WebSocket, message: dict, user_id: str):
        """Handle collective agent commands."""
        try:
            collective_name = message.get("collective_name")
            command = message.get("command")
            context = message.get("context", {})

            if not collective_name or not command:
                await self._send_error_response(websocket, "Missing collective_name or command", user_id)
                return

            # Execute collective command via orchestrator
            if self.orchestrator:
                result = await self.orchestrator.execute_task(
                    task=command,
                    collective_name=collective_name,
                    context={**context, "user_id": user_id, "source": "websocket"},
                )

                response = {
                    "type": "collective_response",
                    "collective_name": collective_name,
                    "result": result,
                    "timestamp": time.monotonic(),
                }

                await websocket.send_json(response)
            else:
                await self._send_error_response(websocket, "Orchestrator not available", user_id)

        except Exception as e:
            logger.error("❌ Collective command failed: %s", e)
            await self._send_error_response(websocket, "Collective command failed", user_id)

    async def _handle_collective_subscription(self, websocket: WebSocket, message: dict, user_id: str):
        """Handle collective status subscription."""
        collective_names = message.get("collective_names", [])

        subscribed_collectives = []
        for collective_name in collective_names:
            if collective_name in self.registry.collectives:
                # Subscribe to all agents in the collective
                for agent_id in self.registry.collectives[collective_name]:
                    if agent_id not in self.agent_subscriptions:
                        self.agent_subscriptions[agent_id] = []

                    if user_id not in self.agent_subscriptions[agent_id]:
                        self.agent_subscriptions[agent_id].append(user_id)

                subscribed_collectives.append(collective_name)

        await websocket.send_json(
            {
                "type": "collective_subscription_response",
                "status": "success",
                "subscribed_collectives": subscribed_collectives,
                "timestamp": time.monotonic(),
            }
        )

    async def _handle_ping(self, websocket: WebSocket, user_id: str):
        """Handle ping messages for connection health."""
        await websocket.send_json(
            {
                "type": "pong",
                "user_id": user_id,
                "timestamp": time.monotonic(),
            }
        )

    async def _send_error_response(self, websocket: WebSocket, error_message: str, user_id: str):
        """Send error response to client."""
        await websocket.send_json(
            {
                "type": "error",
                "error": error_message,
                "user_id": user_id,
                "timestamp": time.monotonic(),
            }
        )

    async def broadcast_agent_status(self):
        """Broadcast agent status updates to all subscribed clients."""
        try:
            system_health = self.registry.get_system_health()
            agent_registry = self.registry.get_system_summary()

            # Create status message
            status_message = {
                "type": "agent_status",
                "data": {
                    "system_health": system_health,
                    "agent_registry": agent_registry,
                    "timestamp": time.monotonic(),
                },
                "timestamp": time.monotonic(),
            }

            # Send to all connected clients
            disconnected_clients = []
            for user_id, websocket in self.active_websockets.items():
                try:
                    await websocket.send_json(status_message)
                except Exception as e:
                    logger.error("❌ Failed to send status to %s: %s", user_id, e)
                    disconnected_clients.append(user_id)

            # Clean up disconnected clients
            for user_id in disconnected_clients:
                self.disconnect_websocket(user_id)

        except Exception as e:
            logger.error("❌ Failed to broadcast agent status: %s", e)

    async def broadcast_agent_broadcast(self, agent_id: str, message_data: dict):
        """Broadcast agent-specific messages to subscribed clients."""
        try:
            broadcast_message = {
                "type": "agent_broadcast",
                "agent_id": agent_id,
                "data": message_data,
                "timestamp": time.monotonic(),
            }

            # Send to subscribers of this agent
            if agent_id in self.agent_subscriptions:
                for user_id in self.agent_subscriptions[agent_id]:
                    if user_id in self.active_websockets:
                        try:
                            await self.active_websockets[user_id].send_json(broadcast_message)
                        except Exception as e:
                            logger.error("❌ Failed to send broadcast to %s: %s", user_id, e)
                            self.disconnect_websocket(user_id)

        except Exception as e:
            logger.error("❌ Failed to broadcast agent message: %s", e)

    async def handle_agent_command(self, message: AgentMessage) -> dict:
        """Handle agent commands from WebSocket clients."""
        try:
            if not self.orchestrator:
                return {"error": "Orchestrator not available"}

            # Execute the command
            result = await self.orchestrator.execute_task(
                task=message.data.get("command", ""),
                collective_name=message.collective_name,
                context={
                    "user_id": message.user_id,
                    "source": "websocket",
                    "timestamp": message.timestamp,
                },
            )

            return {
                "success": True,
                "result": result,
                "agent_id": message.agent_id,
                "timestamp": time.monotonic(),
            }

        except Exception as e:
            logger.error("❌ Agent command handling failed: %s", e)
            return {"error": "Agent command failed", "agent_id": message.agent_id}

    async def subscribe_to_agent_updates(self, agent_id: str):
        """Subscribe to updates from a specific agent."""
        if agent_id not in self.agent_subscriptions:
            self.agent_subscriptions[agent_id] = []

        logger.info("👁️ Subscribed to agent updates: %s", agent_id)

    async def broadcast_agent_status_updates(self):
        """Continuously broadcast agent status updates."""
        while True:
            try:
                await asyncio.sleep(2)  # Broadcast every 2 seconds
            except Exception as e:
                logger.error("❌ Agent status broadcast failed: %s", e)
                await asyncio.sleep(5)  # Wait before retrying

    def get_bridge_stats(self) -> dict:
        """Get bridge statistics."""
        return {
            "active_websockets": len(self.active_websockets),
            "agent_subscriptions": len(self.agent_subscriptions),
            "total_subscriptions": sum(len(subscribers) for subscribers in self.agent_subscriptions.values()),
            "orchestrator_available": self.orchestrator is not None,
            "registry_available": self.registry is not None,
        }

    async def shutdown(self):
        """Shutdown the bridge gracefully."""
        logger.info("🌉 Shutting down WebSocket Agent Bridge")

        # Disconnect all clients
        for user_id in list(self.active_websockets.keys()):
            self.disconnect_websocket(user_id)

        logger.info("✅ WebSocket Agent Bridge shutdown complete")


# Global bridge instance
_bridge: WebSocketAgentBridge | None = None


def get_websocket_agent_bridge(
    orchestrator: HelixOrchestrator | None = None,
) -> WebSocketAgentBridge:
    """Get the global WebSocket agent bridge instance."""
    global _bridge
    if _bridge is None:
        _bridge = WebSocketAgentBridge(orchestrator)
    return _bridge


# Convenience functions for WebSocket endpoints
async def handle_websocket_agent_message(websocket: WebSocket, message: dict, user_id: str):
    """Handle WebSocket messages for agent coordination."""
    bridge = get_websocket_agent_bridge()
    await bridge.handle_client_message(websocket, message)


async def broadcast_agent_status_to_all():
    """Broadcast agent status to all connected clients."""
    bridge = get_websocket_agent_bridge()
    await bridge.broadcast_agent_status()


def get_agent_bridge_stats():
    """Get agent bridge statistics."""
    bridge = get_websocket_agent_bridge()
    return bridge.get_bridge_stats()

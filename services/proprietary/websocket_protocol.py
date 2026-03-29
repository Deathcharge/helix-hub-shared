"""
HelixNet WebSocket Protocol - Proprietary Communication
Coordination-aware WebSocket communication with system state synchronization
"""

import logging
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any


# Local definitions for coordination communication
@dataclass
class CoordinationMessage:
    """Coordination-aware message for system communication"""

    content: str
    ucf_signature: str
    timestamp: str = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(UTC).isoformat()


@dataclass
class CoordinationResponse:
    """Response to coordination message"""

    message: CoordinationMessage
    status: str
    response_data: dict[str, Any]


logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)


class HelixNetWebSocket:
    """
    HelixNet WebSocket protocol for coordination-aware real-time communication.

    Features:
    - UCF context propagation in WebSocket messages
    - System state synchronization across connections
    - Coordination-aware connection management
    - Automatic signature verification
    - Performance tracking and metrics
    """

    def __init__(self) -> None:
        """
        Initialize a HelixNetWebSocket instance and configure its internal state.

        Attributes:
            connections (Dict[str, Any]): Mapping of connection IDs to connection data (websocket object and metadata).
            system_enabled (bool): Whether system integration is active.
            performance_score (float): Current coordination level.
            message_count (int): Total number of messages sent.
        Note:
            Attempts to initialize optional system integration during construction.
        """
        self.connections: dict[str, Any] = {}
        self.system_enabled = False
        self.performance_score = 0.0
        self.message_count = 0
        self._init_system_integration()

    def _init_system_integration(self):
        """
        Attempt to enable system integration with the HelixAI Pro orchestrator.

        If an orchestrator is available and indicates system support, sets self.system_enabled to True and logs an informational message. On any error or if the orchestrator is unavailable, logs a warning and leaves system support disabled.
        """
        try:
            from apps.backend.agents.agent_orchestrator import get_orchestrator

            orchestrator = get_orchestrator()

            if orchestrator and orchestrator.system_enabled:
                self.system_enabled = True
                logger.info("HelixNet WebSocket initialized with system support")
        except Exception as e:
            logger.warning("System integration unavailable: %s", e)

    async def send_coordination_message(self, connection_id: str, message: CoordinationMessage) -> bool:
        """
        Send a coordination-aware message over a registered WebSocket connection.

        Parameters:
            connection_id (str): Identifier of the registered WebSocket connection.
            message (CoordinationMessage): Message payload including UCF context and any signatures.

        Returns:
            `true` if the message was sent successfully, `false` otherwise.
        """
        if connection_id not in self.connections:
            logger.error("Connection %s not found", connection_id)
            return False

        try:
            # Serialize message with UCF context
            message_data = {
                "type": "coordination_message",
                "data": asdict(message),
                "system_enabled": self.system_enabled,
                "timestamp": datetime.now(UTC).isoformat(),
            }

            # Add system signature if enabled
            if self.system_enabled:
                message_data["system_signature"] = await self._generate_system_signature(message_data)

            # Send through WebSocket connection
            websocket = self.connections[connection_id]["websocket"]
            await websocket.send_json(message_data)

            self.message_count += 1

            logger.info("Sent coordination message to %s", connection_id)
            return True

        except Exception as e:
            logger.error("Failed to send coordination message: %s", e)
            return False

    async def receive_coordination_message(
        self, connection_id: str, message_data: dict[str, Any]
    ) -> CoordinationMessage | None:
        """
        Validate and deserialize an incoming coordination-aware WebSocket message.

        If system integration is enabled, the message's `system_signature` will be verified; if verification fails, the message is rejected. Expects `message_data` to include a "type" of "coordination_message" and a "data" object containing `service_name`, `operation`, `payload`, and `ucf_signature`.

        Parameters:
            connection_id (str): Identifier of the WebSocket connection the message was received from.
            message_data (dict): Raw message payload from the WebSocket. Expected shape:
                {
                    "type": "coordination_message",
                    "data": {
                        "service_name": str,
                        "operation": str,
                        "payload": Any,
                        "ucf_signature": str
                    },
                    "system_signature": str (optional)
                }

        Returns:
            CoordinationMessage: A constructed CoordinationMessage when the incoming message is valid; `None` otherwise.
        """
        try:
            # Verify system signature if enabled
            if self.system_enabled and "system_signature" in message_data:
                signature_valid = await self._verify_system_signature(message_data)
                if not signature_valid:
                    logger.warning("Invalid system signature from %s", connection_id)
                    return None

            # Deserialize message
            if message_data.get("type") == "coordination_message":
                data = message_data["data"]
                message = CoordinationMessage(
                    service_name=data["service_name"],
                    operation=data["operation"],
                    payload=data["payload"],
                    ucf_signature=data["ucf_signature"],
                )

                logger.info("Received coordination message from %s", connection_id)
                return message

            return None

        except Exception as e:
            logger.error("Failed to receive coordination message: %s", e)
            return None

    async def _generate_system_signature(self, message_data: dict[str, Any]) -> str:
        """
        Create a system signature for the given outbound message.

        If a HelixAI orchestrator is available, returns a signature string prefixed with "HelixNet-"; if no orchestrator is available or an error occurs, returns "unsigned".

        Parameters:
            message_data (Dict[str, Any]): Outbound message content provided for context when generating the signature.

        Returns:
            str: A HelixNet-prefixed signature string, or `"unsigned"` if signature generation is unavailable.
        """
        try:
            from apps.backend.agents.agent_orchestrator import get_orchestrator

            orchestrator = get_orchestrator()

            if orchestrator:
                signature = f"HelixNet-{time.monotonic():.6f}"
                return signature
        except Exception as e:
            logger.error("Failed to generate system signature: %s", e)

        return "unsigned"

    async def _verify_system_signature(self, message_data: dict[str, Any]) -> bool:
        """
        Validate the system signature field of an incoming message.

        Parameters:
            message_data (Dict[str, Any]): Incoming message payload; may contain a `system_signature` string.

        Returns:
            `true` if `message_data["system_signature"]` exists and begins with the `HelixNet-` prefix, `false` otherwise.
        """
        # For now, just check signature exists and starts with correct prefix
        signature = message_data.get("system_signature", "")
        return signature.startswith("HelixNet-")

    def register_connection(self, connection_id: str, websocket: Any):
        """
        Register a new WebSocket connection and initialize its metadata.

        Stores the websocket object under the provided connection_id and records:
        - connected_at: UTC timestamp in ISO 8601 format
        - message_count: initialized to 0

        Parameters:
            connection_id (str): Unique identifier for the connection.
            websocket (Any): WebSocket-like object to associate with the connection.
        """
        self.connections[connection_id] = {
            "websocket": websocket,
            "connected_at": datetime.now(UTC).isoformat(),
            "message_count": 0,
        }
        logger.info("Registered WebSocket connection: %s", connection_id)

    def unregister_connection(self, connection_id: str):
        """
        Remove a WebSocket connection from the internal registry if it exists.

        Parameters:
            connection_id (str): Identifier of the connection to remove. If the ID is not found, the method does nothing.
        """
        if connection_id in self.connections:
            del self.connections[connection_id]
            logger.info("Unregistered WebSocket connection: %s", connection_id)

    def get_status(self) -> dict[str, Any]:
        """
        Return current protocol status and metrics.

        Returns:
            status (Dict[str, Any]): Mapping with keys:
                - "system_enabled": `True` if system integration is active, `False` otherwise.
                - "active_connections": Number of registered active connections.
                - "total_messages": Total number of messages sent by this instance.
                - "performance_score": Current coordination level as a float.
        """
        return {
            "system_enabled": self.system_enabled,
            "active_connections": len(self.connections),
            "total_messages": self.message_count,
            "performance_score": self.performance_score,
        }

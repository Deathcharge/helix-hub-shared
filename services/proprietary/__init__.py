"""
Helix Collective Proprietary Technology Stack
=============================================

Proprietary integrations and advanced capabilities:

- System Authentication: Coordination-aware auth with UCF signatures
- WebSocket Protocol: HelixNet coordination-aware communication
- Coordination Migration: Zero-downtime state migration
- Database Schema: Optimized coordination state management

(c) Helix Collective 2024 - Proprietary Technology Stack
"""

from .system_auth import SystemAuth
from .websocket_protocol import HelixNetWebSocket

__all__ = [
    "HelixNetWebSocket",
    "SystemAuth",
]

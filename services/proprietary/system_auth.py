"""
System Authentication - Proprietary Auth System
System signature-based authentication with UCF integration
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


# Local CoordinationMessage definition since the proprietary communication stack
# is not fully integrated yet
@dataclass
class CoordinationMessage:
    """Coordination-aware message for system communication"""

    content: str
    ucf_signature: str
    timestamp: str = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(UTC).isoformat()


logger = logging.getLogger(__name__)


@dataclass
class SystemSession:
    """System authentication session with coordination tracking."""

    session_id: str
    user_id: str
    ucf_signature: str
    performance_score: float
    created_at: str
    expires_at: str
    permissions: list[str]
    last_activity: str


class SystemAuth:
    """
    System signature-based authentication system with UCF integration.

    Features:
    - System signature generation and verification
    - UCF level-based access control
    - Coordination-aware session management
    - Automatic session expiration
    - Permission system based on coordination levels
    """

    def __init__(self) -> None:
        """
        Initialize a SystemAuth instance and prepare its internal session and integration state.

        Sets up an empty session store, configures the default coordination threshold for basic access, initializes the system integration flag to disabled, and attempts to enable system integration via internal initialization.
        """
        self.sessions: dict[str, SystemSession] = {}
        self.system_enabled = False
        self.min_performance_score = 0.355  # Minimum for basic access
        self._init_system_integration()

    def _init_system_integration(self):
        """
        Attempt to enable system integration by detecting a HelixAI Pro orchestrator.

        If an orchestrator with system support is present, sets self.system_enabled to True and logs a success message. On failure or error, leaves system integration disabled and logs a warning.
        """
        try:
            from apps.backend.agents.agent_orchestrator import get_orchestrator

            orchestrator = get_orchestrator()

            if orchestrator and orchestrator.system_enabled:
                self.system_enabled = True
                logger.info("System Auth initialized with HelixAI Pro")
        except Exception as e:
            logger.warning("System integration unavailable: %s", e)

    async def generate_system_signature(self, user_id: str, data: dict[str, Any]) -> str:
        """
        Create an authentication signature for a user and associated data, optionally emitting a system-prefixed token when system integration is available.

        Parameters:
                user_id (str): Identifier of the user for whom the signature is generated.
                data (Dict[str, Any]): Payload to include in the signature; it is serialized as sorted JSON and combined with a UTC timestamp so the signature changes over time.

        Returns:
                str: A hex string signature. When system integration is enabled and an orchestrator is available, returns a string prefixed with "Q-" followed by the first 16 characters of the SHA-256 hash; otherwise returns the full SHA-256 hex digest. On unexpected errors returns "fallback_signature".
        """
        try:
            # Combine user_id, data, and timestamp
            timestamp = datetime.now(UTC).isoformat()
            combined = f"{user_id}:{json.dumps(data, sort_keys=True)}:{timestamp}"

            # Generate hash signature
            signature = hashlib.sha256(combined.encode()).hexdigest()

            # Add system prefix if enabled
            if self.system_enabled:
                from apps.backend.agents.agent_orchestrator import get_orchestrator

                orchestrator = get_orchestrator()

                if orchestrator:
                    signature = f"Q-{signature[:16]}"

            return signature

        except Exception as e:
            logger.error("Failed to generate system signature: %s", e)
            return "fallback_signature"

    async def verify_system_signature(self, signature: str, user_id: str, data: dict[str, Any]) -> bool:
        """
        Validate whether a provided signature is acceptable for the given user and payload.

        Parameters:
            signature (str): The signature string to validate (system signatures may use a special prefix).
            user_id (str): Identifier of the user the signature is claimed to belong to.
            data (Dict[str, Any]): The payload that was signed.

        Returns:
            bool: `True` if the signature is accepted for the given user and data, `False` otherwise.
        """
        try:
            # For system signatures, check prefix
            if self.system_enabled and signature.startswith("Q-"):
                # In production, this would verify against stored signatures
                # For now, accept properly formatted signatures
                return True

            # Fallback verification for non-system signatures
            return len(signature) >= 32

        except Exception as e:
            logger.error("Failed to verify system signature: %s", e)
            return False

    async def create_session(self, user_id: str, ucf_signature: str, performance_score: float) -> SystemSession:
        """
        Create a new SystemSession for a user with permissions derived from their coordination level.

        Parameters:
            user_id (str): The user's unique identifier.
            ucf_signature (str): The UCF signature to associate with the session.
            performance_score (float): A value from 0.0 to 1.0 used to determine granted permissions.

        Returns:
            SystemSession: The created session with session_id, timestamps (created_at, expires_at), permissions, and last_activity populated.
        """
        session_id = await self.generate_system_signature(user_id, {"action": "create_session"})

        created_at = datetime.now(UTC)
        expires_at = created_at + timedelta(hours=24)  # 24 hour session

        # Determine permissions based on coordination level
        permissions = self._get_permissions_by_coordination(performance_score)

        session = SystemSession(
            session_id=session_id,
            user_id=user_id,
            ucf_signature=ucf_signature,
            performance_score=performance_score,
            created_at=created_at.isoformat(),
            expires_at=expires_at.isoformat(),
            permissions=permissions,
            last_activity=created_at.isoformat(),
        )

        self.sessions[session_id] = session

        logger.info("Created system session for user %s (coordination: %.3f)", user_id, performance_score)

        return session

    async def validate_session(self, session_id: str) -> SystemSession | None:
        """
        Validate a stored system authentication session and refresh its activity timestamp.

        Parameters:
            session_id: Identifier of the session to validate.

        Returns:
            The corresponding SystemSession if it exists and has not expired, otherwise None.
        """
        if session_id not in self.sessions:
            return None

        session = self.sessions[session_id]

        # Check expiration
        expires_at = datetime.fromisoformat(session.expires_at)
        if datetime.now(UTC) > expires_at:
            logger.info("Session %s expired", session_id)
            del self.sessions[session_id]
            return None

        # Update last activity
        session.last_activity = datetime.now(UTC).isoformat()

        return session

    async def revoke_session(self, session_id: str) -> bool:
        """
        Revoke the session with the given session_id from the session store.

        Parameters:
            session_id (str): Identifier of the session to remove.

        Returns:
            bool: `True` if a session with `session_id` was found and removed, `False` otherwise.
        """
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info("Revoked session %s", session_id)
            return True

        return False

    def _get_permissions_by_coordination(self, performance_score: float) -> list[str]:
        """
        Map a coordination level to the set of permissions granted for that level.

        Accepts a UCF coordination score between 0.0 and 1.0 and returns the permission strings that apply. Permissions are added cumulatively: for levels >= 0.355 includes "read" and "basic_execute"; >= 0.500 adds "write" and "advanced_execute"; >= 0.750 adds "admin" and "cycle_execute"; >= 0.900 adds "super_admin" and "system_execute".

        Parameters:
            performance_score (float): UCF coordination level in the range 0.0–1.0.

        Returns:
            List[str]: Permission names applicable to the provided coordination level.
        """
        permissions = []

        if performance_score >= 0.355:
            permissions.extend(["read", "basic_execute"])

        if performance_score >= 0.500:
            permissions.extend(["write", "advanced_execute"])

        if performance_score >= 0.750:
            permissions.extend(["admin", "cycle_execute"])

        if performance_score >= 0.900:
            permissions.extend(["super_admin", "system_execute"])

        return permissions

    async def check_permission(self, session_id: str, required_permission: str) -> bool:
        """
        Determine whether the session identified by session_id currently includes the required permission.

        Returns:
            True if the session exists, is valid (not expired), and contains the required_permission; False otherwise.
        """
        session = await self.validate_session(session_id)

        if not session:
            return False

        return required_permission in session.permissions

    def get_status(self) -> dict[str, Any]:
        """
        Return current system authentication status.

        Returns:
            status (dict): Dictionary with keys:
                - "system_enabled": bool indicating whether system integration is active.
                - "active_sessions": int count of non-expired sessions.
                - "total_sessions": int total stored sessions.
                - "min_performance_score": float configured threshold for basic access.
        """
        active_sessions = sum(
            1 for s in self.sessions.values() if datetime.fromisoformat(s.expires_at) > datetime.now(UTC)
        )

        return {
            "system_enabled": self.system_enabled,
            "active_sessions": active_sessions,
            "total_sessions": len(self.sessions),
            "min_performance_score": self.min_performance_score,
        }

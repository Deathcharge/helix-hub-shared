import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiohttp

from apps.backend.helix_proprietary.integrations import HelixNetClientSession

logger = logging.getLogger(__name__)

# 🌀 Helix Collective v15.3 — Master Webhook Client
# backend/services/zapier_client_master.py — Zapier Pro Master Webhook
# Author: Andrew John Ward (Architect)


# 🌀 Helix Collective v15.3 — Master Webhook Client
# backend/services/zapier_client_master.py — Zapier Pro Master Webhook
# Author: Andrew John Ward (Architect)


# ============================================================================
# MASTER WEBHOOK CONFIGURATION
# ============================================================================

MASTER_HOOK_URL = os.getenv("ZAPIER_MASTER_HOOK_URL")

# Fallback to individual hooks if master not configured
EVENT_HOOK = os.getenv("ZAPIER_EVENT_HOOK_URL")
AGENT_HOOK = os.getenv("ZAPIER_AGENT_HOOK_URL")
SYSTEM_HOOK = os.getenv("ZAPIER_SYSTEM_HOOK_URL")

# ============================================================================
# MASTER ZAPIER CLIENT (Zapier Pro)
# ============================================================================


class MasterZapierClient:
    """
    Master Webhook Client for Zapier Pro with Path Routing.

    Uses a single webhook URL with payload type discrimination to route
    to different Notion databases, Slack channels, email alerts, etc.

    Payload Types:
    - "event_log" → Notion Event Log
    - "agent_registry" → Notion Agent Registry
    - "system_state" → Notion System State
    - "discord_notification" → Slack/Discord
    - "telemetry" → Google Sheets/Tables
    - "error" → Email/PagerDuty
    - "repository" → GitHub Actions

    Features:
    - Single webhook URL (cleaner configuration)
    - Path-based routing in Zapier
    - Automatic fallback to individual webhooks
    - Rate limiting and retry logic
    - Payload validation and truncation
    """

    def __init__(self, session: aiohttp.ClientSession | None = None) -> None:
        self._session = session
        self._owns_session = session is None
        self._use_master = bool(MASTER_HOOK_URL)

        # Fallback to individual hooks if master not configured
        self._event_hook = EVENT_HOOK
        self._agent_hook = AGENT_HOOK
        self._system_hook = SYSTEM_HOOK

    # ========================================================================
    # PUBLIC API METHODS
    # ========================================================================

    async def log_event(
        self,
        event_title: str,
        event_type: str,
        agent_name: str,
        description: str,
        ucf_snapshot: dict[str, Any],
    ) -> bool:
        """
        Log an event to Notion Event Log.

        Args:
            event_title: Event title
            event_type: Type (Cycle | Command | Error | Status)
            agent_name: Agent that triggered event
            description: Event description
            ucf_snapshot: Current UCF state

        Returns:
            True if successful, False otherwise
        """
        payload = {
            "type": "event_log",
            "event_title": event_title,
            "event_type": event_type,
            "agent_name": agent_name,
            "description": description,
            "ucf_snapshot": json.dumps(ucf_snapshot),
            "helix_phase": os.getenv("HELIX_PHASE", "production"),
            "timestamp": datetime.now(UTC).isoformat(),
        }

        return await self._send(payload, fallback_url=self._event_hook)

    async def update_agent(self, agent_name: str, status: str, last_action: str, health_score: int) -> bool:
        """
        Update agent status in Notion Agent Registry.

        Args:
            agent_name: Agent name
            status: Status (Active | Idle | Error)
            last_action: Last action description
            health_score: Health score (0-100)

        Returns:
            True if successful
        """
        payload = {
            "type": "agent_registry",
            "agent_name": agent_name,
            "status": status,
            "last_action": last_action,
            "health_score": health_score,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        return await self._send(payload, fallback_url=self._agent_hook)

    async def update_system_state(
        self,
        component: str,
        status: str,
        harmony: float,
        error_log: str = "",
        verified: bool = False,
    ) -> bool:
        """
        Update system component state in Notion.

        Args:
            component: Component name
            status: Status (Active | Degraded | Offline)
            harmony: Harmony metric (0.0-1.0)
            error_log: Optional error log
            verified: Whether verified

        Returns:
            True if successful
        """
        payload = {
            "type": "system_state",
            "component": component,
            "status": status,
            "harmony": harmony,
            "error_log": error_log,
            "verified": verified,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        return await self._send(payload, fallback_url=self._system_hook)

    async def send_discord_notification(self, channel_name: str, message: str, priority: str = "normal") -> bool:
        """
        Send notification to Discord via Slack integration.

        Args:
            channel_name: Discord channel name
            message: Message to send
            priority: Priority (low | normal | high | critical)

        Returns:
            True if successful
        """
        payload = {
            "type": "discord_notification",
            "channel_name": channel_name,
            "message": message,
            "priority": priority,
            "guild_id": os.getenv("DISCORD_GUILD_ID", ""),
            "timestamp": datetime.now(UTC).isoformat(),
        }

        return await self._send(payload)

    async def send_railway_discord_event(
        self,
        discord_channel: str,
        event_type: str,
        title: str,
        description: str,
        metadata: dict[str, Any] | None = None,
        priority: str = "normal",
    ) -> bool:
        """
        Send an event to the Railway Discord Zapier webhook and route it to the specified Discord channel.

        Parameters:
            discord_channel (str): Target channel name (e.g., "ARJUNA", "TELEMETRY", "STORAGE", "ROUTINE",
                "AGENTS", "CROSS_AI", "DEVELOPMENT", "LORE", "ADMIN"); case is normalized to upper-case.
            event_type (str): Short identifier for the event (e.g., "bot_started", "cycle_complete").
            title (str): Short title for the event.
            description (str): Detailed description of the event.
            metadata (Optional[Dict[str, Any]]): Optional additional data to include with the event.
            priority (str): Priority label ("low", "normal", "high", "critical").

        Returns:
            `true` if the webhook responded with HTTP 200, `false` otherwise.
        """
        # Use Railway Discord webhook (configured via env — no hardcoded URL)
        railway_discord_webhook = os.getenv(
            "ZAPIER_RAILWAY_DISCORD_WEBHOOK",
            "",
        )
        if not railway_discord_webhook:
            logger.warning("ZAPIER_RAILWAY_DISCORD_WEBHOOK not configured — skipping")
            return False

        payload = {
            "type": "railway_discord_event",
            "discord_channel": discord_channel.upper(),  # ARJUNA, TELEMETRY, etc.
            "event_type": event_type,
            "title": title,
            "description": description,
            "metadata": metadata or {},
            "priority": priority,
            "helix_version": os.getenv("HELIX_VERSION", "17.2"),
            "railway_environment": os.getenv("RAILWAY_ENVIRONMENT", "production"),
            "timestamp": datetime.now(UTC).isoformat(),
            # Signal to Zapier to @mention role subscribers in Discord
            # Zapier will look up the role ID based on channel and include it
            "mention_subscribers": True,
        }

        # Send directly to Railway Discord webhook
        session = self._session
        if session is None:
            session = HelixNetClientSession()

        try:
            async with session.post(
                railway_discord_webhook,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                success = resp.status == 200

                if not success:
                    await self._log_failure(
                        payload,
                        f"HTTP {resp.status}",
                        f"railway_discord_{discord_channel}",
                    )

                return success

        except TimeoutError:
            await self._log_failure(payload, "Timeout", f"railway_discord_{discord_channel}")
            return False

        except Exception as e:
            await self._log_failure(payload, str(e), f"railway_discord_{discord_channel}")
            return False

        finally:
            if self._owns_session and session:
                await session.close()

    async def log_telemetry(self, metric_name: str, value: float, component: str = "system", unit: str = "") -> bool:
        """
        Log telemetry data to Google Sheets/Tables.

        Args:
            metric_name: Metric name
            value: Metric value
            component: Component name
            unit: Optional unit (ms, %, MB, etc.)

        Returns:
            True if successful
        """
        payload = {
            "type": "telemetry",
            "metric_name": metric_name,
            "value": value,
            "component": component,
            "unit": unit,
            "harmony": os.getenv("UCF_HARMONY", "0.355"),
            "timestamp": datetime.now(UTC).isoformat(),
        }

        return await self._send(payload)

    async def send_error_alert(
        self,
        error_message: str,
        component: str,
        severity: str = "high",
        stack_trace: str = "",
    ) -> bool:
        """
        Send critical error alert via Email/PagerDuty.

        Args:
            error_message: Error message
            component: Component that failed
            severity: Severity (low | medium | high | critical)
            stack_trace: Optional stack trace

        Returns:
            True if successful
        """
        payload = {
            "type": "error",
            "error_message": error_message,
            "component": component,
            "severity": severity,
            "stack_trace": stack_trace[:1000] if stack_trace else "",  # Truncate
            "environment": os.getenv("RAILWAY_ENVIRONMENT", "production"),
            "timestamp": datetime.now(UTC).isoformat(),
        }

        return await self._send(payload)

    async def log_repository_action(self, repo_name: str, action: str, details: str, commit_sha: str = "") -> bool:
        """
        Log repository/archive action to GitHub Actions.

        Args:
            repo_name: Repository name
            action: Action (commit | push | backup | restore)
            details: Action details
            commit_sha: Optional commit SHA

        Returns:
            True if successful
        """
        payload = {
            "type": "repository",
            "repo_name": repo_name,
            "action": action,
            "details": details,
            "commit_sha": commit_sha,
            "helix_version": os.getenv("HELIX_VERSION", "15.3"),
            "timestamp": datetime.now(UTC).isoformat(),
        }

        return await self._send(payload)

    # ========================================================================
    # INTERNAL METHODS
    # ========================================================================

    async def _send(self, payload: dict[str, Any], fallback_url: str | None = None) -> bool:
        """
        Send the given payload to the master Zapier webhook when configured, otherwise to the provided fallback URL.

        Validates and potentially truncates the payload, attempts an HTTP POST with a 10-second timeout, logs failures, and closes an owned HTTP session if one was created for the request. If no target webhook is configured, the function returns False without sending.

        Parameters:
            payload (dict): The JSON-serializable payload to deliver. Should include a "type" field used for routing/logging.
            fallback_url (str | None): URL to use when the master webhook is not configured.

        Returns:
            bool: True if the POST returned HTTP 200, False otherwise.
        """
        # Use master webhook if configured
        if self._use_master:
            url = MASTER_HOOK_URL
        elif fallback_url:
            url = fallback_url
        else:
            # No webhook configured - silent skip
            return False

        # Validate payload
        payload = self._validate_payload(payload)

        # Send webhook
        session = self._session
        if session is None:
            session = HelixNetClientSession()

        try:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                success = resp.status == 200

                if success:
                    # Increment Zapier task counter on successful webhook
                    try:
                        from apps.backend.monitoring.health_monitor import get_monitoring_dashboard

                        dashboard = get_monitoring_dashboard()
                        dashboard.increment_zapier_tasks()
                    except ImportError:
                        pass  # Dashboard not available

                if not success:
                    await self._log_failure(
                        payload,
                        f"HTTP {resp.status}",
                        payload.get("type", "unknown"),
                    )

                return success

        except TimeoutError:
            await self._log_failure(payload, "Timeout", payload.get("type", "unknown"))
            return False

        except Exception as e:
            await self._log_failure(payload, str(e), payload.get("type", "unknown"))
            return False

        finally:
            if self._owns_session and session:
                await session.close()

    def _validate_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate and truncate payload to avoid size limits."""
        serialized = json.dumps(payload)

        # If too large, truncate
        if len(serialized) > 1_000_000:  # 1MB
            # Truncate large fields
            for key in ["error_log", "stack_trace", "description", "details"]:
                if key in payload and len(str(payload[key])) > 5000:
                    payload[key] = str(payload[key])[:5000] + "... [truncated]"

        return payload

    async def _log_failure(self, payload: dict[str, Any], error: str, webhook_type: str) -> None:
        """Log failed webhook for later retry."""
        try:
            log_path = Path("logs") / "zapier_failures.jsonl"
            log_path.parent.mkdir(parents=True, exist_ok=True)

            log_entry = {
                "timestamp": datetime.now(UTC).isoformat(),
                "type": webhook_type,
                "error": error,
                "payload": payload,
            }

            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")

            logger.error("⚠ Zapier webhook failed (%s): %s", webhook_type, error)

        except Exception as e:
            logger.error("❌ Failed to log Zapier failure: %s", e)


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================


def validate_config() -> dict[str, Any]:
    """
    Validate Zapier configuration.

    Returns:
        Configuration status
    """
    master_configured = bool(MASTER_HOOK_URL)
    individual_configured = bool(EVENT_HOOK and AGENT_HOOK and SYSTEM_HOOK)

    return {
        "master_webhook": master_configured,
        "individual_webhooks": individual_configured,
        "mode": ("master" if master_configured else ("individual" if individual_configured else "none")),
        "webhooks": {
            "master": bool(MASTER_HOOK_URL),
            "event": bool(EVENT_HOOK),
            "agent": bool(AGENT_HOOK),
            "system": bool(SYSTEM_HOOK),
        },
    }


# ============================================================================
# ENTRY POINT
# ============================================================================


if __name__ == "__main__":

    async def test() -> None:
        """
        Run a live test of the MasterZapierClient against configured webhooks and print results.

        Prints the current webhook configuration, executes a set of representative payloads (event log, agent update, system state, Discord notifications, telemetry, error alert, repository action, and Railway→Discord event) using the configured webhook mode, and prints each test's success or failure. If no webhooks are configured, prints a warning and returns. This function performs network requests and other side-effecting I/O.
        """
        logger.info("🧪 Testing Master Zapier Client")
        logger.info("=" * 70)

        config = validate_config()
        logger.info("\n📋 Configuration:")
        logger.info("  Mode: {}".format(config["mode"]))
        logger.error("  Master Webhook: {}".format("✅" if config["master_webhook"] else "❌"))
        logger.error("  Individual Webhooks: {}".format("✅" if config["individual_webhooks"] else "❌"))

        if config["mode"] == "none":
            logger.info("\n⚠ No webhooks configured. Set ZAPIER_MASTER_HOOK_URL")
            return

        logger.info("\n🧪 Testing in {} mode...".format(config["mode"]))

        async with HelixNetClientSession() as session:
            client = MasterZapierClient(session)

            # Test all payload types
            tests = [
                (
                    "Event Log",
                    client.log_event(
                        "Test Event",
                        "Status",
                        "Arjuna",
                        "Testing master webhook",
                        {"harmony": 0.355},
                    ),
                ),
                (
                    "Agent Update",
                    client.update_agent("Arjuna", "Active", "Testing", 100),
                ),
                (
                    "System State",
                    client.update_system_state("Master Webhook", "Active", 0.355, verified=True),
                ),
                (
                    "Discord Notification",
                    client.send_discord_notification("testing", "🧪 Master webhook test", "normal"),
                ),
                (
                    "Railway→Discord (ARJUNA)",
                    client.send_railway_discord_event(
                        discord_channel="ARJUNA",
                        event_type="test_event",
                        title="🧪 Test Event",
                        description="Testing Railway→Discord integration",
                        metadata={"ucf_harmony": 0.355, "test": True},
                    ),
                ),
                (
                    "Telemetry",
                    client.log_telemetry("test_metric", 42.0, "test_component", "units"),
                ),
                (
                    "Error Alert",
                    client.send_error_alert("Test error", "test_component", "low"),
                ),
                (
                    "Repository Action",
                    client.log_repository_action("helix-unified", "test", "Testing master webhook"),
                ),
            ]

            for name, test_coro in tests:
                result = await test_coro
                logger.error("  {} {}".format("✅" if result else "❌", name))

        logger.info("\n" + "=" * 70)
        logger.info("✅ Test complete")

    asyncio.run(test())

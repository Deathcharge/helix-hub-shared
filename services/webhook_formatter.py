"""
Enhanced Webhook Output Formatter for Helix Collective v17.0

Provides rich embed formatting, automatic retries, health monitoring,
and beautiful Discord webhook messages.
"""

import asyncio
import logging
import time
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import aiohttp

from apps.backend.helix_proprietary.integrations import HelixNetClientSession

logger = logging.getLogger(__name__)


class EmbedColor(Enum):
    """Standard colors for different message types"""

    SUCCESS = 0x00FF00  # Green
    INFO = 0x5865F2  # Blurple
    WARNING = 0xFFA500  # Orange
    ERROR = 0xFF0000  # Red
    UCF = 0x9B59B6  # Purple
    ARJUNA = 0x3498DB  # Blue
    ROUTINE = 0xE74C3C  # Red
    AGENT = 0x2ECC71  # Emerald


class WebhookFormatter:
    """
    Enhanced webhook formatter with embeds, retries, and health checks.
    """

    def __init__(self, max_retries: int = 3, timeout: int = 10) -> None:
        self.max_retries = max_retries
        self.timeout = timeout
        self.session: aiohttp.ClientSession | None = None
        self.health_stats: dict[str, dict[str, Any]] = {}

    async def __aenter__(self):
        """
        Enter the async context, creating and storing a HelixNetClientSession on the instance.

        Returns:
            self: The WebhookFormatter instance with an initialized `session`.
        """
        self.session = HelixNetClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Closes the internal HelixNetClientSession if one exists when exiting the async context.
        """
        if self.session:
            await self.session.close()

    def create_embed(
        self,
        title: str,
        description: str = "",
        color: EmbedColor = EmbedColor.INFO,
        fields: list[dict[str, Any]] | None = None,
        footer: str | None = None,
        thumbnail: str | None = None,
        image: str | None = None,
        author: dict[str, str] | None = None,
        timestamp: bool = True,
    ) -> dict[str, Any]:
        """
        Create a rich embed for Discord webhooks.

        Args:
            title: Embed title
            description: Embed description
            color: Color from EmbedColor enum
            fields: List of fields [{"name": str, "value": str, "inline": bool}]
            footer: Footer text
            thumbnail: Thumbnail URL
            image: Image URL
            author: Author dict {"name": str, "icon_url": str}
            timestamp: Include current timestamp

        Returns:
            Embed dictionary ready for webhook delivery
        """
        embed = {
            "title": title,
            "description": description,
            "color": color.value if isinstance(color, EmbedColor) else color,
        }

        if fields:
            embed["fields"] = fields

        if footer:
            embed["footer"] = {"text": footer}

        if thumbnail:
            embed["thumbnail"] = {"url": thumbnail}

        if image:
            embed["image"] = {"url": image}

        if author:
            embed["author"] = author

        if timestamp:
            embed["timestamp"] = datetime.now(UTC).isoformat()

        return embed

    async def send_webhook(
        self,
        webhook_url: str,
        content: str | None = None,
        embeds: list[dict[str, Any]] | None = None,
        username: str | None = None,
        avatar_url: str | None = None,
    ) -> bool:
        """
        Send a payload to a Discord webhook and record delivery health for the target webhook.

        Parameters:
            webhook_url (str): Discord webhook URL.
            content (Optional[str]): Plain-text message content.
            embeds (Optional[List[Dict[str, Any]]]): List of embed objects
                following Discord embed structure.
            username (Optional[str]): Override the webhook's displayed username.
            avatar_url (Optional[str]): Override the webhook's avatar URL.

        Returns:
            True if delivery succeeded, False otherwise.
        """
        if not self.session:
            self.session = HelixNetClientSession()

        payload = {}

        if content:
            payload["content"] = content

        if embeds:
            payload["embeds"] = embeds

        if username:
            payload["username"] = username

        if avatar_url:
            payload["avatar_url"] = avatar_url

        # Track health stats
        webhook_name = self._extract_webhook_name(webhook_url)
        if webhook_name not in self.health_stats:
            self.health_stats[webhook_name] = {
                "sent": 0,
                "failed": 0,
                "last_success": None,
                "last_failure": None,
                "avg_response_time": 0,
                "total_response_time": 0,
            }

        for attempt in range(self.max_retries):
            try:
                start_time = time.monotonic()
                async with self.session.post(
                    webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as response:
                    response_time = time.monotonic() - start_time

                    if response.status == 204:
                        # Success!
                        self._record_success(webhook_name, response_time)
                        logger.info(
                            "✅ Webhook delivered to %s (%.2f)s",
                            webhook_name,
                            response_time,
                        )
                        return True

                    if response.status == 429:
                        # Rate limited, wait and retry
                        retry_after = int(response.headers.get("Retry-After", 1))
                        logger.warning(
                            "⏳ Rate limited on %s, retrying after %ds",
                            webhook_name,
                            retry_after,
                        )
                        await asyncio.sleep(retry_after)
                        continue

                    # Other error
                    error_text = await response.text()
                    logger.error(
                        "❌ Webhook error %d on %s: %s",
                        response.status,
                        webhook_name,
                        error_text,
                    )

                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(2**attempt)  # Exponential backoff
                        continue

                    self._record_failure(webhook_name)
                    return False

            except TimeoutError:
                logger.error(
                    "⏰ Webhook timeout on %s (attempt %d/%d)",
                    webhook_name,
                    attempt + 1,
                    self.max_retries,
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2**attempt)
                    continue

                self._record_failure(webhook_name)
                return False

            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("💥 Webhook exception on %s: %s", webhook_name, e)
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2**attempt)
                    continue

                self._record_failure(webhook_name)
                return False

        self._record_failure(webhook_name)
        return False

    def _extract_webhook_name(self, webhook_url: str) -> str:
        """Extract channel name from webhook URL"""
        try:
            parts = webhook_url.split("/")
            webhook_id = parts[-2] if len(parts) >= 2 else "unknown"
            return f"webhook-{webhook_id[:8]}"
        except (ValueError, TypeError, KeyError, IndexError):
            return "unknown"

    def _record_success(self, webhook_name: str, response_time: float):
        """Record successful webhook delivery"""
        stats = self.health_stats[webhook_name]
        stats["sent"] += 1
        stats["last_success"] = datetime.now(UTC).isoformat()
        stats["total_response_time"] += response_time
        stats["avg_response_time"] = stats["total_response_time"] / stats["sent"]

    def _record_failure(self, webhook_name: str):
        """Record failed webhook delivery"""
        stats = self.health_stats[webhook_name]
        stats["failed"] += 1
        stats["last_failure"] = datetime.now(UTC).isoformat()

    async def test_webhook_health(self, webhook_url: str, channel_name: str = "unknown") -> dict[str, Any]:
        """
        Test webhook health and return diagnostics.

        Args:
            webhook_url: Webhook URL to test
            channel_name: Human-readable channel name

        Returns:
            Health report dict
        """
        test_embed = self.create_embed(
            title="🏥 Webhook Health Check",
            description=f"Testing webhook for #{channel_name}",
            color=EmbedColor.INFO,
            fields=[
                {
                    "name": "Test Time",
                    "value": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "inline": True,
                },
                {"name": "Channel", "value": channel_name, "inline": True},
            ],
            footer="Helix Collective v17.0 - Webhook Health Monitor",
        )

        start_time = time.monotonic()
        success = await self.send_webhook(webhook_url, embeds=[test_embed])
        response_time = time.monotonic() - start_time

        return {
            "channel": channel_name,
            "url": webhook_url,
            "healthy": success,
            "response_time": response_time,
            "status": "✅ Healthy" if success else "❌ Failed",
            "tested_at": datetime.now(UTC).isoformat(),
        }

    def get_health_stats(self) -> dict[str, dict[str, Any]]:
        """Get health statistics for all webhooks"""
        return self.health_stats


# Convenience functions for common webhook patterns


async def send_ucf_update(
    webhook_url: str,
    harmony: float,
    resilience: float,
    throughput: float,
    agent_count: int = 0,
):
    """Send UCF state update with beautiful formatting"""
    async with WebhookFormatter() as formatter:
        # Determine color based on harmony
        if harmony >= 0.8:
            color = EmbedColor.SUCCESS
            status = "🌟 Optimal"
        elif harmony >= 0.6:
            color = EmbedColor.UCF
            status = "✨ Balanced"
        elif harmony >= 0.4:
            color = EmbedColor.WARNING
            status = "⚠️ Fluctuating"
        else:
            color = EmbedColor.ERROR
            status = "⚡ Turbulent"

        embed = formatter.create_embed(
            title="🌀 UCF State Update",
            description=f"Unified Coordination Field Metrics - Status: {status}",
            color=color,
            fields=[
                {"name": "🎵 Harmony", "value": f"{harmony:.2%}", "inline": True},
                {"name": "🛡️ Resilience", "value": f"{resilience:.2%}", "inline": True},
                {"name": "⚡ Throughput", "value": f"{throughput:.2%}", "inline": True},
                {"name": "👥 Active Agents", "value": str(agent_count), "inline": True},
                {
                    "name": "📊 Overall Health",
                    "value": f"{(harmony + resilience + throughput) / 3:.2%}",
                    "inline": True,
                },
            ],
            footer="Real-time coordination metrics • Helix Collective v17.0",
        )

        await formatter.send_webhook(webhook_url, embeds=[embed])


async def send_deployment_status(
    webhook_url: str,
    service_name: str,
    status: str,
    environment: str = "production",
    commit_hash: str | None = None,
    deploy_time: float | None = None,
):
    """Send deployment status notification"""
    async with WebhookFormatter() as formatter:
        color = EmbedColor.SUCCESS if status == "success" else EmbedColor.ERROR
        emoji = "✅" if status == "success" else "❌"

        fields = [
            {"name": "Service", "value": service_name, "inline": True},
            {"name": "Environment", "value": environment, "inline": True},
            {"name": "Status", "value": f"{emoji} {status.title()}", "inline": True},
        ]

        if commit_hash:
            fields.append({"name": "Commit", "value": f"`{commit_hash[:8]}`", "inline": True})

        if deploy_time:
            fields.append({"name": "Deploy Time", "value": f"{deploy_time:.1f}s", "inline": True})

        embed = formatter.create_embed(
            title=f"🚀 Deployment {status.title()}",
            description=f"Railway deployment for {service_name}",
            color=color,
            fields=fields,
            footer="Helix Collective v17.0 - Railway Integration",
        )

        await formatter.send_webhook(webhook_url, embeds=[embed])


async def send_agent_message(
    webhook_url: str,
    agent_name: str,
    message: str,
    agent_emoji: str = "🤖",
    agent_color: int = 0x5865F2,
):
    """Send message from a specific agent with personality"""
    async with WebhookFormatter() as formatter:
        embed = formatter.create_embed(
            title=f"{agent_emoji} {agent_name}",
            description=message,
            color=agent_color,
            footer=f"{agent_name} • Helix Collective v17.0",
            timestamp=True,
        )

        await formatter.send_webhook(
            webhook_url,
            embeds=[embed],
            username=f"Helix • {agent_name}",
            avatar_url=None,  # Could add agent-specific avatars
        )


# Export main class and convenience functions
__all__ = [
    "EmbedColor",
    "WebhookFormatter",
    "send_agent_message",
    "send_deployment_status",
    "send_ucf_update",
]

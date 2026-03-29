"""
Feedback notification service for Helix Collective.

This service handles sending notifications for new feedback,
admin alerts, and user responses via Discord webhooks and other channels.
"""

import logging
import os

import httpx

from ..models.feedback import Feedback

logger = logging.getLogger(__name__)

_FRONTEND_URL = os.getenv("FRONTEND_URL", "https://helixcollective.work").rstrip("/")


class FeedbackNotificationService:
    """Service for sending feedback notifications"""

    def __init__(self) -> None:
        self.discord_webhook_url = os.getenv("DISCORD_FEEDBACK_WEBHOOK")
        self.client = httpx.AsyncClient(timeout=10.0)

    async def send_discord_notification(self, feedback: Feedback) -> bool:
        """
        Send feedback notification to Discord webhook

        Args:
            feedback: Feedback object to notify about

        Returns:
            True if notification sent successfully, False otherwise
        """
        if not self.discord_webhook_url:
            logger.warning("Discord webhook URL not configured")
            return False

        try:
            priority_emoji = {
                "low": "🟢",
                "medium": "🟡",
                "high": "🔴",
                "critical": "🚨",
            }.get(feedback.priority, "ℹ️")

            priority_color = {
                "low": 0x00FF00,  # Green
                "medium": 0xFFFF00,  # Yellow
                "high": 0xFF0000,  # Red
                "critical": 0xFF00FF,  # Purple
            }.get(
                feedback.priority, 0x00FFFF
            )  # Default: Cyan

            # Build Discord embed
            embed = {
                "title": f"{priority_emoji} New Feedback: {feedback.category or 'General'}",
                "description": feedback.text[:2000],  # Discord has 2000 char limit for embeds
                "color": priority_color,
                "fields": [
                    {"name": "Page", "value": feedback.page, "inline": True},
                    {"name": "Status", "value": feedback.status, "inline": True},
                    {"name": "Priority", "value": feedback.priority, "inline": True},
                    {
                        "name": "User",
                        "value": feedback.user_id or "Anonymous",
                        "inline": True,
                    },
                    {"name": "IP", "value": feedback.ip, "inline": True},
                    {
                        "name": "User Agent",
                        "value": feedback.user_agent[:500],
                        "inline": False,
                    },
                ],
                "footer": {"text": f"Feedback ID: {feedback.id}"},
            }

            # Add metadata if available
            if feedback.metadata:
                metadata_str = "\n".join(f"{k}: {v}" for k, v in feedback.metadata.items())
                embed["fields"].append({"name": "Metadata", "value": metadata_str[:1000], "inline": False})

            payload = {
                "content": f"**New Feedback Received** {priority_emoji}",
                "embeds": [embed],
                "username": "Helix Feedback Bot",
                "avatar_url": f"{_FRONTEND_URL}/favicon.ico",
            }

            # Send to Discord
            response = await self.client.post(
                self.discord_webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 204:
                logger.info("Discord notification sent for feedback %s", feedback.id)
                return True
            else:
                logger.error("Discord notification failed: %s - %s", response.status_code, response.text)
                return False

        except Exception as e:
            logger.error("Error sending Discord notification: %s", e)
            return False

    async def send_admin_alert(self, feedback: Feedback) -> bool:
        """
        Send alert to admin for high-priority feedback

        Args:
            feedback: Feedback object to alert about

        Returns:
            True if alert sent successfully, False otherwise
        """
        if feedback.priority not in ["high", "critical"]:
            logger.debug("Skipping admin alert for %s priority feedback", feedback.priority)
            return False

        if not self.discord_webhook_url:
            logger.warning("Discord webhook URL not configured for admin alerts")
            return False

        try:
            admin_webhook_url = os.getenv("DISCORD_ADMIN_WEBHOOK") or self.discord_webhook_url

            priority_emoji = "🚨" if feedback.priority == "critical" else "🔴"

            embed = {
                "title": f"{priority_emoji} HIGH PRIORITY FEEDBACK REQUIRES ATTENTION",
                "description": f"**{feedback.text[:1000]}**",
                "color": 0xFF0000,  # Red
                "fields": [
                    {
                        "name": "Category",
                        "value": feedback.category or "General",
                        "inline": True,
                    },
                    {"name": "Page", "value": feedback.page, "inline": True},
                    {
                        "name": "User",
                        "value": feedback.user_id or "Anonymous",
                        "inline": True,
                    },
                    {"name": "Feedback ID", "value": feedback.id, "inline": True},
                ],
                "footer": {"text": "Please review this feedback immediately"},
            }

            payload = {
                "content": f"<@&ADMIN_ROLE_ID> {priority_emoji} **URGENT FEEDBACK ALERT** {priority_emoji}",
                "embeds": [embed],
                "username": "Helix Admin Alert",
                "avatar_url": f"{_FRONTEND_URL}/favicon.ico",
            }

            response = await self.client.post(
                admin_webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 204:
                logger.info("Admin alert sent for feedback %s", feedback.id)
                return True
            else:
                logger.error("Admin alert failed: %s - %s", response.status_code, response.text)
                return False

        except Exception as e:
            logger.error("Error sending admin alert: %s", e)
            return False

    async def send_user_response_notification(
        self,
        feedback: Feedback,
        response_text: str,
        contact_method: str | None = None,
    ) -> bool:
        """
        Send notification to user about feedback response

        Args:
            feedback: Original feedback object
            response_text: Admin response text
            contact_method: How to contact user (email, discord, etc.)

        Returns:
            True if notification sent successfully, False otherwise
        """
        # For now, we'll just log this as the actual implementation
        # would depend on user contact preferences and available channels
        logger.info("User response notification would be sent for feedback %s", feedback.id)
        logger.info("Response: %s...", response_text[:100])

        # In a real implementation, this would:
        # 1. Check user's notification preferences
        # 2. Send via appropriate channel (email, in-app, etc.)
        # 3. Handle errors and retries

        return True

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()


# Initialize notification service
notification_service = FeedbackNotificationService()

"""
Notification Service for Helix Collective

Provides centralized notification functionality for workflows and system events.
Integrates with email_service for email notifications.
"""

import logging
import os
from typing import Any

import aiohttp

try:
    from apps.backend.core.resilience import retry_with_backoff
except ImportError:

    def retry_with_backoff(**_kw):
        def _noop(fn):
            return fn

        return _noop


logger = logging.getLogger(__name__)

_FRONTEND_URL = os.getenv("FRONTEND_URL", "https://helixcollective.work").rstrip("/")


class NotificationService:
    """Service for sending notifications via email, webhook, and other channels"""

    def __init__(self) -> None:
        self.notification_providers = {}
        self._email_service = None

    @property
    def email_service(self):
        """Lazy load email service to avoid circular imports"""
        if self._email_service is None:
            try:
                from apps.backend.services.email_service import email_service

                self._email_service = email_service
            except ImportError as e:
                logger.warning("Email service not available: %s", e)
        return self._email_service

    async def send_notification(
        self,
        notification_type: str,
        recipients: list[str],
        message: str,
        context: dict[str, Any] | None = None,
    ) -> bool:
        """
        Send a notification

        Args:
            notification_type: Type of notification (email, webhook, etc.)
            recipients: List of recipients
            message: Notification message
            context: Additional context data

        Returns:
            True if notification sent successfully
        """
        try:
            logger.info(
                "Sending %s notification to %d recipients: %s...",
                notification_type,
                len(recipients),
                message[:50],
            )

            if notification_type == "email":
                return await self._send_email_notification(recipients, message, context)
            elif notification_type == "webhook":
                return await self._send_webhook_notification(recipients, message, context)
            elif notification_type == "slack":
                return await self._send_slack_notification(recipients, message, context)
            elif notification_type == "discord":
                return await self._send_discord_notification(recipients, message, context)
            else:
                logger.warning(
                    "Notification type %s not implemented, logging only",
                    notification_type,
                )
                return True

        except Exception as e:
            logger.error("Failed to send notification: %s", e)
            return False

    async def _send_email_notification(
        self,
        recipients: list[str],
        message: str,
        context: dict[str, Any] | None = None,
    ) -> bool:
        """Send email notification via email_service"""
        if not self.email_service:
            logger.warning("Email service not available, logging notification only")
            logger.info("Would send email to %s: %s", recipients, message)
            return True

        subject = (context or {}).get("subject", "Helix Collective Notification")
        html_content = self._format_email_html(message, context)

        results = []
        for recipient in recipients:
            try:
                result = await self.email_service.send_email(
                    to_email=recipient,
                    subject=subject,
                    html_content=html_content,
                    from_name="Helix Collective",
                )
                results.append(result)
            except Exception as e:
                logger.error("Failed to send email to %s: %s", recipient, e)
                results.append(False)

        return all(results)

    def _format_email_html(self, message: str, context: dict[str, Any] | None = None) -> str:
        """Format message as HTML email"""
        ctx = context or {}
        title = ctx.get("title", "Notification")
        action_url = ctx.get("action_url")
        action_label = ctx.get("action_label", "View Details")

        action_button = ""
        if action_url:
            action_button = f"""
            <div style="text-align: center; margin: 30px 0;">
                <a href="{action_url}"
                   style="background: #667eea; color: white; padding: 12px 24px;
                          text-decoration: none; border-radius: 6px; font-weight: bold;">
                    {action_label} →
                </a>
            </div>
            """

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{title}</title>
        </head>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        padding: 40px 20px; text-align: center;">
                <h1 style="color: white; margin: 0; font-size: 24px;">🌀 {title}</h1>
            </div>

            <div style="padding: 40px 20px; background: #f8f9fa;">
                <p style="color: #666; line-height: 1.6; white-space: pre-wrap;">
                    {message}
                </p>
                {action_button}
            </div>

            <div style="background: #333; color: white; padding: 20px; text-align: center;">
                <p style="margin: 0; font-size: 14px;">
                    © 2025 Helix Collective. Building the future of AI collaboration.
                </p>
            </div>
        </body>
        </html>
        """

    @retry_with_backoff(max_retries=2, base_delay=1.0, exceptions=(Exception,))
    async def _send_webhook_notification(
        self,
        recipients: list[str],
        message: str,
        context: dict[str, Any] | None = None,
    ) -> bool:
        """Send webhook notification to URLs"""
        results = []
        payload = {
            "message": message,
            "timestamp": context.get("timestamp") if context else None,
            "event_type": (context.get("event_type", "notification") if context else "notification"),
            "data": context.get("data", {}) if context else {},
        }

        async with aiohttp.ClientSession() as session:
            for webhook_url in recipients:
                try:
                    async with session.post(
                        webhook_url,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as response:
                        if response.status in (200, 201, 202, 204):
                            logger.info("Webhook sent successfully to %s", webhook_url)
                            results.append(True)
                        else:
                            logger.warning(
                                "Webhook to %s returned status %d",
                                webhook_url,
                                response.status,
                            )
                            results.append(False)
                except Exception as e:
                    logger.error("Failed to send webhook to %s: %s", webhook_url, e)
                    results.append(False)

        return all(results) if results else True

    @retry_with_backoff(max_retries=2, base_delay=1.0, exceptions=(Exception,))
    async def _send_slack_notification(
        self,
        recipients: list[str],
        message: str,
        context: dict[str, Any] | None = None,
    ) -> bool:
        """Send Slack notification via webhook"""
        ctx = context or {}
        payload = {
            "text": message,
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{ctx.get('title', 'Notification')}*\n{message}",
                    },
                }
            ],
        }

        async with aiohttp.ClientSession() as session:
            results = []
            for webhook_url in recipients:
                try:
                    async with session.post(
                        webhook_url,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as response:
                        results.append(response.status == 200)
                except Exception as e:
                    logger.error("Failed to send Slack notification: %s", e)
                    results.append(False)
            return all(results) if results else True

    @retry_with_backoff(max_retries=2, base_delay=1.0, exceptions=(Exception,))
    async def _send_discord_notification(
        self,
        recipients: list[str],
        message: str,
        context: dict[str, Any] | None = None,
    ) -> bool:
        """Send Discord notification via webhook"""
        ctx = context or {}
        payload = {
            "content": message,
            "embeds": [
                {
                    "title": ctx.get("title", "Notification"),
                    "description": message,
                    "color": 6570239,  # Purple color
                }
            ],
        }

        async with aiohttp.ClientSession() as session:
            results = []
            for webhook_url in recipients:
                try:
                    async with session.post(
                        webhook_url,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as response:
                        results.append(response.status in (200, 204))
                except Exception as e:
                    logger.error("Failed to send Discord notification: %s", e)
                    results.append(False)
            return all(results) if results else True

    async def send_workflow_notification(
        self,
        workflow_id: str,
        event_type: str,
        message: str,
        recipients: list[dict[str, Any]] | None = None,
    ) -> bool:
        """
        Send workflow-specific notification

        Args:
            workflow_id: ID of the workflow
            event_type: Type of workflow event (started, completed, failed, etc.)
            message: Notification message
            recipients: List of recipient configs with 'type' and 'address' keys

        Returns:
            True if all notifications sent successfully
        """
        if not recipients:
            logger.info(
                "No recipients configured for workflow %s %s notification",
                workflow_id,
                event_type,
            )
            return True

        context = {
            "workflow_id": workflow_id,
            "event_type": event_type,
            "title": f"Workflow {event_type.capitalize()}",
            "action_url": f"{_FRONTEND_URL}/workflows/{workflow_id}",
            "action_label": "View Workflow",
        }

        results = []
        for recipient in recipients:
            notification_type = recipient.get("type", "email")
            address = recipient.get("address") or recipient.get("url")
            if address:
                result = await self.send_notification(
                    notification_type=notification_type,
                    recipients=[address],
                    message=message,
                    context=context,
                )
                results.append(result)

        return all(results) if results else True

    # ========================================================================
    # User-preference-aware notification helpers
    # ========================================================================

    async def _get_user_notification_prefs(self, user_id: str) -> dict:
        """Load notification preferences for a user."""
        import json

        defaults = {"email": True, "push": False, "coordination": True, "agents": True}
        try:
            from apps.backend.core.unified_auth import Database

            rows = await Database.fetch(
                "SELECT notification_prefs FROM user_preferences WHERE user_id = $1",
                user_id,
            )
            if rows and rows[0]["notification_prefs"]:
                stored = json.loads(rows[0]["notification_prefs"])
                return {**defaults, **stored}
        except (ImportError, AttributeError, json.JSONDecodeError) as e:
            logger.debug("Failed to load notification preferences: %s", e)
        except Exception as e:
            logger.warning("Unexpected error loading preferences: %s", e)
        return defaults

    async def _get_user_email(self, user_id: str) -> str | None:
        """Fetch user email address."""
        try:
            from apps.backend.core.unified_auth import Database

            rows = await Database.fetch("SELECT email FROM users WHERE id = $1", user_id)
            if rows:
                return rows[0]["email"]
        except (ImportError, AttributeError) as e:
            logger.debug("Could not fetch email for user %s: %s", user_id, e)
        except Exception as e:
            logger.warning("Unexpected error fetching email for user %s: %s", user_id, e)
        return None

    async def notify_user(
        self,
        user_id: str,
        category: str,
        subject: str,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> bool:
        """Send a notification to a user respecting their preferences.

        Args:
            user_id:  Target user ID.
            category: Preference key — ``email``, ``agents``, or ``coordination``.
            subject:  Email subject line.
            message:  Notification message body.
            context:  Extra context passed to the email template.

        Returns:
            True if dispatched, False if opted-out or email unavailable.
        """
        prefs = await self._get_user_notification_prefs(user_id)

        # Check category opt-out
        if not prefs.get(category, True):
            logger.info("Notification skipped for user %s (category '%s' disabled)", user_id, category)
            return False

        # Master email toggle
        if not prefs.get("email", True):
            logger.info("Notification skipped for user %s (email disabled)", user_id)
            return False

        email_addr = await self._get_user_email(user_id)
        if not email_addr:
            logger.warning("Cannot notify user %s — no email on file", user_id)
            return False

        ctx = {**(context or {}), "subject": subject}
        return await self.send_notification(
            notification_type="email",
            recipients=[email_addr],
            message=message,
            context=ctx,
        )

    async def notify_agent_activity(self, user_id: str, agent_name: str, summary: str) -> bool:
        """Notify user of agent activity (respects 'agents' preference)."""
        return await self.notify_user(
            user_id=user_id,
            category="agents",
            subject=f"🌀 Agent Update — {agent_name}",
            message=f"{agent_name} has new activity:\n\n{summary}",
            context={
                "title": "Agent Activity",
                "action_url": f"{_FRONTEND_URL}/agents",
                "action_label": "View Agents",
            },
        )

    async def notify_coordination_event(self, user_id: str, event_type: str, details: str) -> bool:
        """Notify user of coordination/UCF events (respects 'coordination' preference)."""
        return await self.notify_user(
            user_id=user_id,
            category="coordination",
            subject=f"🌀 Coordination Event — {event_type}",
            message=f"A {event_type} event has been recorded:\n\n{details}",
            context={
                "title": "Coordination Event",
                "action_url": f"{_FRONTEND_URL}/coordination/analytics",
                "action_label": "View Dashboard",
            },
        )

    async def notify_security_alert(self, user_id: str, alert: str) -> bool:
        """Notify user of a security event (always sent if email is enabled)."""
        return await self.notify_user(
            user_id=user_id,
            category="email",
            subject="🔒 Security Alert — Helix Collective",
            message=f"Security Alert: {alert}\n\nIf this wasn't you, please change your password immediately.",
            context={
                "title": "Security Alert",
                "action_url": f"{_FRONTEND_URL}/settings",
                "action_label": "Review Settings",
            },
        )


# Global instance
notification_service = NotificationService()

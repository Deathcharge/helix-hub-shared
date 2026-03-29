"""
📧 Team Email Service - Helix Collective v17.1
Email notifications for team management operations

Handles:
- Team invitation emails
- Role change notifications
- Team membership updates

Author: Claude (Automation)
Version: 17.1.0
"""

import logging
import os

import requests
from jinja2 import Template

logger = logging.getLogger(__name__)


class TeamEmailService:
    """
    Email service for team management notifications

    Uses SendGrid or similar email service for sending notifications
    """

    def __init__(self) -> None:
        self.api_key = os.getenv("SENDGRID_API_KEY")
        self.from_email = os.getenv("FROM_EMAIL", "noreply@helixspiral.work")
        self.base_url = os.getenv("BASE_URL", "https://helixspiral.work")

        # Email templates
        self.invitation_template = Template(
            """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Team Invitation - Helix Collective</title>
</head>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 40px 20px; text-align: center;">
        <h1 style="color: white; margin: 0; font-size: 28px;">🌀 Helix Collective</h1>
        <p style="color: #e8e8e8; margin: 10px 0 0 0;">Multi-Agent Coordination Platform</p>
    </div>

    <div style="padding: 40px 30px; background: white;">
        <h2 style="color: #333; margin-top: 0;">You're Invited to Join {{ team_name }}!</h2>

        <p>Hello,</p>

        <p><strong>{{ inviter_name }}</strong> has invited you to join the <strong>{{ team_name }}</strong> team on Helix Collective.</p>

        <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 30px 0;">
            <p style="margin: 0; font-size: 16px;"><strong>Team:</strong> {{ team_name }}</p>
            <p style="margin: 10px 0 0 0; font-size: 16px;"><strong>Role:</strong> {{ role|title }}</p>
            <p style="margin: 10px 0 0 0; font-size: 16px;"><strong>Invited by:</strong> {{ inviter_name }}</p>
        </div>

        <div style="text-align: center; margin: 40px 0;">
            <a href="{{ accept_url }}" style="background: #667eea; color: white; padding: 15px 30px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">Accept Invitation</a>
        </div>

        <p style="color: #666; font-size: 14px; margin-top: 40px;">
            This invitation will expire in 7 days. If you have any questions, please contact the team administrator.
        </p>

        <hr style="border: none; border-top: 1px solid #eee; margin: 40px 0;">

        <p style="color: #666; font-size: 12px; text-align: center;">
            Helix Collective - Emergent Intelligence Revolution<br>
            If you did not expect this invitation, you can safely ignore this email.
        </p>
    </div>
</body>
</html>
        """
        )

        self.role_change_template = Template(
            """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Role Updated - Helix Collective</title>
</head>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 40px 20px; text-align: center;">
        <h1 style="color: white; margin: 0; font-size: 28px;">🌀 Helix Collective</h1>
    </div>

    <div style="padding: 40px 30px; background: white;">
        <h2 style="color: #333; margin-top: 0;">Your Role Has Been Updated</h2>

        <p>Hello <strong>{{ user_name }}</strong>,</p>

        <p>Your role in the <strong>{{ team_name }}</strong> team has been updated.</p>

        <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 30px 0;">
            <p style="margin: 0; font-size: 16px;"><strong>Team:</strong> {{ team_name }}</p>
            <p style="margin: 10px 0 0 0; font-size: 16px;"><strong>New Role:</strong> {{ new_role|title }}</p>
            <p style="margin: 10px 0 0 0; font-size: 16px;"><strong>Changed by:</strong> {{ changer_name }}</p>
        </div>

        <div style="text-align: center; margin: 40px 0;">
            <a href="{{ team_url }}" style="background: #667eea; color: white; padding: 15px 30px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">View Team</a>
        </div>

        <hr style="border: none; border-top: 1px solid #eee; margin: 40px 0;">

        <p style="color: #666; font-size: 12px; text-align: center;">
            Helix Collective - Emergent Intelligence Revolution
        </p>
    </div>
</body>
</html>
        """
        )

    async def send_team_invitation(
        self,
        to_email: str,
        team_name: str,
        inviter_name: str,
        role: str,
        invitation_token: str,
    ) -> bool:
        """
        Send team invitation email

        Args:
            to_email: Recipient email
            team_name: Name of the team
            inviter_name: Name of the person sending the invitation
            role: Role being offered
            invitation_token: Invitation token for acceptance

        Returns:
            Success status
        """
        try:
            accept_url = f"{self.base_url}/teams/accept/{invitation_token}"

            html_content = self.invitation_template.render(
                team_name=team_name,
                inviter_name=inviter_name,
                role=role,
                accept_url=accept_url,
            )

            subject = f"You're invited to join {team_name} on Helix Collective"

            return await self._send_email(to_email, subject, html_content)

        except (ValueError, KeyError, TypeError) as e:
            logger.debug("Team invitation template error: %s", e)
            return False
        except Exception as e:
            logger.error("Failed to send team invitation email: %s", e)
            return False

    async def send_role_change_notification(
        self,
        to_email: str,
        user_name: str,
        team_name: str,
        new_role: str,
        changer_name: str,
    ) -> bool:
        """
        Send role change notification email

        Args:
            to_email: Recipient email
            user_name: Name of the user whose role changed
            team_name: Name of the team
            new_role: New role assigned
            changer_name: Name of the person who made the change

        Returns:
            Success status
        """
        try:
            team_url = f"{self.base_url}/teams/{team_name.lower().replace(' ', '-')}"

            html_content = self.role_change_template.render(
                user_name=user_name,
                team_name=team_name,
                new_role=new_role,
                changer_name=changer_name,
                team_url=team_url,
            )

            subject = f"Your role in {team_name} has been updated"

            return await self._send_email(to_email, subject, html_content)

        except (ValueError, KeyError, TypeError) as e:
            logger.debug("Role change notification template error: %s", e)
            return False
        except Exception as e:
            logger.error("Failed to send role change notification: %s", e)
            return False

    async def _send_email(self, to_email: str, subject: str, html_content: str) -> bool:
        """
        Send email using SendGrid API

        Args:
            to_email: Recipient email
            subject: Email subject
            html_content: HTML email content

        Returns:
            Success status
        """
        if not self.api_key:
            logger.warning("SendGrid API key not configured, skipping email send")
            return False

        try:
            url = "https://api.sendgrid.com/v3/mail/send"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            payload = {
                "personalizations": [{"to": [{"email": to_email}], "subject": subject}],
                "from": {"email": self.from_email},
                "content": [{"type": "text/html", "value": html_content}],
            }

            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()

            logger.info("Email sent successfully to %s", to_email)
            return True

        except requests.exceptions.RequestException as e:
            logger.error("Failed to send email via SendGrid: %s", e)
            return False
        except Exception as e:
            logger.error("Unexpected error sending email: %s", e)
            return False


# Global email service instance
team_email_service = TeamEmailService()

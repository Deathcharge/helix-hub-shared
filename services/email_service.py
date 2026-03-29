"""
🌀 Helix - Email Service
SendGrid integration for transactional emails
"""

import asyncio
import logging
import os

try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Content, Email, Mail, To

    HAS_SENDGRID = True
except ImportError:
    HAS_SENDGRID = False
    SendGridAPIClient = None  # type: ignore

try:
    from apps.backend.core.resilience import retry_with_backoff
except ImportError:

    def retry_with_backoff(**_kw):
        def _noop(fn):
            return fn

        return _noop


logger = logging.getLogger(__name__)


class EmailService:
    """Email service using SendGrid"""

    def __init__(self) -> None:
        self.api_key = os.getenv("SENDGRID_API_KEY")
        self.from_email = os.getenv("FROM_EMAIL", "noreply@helixcollective.work")
        self.from_name = os.getenv("FROM_NAME", "Helix")
        self.frontend_url = os.getenv("FRONTEND_URL", "https://helixcollective.work").rstrip("/")
        self.client = None

        if HAS_SENDGRID and self.api_key:
            try:
                self.client = SendGridAPIClient(self.api_key)
                logger.info("✅ Email service initialized with SendGrid")
            except (ImportError, ValueError, TypeError) as e:
                logger.debug("SendGrid initialization error: %s", e)
            except Exception as e:
                logger.error("❌ Failed to initialize SendGrid: %s", e)
        else:
            logger.warning("⚠️ SendGrid not configured - emails will be logged only")

    @retry_with_backoff(max_retries=2, base_delay=1.0, exceptions=(Exception,))
    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str | None = None,
        from_name: str = "Helix",
    ) -> bool:
        """Send email via SendGrid"""
        if not self.client:
            _is_prod = os.getenv("RAILWAY_ENVIRONMENT", "").lower() in ("production", "prod")
            if _is_prod:
                logger.error(
                    "❌ Email delivery failed — SENDGRID_API_KEY not configured in production. "
                    "Email to %s ('%s') was NOT sent.",
                    to_email,
                    subject,
                )
                return False
            logger.info("📧 [LOG ONLY] Would send email to %s: %s", to_email, subject)
            return True

        try:
            from_email_obj = Email(self.from_email, from_name or self.from_name)
            to_email_obj = To(to_email)
            content = Content("text/html", html_content)

            mail = Mail(from_email_obj, to_email_obj, subject, content)

            if text_content:
                mail.add_content(Content("text/plain", text_content))

            response = self.client.send(mail)

            if response.status_code in [200, 201, 202]:
                logger.info("✅ Email sent to %s: %s", to_email, subject)
                return True
            else:
                logger.error("❌ Email failed to %s: %s", to_email, response.status_code)
                return False

        except (ConnectionError, TimeoutError) as e:
            logger.warning("Email connection error to %s: %s", to_email, e)
            return False
        except Exception as e:
            logger.error("❌ Email error to %s: %s", to_email, e)
            return False

    def send_email_background(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str | None = None,
        from_name: str = "Helix",
    ) -> None:
        """Fire-and-forget email send via asyncio.create_task.

        Use this instead of ``await send_email()`` when the caller does not
        need to know whether the email succeeded (notifications, reminders,
        confirmations).  The HTTP response is returned immediately while the
        email is delivered in the background.
        """

        async def _safe_send() -> None:
            try:
                await self.send_email(
                    to_email=to_email,
                    subject=subject,
                    html_content=html_content,
                    text_content=text_content,
                    from_name=from_name,
                )
            except Exception as exc:
                logger.error("Background email to %s failed: %s", to_email, exc)

        try:
            asyncio.create_task(_safe_send())
        except RuntimeError:
            # No running event loop — fall back to sync-safe scheduling
            logger.warning("No running loop for background email to %s", to_email)

    async def send_welcome_email(self, user_email: str, user_name: str) -> bool:
        """Send welcome email to new user"""
        subject = "Welcome to Helix! 🌀"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Welcome to Helix</title>
        </head>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 40px 20px; text-align: center;">
                <h1 style="color: white; margin: 0; font-size: 32px;">🌀 Welcome to Helix</h1>
            </div>

            <div style="padding: 40px 20px; background: #f8f9fa;">
                <h2 style="color: #333; margin-top: 0;">Hello {user_name}!</h2>

                <p style="color: #666; line-height: 1.6;">
                    Welcome to Helix! You've joined a revolutionary platform that brings together
                    AI agents, system computing, and collective intelligence.
                </p>

                <div style="background: white; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #333;">🚀 What's Next?</h3>
                    <ul style="color: #666; line-height: 1.8;">
                        <li><strong>Complete your profile</strong> - Add your preferences and settings</li>
                        <li><strong>Explore agents</strong> - Discover and rent AI agents for your tasks</li>
                        <li><strong>Join the community</strong> - Connect with other Helix users</li>
                        <li><strong>Start building</strong> - Use our Web OS and system tools</li>
                    </ul>
                </div>

                <div style="text-align: center; margin: 30px 0;">
                    <a href="{self.frontend_url}/dashboard"
                       style="background: #667eea; color: white; padding: 12px 24px;
                              text-decoration: none; border-radius: 6px; font-weight: bold;">
                        Get Started →
                    </a>
                </div>

                <p style="color: #999; font-size: 14px; text-align: center;">
                    Questions? Reply to this email or visit our <a href="{self.frontend_url}/docs">documentation</a>.
                </p>
            </div>

            <div style="background: #333; color: white; padding: 20px; text-align: center;">
                <p style="margin: 0; font-size: 14px;">
                    © 2025 Helix. Building the future of AI collaboration.
                </p>
            </div>
        </body>
        </html>
        """

        return await self.send_email(user_email, subject, html_content)

    async def send_password_reset_email(self, user_email: str, reset_token: str) -> bool:
        """Send password reset email"""
        subject = "Reset Your Helix Password"

        reset_url = f"{self.frontend_url}/auth/reset-password?token={reset_token}"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Reset Your Password</title>
        </head>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #667eea; padding: 40px 20px; text-align: center;">
                <h1 style="color: white; margin: 0;">🔐 Password Reset</h1>
            </div>

            <div style="padding: 40px 20px; background: #f8f9fa;">
                <p style="color: #666; line-height: 1.6;">
                    We received a request to reset your password for your Helix account.
                    Click the button below to create a new password:
                </p>

                <div style="text-align: center; margin: 30px 0;">
                    <a href="{reset_url}"
                       style="background: #667eea; color: white; padding: 12px 24px;
                              text-decoration: none; border-radius: 6px; font-weight: bold;">
                        Reset Password →
                    </a>
                </div>

                <p style="color: #999; font-size: 14px;">
                    This link will expire in 1 hour. If you didn't request this reset,
                    please ignore this email.
                </p>

                <p style="color: #999; font-size: 14px;">
                    For security, never share this email or the reset link with anyone.
                </p>
            </div>
        </body>
        </html>
        """

        return await self.send_email(user_email, subject, html_content)

    async def send_verification_email(self, user_email: str, verification_token: str) -> bool:
        """Send email verification"""
        subject = "Verify Your Helix Account"

        verify_url = f"{self.frontend_url}/auth/verify?token={verification_token}"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Verify Your Account</title>
        </head>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #667eea; padding: 40px 20px; text-align: center;">
                <h1 style="color: white; margin: 0;">✅ Verify Your Account</h1>
            </div>

            <div style="padding: 40px 20px; background: #f8f9fa;">
                <p style="color: #666; line-height: 1.6;">
                    Welcome! Please verify your email address to complete your Helix registration.
                </p>

                <div style="text-align: center; margin: 30px 0;">
                    <a href="{verify_url}"
                       style="background: #28a745; color: white; padding: 12px 24px;
                              text-decoration: none; border-radius: 6px; font-weight: bold;">
                        Verify Email →
                    </a>
                </div>

                <p style="color: #999; font-size: 14px;">
                    This link will expire in 24 hours. After verification, you'll have full access
                    to all Helix features.
                </p>
            </div>
        </body>
        </html>
        """

        return await self.send_email(user_email, subject, html_content)

    async def send_referral_email(self, to_email: str, referrer_name: str, referral_code: str, share_url: str) -> bool:
        """Send referral invitation email"""
        subject = f"{referrer_name} invited you to Helix! 🎁"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Join Helix</title>
        </head>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 40px 20px; text-align: center;">
                <h1 style="color: white; margin: 0; font-size: 32px;">🌀 You're Invited!</h1>
            </div>

            <div style="padding: 40px 20px; background: #f8f9fa;">
                <h2 style="color: #333; margin-top: 0;">Hi there!</h2>

                <p style="color: #666; line-height: 1.6;">
                    <strong>{referrer_name}</strong> thinks you'd love Helix - the revolutionary
                    AI platform that brings together intelligent agents, system computing, and
                    collective coordination.
                </p>

                <div style="background: white; padding: 20px; border-radius: 8px; margin: 20px 0; text-align: center;">
                    <h3 style="margin-top: 0; color: #667eea;">🎁 Your Welcome Gift</h3>
                    <p style="color: #333; font-size: 24px; font-weight: bold;">$5 Credit</p>
                    <p style="color: #666;">Use code: <code style="background: #eee; padding: 4px 8px; border-radius: 4px;">{referral_code}</code></p>
                </div>

                <div style="text-align: center; margin: 30px 0;">
                    <a href="{share_url}"
                       style="background: #667eea; color: white; padding: 14px 28px;
                              text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 16px;">
                        Join Helix →
                    </a>
                </div>

                <div style="background: white; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #333;">✨ What You'll Get</h3>
                    <ul style="color: #666; line-height: 1.8;">
                        <li><strong>14+ AI Agents</strong> - Each with unique personalities and capabilities</li>
                        <li><strong>Helix Spirals</strong> - Coordination-aware workflow automation</li>
                        <li><strong>Web OS</strong> - Browser-based operating system</li>
                        <li><strong>Community Access</strong> - Forums, Discord, and more</li>
                    </ul>
                </div>

                <p style="color: #999; font-size: 14px; text-align: center;">
                    Questions? Visit our <a href="{self.frontend_url}/help" style="color: #667eea;">Help Center</a>.
                </p>
            </div>

            <div style="background: #333; color: white; padding: 20px; text-align: center;">
                <p style="margin: 0; font-size: 14px;">
                    © 2025 Helix. Building the future of AI collaboration.
                </p>
            </div>
        </body>
        </html>
        """

        return await self.send_email(to_email, subject, html_content)


# Global email service instance
email_service = EmailService()

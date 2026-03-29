"""
📧 Email Automation Service
Automated transactional and marketing emails for SaaS platform

Supports:
- Welcome emails
- Password reset
- Usage alerts
- Team invitations
- Billing notifications
- Activity summaries
"""

import logging
import os

import httpx
from jinja2 import Environment, FileSystemLoader, TemplateNotFound, UndefinedError, select_autoescape
from pydantic import BaseModel

try:
    from apps.backend.core.resilience import retry_with_backoff
except ImportError:

    def retry_with_backoff(**_kw):
        def _noop(fn):
            return fn

        return _noop

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Email provider (supports SendGrid, Mailgun, Resend, SMTP)
EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "sendgrid")  # sendgrid, mailgun, resend, smtp
EMAIL_FROM = os.getenv("EMAIL_FROM", "noreply@helixspirals.work")
EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "Helix Collective")

# Provider-specific API keys
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
MAILGUN_API_KEY = os.getenv("MAILGUN_API_KEY")
MAILGUN_DOMAIN = os.getenv("MAILGUN_DOMAIN")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")

# SMTP configuration
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

# Frontend base URL for links in emails
FRONTEND_BASE_URL = os.getenv("FRONTEND_URL", "") or os.getenv("NEXT_PUBLIC_APP_URL", "")

# Template directory
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "templates", "emails")


# ============================================================================
# PYDANTIC MODELS
# ============================================================================


class EmailTemplate(BaseModel):
    """Email template data"""

    subject: str
    html: str
    text: str | None = None


class EmailRecipient(BaseModel):
    """Email recipient"""

    email: str
    name: str | None = None


# ============================================================================
# TEMPLATE RENDERING
# ============================================================================

# Initialize Jinja2 environment
try:
    jinja_env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "xml"]),
    )
except (ValueError, TypeError, KeyError, IndexError):
    jinja_env = None
    logger.warning("⚠️ Email templates directory not found: %s", TEMPLATE_DIR)


def render_template(template_name: str, context: dict) -> EmailTemplate:
    """Render email template with context"""
    if not jinja_env:
        # Fallback to basic template
        return EmailTemplate(
            subject=context.get("subject", "Notification from Helix"),
            html="<html><body>{}</body></html>".format(context.get("message", "")),
            text=context.get("message", ""),
        )

    # Render HTML template
    html_template = jinja_env.get_template(f"{template_name}.html")
    html = html_template.render(**context)

    # Try to render text template
    try:
        text_template = jinja_env.get_template(f"{template_name}.txt")
        text = text_template.render(**context)
    except (TemplateNotFound, UndefinedError) as e:
        logger.debug("Text template not found or undefined: %s", e)
        text = None
    except Exception as e:
        logger.warning("Unexpected error rendering text template: %s", e)
        text = None

    return EmailTemplate(subject=context.get("subject", "Notification from Helix"), html=html, text=text)


# ============================================================================
# EMAIL SENDING
# ============================================================================


@retry_with_backoff(max_retries=2, base_delay=1.0, exceptions=(Exception,))
async def send_email_sendgrid(to: EmailRecipient, subject: str, html: str, text: str | None = None) -> bool:
    """Send email via SendGrid"""
    if not SENDGRID_API_KEY:
        logger.info("⚠️ SendGrid API key not configured")
        return False

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {SENDGRID_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "personalizations": [{"to": [{"email": to.email, "name": to.name}]}],
                "from": {"email": EMAIL_FROM, "name": EMAIL_FROM_NAME},
                "subject": subject,
                "content": [{"type": "text/html", "value": html}]
                + ([{"type": "text/plain", "value": text}] if text else []),
            },
        )

        return response.status_code == 202


@retry_with_backoff(max_retries=2, base_delay=1.0, exceptions=(Exception,))
async def send_email_mailgun(to: EmailRecipient, subject: str, html: str, text: str | None = None) -> bool:
    """Send email via Mailgun"""
    if not MAILGUN_API_KEY or not MAILGUN_DOMAIN:
        logger.info("⚠️ Mailgun API key or domain not configured")
        return False

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"https://api.mailgun.net/v3/{MAILGUN_DOMAIN}/messages",
            auth=("api", MAILGUN_API_KEY),
            data={
                "from": f"{EMAIL_FROM_NAME} <{EMAIL_FROM}>",
                "to": f"{to.name or to.email} <{to.email}>",
                "subject": subject,
                "html": html,
                "text": text or "",
            },
        )

        return response.status_code == 200


@retry_with_backoff(max_retries=2, base_delay=1.0, exceptions=(Exception,))
async def send_email_resend(to: EmailRecipient, subject: str, html: str, text: str | None = None) -> bool:
    """Send email via Resend"""
    if not RESEND_API_KEY:
        logger.info("⚠️ Resend API key not configured")
        return False

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": f"{EMAIL_FROM_NAME} <{EMAIL_FROM}>",
                "to": [to.email],
                "subject": subject,
                "html": html,
                "text": text,
            },
        )

        return response.status_code in [200, 201]


async def send_email(to: EmailRecipient, subject: str, html: str, text: str | None = None) -> bool:
    """Send email using configured provider"""
    try:
        if EMAIL_PROVIDER == "sendgrid":
            return await send_email_sendgrid(to, subject, html, text)
        elif EMAIL_PROVIDER == "mailgun":
            return await send_email_mailgun(to, subject, html, text)
        elif EMAIL_PROVIDER == "resend":
            return await send_email_resend(to, subject, html, text)
        else:
            logger.info("⚠️ Unsupported email provider: %s", EMAIL_PROVIDER)
            return False
    except Exception as e:
        logger.error("❌ Failed to send email: %s", e)
        return False


# ============================================================================
# AUTOMATED EMAIL FUNCTIONS
# ============================================================================


async def send_welcome_email(user_email: str, user_name: str, activation_link: str | None = None):
    """Send welcome email to new user"""
    template = render_template(
        "welcome",
        {
            "subject": f"Welcome to Helix, {user_name}! 🌀",
            "user_name": user_name,
            "activation_link": activation_link,
            "dashboard_url": f"{FRONTEND_BASE_URL}/dashboard",
            "docs_url": f"{FRONTEND_BASE_URL}/docs",
        },
    )

    return await send_email(
        to=EmailRecipient(email=user_email, name=user_name),
        subject=template.subject,
        html=template.html,
        text=template.text,
    )


async def send_password_reset_email(user_email: str, user_name: str, reset_token: str):
    """Send password reset email"""
    reset_link = f"{FRONTEND_BASE_URL}/reset-password?token={reset_token}"

    template = render_template(
        "password_reset",
        {
            "subject": "Reset Your Helix Password",
            "user_name": user_name,
            "reset_link": reset_link,
            "expires_hours": 24,
        },
    )

    return await send_email(
        to=EmailRecipient(email=user_email, name=user_name),
        subject=template.subject,
        html=template.html,
        text=template.text,
    )


async def send_team_invitation_email(
    invitee_email: str,
    team_name: str,
    inviter_name: str,
    invitation_token: str,
    role: str,
):
    """Send team invitation email"""
    invitation_link = f"{FRONTEND_BASE_URL}/accept-invitation?token={invitation_token}"

    template = render_template(
        "team_invitation",
        {
            "subject": f"{inviter_name} invited you to join {team_name} on Helix",
            "team_name": team_name,
            "inviter_name": inviter_name,
            "role": role,
            "invitation_link": invitation_link,
            "expires_days": 7,
        },
    )

    return await send_email(
        to=EmailRecipient(email=invitee_email),
        subject=template.subject,
        html=template.html,
        text=template.text,
    )


# ============================================================================
# BATCH EMAIL SENDING
# ============================================================================


async def send_bulk_email(
    recipients: list[EmailRecipient],
    subject: str,
    html: str,
    text: str | None = None,
    batch_size: int = 100,
):
    """Send email to multiple recipients in batches"""
    results = []

    for i in range(0, len(recipients), batch_size):
        batch = recipients[i : i + batch_size]

        for recipient in batch:
            success = await send_email(recipient, subject, html, text)
            results.append({"email": recipient.email, "success": success})

    return results


# ============================================================================
# EMAIL HEALTH CHECK
# ============================================================================


def check_email_configuration() -> dict:
    """Check if email is properly configured"""
    checks = {
        "provider": EMAIL_PROVIDER,
        "from_address": EMAIL_FROM,
        "configured": False,
        "provider_specific": {},
    }

    if EMAIL_PROVIDER == "sendgrid":
        checks["provider_specific"]["api_key_set"] = bool(SENDGRID_API_KEY)
        checks["configured"] = bool(SENDGRID_API_KEY)
    elif EMAIL_PROVIDER == "mailgun":
        checks["provider_specific"]["api_key_set"] = bool(MAILGUN_API_KEY)
        checks["provider_specific"]["domain_set"] = bool(MAILGUN_DOMAIN)
        checks["configured"] = bool(MAILGUN_API_KEY and MAILGUN_DOMAIN)
    elif EMAIL_PROVIDER == "resend":
        checks["provider_specific"]["api_key_set"] = bool(RESEND_API_KEY)
        checks["configured"] = bool(RESEND_API_KEY)
    elif EMAIL_PROVIDER == "smtp":
        checks["provider_specific"]["host"] = SMTP_HOST
        checks["provider_specific"]["port"] = SMTP_PORT
        checks["provider_specific"]["credentials_set"] = bool(SMTP_USER and SMTP_PASSWORD)
        checks["configured"] = bool(SMTP_USER and SMTP_PASSWORD)

    checks["templates_available"] = jinja_env is not None

    return checks


# Alias for route compatibility
check_email_health = check_email_configuration


# Fix signature for route compatibility
async def send_usage_alert_email(
    user_email: str,
    user_name: str,
    usage_metric: str = None,
    current_usage: int = None,
    limit: int = None,
    percentage_used: int = None,
    # Legacy params
    usage_percent: float = None,
    tier: str = None,
):
    """Send usage limit alert - supports both new and legacy signatures"""
    # Use new signature params if provided, otherwise fall back to legacy
    if percentage_used is not None:
        usage = percentage_used
    elif usage_percent is not None:
        usage = usage_percent
    else:
        usage = (current_usage / limit * 100) if limit else 0

    tier_name = usage_metric or tier or "plan"

    template = render_template(
        "usage_alert",
        {
            "subject": f"Usage You've used {usage}% of your {tier_name}",
            "user_name": user_name,
            "usage_percent": usage,
            "usage_metric": usage_metric,
            "current_usage": current_usage,
            "limit": limit,
            "tier": tier_name,
            "upgrade_url": f"{FRONTEND_BASE_URL}/upgrade",
        },
    )

    return await send_email(
        to=EmailRecipient(email=user_email, name=user_name),
        subject=template.subject,
        html=template.html,
        text=template.text,
    )


# Fix billing notification signature for route compatibility
async def send_billing_notification_email(
    user_email: str,
    user_name: str,
    event_type: str = None,
    plan_name: str = None,
    amount: float | None = None,
    next_billing_date: str | None = None,
    failure_reason: str | None = None,
    # Legacy params
    notification_type: str = None,
):
    """Send billing notification - supports both new and legacy signatures"""
    notif_type = event_type or notification_type or "payment_success"

    subjects = {
        "payment_success": "Payment Successful - Helix",
        "payment_failed": "Payment Failed - Action Required",
        "subscription_cancelled": "Your Helix subscription has been canceled",
    }

    template = render_template(
        "billing_notification",
        {
            "subject": subjects.get(notif_type, "Billing Notification"),
            "user_name": user_name,
            "notification_type": notif_type,
            "event_type": event_type,
            "plan_name": plan_name,
            "amount": amount,
            "next_billing_date": next_billing_date,
            "failure_reason": failure_reason,
            "billing_url": f"{FRONTEND_BASE_URL}/billing",
        },
    )

    return await send_email(
        to=EmailRecipient(email=user_email, name=user_name),
        subject=template.subject,
        html=template.html,
        text=template.text,
    )


# Fix weekly summary signature for route compatibility
async def send_weekly_summary_email(
    user_email: str,
    user_name: str,
    summary_data: dict = None,
    # Legacy param
    stats: dict = None,
):
    """Send weekly activity summary - supports both new and legacy signatures"""
    data = summary_data or stats or {}

    template = render_template(
        "weekly_summary",
        {
            "subject": "Your Helix Weekly Summary",
            "user_name": user_name,
            "api_calls": data.get("api_calls", 0),
            "agent_sessions": data.get("agent_sessions", 0),
            "tokens_used": data.get("tokens_used", 0),
            "top_feature": data.get("top_feature", "API"),
            "dashboard_url": f"{FRONTEND_BASE_URL}/dashboard",
        },
    )

    return await send_email(
        to=EmailRecipient(email=user_email, name=user_name),
        subject=template.subject,
        html=template.html,
        text=template.text,
    )


# Fix feature announcement signature for route compatibility
async def send_feature_announcement_email(
    user_email: str,
    user_name: str,
    feature_name: str,
    feature_description: str,
    feature_link: str = None,
    # Legacy param
    feature_url: str = None,
):
    """Send new feature announcement - supports both new and legacy signatures"""
    url = feature_link or feature_url or FRONTEND_BASE_URL

    template = render_template(
        "feature_announcement",
        {
            "subject": f"New Feature: {feature_name}",
            "user_name": user_name,
            "feature_name": feature_name,
            "feature_description": feature_description,
            "feature_url": url,
        },
    )

    return await send_email(
        to=EmailRecipient(email=user_email, name=user_name),
        subject=template.subject,
        html=template.html,
        text=template.text,
    )

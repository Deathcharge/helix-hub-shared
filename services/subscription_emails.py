"""
🌀 Helix Collective v17.1 - Subscription Email Templates & Automation
====================================================================

Automated email notifications for subscription lifecycle events:
- Trial warnings (7d, 3d, 1d before expiry)
- Subscription renewed
- Payment failed
- Downgrade to free tier
- Usage limit warnings (80%, 100%)

Integrates with:
- SendGrid for email delivery
- Usage Service for limit tracking
- Stripe webhooks for payment events

Author: Claude (Helix Architect)
Date: 2026-02-03
Version: 17.1.0
"""

import logging
import os
from html import escape as _html_escape

from apps.backend.services.email_service import EmailService

logger = logging.getLogger(__name__)


def _safe(value: str) -> str:
    """HTML-escape a user-provided string for safe interpolation into templates."""
    return _html_escape(str(value), quote=True)

_FRONTEND_URL = os.getenv("FRONTEND_URL", "{_FRONTEND_URL}").rstrip("/")


# ============================================================================
# EMAIL TEMPLATES
# ============================================================================


def get_trial_ending_email(user_name: str, days_remaining: int, tier: str) -> tuple:
    """
    Generate trial ending warning email.

    Args:
        user_name: User's name
        days_remaining: Days until trial expires (7, 3, or 1)
        tier: Trial tier name

    Returns:
        (subject, html_content) tuple
    """
    user_name = _safe(user_name)
    tier = _safe(tier)
    urgency_map = {
        7: ("soon", "🔔", "#6366f1"),
        3: ("in just 3 days", "⚠️", "#f59e0b"),
        1: ("tomorrow", "🚨", "#ef4444"),
    }

    urgency_text, emoji, color = urgency_map.get(days_remaining, ("soon", "🔔", "#6366f1"))

    subject = f"{emoji} Your Helix trial ends {urgency_text}!"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Trial Ending Soon</title>
    </head>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: {color}; padding: 40px 20px; text-align: center;">
            <h1 style="color: white; margin: 0; font-size: 32px;">{emoji} Trial Ending Soon</h1>
        </div>

        <div style="padding: 40px 20px; background: #f8f9fa;">
            <h2 style="color: #333; margin-top: 0;">Hi {user_name}!</h2>

            <p style="color: #666; line-height: 1.6; font-size: 16px;">
                Your <strong>{tier}</strong> trial ends in <strong style="color: {color};">{days_remaining} day{"s" if days_remaining > 1 else ""}</strong>.
            </p>

            <div style="background: white; padding: 25px; border-radius: 8px; margin: 25px 0; border-left: 4px solid {color};">
                <h3 style="margin-top: 0; color: #333;">Don't lose access to:</h3>
                <ul style="color: #666; line-height: 1.8;">
                    <li>All 16 AI agents with unlimited access</li>
                    <li>Full Web OS suite (12+ applications)</li>
                    <li>Unlimited API calls and workflows</li>
                    <li>Priority support and advanced features</li>
                    <li>Agent Emergence Simulator</li>
                </ul>
            </div>

            <div style="text-align: center; margin: 35px 0;">
                <a href="{_FRONTEND_URL}/pricing"
                   style="background: {color}; color: white; padding: 16px 32px;
                          text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 16px; display: inline-block;">
                    Subscribe Now & Save 20%
                </a>
            </div>

            <div style="background: #fff3cd; padding: 20px; border-radius: 6px; margin: 20px 0;">
                <p style="margin: 0; color: #856404; font-size: 14px;">
                    <strong>💡 Special Offer:</strong> Subscribe before your trial ends and get 20% off your first 3 months!
                </p>
            </div>

            <p style="color: #999; font-size: 14px; text-align: center; margin-top: 30px;">
                Questions? <a href="{_FRONTEND_URL}/help" style="color: {color};">Visit our help center</a>
                or reply to this email.
            </p>
        </div>

        <div style="background: #333; color: white; padding: 20px; text-align: center;">
            <p style="margin: 0; font-size: 14px;">
                © 2026 Helix Collective • <a href="{_FRONTEND_URL}/pricing" style="color: #a78bfa;">View Plans</a>
            </p>
        </div>
    </body>
    </html>
    """

    return subject, html_content


def get_subscription_renewed_email(user_name: str, tier: str, amount: float, next_billing_date: str) -> tuple:
    """
    Generate subscription renewed confirmation email.

    Args:
        user_name: User's name
        tier: Subscription tier
        amount: Billing amount
        next_billing_date: Next billing date (formatted string)

    Returns:
        (subject, html_content) tuple
    """
    subject = f"✅ Subscription Renewed - {_safe(tier).title()} Plan"

    user_name = _safe(user_name)
    tier = _safe(tier)
    next_billing_date = _safe(next_billing_date)

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Subscription Renewed</title>
    </head>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 40px 20px; text-align: center;">
            <h1 style="color: white; margin: 0; font-size: 32px;">✅ Payment Successful</h1>
        </div>

        <div style="padding: 40px 20px; background: #f8f9fa;">
            <h2 style="color: #333; margin-top: 0;">Hi {user_name}!</h2>

            <p style="color: #666; line-height: 1.6; font-size: 16px;">
                Your subscription has been successfully renewed. Thank you for being a valued member of Helix Collective!
            </p>

            <div style="background: white; padding: 25px; border-radius: 8px; margin: 25px 0;">
                <h3 style="margin-top: 0; color: #333;">📋 Payment Details</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr style="border-bottom: 1px solid #e5e7eb;">
                        <td style="padding: 12px 0; color: #666;">Plan:</td>
                        <td style="padding: 12px 0; text-align: right; font-weight: bold; color: #333;">{tier.title()}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #e5e7eb;">
                        <td style="padding: 12px 0; color: #666;">Amount Charged:</td>
                        <td style="padding: 12px 0; text-align: right; font-weight: bold; color: #333;">${amount:.2f}</td>
                    </tr>
                    <tr>
                        <td style="padding: 12px 0; color: #666;">Next Billing Date:</td>
                        <td style="padding: 12px 0; text-align: right; font-weight: bold; color: #333;">{next_billing_date}</td>
                    </tr>
                </table>
            </div>

            <div style="text-align: center; margin: 30px 0;">
                <a href="{_FRONTEND_URL}/billing"
                   style="background: #6366f1; color: white; padding: 12px 24px;
                          text-decoration: none; border-radius: 6px; font-weight: bold; margin-right: 10px;">
                    View Invoice
                </a>
                <a href="{_FRONTEND_URL}/billing"
                   style="background: white; color: #6366f1; padding: 12px 24px; border: 2px solid #6366f1;
                          text-decoration: none; border-radius: 6px; font-weight: bold;">
                    Manage Subscription
                </a>
            </div>

            <p style="color: #999; font-size: 14px; text-align: center; margin-top: 30px;">
                Need to update your payment method?
                <a href="{_FRONTEND_URL}/billing" style="color: #6366f1;">Manage your billing settings</a>
            </p>
        </div>

        <div style="background: #333; color: white; padding: 20px; text-align: center;">
            <p style="margin: 0; font-size: 14px;">
                © 2026 Helix Collective • <a href="{_FRONTEND_URL}/help" style="color: #a78bfa;">Help Center</a>
            </p>
        </div>
    </body>
    </html>
    """

    return subject, html_content


def get_payment_failed_email(
    user_name: str,
    tier: str,
    amount: float,
    retry_date: str,
    reason: str | None = None,
) -> tuple:
    """
    Generate payment failed notification email.

    Args:
        user_name: User's name
        tier: Subscription tier
        amount: Failed payment amount
        retry_date: Next retry attempt date
        reason: Failure reason (optional)

    Returns:
        (subject, html_content) tuple
    """
    subject = "🚨 Payment Failed - Action Required"

    user_name = _safe(user_name)
    tier = _safe(tier)
    retry_date = _safe(retry_date)

    reason_text = ""
    if reason:
        reason_text = f"""
        <div style="background: #fef2f2; padding: 15px; border-radius: 6px; margin: 15px 0;">
            <p style="margin: 0; color: #991b1b; font-size: 14px;">
                <strong>Reason:</strong> {_safe(reason)}
            </p>
        </div>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Payment Failed</title>
    </head>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: #ef4444; padding: 40px 20px; text-align: center;">
            <h1 style="color: white; margin: 0; font-size: 32px;">🚨 Payment Failed</h1>
        </div>

        <div style="padding: 40px 20px; background: #f8f9fa;">
            <h2 style="color: #333; margin-top: 0;">Hi {user_name},</h2>

            <p style="color: #666; line-height: 1.6; font-size: 16px;">
                We were unable to process your payment for your <strong>{tier.title()}</strong> subscription.
            </p>

            {reason_text}

            <div style="background: white; padding: 25px; border-radius: 8px; margin: 25px 0; border-left: 4px solid #ef4444;">
                <h3 style="margin-top: 0; color: #333;">⚠️ What This Means:</h3>
                <ul style="color: #666; line-height: 1.8;">
                    <li>Your subscription is still active for now</li>
                    <li>We'll automatically retry on <strong>{retry_date}</strong></li>
                    <li>Update your payment method to avoid service interruption</li>
                    <li>After 3 failed attempts, your account will downgrade to Free</li>
                </ul>
            </div>

            <div style="text-align: center; margin: 35px 0;">
                <a href="{_FRONTEND_URL}/billing"
                   style="background: #ef4444; color: white; padding: 16px 32px;
                          text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 16px;">
                    Update Payment Method
                </a>
            </div>

            <div style="background: white; padding: 20px; border-radius: 6px; margin: 20px 0;">
                <h4 style="margin-top: 0; color: #333;">💳 Payment Details</h4>
                <p style="color: #666; margin: 5px 0;"><strong>Amount:</strong> ${amount:.2f}</p>
                <p style="color: #666; margin: 5px 0;"><strong>Next Retry:</strong> {retry_date}</p>
            </div>

            <p style="color: #999; font-size: 14px; text-align: center; margin-top: 30px;">
                Having trouble? <a href="{_FRONTEND_URL}/help" style="color: #ef4444;">Contact support</a>
            </p>
        </div>

        <div style="background: #333; color: white; padding: 20px; text-align: center;">
            <p style="margin: 0; font-size: 14px;">
                © 2026 Helix Collective • <a href="{_FRONTEND_URL}/billing" style="color: #a78bfa;">Billing Settings</a>
            </p>
        </div>
    </body>
    </html>
    """

    return subject, html_content


def get_downgrade_notification_email(user_name: str, previous_tier: str) -> tuple:
    """
    Generate downgrade to free tier notification email.

    Args:
        user_name: User's name
        previous_tier: Previous subscription tier

    Returns:
        (subject, html_content) tuple
    """
    subject = "Your Helix Subscription Has Ended"

    user_name = _safe(user_name)
    previous_tier = _safe(previous_tier)

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Subscription Ended</title>
    </head>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: #64748b; padding: 40px 20px; text-align: center;">
            <h1 style="color: white; margin: 0; font-size: 32px;">Subscription Ended</h1>
        </div>

        <div style="padding: 40px 20px; background: #f8f9fa;">
            <h2 style="color: #333; margin-top: 0;">Hi {user_name},</h2>

            <p style="color: #666; line-height: 1.6; font-size: 16px;">
                Your <strong>{previous_tier.title()}</strong> subscription has ended, and your account has been moved to our Free tier.
            </p>

            <div style="background: white; padding: 25px; border-radius: 8px; margin: 25px 0;">
                <h3 style="margin-top: 0; color: #333;">What You Still Have:</h3>
                <ul style="color: #666; line-height: 1.8;">
                    <li>Access to 3 AI agents</li>
                    <li>100MB storage</li>
                    <li>Community support</li>
                    <li>Basic Web OS features</li>
                </ul>
            </div>

            <div style="background: #fef3c7; padding: 20px; border-radius: 8px; margin: 25px 0;">
                <h3 style="margin-top: 0; color: #92400e;">What You're Missing:</h3>
                <ul style="color: #78350f; line-height: 1.8; margin-bottom: 0;">
                    <li>Access to all 16 AI agents</li>
                    <li>Unlimited API calls</li>
                    <li>Full Web OS suite (12+ apps)</li>
                    <li>Priority support</li>
                    <li>Advanced features & analytics</li>
                </ul>
            </div>

            <div style="text-align: center; margin: 35px 0;">
                <a href="{_FRONTEND_URL}/pricing"
                   style="background: #6366f1; color: white; padding: 16px 32px;
                          text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 16px;">
                    Reactivate Your Subscription
                </a>
            </div>

            <p style="color: #666; font-size: 14px; text-align: center; margin-top: 30px;">
                We'd love to have you back! Reactivate anytime to restore full access.
            </p>

            <p style="color: #999; font-size: 14px; text-align: center;">
                Questions? <a href="{_FRONTEND_URL}/help" style="color: #6366f1;">Contact support</a>
            </p>
        </div>

        <div style="background: #333; color: white; padding: 20px; text-align: center;">
            <p style="margin: 0; font-size: 14px;">
                © 2026 Helix Collective • <a href="{_FRONTEND_URL}/pricing" style="color: #a78bfa;">View Plans</a>
            </p>
        </div>
    </body>
    </html>
    """

    return subject, html_content


def get_refund_notification_email(user_name: str, amount: float, charge_id: str) -> tuple:
    """
    Generate refund notification email.

    Args:
        user_name: User's name
        amount: Refund amount in dollars
        charge_id: Stripe charge ID

    Returns:
        (subject, html_content) tuple
    """
    subject = "Refund Processed - Helix Collective"

    user_name = _safe(user_name)
    charge_id = _safe(charge_id)

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Refund Processed</title>
    </head>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: #6366f1; padding: 40px 20px; text-align: center;">
            <h1 style="color: white; margin: 0; font-size: 32px;">Refund Processed</h1>
        </div>

        <div style="padding: 40px 20px; background: #f8f9fa;">
            <h2 style="color: #333; margin-top: 0;">Hi {user_name},</h2>

            <p style="color: #666; line-height: 1.6; font-size: 16px;">
                A refund has been processed for your account. The funds will be returned to your original payment method.
            </p>

            <div style="background: white; padding: 25px; border-radius: 8px; margin: 25px 0;">
                <h3 style="margin-top: 0; color: #333;">Refund Details</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr style="border-bottom: 1px solid #e5e7eb;">
                        <td style="padding: 12px 0; color: #666;">Amount Refunded:</td>
                        <td style="padding: 12px 0; text-align: right; font-weight: bold; color: #333;">${amount:.2f}</td>
                    </tr>
                    <tr>
                        <td style="padding: 12px 0; color: #666;">Reference:</td>
                        <td style="padding: 12px 0; text-align: right; font-weight: bold; color: #333;">{charge_id}</td>
                    </tr>
                </table>
            </div>

            <p style="color: #666; line-height: 1.6; font-size: 14px;">
                Please allow 5-10 business days for the refund to appear on your statement, depending on your bank.
            </p>

            <p style="color: #999; font-size: 14px; text-align: center; margin-top: 30px;">
                Questions? <a href="{_FRONTEND_URL}/help" style="color: #6366f1;">Contact support</a>
            </p>
        </div>

        <div style="background: #333; color: white; padding: 20px; text-align: center;">
            <p style="margin: 0; font-size: 14px;">
                &copy; 2026 Helix Collective &bull; <a href="{_FRONTEND_URL}/billing" style="color: #a78bfa;">Billing Settings</a>
            </p>
        </div>
    </body>
    </html>
    """

    return subject, html_content


def get_payment_action_required_email(user_name: str, tier: str, amount: float, hosted_invoice_url: str) -> tuple:
    """
    Generate payment action required (3D Secure / SCA) email.

    Args:
        user_name: User's name
        tier: Subscription tier
        amount: Payment amount in dollars
        hosted_invoice_url: Stripe hosted invoice URL for completing payment

    Returns:
        (subject, html_content) tuple
    """
    subject = "Action Required - Complete Your Payment"

    user_name = _safe(user_name)
    tier = _safe(tier)

    # Validate hosted_invoice_url to prevent javascript: or data: URI injection
    if hosted_invoice_url and hosted_invoice_url.startswith("https://"):
        payment_link = hosted_invoice_url
    else:
        payment_link = f"{_FRONTEND_URL}/billing"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Payment Action Required</title>
    </head>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: #f59e0b; padding: 40px 20px; text-align: center;">
            <h1 style="color: white; margin: 0; font-size: 32px;">Payment Action Required</h1>
        </div>

        <div style="padding: 40px 20px; background: #f8f9fa;">
            <h2 style="color: #333; margin-top: 0;">Hi {user_name},</h2>

            <p style="color: #666; line-height: 1.6; font-size: 16px;">
                Your payment for the <strong>{tier.title()}</strong> plan requires additional verification to complete.
                This is typically a security step required by your bank (3D Secure).
            </p>

            <div style="background: white; padding: 25px; border-radius: 8px; margin: 25px 0; border-left: 4px solid #f59e0b;">
                <h3 style="margin-top: 0; color: #333;">What You Need To Do:</h3>
                <ol style="color: #666; line-height: 1.8;">
                    <li>Click the button below to open the secure payment page</li>
                    <li>Complete the verification step required by your bank</li>
                    <li>Your subscription will be activated immediately after verification</li>
                </ol>
            </div>

            <div style="background: white; padding: 20px; border-radius: 6px; margin: 20px 0;">
                <p style="color: #666; margin: 5px 0;"><strong>Amount:</strong> ${amount:.2f}</p>
                <p style="color: #666; margin: 5px 0;"><strong>Plan:</strong> {tier.title()}</p>
            </div>

            <div style="text-align: center; margin: 35px 0;">
                <a href="{payment_link}"
                   style="background: #f59e0b; color: white; padding: 16px 32px;
                          text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 16px;">
                    Complete Payment
                </a>
            </div>

            <p style="color: #999; font-size: 14px; text-align: center; margin-top: 30px;">
                If you did not make this purchase, please
                <a href="{_FRONTEND_URL}/help" style="color: #f59e0b;">contact support</a> immediately.
            </p>
        </div>

        <div style="background: #333; color: white; padding: 20px; text-align: center;">
            <p style="margin: 0; font-size: 14px;">
                &copy; 2026 Helix Collective &bull; <a href="{_FRONTEND_URL}/billing" style="color: #a78bfa;">Billing Settings</a>
            </p>
        </div>
    </body>
    </html>
    """

    return subject, html_content


def get_usage_warning_email(
    user_name: str,
    resource_type: str,
    percentage: float,
    current: int,
    limit: int,
    tier: str,
) -> tuple:
    """
    Generate usage limit warning email.

    Args:
        user_name: User's name
        resource_type: Type of resource (api_calls, storage, etc.)
        percentage: Usage percentage
        current: Current usage
        limit: Limit value
        tier: Current tier

    Returns:
        (subject, html_content) tuple
    """
    resource_display = resource_type.replace("_", " ").replace(" per day", "").replace(" per month", "").title()

    user_name = _safe(user_name)
    tier = _safe(tier)
    resource_display = _safe(resource_display)

    if percentage >= 100:
        subject = f"🚨 {resource_display} Limit Reached"
        color = "#ef4444"
        emoji = "🚨"
        status = "reached"
    else:
        subject = f"⚠️ {resource_display} Limit Warning ({int(percentage)}%)"
        color = "#f59e0b"
        emoji = "⚠️"
        status = "approaching"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Usage Warning</title>
    </head>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: {color}; padding: 40px 20px; text-align: center;">
            <h1 style="color: white; margin: 0; font-size: 32px;">{emoji} Usage Alert</h1>
        </div>

        <div style="padding: 40px 20px; background: #f8f9fa;">
            <h2 style="color: #333; margin-top: 0;">Hi {user_name}!</h2>

            <p style="color: #666; line-height: 1.6; font-size: 16px;">
                You're {status} your <strong>{resource_display}</strong> limit on the <strong>{tier.title()}</strong> plan.
            </p>

            <div style="background: white; padding: 25px; border-radius: 8px; margin: 25px 0;">
                <h3 style="margin-top: 0; color: #333;">Current Usage:</h3>

                <div style="background: #f3f4f6; border-radius: 8px; overflow: hidden; margin: 15px 0;">
                    <div style="height: 30px; background: {color}; width: {min(percentage, 100)}%;"></div>
                </div>

                <p style="color: #666; text-align: center; margin: 10px 0;">
                    <strong style="font-size: 24px; color: {color};">{current:,}</strong>
                    <span style="color: #999;">of {limit:,}</span>
                    <span style="color: {color}; font-weight: bold; margin-left: 10px;">({int(percentage)}%)</span>
                </p>
            </div>

            <div style="background: #fef3c7; padding: 20px; border-radius: 8px; margin: 25px 0;">
                <h4 style="margin-top: 0; color: #92400e;">What happens next?</h4>
                <p style="color: #78350f; margin-bottom: 0;">
                    {"You've reached your limit. Upgrade to continue using this feature." if percentage >= 100 else "Upgrade now to avoid any service interruptions."}
                </p>
            </div>

            <div style="text-align: center; margin: 35px 0;">
                <a href="{_FRONTEND_URL}/pricing"
                   style="background: {color}; color: white; padding: 16px 32px;
                          text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 16px;">
                    Upgrade Your Plan
                </a>
            </div>

            <p style="color: #999; font-size: 14px; text-align: center; margin-top: 30px;">
                <a href="{_FRONTEND_URL}/billing" style="color: {color};">View usage details</a> •
                <a href="{_FRONTEND_URL}/help" style="color: {color};">Get help</a>
            </p>
        </div>

        <div style="background: #333; color: white; padding: 20px; text-align: center;">
            <p style="margin: 0; font-size: 14px;">
                © 2026 Helix Collective • <a href="{_FRONTEND_URL}/pricing" style="color: #a78bfa;">View Plans</a>
            </p>
        </div>
    </body>
    </html>
    """

    return subject, html_content


# ============================================================================
# EMAIL SENDING FUNCTIONS
# ============================================================================


class SubscriptionEmailService:
    """Service for sending subscription lifecycle emails"""

    def __init__(self) -> None:
        self.email_service = EmailService()

    async def send_trial_warning(self, user_email: str, user_name: str, days_remaining: int, tier: str) -> bool:
        """Send trial ending warning email"""
        try:
            subject, html_content = get_trial_ending_email(user_name, days_remaining, tier)
            result = await self.email_service.send_email(user_email, subject, html_content)
            logger.info("📧 Sent trial warning (%sd) to %s", days_remaining, user_email)
            return result
        except Exception as e:
            logger.error("❌ Failed to send trial warning: %s", e)
            return False

    async def send_subscription_renewed(
        self,
        user_email: str,
        user_name: str,
        tier: str,
        amount: float,
        next_billing_date: str,
    ) -> bool:
        """Send subscription renewed confirmation"""
        try:
            subject, html_content = get_subscription_renewed_email(user_name, tier, amount, next_billing_date)
            result = await self.email_service.send_email(user_email, subject, html_content)
            logger.info("✅ Sent renewal confirmation to %s", user_email)
            return result
        except Exception as e:
            logger.error("❌ Failed to send renewal email: %s", e)
            return False

    async def send_payment_failed(
        self,
        user_email: str,
        user_name: str,
        tier: str,
        amount: float,
        retry_date: str,
        reason: str | None = None,
    ) -> bool:
        """Send payment failed notification"""
        try:
            subject, html_content = get_payment_failed_email(user_name, tier, amount, retry_date, reason)
            result = await self.email_service.send_email(user_email, subject, html_content)
            logger.info("⚠️ Sent payment failed notice to %s", user_email)
            return result
        except Exception as e:
            logger.error("❌ Failed to send payment failed email: %s", e)
            return False

    async def send_downgrade_notification(self, user_email: str, user_name: str, previous_tier: str) -> bool:
        """Send downgrade to free tier notification"""
        try:
            subject, html_content = get_downgrade_notification_email(user_name, previous_tier)
            result = await self.email_service.send_email(user_email, subject, html_content)
            logger.info("📉 Sent downgrade notification to %s", user_email)
            return result
        except Exception as e:
            logger.error("❌ Failed to send downgrade email: %s", e)
            return False

    async def send_refund_notification(
        self,
        user_email: str,
        user_name: str,
        amount: float,
        charge_id: str,
    ) -> bool:
        """Send refund processed notification"""
        try:
            subject, html_content = get_refund_notification_email(user_name, amount, charge_id)
            result = await self.email_service.send_email(user_email, subject, html_content)
            logger.info("Sent refund notification to %s", user_email)
            return result
        except Exception as e:
            logger.error("Failed to send refund notification email: %s", e)
            return False

    async def send_payment_action_required(
        self,
        user_email: str,
        user_name: str,
        tier: str,
        amount: float,
        hosted_invoice_url: str,
    ) -> bool:
        """Send payment action required (3D Secure / SCA) notification"""
        try:
            subject, html_content = get_payment_action_required_email(user_name, tier, amount, hosted_invoice_url)
            result = await self.email_service.send_email(user_email, subject, html_content)
            logger.info("Sent payment action required notification to %s", user_email)
            return result
        except Exception as e:
            logger.error("Failed to send payment action required email: %s", e)
            return False

    async def send_usage_warning(
        self,
        user_email: str,
        user_name: str,
        resource_type: str,
        percentage: float,
        current: int,
        limit: int,
        tier: str,
    ) -> bool:
        """Send usage limit warning"""
        try:
            subject, html_content = get_usage_warning_email(user_name, resource_type, percentage, current, limit, tier)
            result = await self.email_service.send_email(user_email, subject, html_content)
            logger.info("⚠️ Sent usage warning (%s %s%) to %s", resource_type, int(percentage), user_email)
            return result
        except Exception as e:
            logger.error("❌ Failed to send usage warning: %s", e)
            return False


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_subscription_email_service: SubscriptionEmailService | None = None


def get_subscription_email_service() -> SubscriptionEmailService:
    """Get or create subscription email service singleton"""
    global _subscription_email_service
    if _subscription_email_service is None:
        _subscription_email_service = SubscriptionEmailService()
    return _subscription_email_service

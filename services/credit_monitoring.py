"""
Credit Monitoring and Alerts Service

Monitors user credit usage and sends alerts when:
- Credits are running low (80% threshold)
- Credits are exhausted (100% threshold)
- Unusual spending patterns detected

Author: Andrew John Ward
Version: 2.0 - Credit-Based Pricing
"""

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.backend.db_models import CreditTransaction, User
from apps.backend.services.credit_service import CreditBalance, CreditService

logger = logging.getLogger(__name__)


@dataclass
class CreditAlert:
    """Credit alert information"""

    user_id: str
    alert_type: str  # 'low_credit', 'credit_exhausted', 'unusual_spending'
    severity: str  # 'info', 'warning', 'critical'
    message: str
    credits_remaining: float
    credits_percentage: float
    recommended_action: str


class CreditMonitoringService:
    """
    Credit monitoring and alerts service

    Monitors credit usage and sends alerts to users when they're running low.
    """

    # Alert thresholds
    LOW_CREDIT_THRESHOLD = 0.8  # 80% of credits used
    CRITICAL_CREDIT_THRESHOLD = 0.95  # 95% of credits used

    # Unusual spending detection
    UNUSUAL_SPENDING_MULTIPLIER = 3.0  # 3x average daily spending

    def __init__(self, db: AsyncSession):
        self.db = db
        self.credit_service = CreditService(db)

    async def check_all_users(self) -> list[CreditAlert]:
        """
        Check all users for credit alerts

        Returns:
            List of CreditAlert objects
        """
        alerts = []

        # Get all users
        result = await self.db.execute(select(User))
        users = result.scalars().all()

        for user in users:
            try:
                user_alerts = await self.check_user(user.id)
                alerts.extend(user_alerts)
            except Exception as e:
                logger.error("Error checking user %s: %s", user.id, e)

        return alerts

    async def check_user(self, user_id: str) -> list[CreditAlert]:
        """
        Check a single user for credit alerts

        Args:
            user_id: User ID

        Returns:
            List of CreditAlert objects
        """
        alerts = []

        try:
            # Get user's credit balance
            balance = await self.credit_service.get_credit_balance(user_id)

            # Skip BYOT users (they don't use credits)
            if balance.byot_enabled:
                return alerts

            # Calculate percentage used
            credits_percentage = balance.credits_used / balance.credits_monthly if balance.credits_monthly > 0 else 0

            # Check for low credit alert
            if credits_percentage >= self.LOW_CREDIT_THRESHOLD and credits_percentage < self.CRITICAL_CREDIT_THRESHOLD:
                alert = CreditAlert(
                    user_id=user_id,
                    alert_type="low_credit",
                    severity="warning",
                    message=f"You've used {credits_percentage * 100:.1f}% of your monthly credits.",
                    credits_remaining=balance.credits_remaining,
                    credits_percentage=credits_percentage * 100,
                    recommended_action="Purchase additional credits or enable BYOT to continue using the platform.",
                )
                alerts.append(alert)

            # Check for critical credit alert
            elif credits_percentage >= self.CRITICAL_CREDIT_THRESHOLD:
                alert = CreditAlert(
                    user_id=user_id,
                    alert_type="credit_exhausted",
                    severity="critical",
                    message=f"You've used {credits_percentage * 100:.1f}% of your monthly credits. Your credits will be exhausted soon.",
                    credits_remaining=balance.credits_remaining,
                    credits_percentage=credits_percentage * 100,
                    recommended_action="Purchase additional credits immediately or enable BYOT to avoid service interruption.",
                )
                alerts.append(alert)

            # Check for unusual spending
            unusual_spending_alert = await self.check_unusual_spending(user_id, balance)
            if unusual_spending_alert:
                alerts.append(unusual_spending_alert)

        except Exception as e:
            logger.error("Error checking user %s: %s", user_id, e)

        return alerts

    async def check_unusual_spending(
        self,
        user_id: str,
        balance: CreditBalance,
    ) -> CreditAlert | None:
        """
        Check for unusual spending patterns

        Args:
            user_id: User ID
            balance: User's credit balance

        Returns:
            CreditAlert if unusual spending detected, None otherwise
        """
        try:
            # Get usage statistics for the last 30 days
            usage_stats = await self.credit_service.get_usage_stats(user_id, days=30)

            if usage_stats.total_requests == 0:
                return None

            # Calculate average daily spending
            avg_daily_cost = usage_stats.total_cost / 30

            # Get today's spending
            today = datetime.now(UTC).date()
            today_start = datetime.combine(today, datetime.min.time(), tzinfo=UTC)

            result = await self.db.execute(
                select(CreditTransaction).where(
                    and_(
                        CreditTransaction.user_id == user_id,
                        CreditTransaction.created_at >= today_start,
                        CreditTransaction.transaction_type == "usage",
                    )
                )
            )
            today_transactions = result.scalars().all()

            today_cost = sum(abs(t.amount) for t in today_transactions)

            # Check if today's spending is unusually high
            if avg_daily_cost > 0 and today_cost > avg_daily_cost * self.UNUSUAL_SPENDING_MULTIPLIER:
                return CreditAlert(
                    user_id=user_id,
                    alert_type="unusual_spending",
                    severity="warning",
                    message=f"Your spending today (${today_cost:.2f}) is significantly higher than your average (${avg_daily_cost:.2f}/day).",
                    credits_remaining=balance.credits_remaining,
                    credits_percentage=(
                        (balance.credits_used / balance.credits_monthly * 100) if balance.credits_monthly > 0 else 0
                    ),
                    recommended_action="Review your usage patterns and consider enabling BYOT if you expect high usage.",
                )

        except Exception as e:
            logger.error("Error checking unusual spending for user %s: %s", user_id, e)

        return None

    async def send_alert(self, alert: CreditAlert) -> bool:
        """
        Send a credit alert to the user via email (with log fallback).

        Args:
            alert: CreditAlert object

        Returns:
            True if alert was sent successfully, False otherwise
        """
        try:
            # Get user information
            result = await self.db.execute(select(User).where(User.id == alert.user_id))
            user = result.scalar_one_or_none()

            if not user:
                logger.error("User not found: %s", alert.user_id)
                return False

            logger.info(
                "Credit alert for user %s: %s - %s",
                alert.user_id,
                alert.alert_type,
                alert.message,
            )

            # Send email notification if user has an email address
            user_email = getattr(user, "email", None)
            if user_email:
                try:
                    from apps.backend.services.email_service import EmailService

                    email_svc = EmailService()

                    severity_emoji = {
                        "info": "ℹ️",
                        "warning": "⚠️",
                        "critical": "🚨",
                    }.get(alert.severity, "📋")

                    subject = f"{severity_emoji} Helix Credit Alert: {alert.alert_type.replace('_', ' ').title()}"

                    html_content = (
                        f"<h2>{severity_emoji} Credit Alert</h2>"
                        f"<p>{alert.message}</p>"
                        f"<p><strong>Credits remaining:</strong> {alert.credits_remaining:.2f}</p>"
                        f"<p><strong>Recommended action:</strong> {alert.recommended_action}</p>"
                        f"<hr/>"
                        f"<p style='color: #888; font-size: 12px;'>"
                        f"Manage your credits at <a href='{os.getenv('FRONTEND_URL', 'https://helixcollective.work').rstrip('/')}/billing'>billing settings</a>"
                        f"</p>"
                    )

                    await email_svc.send_email(
                        to_email=user_email,
                        subject=subject,
                        html_content=html_content,
                    )
                except Exception as email_err:
                    logger.warning(
                        "Failed to send credit alert email to user %s: %s",
                        alert.user_id,
                        email_err,
                    )

            return True

        except Exception as e:
            logger.error("Error sending alert to user %s: %s", alert.user_id, e)
            return False

    async def get_low_credit_users(self, threshold: float = 0.8) -> list[CreditBalance]:
        """
        Get users with low credits

        Args:
            threshold: Credit threshold (0.0 to 1.0)

        Returns:
            List of CreditBalance objects
        """
        low_credit_users = []

        # Get all users
        result = await self.db.execute(select(User))
        users = result.scalars().all()

        for user in users:
            try:
                balance = await self.credit_service.get_credit_balance(user.id)

                # Skip BYOT users
                if balance.byot_enabled:
                    continue

                # Calculate percentage used
                credits_percentage = (
                    balance.credits_used / balance.credits_monthly if balance.credits_monthly > 0 else 0
                )

                if credits_percentage >= threshold:
                    low_credit_users.append(balance)

            except Exception as e:
                logger.error("Error getting balance for user %s: %s", user.id, e)

        return low_credit_users

    async def generate_daily_report(self) -> dict:
        """
        Generate a daily credit usage report

        Returns:
            Dictionary with daily report statistics
        """
        try:
            # Get all users
            result = await self.db.execute(select(User))
            users = result.scalars().all()

            total_users = len(users)
            low_credit_users = await self.get_low_credit_users(threshold=0.8)
            critical_users = await self.get_low_credit_users(threshold=0.95)

            # Calculate total credits used
            total_credits_used = 0.0
            total_credits_allocated = 0.0

            for user in users:
                try:
                    balance = await self.credit_service.get_credit_balance(user.id)
                    total_credits_used += balance.credits_used
                    total_credits_allocated += balance.credits_monthly
                except Exception as e:
                    logger.error("Error getting balance for user %s: %s", user.id, e)

            # Calculate overall usage percentage
            overall_usage_percentage = (
                (total_credits_used / total_credits_allocated * 100) if total_credits_allocated > 0 else 0
            )

            return {
                "date": datetime.now(UTC).isoformat(),
                "total_users": total_users,
                "low_credit_users": len(low_credit_users),
                "critical_users": len(critical_users),
                "total_credits_used": round(total_credits_used, 2),
                "total_credits_allocated": round(total_credits_allocated, 2),
                "overall_usage_percentage": round(overall_usage_percentage, 2),
                "low_credit_users_list": [u.user_id for u in low_credit_users],
                "critical_users_list": [u.user_id for u in critical_users],
            }

        except Exception as e:
            logger.error("Error generating daily report: %s", e)
            return {}


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


async def get_credit_monitoring_service(db: AsyncSession) -> CreditMonitoringService:
    """Get credit monitoring service instance"""
    return CreditMonitoringService(db)

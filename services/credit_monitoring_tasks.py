"""
Credit Monitoring Scheduled Tasks

Background tasks for credit monitoring and alerts.
Run these tasks periodically (e.g., via cron, Celery, or APScheduler).

Author: Andrew John Ward
Version: 2.1 - Credit-Based Pricing with persistent report storage
"""

import asyncio
import logging
from datetime import UTC, datetime

from apps.backend.db_models import CreditReport, get_db
from apps.backend.services.credit_monitoring import get_credit_monitoring_service

logger = logging.getLogger(__name__)


async def run_daily_credit_check():
    """
    Run daily credit check for all users

    This task should be scheduled to run once per day (e.g., at 9 AM UTC).
    It checks all users for low credits and sends alerts.
    """
    logger.info("Starting daily credit check...")

    try:
        async for db in get_db():
            monitoring_service = await get_credit_monitoring_service(db)

            # Check all users for alerts
            alerts = await monitoring_service.check_all_users()

            logger.info("Found %s credit alerts", len(alerts))

            # Send alerts
            for alert in alerts:
                success = await monitoring_service.send_alert(alert)
                if success:
                    logger.info("Alert sent to user %s: %s", alert.user_id, alert.alert_type)
                else:
                    logger.error("Failed to send alert to user %s", alert.user_id)

            # Generate daily report
            report = await monitoring_service.generate_daily_report()
            logger.info("Daily report: %s", report)

            logger.info("Daily credit check completed")
            break

    except Exception as e:
        logger.error("Error in daily credit check: %s", e)


async def run_hourly_credit_check():
    """
    Run hourly credit check for critical users

    This task should be scheduled to run once per hour.
    It only checks users with critical credit levels (95%+ used).
    """
    logger.info("Starting hourly credit check...")

    try:
        async for db in get_db():
            monitoring_service = await get_credit_monitoring_service(db)

            # Get critical users (95%+ credits used)
            critical_users = await monitoring_service.get_low_credit_users(threshold=0.95)

            logger.info("Found %s critical users", len(critical_users))

            # Check each critical user
            for user_balance in critical_users:
                alerts = await monitoring_service.check_user(user_balance.user_id)

                # Send alerts
                for alert in alerts:
                    success = await monitoring_service.send_alert(alert)
                    if success:
                        logger.info("Alert sent to user %s: %s", alert.user_id, alert.alert_type)
                    else:
                        logger.error("Failed to send alert to user %s", alert.user_id)

            logger.info("Hourly credit check completed")
            break

    except Exception as e:
        logger.error("Error in hourly credit check: %s", e)


async def generate_daily_report():
    """
    Generate daily credit usage report and persist it to the database.

    This task should be scheduled to run once per day (e.g., at midnight UTC).
    Reports are stored in the ``credit_reports`` table for historical analysis,
    admin dashboards, and anomaly detection.
    """
    logger.info("Generating daily credit report...")

    try:
        async for db in get_db():
            monitoring_service = await get_credit_monitoring_service(db)

            # Generate report
            report = await monitoring_service.generate_daily_report()

            if not report:
                logger.warning("Daily report returned empty — skipping storage")
                break

            # Persist to credit_reports table
            credit_report = CreditReport(
                report_date=datetime.now(UTC),
                total_users=report.get("total_users", 0),
                low_credit_users=report.get("low_credit_users", 0),
                critical_users=report.get("critical_users", 0),
                total_credits_used=report.get("total_credits_used", 0),
                total_credits_allocated=report.get("total_credits_allocated", 0),
                overall_usage_percentage=report.get("overall_usage_percentage", 0),
                report_data=report,  # Full dict for extensibility
            )
            db.add(credit_report)
            await db.commit()

            logger.info(
                "Daily report stored: %s users, %.1f%% usage, %s low-credit, %s critical",
                report.get("total_users", 0),
                report.get("overall_usage_percentage", 0),
                report.get("low_credit_users", 0),
                report.get("critical_users", 0),
            )
            break

    except Exception as e:
        logger.error("Error generating daily report: %s", e)


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    """
    Run credit monitoring tasks

    Usage:
        python -m apps.backend.services.credit_monitoring_tasks daily
        python -m apps.backend.services.credit_monitoring_tasks hourly
        python -m apps.backend.services.credit_monitoring_tasks report
    """
    import sys

    # Support both positional (daily) and flag (--task daily) syntax
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        # Check for --task flag
        for i, a in enumerate(sys.argv[1:], 1):
            if a == "--task" and i + 1 < len(sys.argv):
                args = [sys.argv[i + 1]]
                break

    task = args[0] if args else "daily"

    if task == "daily":
        asyncio.run(run_daily_credit_check())
    elif task == "hourly":
        asyncio.run(run_hourly_credit_check())
    elif task == "report":
        asyncio.run(generate_daily_report())
    else:
        logger.error("Unknown task: %s", task)
        logger.info("Available tasks: daily, hourly, report")
        sys.exit(1)

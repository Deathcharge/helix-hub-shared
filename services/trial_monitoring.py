"""
🌀 Helix Collective v17.1 - Trial Monitoring & Automated Notifications
======================================================================

Scheduled tasks for monitoring trial subscriptions and sending automated warnings:
- 7-day warning (when trial has 7 days remaining)
- 3-day warning (when trial has 3 days remaining)
- 1-day warning (when trial expires tomorrow)

Runs daily via APScheduler or cron job.

Author: Claude (Helix Architect)
Date: 2026-02-03
Version: 17.1.0
"""

import logging
from datetime import UTC, datetime

from apps.backend.core.unified_auth import Database
from apps.backend.services.subscription_emails import get_subscription_email_service

logger = logging.getLogger(__name__)


# ============================================================================
# TRIAL MONITORING
# ============================================================================


async def check_trial_endings() -> dict[str, int]:
    """
    Check for trials ending soon and send warning emails.

    Returns:
        Statistics: {emails_sent_7d, emails_sent_3d, emails_sent_1d, errors}
    """
    stats = {"emails_sent_7d": 0, "emails_sent_3d": 0, "emails_sent_1d": 0, "errors": 0}

    try:
        logger.info("🔍 Starting trial monitoring check...")

        # Get all users with active trials
        users_with_trials = await Database.fetch(
            """
            SELECT id, email, name, trial_end, tier
            FROM users
            WHERE trial_end IS NOT NULL
            AND trial_end > NOW()
            AND subscription_tier IN ('free', 'trial')
            ORDER BY trial_end ASC
            """
        )

        if not users_with_trials:
            logger.info("✅ No active trials found")
            return stats

        logger.info("📋 Found %s active trials to monitor", len(users_with_trials))

        now = datetime.now(UTC)
        email_service = get_subscription_email_service()

        for user in users_with_trials:
            try:
                # Calculate days remaining
                trial_end = user["trial_end"]
                if trial_end.tzinfo is None:
                    trial_end = trial_end.replace(tzinfo=UTC)

                days_remaining = (trial_end - now).days

                # Send appropriate warning based on days remaining
                should_send = False
                if days_remaining == 7:
                    should_send = True
                    stat_key = "emails_sent_7d"
                elif days_remaining == 3:
                    should_send = True
                    stat_key = "emails_sent_3d"
                elif days_remaining == 1:
                    should_send = True
                    stat_key = "emails_sent_1d"

                if should_send:
                    # Check if we've already sent this warning (using database flag)
                    already_sent = await _check_trial_warning_sent(user["id"], days_remaining)

                    if not already_sent:
                        # Send warning email
                        success = await email_service.send_trial_warning(
                            user_email=user["email"],
                            user_name=user["name"] or "there",
                            days_remaining=days_remaining,
                            tier=user["tier"] or "trial",
                        )

                        if success:
                            # Mark as sent to avoid duplicate emails
                            await _mark_trial_warning_sent(user["id"], days_remaining)
                            stats[stat_key] += 1
                            logger.info("✅ Sent %sd warning to %s", days_remaining, user["email"])
                        else:
                            stats["errors"] += 1
                            logger.warning("⚠️ Failed to send %sd warning to %s", days_remaining, user["email"])
                    else:
                        logger.debug("⏭️ Already sent %sd warning to %s", days_remaining, user["email"])

            except Exception as e:
                stats["errors"] += 1
                logger.error("❌ Error processing trial for user %s: %s", user.get("id"), e)

        logger.info(
            f"✅ Trial monitoring complete: "
            f"7d={stats['emails_sent_7d']}, 3d={stats['emails_sent_3d']}, "
            f"1d={stats['emails_sent_1d']}, errors={stats['errors']}"
        )

        return stats

    except Exception as e:
        logger.error("❌ Trial monitoring failed: %s", e)
        stats["errors"] += 1
        return stats


async def _check_trial_warning_sent(user_id: str, days_remaining: int) -> bool:
    """
    Check if trial warning has already been sent.

    Args:
        user_id: User identifier
        days_remaining: Days until trial ends

    Returns:
        True if warning already sent, False otherwise
    """
    try:
        # Check trial_warnings table (create if doesn't exist)
        result = await Database.fetchval(
            """
            SELECT COUNT(*) FROM trial_warnings
            WHERE user_id = $1 AND days_remaining = $2
            AND sent_at > NOW() - INTERVAL '48 hours'
            """,
            user_id,
            days_remaining,
        )
        return result > 0
    except Exception as e:
        # Table might not exist - assume not sent
        logger.debug("Trial warnings table query failed (expected on first run): %s", e)
        return False


async def _mark_trial_warning_sent(user_id: str, days_remaining: int):
    """
    Mark trial warning as sent.

    Args:
        user_id: User identifier
        days_remaining: Days until trial ends
    """
    try:
        await Database.execute(
            """
            INSERT INTO trial_warnings (user_id, days_remaining, sent_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (user_id, days_remaining)
            DO UPDATE SET sent_at = NOW()
            """,
            user_id,
            days_remaining,
        )
    except Exception as e:
        # Table might not exist - log warning
        logger.warning("Failed to mark trial warning as sent (table might not exist): %s", e)


# ============================================================================
# DATABASE MIGRATION (Create trial_warnings table)
# ============================================================================


async def ensure_trial_warnings_table():
    """Create trial_warnings table if it doesn't exist"""
    try:
        await Database.execute(
            """
            CREATE TABLE IF NOT EXISTS trial_warnings (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                days_remaining INTEGER NOT NULL,
                sent_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE(user_id, days_remaining)
            )
            """
        )

        # Create index for faster lookups
        await Database.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_trial_warnings_user_days
            ON trial_warnings(user_id, days_remaining)
            """
        )

        logger.info("✅ Trial warnings table ready")
    except Exception as e:
        logger.error("❌ Failed to create trial_warnings table: %s", e)


# ============================================================================
# SCHEDULER INTEGRATION
# ============================================================================


async def schedule_trial_monitoring():
    """
    Set up APScheduler job for daily trial monitoring.
    Call this from FastAPI startup event.
    """
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger

        # Ensure table exists
        await ensure_trial_warnings_table()

        scheduler = AsyncIOScheduler()

        # Run daily at 9:00 AM UTC
        scheduler.add_job(
            check_trial_endings,
            CronTrigger(hour=9, minute=0),
            id="trial_monitoring",
            replace_existing=True,
            name="Trial Ending Monitoring",
        )

        scheduler.start()
        logger.info("✅ Trial monitoring scheduler started (daily at 9:00 AM UTC)")

        return scheduler

    except ImportError:
        logger.warning(
            "⚠️ APScheduler not installed. Run: pip install apscheduler\n" "Trial monitoring will not run automatically."
        )
        return None
    except Exception as e:
        logger.error("❌ Failed to start trial monitoring scheduler: %s", e)
        return None


# ============================================================================
# MANUAL TRIGGER (for testing)
# ============================================================================


async def run_trial_monitoring_now():
    """
    Manually trigger trial monitoring (for testing/debugging).

    Usage:
        from apps.backend.services.trial_monitoring import run_trial_monitoring_now
        await run_trial_monitoring_now()
    """
    logger.info("🔧 Manual trial monitoring triggered")
    await ensure_trial_warnings_table()
    return await check_trial_endings()

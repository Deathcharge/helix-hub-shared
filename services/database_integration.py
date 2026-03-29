"""
🌀 Helix Collective - Database Integration Layer
Connects new SaaS services to PostgreSQL database
"""

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# Import existing database connection
try:
    from apps.backend.core.unified_auth import Database

    HAS_DATABASE = True
except ImportError:
    Database = None
    HAS_DATABASE = False
    logger.warning("Database not available - using mock data")

# ============================================================================
# BILLING & SUBSCRIPTION QUERIES
# ============================================================================


class BillingDatabase:
    """Database operations for billing service"""

    @staticmethod
    async def get_user_billing_info(user_id: str) -> dict[str, Any] | None:
        """Get user's billing information"""
        if not HAS_DATABASE:
            return None

        try:
            row = await Database.fetchrow(
                """
                SELECT
                    u.email,
                    u.created_at,
                    s.stripe_subscription_id,
                    s.billing_cycle,
                    s.cancel_at_period_end
                FROM users u
                LEFT JOIN subscriptions s ON u.id = s.user_id AND s.status = 'active'
                WHERE u.id = $1
            """,
                user_id,
            )
            if row:
                return dict(row)
            return None
        except (ConnectionError, TimeoutError) as e:
            logger.debug("Database connection error fetching billing info: %s", e)
            return None
        except Exception as e:
            logger.error("Error fetching billing info: %s", e)
            return None

    @staticmethod
    async def get_user_usage(user_id: str, period_days: int = 30) -> dict[str, int]:
        """Get user's resource usage for period"""
        if not HAS_DATABASE:
            return {}

        try:
            rows = await Database.fetch(
                """
                SELECT resource_type, SUM(quantity)::int as total
                FROM usage_records
                WHERE user_id = $1
                AND recorded_at > NOW() - INTERVAL '$2 days'
                GROUP BY resource_type
            """,
                user_id,
                period_days,
            )

            return {row["resource_type"]: row["total"] for row in rows}
        except (ConnectionError, TimeoutError) as e:
            logger.debug("Database connection error fetching usage: %s", e)
            return {}
        except Exception as e:
            logger.error("Error fetching usage: %s", e)
            return {}

    @staticmethod
    async def track_usage(
        user_id: str,
        resource_type: str,
        quantity: int = 1,
        metadata: dict[str, Any] | None = None,
    ):
        """Record usage event"""
        if not HAS_DATABASE:
            return

        try:
            await Database.execute(
                """
                INSERT INTO usage_records (user_id, resource_type, quantity, metadata)
                VALUES ($1, $2, $3, $4)
            """,
                user_id,
                resource_type,
                quantity,
                metadata or {},
            )
        except Exception as e:
            logger.error("Error tracking usage: %s", e)

    @staticmethod
    async def create_subscription(
        user_id: str,
        stripe_subscription_id: str,
        stripe_customer_id: str,
        tier: str,
        billing_cycle: str,
        current_period_start: datetime,
        current_period_end: datetime,
    ):
        """Create subscription record"""
        if not HAS_DATABASE:
            return

        try:
            await Database.execute(
                """
                INSERT INTO subscriptions (
                    user_id, stripe_subscription_id, stripe_customer_id,
                    tier, billing_cycle, status,
                    current_period_start, current_period_end
                )
                VALUES ($1, $2, $3, $4, $5, 'active', $6, $7)
                ON CONFLICT (stripe_subscription_id) DO UPDATE SET
                    status = 'active',
                    tier = $4,
                    billing_cycle = $5,
                    current_period_start = $6,
                    current_period_end = $7,
                    updated_at = CURRENT_TIMESTAMP
            """,
                user_id,
                stripe_subscription_id,
                stripe_customer_id,
                tier,
                billing_cycle,
                current_period_start,
                current_period_end,
            )

            # Update user record
            await Database.execute(
                """
                UPDATE users SET
                    subscription_tier = $1,
                    subscription_status = 'active',
                    stripe_customer_id = $2,
                    stripe_subscription_id = $3,
                    current_period_start = $4,
                    current_period_end = $5
                WHERE id = $6
            """,
                tier,
                stripe_customer_id,
                stripe_subscription_id,
                current_period_start,
                current_period_end,
                user_id,
            )
        except Exception as e:
            logger.error("Error creating subscription: %s", e)

    @staticmethod
    async def record_payment(
        user_id: str,
        stripe_payment_id: str,
        stripe_invoice_id: str,
        amount_usd: float,
        status: str,
        description: str = "",
    ):
        """Record payment"""
        if not HAS_DATABASE:
            return

        try:
            await Database.execute(
                """
                INSERT INTO payments (
                    user_id, stripe_payment_id, stripe_invoice_id,
                    amount_usd, status, description
                )
                VALUES ($1, $2, $3, $4, $5, $6)
            """,
                user_id,
                stripe_payment_id,
                stripe_invoice_id,
                amount_usd,
                status,
                description,
            )
        except Exception as e:
            logger.error("Error recording payment: %s", e)


# ============================================================================
# MONITORING & METRICS QUERIES
# ============================================================================


class MonitoringDatabase:
    """Database operations for monitoring service"""

    @staticmethod
    async def store_metric(
        metric_name: str,
        metric_value: float,
        unit: str = "",
        tags: dict[str, str] | None = None,
    ):
        """Store system metric"""
        if not HAS_DATABASE:
            return

        try:
            await Database.execute(
                """
                INSERT INTO system_metrics (metric_name, metric_value, unit, tags)
                VALUES ($1, $2, $3, $4)
            """,
                metric_name,
                metric_value,
                unit,
                tags or {},
            )
        except Exception as e:
            logger.error("Error storing metric: %s", e)

    @staticmethod
    async def get_metrics(metric_name: str, limit: int = 100, since: datetime | None = None) -> list[dict[str, Any]]:
        """Get historical metrics"""
        if not HAS_DATABASE:
            return []

        try:
            query = """
                SELECT metric_name, metric_value, unit, tags, recorded_at
                FROM system_metrics
                WHERE metric_name = $1
            """
            params = [metric_name]

            if since:
                query += " AND recorded_at >= $2"
                params.append(since)

            query += " ORDER BY recorded_at DESC LIMIT $%d" % (len(params) + 1)
            params.append(limit)

            rows = await Database.fetch(query, *params)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error("Error fetching metrics: %s", e)
            return []

    @staticmethod
    async def create_alert(alert_id: str, severity: str, title: str, message: str, service: str):
        """Create system alert"""
        if not HAS_DATABASE:
            return

        try:
            await Database.execute(
                """
                INSERT INTO system_alerts (alert_id, severity, title, message, service)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (alert_id) DO NOTHING
            """,
                alert_id,
                severity,
                title,
                message,
                service,
            )
        except Exception as e:
            logger.error("Error creating alert: %s", e)

    @staticmethod
    async def get_alerts(severity: str | None = None, resolved: bool | None = None) -> list[dict[str, Any]]:
        """Get system alerts"""
        if not HAS_DATABASE:
            return []

        try:
            query = """
                SELECT alert_id, severity, title, message, service, resolved, created_at, resolved_at
                FROM system_alerts
                WHERE 1=1
            """
            params = []

            if severity:
                query += " AND severity = $%d" % (len(params) + 1)
                params.append(severity)

            if resolved is not None:
                query += " AND resolved = $%d" % (len(params) + 1)
                params.append(resolved)

            query += " ORDER BY created_at DESC LIMIT 100"

            rows = await Database.fetch(query, *params)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error("Error fetching alerts: %s", e)
            return []

    @staticmethod
    async def store_health_check(
        service_name: str,
        status: str,
        response_time_ms: float,
        details: dict[str, Any] | None = None,
    ):
        """Store health check result"""
        if not HAS_DATABASE:
            return

        try:
            await Database.execute(
                """
                INSERT INTO health_checks (service_name, status, response_time_ms, details)
                VALUES ($1, $2, $3, $4)
            """,
                service_name,
                status,
                response_time_ms,
                details or {},
            )
        except Exception as e:
            logger.error("Error storing health check: %s", e)


# ============================================================================
# ADMIN & ANALYTICS QUERIES
# ============================================================================


class AdminDatabase:
    """Database operations for admin dashboard"""

    @staticmethod
    async def get_user_stats() -> dict[str, Any]:
        """Get user statistics"""
        if not HAS_DATABASE:
            return {
                "total_users": 0,
                "active_users": 0,
                "new_users_today": 0,
                "new_users_week": 0,
                "users_by_tier": {},
            }

        try:
            stats = await Database.fetchrow(
                """
                SELECT
                    COUNT(*) as total_users,
                    COUNT(*) FILTER (WHERE last_active > NOW() - INTERVAL '30 days') as active_users,
                    COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE) as new_users_today,
                    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '7 days') as new_users_week
                FROM users
            """
            )

            tiers = await Database.fetch(
                """
                SELECT subscription_tier, COUNT(*) as count
                FROM users
                GROUP BY subscription_tier
            """
            )

            return {
                "total_users": stats["total_users"],
                "active_users": stats["active_users"],
                "new_users_today": stats["new_users_today"],
                "new_users_week": stats["new_users_week"],
                "users_by_tier": {row["subscription_tier"]: row["count"] for row in tiers},
            }
        except Exception as e:
            logger.error("Error fetching user stats: %s", e)
            return {}

    @staticmethod
    async def get_revenue_metrics() -> dict[str, Any]:
        """Get revenue metrics"""
        if not HAS_DATABASE:
            return {
                "mrr": 0,
                "arr": 0,
                "total_revenue_month": 0,
                "total_revenue_year": 0,
            }

        try:
            revenue = await Database.fetchrow(
                """
                SELECT
                    SUM(amount_usd) FILTER (WHERE created_at > DATE_TRUNC('month', CURRENT_DATE)) as revenue_month,
                    SUM(amount_usd) FILTER (WHERE created_at > DATE_TRUNC('year', CURRENT_DATE)) as revenue_year
                FROM payments
                WHERE status = 'succeeded'
            """
            )

            return {
                "mrr": revenue["revenue_month"] or 0,
                "arr": (revenue["revenue_month"] or 0) * 12,
                "total_revenue_month": revenue["revenue_month"] or 0,
                "total_revenue_year": revenue["revenue_year"] or 0,
            }
        except Exception as e:
            logger.error("Error fetching revenue metrics: %s", e)
            return {}

    @staticmethod
    async def list_users(
        page: int = 1,
        page_size: int = 50,
        tier: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """List users with pagination"""
        if not HAS_DATABASE:
            return {"users": [], "total": 0, "page": page, "page_size": page_size}

        try:
            offset = (page - 1) * page_size

            query = "SELECT * FROM v_user_subscription_summary WHERE 1=1"
            params = []

            if tier:
                query += " AND subscription_tier = $%d" % (len(params) + 1)
                params.append(tier)

            if status:
                query += " AND subscription_status = $%d" % (len(params) + 1)
                params.append(status)

            query += " ORDER BY user_id DESC LIMIT $%d OFFSET $%d" % (
                len(params) + 1,
                len(params) + 2,
            )
            params.extend([page_size, offset])

            rows = await Database.fetch(query, *params)

            # Get total count
            count_query = "SELECT COUNT(*) FROM users WHERE 1=1"
            count_params = []
            if tier:
                count_query += " AND subscription_tier = $1"
                count_params.append(tier)

            total = await Database.fetchval(count_query, *count_params)

            return {
                "users": [dict(row) for row in rows],
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size,
            }
        except Exception as e:
            logger.error("Error listing users: %s", e)
            return {"users": [], "total": 0, "page": page, "page_size": page_size}

    @staticmethod
    async def suspend_user(user_id: str, reason: str):
        """Suspend user account"""
        if not HAS_DATABASE:
            return

        try:
            await Database.execute(
                """
                UPDATE users SET
                    subscription_status = 'suspended',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
            """,
                user_id,
            )

            # Log action
            await Database.execute(
                """
                INSERT INTO audit_log (action, target_user_id, details)
                VALUES ('user_suspended', $1, $2)
            """,
                user_id,
                {"reason": reason},
            )
        except Exception as e:
            logger.error("Error suspending user: %s", e)

    @staticmethod
    async def activate_user(user_id: str):
        """Activate suspended user"""
        if not HAS_DATABASE:
            return

        try:
            await Database.execute(
                """
                UPDATE users SET
                    subscription_status = 'active',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
            """,
                user_id,
            )

            # Log action
            await Database.execute(
                """
                INSERT INTO audit_log (action, target_user_id)
                VALUES ('user_activated', $1)
            """,
                user_id,
            )
        except Exception as e:
            logger.error("Error activating user: %s", e)

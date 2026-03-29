"""
🌀 Helix Collective v17.1 - Consolidated Usage Tracking Service
===============================================================

Unified usage tracking, quota enforcement, and rate limiting with Redis caching.
Consolidates functionality from:
- middleware/usage_tracking.py (request tracking)
- services/billing_service.py (UsageTracker)
- saas_stripe.py (webhook usage tracking)

Features:
- Real-time usage tracking with Redis caching
- Multi-level limits: daily, monthly, concurrent
- Soft limits (80% warning) and grace periods (110% hard limit)
- WebSocket notifications for usage alerts
- Automatic tier limit enforcement
- Usage analytics and reporting

Author: Claude (Helix Architect)
Date: 2026-02-03
Version: 17.1.0
"""

import logging
import os
import time
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as redis

from apps.backend.config.unified_pricing import PlatformTier, get_tier_config, get_tier_limits
from apps.backend.core.redis_client import get_redis

logger = logging.getLogger(__name__)


def _is_production_env() -> bool:
    """Return True when running in production-like environments."""
    env = (os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("ENVIRONMENT") or "").lower()
    return env == "production"


def _fail_open_enabled() -> bool:
    """
    Decide whether quota/rate-limit checks should fail open.

    Defaults:
    - Production: fail closed
    - Non-production: fail open

    Override with USAGE_ENFORCEMENT_MODE:
    - strict: fail closed
    - permissive: fail open
    """
    mode = os.getenv("USAGE_ENFORCEMENT_MODE", "").strip().lower()
    if mode == "strict":
        return False
    if mode == "permissive":
        return True
    return not _is_production_env()


# Admin bypass integration
try:
    from apps.backend.security.admin_bypass import is_admin_user_id

    ADMIN_BYPASS_AVAILABLE = True
except ImportError:
    ADMIN_BYPASS_AVAILABLE = False
    logger.warning("Admin bypass not available - all users subject to limits")


# ============================================================================
# USAGE TRACKING SERVICE
# ============================================================================


class UsageService:
    """Consolidated usage tracking with Redis caching"""

    def __init__(self) -> None:
        self.redis_client: redis.Redis | None = None
        self._cache_ttl = 300  # 5 minutes cache TTL
        self._grace_period_percentage = 10  # 10% overage allowed
        self._warning_percentage = 80  # Warn at 80% usage

    async def initialize(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = await get_redis()
            if self.redis_client:
                logger.info("✅ Usage Service initialized with Redis caching")
            else:
                logger.warning("⚠️ Redis unavailable - usage tracking will use database only")
        except (ConnectionError, TimeoutError) as e:
            logger.warning("⚠️ Redis unavailable during Usage Service init: %s", e)
            self.redis_client = None
        except Exception as e:
            logger.error("❌ Failed to initialize Usage Service: %s", e)
            self.redis_client = None

    # ========================================================================
    # USAGE TRACKING
    # ========================================================================

    async def track_usage(
        self,
        user_id: str,
        resource_type: str,
        quantity: int = 1,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Track resource usage and check limits.

        Args:
            user_id: User identifier
            resource_type: Type of resource (api_calls, agents_created, storage_gb, etc.)
            quantity: Amount used
            metadata: Additional context (endpoint, model, cost, etc.)

        Returns:
            Dict with usage info and limit status
        """
        try:
            # Admin bypass - unlimited usage
            if ADMIN_BYPASS_AVAILABLE and is_admin_user_id(user_id):
                return {
                    "success": True,
                    "current_usage": 0,
                    "limit": -1,  # Unlimited
                    "percentage_used": 0,
                    "is_warning": False,
                    "is_exceeded": False,
                    "tier": "enterprise",
                    "is_admin": True,
                }

            # Get current usage from Redis cache
            current_usage = await self._get_cached_usage(user_id, resource_type)
            new_usage = current_usage + quantity

            # Update cache
            await self._update_cached_usage(user_id, resource_type, new_usage)

            # Get user tier and limits
            tier = await self._get_user_tier(user_id)
            limits = get_tier_limits(tier)
            limit = limits.get(resource_type, 0)

            # Calculate percentages
            percentage_used = (new_usage / limit * 100) if limit > 0 and limit != -1 else 0
            is_warning = percentage_used >= self._warning_percentage
            is_exceeded = percentage_used >= (100 + self._grace_period_percentage)

            # Store in database for analytics (async, non-blocking)
            await self._persist_usage(user_id, resource_type, quantity, metadata)

            # Send usage alerts if needed
            if is_warning and not is_exceeded:
                await self._send_usage_alert(user_id, resource_type, percentage_used, "warning")
            elif is_exceeded:
                await self._send_usage_alert(user_id, resource_type, percentage_used, "exceeded")

            return {
                "success": True,
                "current_usage": new_usage,
                "limit": limit,
                "percentage_used": percentage_used,
                "is_warning": is_warning,
                "is_exceeded": is_exceeded,
                "tier": tier.value if hasattr(tier, "value") else str(tier),
            }

        except Exception as e:
            logger.error("Error tracking usage for user %s: %s", user_id, e)
            return {
                "success": False,
                "error": "Failed to track usage",
                "current_usage": 0,
                "limit": 0,
                "percentage_used": 0,
            }

    async def track_api_call(
        self,
        user_id: str,
        endpoint: str,
        response_time_ms: int,
        status_code: int,
        tokens: int = 0,
        cost_usd: float = 0.0,
        model: str | None = None,
    ) -> dict[str, Any]:
        """
        Track API call with detailed metrics.

        Args:
            user_id: User identifier
            endpoint: API endpoint path
            response_time_ms: Response time in milliseconds
            status_code: HTTP status code
            tokens: Tokens used (for LLM calls)
            cost_usd: Cost in USD
            model: Model name (if applicable)

        Returns:
            Usage tracking result
        """
        metadata = {
            "endpoint": endpoint,
            "response_time_ms": response_time_ms,
            "status_code": status_code,
            "tokens": tokens,
            "cost_usd": cost_usd,
            "model": model,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        return await self.track_usage(user_id, "api_calls_per_day", 1, metadata)

    # ========================================================================
    # QUOTA CHECKING & ENFORCEMENT
    # ========================================================================

    async def check_quota(
        self, user_id: str, resource_type: str, quantity: int = 1
    ) -> tuple[bool, str | None, dict[str, Any]]:
        """
        Check if user can use a resource without exceeding limits.

        Args:
            user_id: User identifier
            resource_type: Type of resource
            quantity: Amount to check

        Returns:
            (allowed, reason, limits_info) tuple
        """
        try:
            # Admin bypass - always allowed
            if ADMIN_BYPASS_AVAILABLE and is_admin_user_id(user_id):
                return (True, None, {"is_admin": True, "limit": -1})

            # Get current usage
            current_usage = await self._get_cached_usage(user_id, resource_type)

            # Get user tier and limits
            tier = await self._get_user_tier(user_id)
            limits = get_tier_limits(tier)
            limit = limits.get(resource_type, -1)  # -1 = unlimited for unknown keys

            if limit == 0:
                # Explicit zero means the feature is not available for this tier
                return (
                    False,
                    f"{resource_type} is not available on your plan. Upgrade to access it.",
                    {"current": current_usage, "limit": 0, "tier": str(tier)},
                )

            # Unlimited (-1) means always allowed
            if limit == -1:
                return True, None, {"current": current_usage, "limit": "unlimited"}

            # Check if would exceed hard limit (with grace period)
            grace_limit = int(limit * (1 + self._grace_period_percentage / 100))
            would_exceed = (current_usage + quantity) > grace_limit

            if would_exceed:
                return (
                    False,
                    f"{resource_type} limit exceeded. Upgrade your plan for higher limits.",
                    {
                        "current": current_usage,
                        "limit": limit,
                        "grace_limit": grace_limit,
                        "requested": quantity,
                        "tier": tier.value if hasattr(tier, "value") else str(tier),
                    },
                )

            # Within limits
            return (
                True,
                None,
                {
                    "current": current_usage,
                    "limit": limit,
                    "remaining": limit - current_usage,
                    "percentage": (current_usage / limit * 100) if limit > 0 else 0,
                },
            )

        except Exception as e:
            logger.error("Error checking quota for user %s: %s", user_id, e)
            if _fail_open_enabled():
                # Fail open in non-production/dev to preserve local velocity.
                return True, None, {"error": "Quota check failed", "enforcement_mode": "permissive"}

            # Fail closed in production to prevent unlimited usage abuse.
            return (
                False,
                "Quota service unavailable. Please retry shortly.",
                {"error": "quota_check_failed", "enforcement_mode": "strict"},
            )

    async def enforce_rate_limit(
        self, user_id: str, endpoint: str, window_seconds: int = 60
    ) -> tuple[bool, dict[str, Any] | None]:
        """
        Enforce rate limiting using sliding window.

        Args:
            user_id: User identifier
            endpoint: API endpoint
            window_seconds: Time window in seconds

        Returns:
            (allowed, rate_limit_info) tuple
        """
        if not self.redis_client:
            if _fail_open_enabled():
                return True, None  # Fail open in non-production/dev
            return (
                False,
                {
                    "error": "rate_limit_backend_unavailable",
                    "retry_after": 30,
                    "enforcement_mode": "strict",
                },
            )

        try:
            # Get user tier and rate limits
            tier = await self._get_user_tier(user_id)
            get_tier_config(tier)

            # Map tier to requests per minute - derived from monthly limits
            # Free: 1k/mo ≈ 10/min burst, Hobby: 10k/mo ≈ 30/min,
            # Starter: 50k/mo ≈ 60/min, Pro: 200k/mo ≈ 120/min, Enterprise: unlimited ≈ 600/min
            tier_rate_limits = {
                PlatformTier.FREE: 10,
                PlatformTier.HOBBY: 30,
                PlatformTier.STARTER: 60,
                PlatformTier.PRO: 120,
                PlatformTier.ENTERPRISE: 600,
            }

            rate_limit = tier_rate_limits.get(tier, 10)
            key = f"rate_limit:{user_id}:{endpoint}"

            # Use Redis sliding window
            now = time.time()
            window_start = now - window_seconds

            # Remove old entries
            await self.redis_client.zremrangebyscore(key, 0, window_start)

            # Count requests in window
            count = await self.redis_client.zcard(key)

            if count >= rate_limit:
                # Get time until reset
                oldest = await self.redis_client.zrange(key, 0, 0, withscores=True)
                reset_time = int(oldest[0][1] + window_seconds) if oldest else int(now)

                return (
                    False,
                    {
                        "limit": rate_limit,
                        "remaining": 0,
                        "reset": reset_time,
                        "retry_after": reset_time - int(now),
                    },
                )

            # Add current request
            await self.redis_client.zadd(key, {str(now): now})
            await self.redis_client.expire(key, window_seconds)

            return (
                True,
                {
                    "limit": rate_limit,
                    "remaining": rate_limit - count - 1,
                    "reset": int(now + window_seconds),
                },
            )

        except Exception as e:
            logger.error("Rate limit check failed: %s", e)
            if _fail_open_enabled():
                return True, None  # Fail open in non-production/dev

            return (
                False,
                {
                    "error": "rate_limit_check_failed",
                    "retry_after": 30,
                    "enforcement_mode": "strict",
                },
            )

    # ========================================================================
    # USAGE ANALYTICS
    # ========================================================================

    async def get_usage_summary(self, user_id: str, period: str = "current") -> dict[str, Any]:
        """
        Get comprehensive usage summary for user.

        Args:
            user_id: User identifier
            period: "current", "last_30_days", "last_month"

        Returns:
            Usage summary with all tracked resources
        """
        try:
            tier = await self._get_user_tier(user_id)
            limits = get_tier_limits(tier)

            # Get usage for all tracked resources
            resources = [
                "api_calls_per_day",
                "api_calls_per_month",
                "agents_concurrent",
                "cycles_per_month",
                "workflows_per_month",
                "storage_gb",
            ]

            usage_data = {}
            for resource in resources:
                current = await self._get_cached_usage(user_id, resource)
                limit = limits.get(resource, 0)

                usage_data[resource] = {
                    "current": current,
                    "limit": limit if limit != -1 else "unlimited",
                    "percentage": (current / limit * 100) if limit > 0 else 0,
                    "remaining": max(0, limit - current) if limit > 0 else None,
                }

            return {
                "user_id": user_id,
                "tier": tier.value if hasattr(tier, "value") else str(tier),
                "period": period,
                "usage": usage_data,
                "generated_at": datetime.now(UTC).isoformat(),
            }

        except Exception as e:
            logger.error("Error generating usage summary: %s", e)
            return {"error": "Failed to generate usage summary"}

    async def get_top_consumers(self, resource_type: str, limit: int = 10) -> list[dict[str, Any]]:
        """
        Get top resource consumers (admin analytics).

        Args:
            resource_type: Resource type to analyze
            limit: Number of results

        Returns:
            List of top consumers with usage stats
        """
        # Query database for top consumers by usage
        try:
            from datetime import datetime, timedelta

            from sqlalchemy import func, select

            from ..db_models import UsageLog, get_session

            with get_session() as session:
                # Get top users by request count in last 30 days
                cutoff = datetime.now(UTC) - timedelta(days=30)
                stmt = (
                    select(
                        UsageLog.user_id,
                        func.count(UsageLog.id).label("request_count"),
                    )
                    .where(UsageLog.timestamp >= cutoff)
                    .group_by(UsageLog.user_id)
                    .order_by(func.count(UsageLog.id).desc())
                    .limit(limit)
                )
                results = session.execute(stmt).all()
                return [
                    {
                        "user_id": row[0],
                        "resource_type": resource_type,
                        "usage_count": row[1],
                    }
                    for row in results
                ]
        except Exception as e:
            logger.warning("Failed to query top consumers: %s", e)
            return []

    # ========================================================================
    # CACHE MANAGEMENT
    # ========================================================================

    async def _get_cached_usage(self, user_id: str, resource_type: str) -> int:
        """Get usage from Redis cache or database"""
        if not self.redis_client:
            # Fallback to database
            return await self._get_db_usage(user_id, resource_type)

        try:
            # Get from cache
            cache_key = f"usage:{user_id}:{resource_type}"
            cached = await self.redis_client.get(cache_key)

            if cached is not None:
                return int(cached)

            # Cache miss - get from database and cache
            db_usage = await self._get_db_usage(user_id, resource_type)
            await self.redis_client.setex(cache_key, self._cache_ttl, db_usage)
            return db_usage

        except Exception as e:
            logger.error("Cache read error: %s", e)
            return await self._get_db_usage(user_id, resource_type)

    async def _update_cached_usage(self, user_id: str, resource_type: str, new_value: int):
        """Update usage in Redis cache"""
        if not self.redis_client:
            return

        try:
            cache_key = f"usage:{user_id}:{resource_type}"
            await self.redis_client.setex(cache_key, self._cache_ttl, new_value)
        except Exception as e:
            logger.error("Cache write error: %s", e)

    async def reset_daily_usage(self, user_id: str):
        """Reset daily usage counters (called by scheduled task)"""
        daily_resources = ["api_calls_per_day"]

        for resource in daily_resources:
            await self._update_cached_usage(user_id, resource, 0)

    async def reset_monthly_usage(self, user_id: str):
        """Reset monthly usage counters (called on subscription renewal)"""
        monthly_resources = [
            "api_calls_per_month",
            "copilot_messages_per_month",
            "cycles_per_month",
            "workflows_per_month",
        ]

        for resource in monthly_resources:
            await self._update_cached_usage(user_id, resource, 0)

    # ========================================================================
    # DATABASE OPERATIONS
    # ========================================================================

    async def _get_db_usage(self, user_id: str, resource_type: str) -> int:
        """Get usage from database"""
        try:
            from apps.backend.core.unified_auth import Database

            # Query usage_tracking table for current period
            result = await Database.fetchrow(
                """
                SELECT COALESCE(SUM(quantity), 0) as total
                FROM usage_tracking
                WHERE user_id = $1
                  AND resource_type = $2
                  AND period_end > CURRENT_TIMESTAMP
                """,
                user_id,
                resource_type,
            )

            return int(result["total"]) if result else 0

        except Exception as e:
            logger.error(
                "Failed to get DB usage for user %s, resource %s: %s",
                user_id,
                resource_type,
                str(e),
            )
            return 0

    async def _persist_usage(
        self,
        user_id: str,
        resource_type: str,
        quantity: int,
        metadata: dict[str, Any] | None = None,
    ):
        """Persist usage to database for analytics"""
        try:
            # Import here to avoid circular imports
            from apps.backend.utils.database_helpers import get_database_helpers

            db_helpers = await get_database_helpers()
            if db_helpers:
                await db_helpers.record_usage(
                    user_id=user_id,
                    resource_type=resource_type,
                    quantity=quantity,
                    metadata=metadata or {},
                )
        except Exception as e:
            logger.error("Failed to persist usage: %s", e)

    async def _get_user_tier(self, user_id: str) -> PlatformTier:
        """Get user's subscription tier"""
        try:
            # Check cache first
            if self.redis_client:
                tier_cache_key = f"user_tier:{user_id}"
                cached_tier = await self.redis_client.get(tier_cache_key)
                if cached_tier:
                    if isinstance(cached_tier, bytes):
                        cached_tier = cached_tier.decode("utf-8")
                    return PlatformTier(cached_tier)

            # Get from database
            from apps.backend.state import get_live_state

            state = get_live_state()
            if hasattr(state, "db") and state.db:
                result = await state.db.fetchrow("SELECT subscription_tier FROM users WHERE id = $1", user_id)
                if result:
                    tier = PlatformTier(result["subscription_tier"] or "free")

                    # Cache for 5 minutes
                    if self.redis_client:
                        await self.redis_client.setex(tier_cache_key, 300, tier.value)

                    return tier

            return PlatformTier.FREE

        except Exception as e:
            logger.error("Error getting user tier: %s", e)
            return PlatformTier.FREE

    # ========================================================================
    # NOTIFICATIONS
    # ========================================================================

    async def _send_usage_alert(self, user_id: str, resource_type: str, percentage: float, alert_type: str):
        """Send usage alert via WebSocket and email"""
        try:
            # Send WebSocket notification (real-time)
            from apps.backend.websocket_manager import manager as websocket_manager

            message = {
                "type": "usage_alert",
                "alert_type": alert_type,  # "warning" or "exceeded"
                "resource": resource_type,
                "percentage": round(percentage, 2),
                "timestamp": datetime.now(UTC).isoformat(),
            }

            if alert_type == "warning":
                message["message"] = (
                    f"You've used {percentage:.0f}% of your {resource_type.replace('_', ' ')} limit. "
                    "Consider upgrading your plan to avoid interruptions."
                )
            else:
                message["message"] = (
                    f"You've exceeded your {resource_type.replace('_', ' ')} limit. "
                    "Upgrade now to continue using this feature."
                )

            await websocket_manager.send_personal_message(user_id, message)

            # Send email notification for critical alerts (100% exceeded)
            if percentage >= 100:
                try:
                    from apps.backend.core.unified_auth import Database
                    from apps.backend.services.subscription_emails import get_subscription_email_service

                    # Get user details
                    user_info = await Database.fetchrow("SELECT email, name, tier FROM users WHERE id = $1", user_id)

                    if user_info:
                        # Get current and limit values from cached data
                        cached_usage = await self._get_cached_usage(user_id, resource_type)
                        current = cached_usage.get("current", 0)

                        tier = user_info["tier"]
                        limits = get_tier_limits(tier)
                        limit = limits.get(resource_type, 0)

                        # Send email warning
                        email_service = get_subscription_email_service()
                        await email_service.send_usage_warning(
                            user_email=user_info["email"],
                            user_name=user_info["name"] or "there",
                            resource_type=resource_type,
                            percentage=percentage,
                            current=current,
                            limit=limit,
                            tier=tier,
                        )
                        logger.info(
                            f"📧 Sent usage warning email to {user_info['email']} "
                            f"for {resource_type} ({percentage:.0f}%)"
                        )
                except Exception as e:
                    logger.error("Failed to send usage warning email: %s", e)

        except Exception as e:
            logger.error("Failed to send usage alert: %s", e)


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_usage_service: UsageService | None = None


async def get_usage_service() -> UsageService:
    """Get or create usage service singleton"""
    global _usage_service
    if _usage_service is None:
        _usage_service = UsageService()
        await _usage_service.initialize()
    return _usage_service


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================


async def track_usage(
    user_id: str,
    resource_type: str,
    quantity: int = 1,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Track resource usage - convenience function"""
    service = await get_usage_service()
    return await service.track_usage(user_id, resource_type, quantity, metadata)


async def check_quota(user_id: str, resource_type: str, quantity: int = 1) -> tuple[bool, str | None, dict[str, Any]]:
    """Check quota - convenience function"""
    service = await get_usage_service()
    return await service.check_quota(user_id, resource_type, quantity)


async def enforce_rate_limit(user_id: str, endpoint: str) -> tuple[bool, dict[str, Any] | None]:
    """Enforce rate limit - convenience function"""
    service = await get_usage_service()
    return await service.enforce_rate_limit(user_id, endpoint)

"""
🌀 Helix Collective - Admin Dashboard Backend
Comprehensive admin interface for platform management

NOTE: LEGACY — superseded by apps/backend/routes/admin_dashboard.py which has
real DB queries, admin auth guards, and is already registered in router_registry.
This file is retained for reference but is NOT wired to the app.
"""

import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select

from ..db_models import Subscription, UsageLog, User, get_session
from ..utils.database_helpers import get_database_helpers

logger = logging.getLogger(__name__)

# ============================================================================
# MODELS
# ============================================================================


class UserStats(BaseModel):
    """User statistics"""

    total_users: int
    active_users: int
    new_users_today: int
    new_users_week: int
    users_by_tier: dict[str, int]


class SystemHealth(BaseModel):
    """System health metrics"""

    status: str  # healthy, degraded, down
    uptime_seconds: int
    services: dict[str, dict[str, Any]]
    database_status: str
    redis_status: str
    api_response_time_ms: float


class RevenueMetrics(BaseModel):
    """Revenue and billing metrics"""

    mrr: float  # Monthly Recurring Revenue
    arr: float  # Annual Recurring Revenue
    total_revenue_month: float
    total_revenue_year: float
    churn_rate: float
    conversion_rate: float


class UsageMetrics(BaseModel):
    """Platform usage metrics"""

    total_api_calls: int
    total_agents_created: int
    total_cycles_performed: int
    total_integrations_active: int
    avg_api_calls_per_user: float
    peak_concurrent_users: int


class AdminUser(BaseModel):
    """Admin user details"""

    user_id: str
    email: str
    subscription_tier: str
    created_at: datetime
    last_active: datetime
    total_api_calls: int
    total_spent: float
    status: str  # active, suspended, deleted


# ============================================================================
# ADMIN DASHBOARD SERVICE
# ============================================================================


class AdminDashboard:
    """Admin dashboard backend service"""

    def __init__(self) -> None:
        self.router = APIRouter(prefix="/api/admin", tags=["admin"])
        self._setup_routes()

    def _setup_routes(self):
        """Setup admin dashboard routes"""

        @self.router.get("/stats/users")
        async def get_user_stats() -> UserStats:
            """Get comprehensive user statistics"""
            try:

                db_helpers = await get_database_helpers()
                if db_helpers:
                    stats = await db_helpers.get_user_statistics()

                    if stats:
                        return UserStats(
                            total_users=stats.get("total_users", 0),
                            active_users=stats.get("active_users_7d", 0),
                            new_users_today=stats.get("new_users_today", 0),
                            new_users_week=stats.get("new_users_30d", 0),
                            users_by_tier=stats.get("users_by_tier", {}),
                        )
            except Exception as e:
                logger.warning("Database query failed, using fallback: %s", e)

            # Fallback to mock data
            return UserStats(
                total_users=0,
                active_users=0,
                new_users_today=0,
                new_users_week=0,
                users_by_tier={"free": 0, "pro": 0, "enterprise": 0},
            )

        @self.router.get("/stats/revenue")
        async def get_revenue_metrics() -> RevenueMetrics:
            """Get revenue and billing metrics"""
            try:
                db_helpers = await get_database_helpers()
                if db_helpers:
                    revenue = await db_helpers.get_revenue_statistics()

                    if revenue:
                        total_revenue = revenue.get("total_revenue", 0)
                        revenue_30d = revenue.get("revenue_30d", 0)

                        # Calculate real churn rate from DB
                        churn_rate = 0.0
                        conversion_rate = 0.0
                        try:
                            from apps.backend.database import get_session

                            with get_session() as session:
                                # Churn: cancelled subscriptions in last 30d / total active at start
                                thirty_days_ago = datetime.now(UTC) - timedelta(days=30)
                                cancelled = (
                                    session.execute(
                                        select(func.count())
                                        .select_from(Subscription)
                                        .where(
                                            Subscription.status == "cancelled",
                                            Subscription.updated_at >= thirty_days_ago,
                                        )
                                    ).scalar()
                                    or 0
                                )
                                total_active = (
                                    session.execute(
                                        select(func.count())
                                        .select_from(Subscription)
                                        .where(Subscription.status == "active")
                                    ).scalar()
                                    or 0
                                )
                                if total_active + cancelled > 0:
                                    churn_rate = round((cancelled / (total_active + cancelled)) * 100, 2)

                                # Conversion: paid users / total users
                                total_users = session.execute(select(func.count()).select_from(User)).scalar() or 0
                                paid_users = (
                                    session.execute(
                                        select(func.count())
                                        .select_from(User)
                                        .join(Subscription, User.id == Subscription.user_id)
                                        .where(Subscription.tier != "free", Subscription.status == "active")
                                    ).scalar()
                                    or 0
                                )
                                if total_users > 0:
                                    conversion_rate = round((paid_users / total_users) * 100, 2)
                        except Exception as e:
                            logger.warning("Could not calculate churn/conversion: %s", e)

                        return RevenueMetrics(
                            mrr=revenue_30d,
                            arr=revenue_30d * 12,
                            total_revenue_month=revenue_30d,
                            total_revenue_year=total_revenue,
                            churn_rate=churn_rate,
                            conversion_rate=conversion_rate,
                        )
            except Exception as e:
                logger.warning("Database query failed, using fallback: %s", e)

            # Fallback
            return RevenueMetrics(
                mrr=0.0,
                arr=0.0,
                total_revenue_month=0.0,
                total_revenue_year=0.0,
                churn_rate=0.0,
                conversion_rate=0.0,
            )

        @self.router.get("/stats/usage")
        async def get_usage_metrics() -> UsageMetrics:
            """Get platform usage metrics"""
            try:
                db_helpers = await get_database_helpers()
                if db_helpers:
                    usage = await db_helpers.get_usage_statistics()

                    if usage:
                        total_requests = usage.get("total_requests", 0)
                        unique_users = usage.get("unique_users", 0)

                        return UsageMetrics(
                            total_api_calls=total_requests,
                            total_agents_created=usage.get("total_agents", 0),
                            total_cycles_performed=usage.get("total_cycles", 0),
                            total_integrations_active=usage.get("active_integrations", 0),
                            avg_api_calls_per_user=(total_requests / unique_users if unique_users > 0 else 0),
                            peak_concurrent_users=usage.get("peak_concurrent", 0),
                        )
            except Exception as e:
                logger.warning("Database query failed, using fallback: %s", e)

            # Fallback
            return UsageMetrics(
                total_api_calls=0,
                total_agents_created=0,
                total_cycles_performed=0,
                total_integrations_active=0,
                avg_api_calls_per_user=0.0,
                peak_concurrent_users=0,
            )

        @self.router.get("/health/system")
        async def get_system_health() -> SystemHealth:
            """Get comprehensive system health"""
            import time as _time

            import httpx

            services: dict[str, dict[str, Any]] = {}
            overall_status = "healthy"

            # Calculate uptime from process start
            try:
                import psutil

                process = psutil.Process()
                uptime_seconds = int(_time.time() - process.create_time())
            except (ImportError, psutil.Error, OSError, AttributeError):
                uptime_seconds = 0  # Cannot determine
            except Exception as e:
                logger.debug("Unexpected error getting uptime: %s", e)
                uptime_seconds = 0

            # Check core_api (self-check)
            api_start = _time.time()
            services["core_api"] = {
                "status": "healthy",
                "response_time_ms": round((_time.time() - api_start) * 1000, 1),
            }

            # Check database
            db_status = "healthy"
            try:
                from apps.backend.database import get_session

                with get_session() as session:
                    session.execute(select(func.count()).select_from(User))
                db_status = "healthy"
            except Exception as e:
                db_status = "degraded"
                overall_status = "degraded"
                logger.warning("Database health check failed: %s", e)

            # Check Redis
            redis_status = "healthy"
            try:
                import redis as _redis

                redis_url = os.environ.get("REDIS_URL", "")
                if redis_url:
                    r = _redis.from_url(redis_url, socket_timeout=2)
                    r.ping()
                    info = r.info("clients")
                    redis_connections = info.get("connected_clients", 0)
                else:
                    redis_status = "not_configured"
                    redis_connections = 0
            except (ImportError, ConnectionError, TimeoutError, OSError) as e:
                logger.debug("Redis health check failed: %s", e)
                redis_status = "degraded"
                redis_connections = 0
                overall_status = "degraded"
            except Exception as e:
                logger.warning("Unexpected Redis error: %s", e)
                redis_status = "degraded"
                redis_connections = 0
                overall_status = "degraded"

            # Check WebSocket service
            ws_port = os.environ.get("WS_PORT", "8002")
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(f"http://localhost:{ws_port}/health")
                    ws_healthy = resp.status_code == 200
                services["websocket"] = {
                    "status": "healthy" if ws_healthy else "degraded",
                    "connections": redis_connections,
                }
            except (ImportError, httpx.RequestError, OSError) as e:
                logger.debug("WebSocket service check failed: %s", e)
                services["websocket"] = {"status": "unreachable", "connections": 0}
            except Exception as e:
                logger.warning("Unexpected WebSocket error: %s", e)
                services["websocket"] = {"status": "unreachable", "connections": 0}

            # Check Integration Hub
            ih_port = os.environ.get("IH_PORT", "8003")
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(f"http://localhost:{ih_port}/health")
                    ih_healthy = resp.status_code == 200
                services["integration_hub"] = {
                    "status": "healthy" if ih_healthy else "degraded",
                    "queue_depth": 0,
                }
            except (ImportError, httpx.RequestError, OSError) as e:
                logger.debug("Integration Hub check failed: %s", e)
                services["integration_hub"] = {"status": "unreachable", "queue_depth": 0}
            except Exception as e:
                logger.warning("Unexpected Integration Hub error: %s", e)
                services["integration_hub"] = {"status": "unreachable", "queue_depth": 0}

            # Measure API response time
            api_response_time = round((_time.time() - api_start) * 1000, 1)

            if any(s.get("status") == "unreachable" for s in services.values()):
                overall_status = "degraded"

            return SystemHealth(
                status=overall_status,
                uptime_seconds=uptime_seconds,
                services=services,
                database_status=db_status,
                redis_status=redis_status,
                api_response_time_ms=api_response_time,
            )

        @self.router.get("/users")
        async def list_users(
            page: int = Query(1, ge=1),
            page_size: int = Query(50, ge=1, le=100),
            tier: str | None = None,
            status: str | None = None,
            search: str | None = None,
        ) -> dict[str, Any]:
            """List users with pagination and filters"""
            try:

                from apps.backend.database import get_session
                from apps.backend.saas.models.subscription import Subscription
                from apps.backend.saas.models.user import User

                with get_session() as session:
                    # Base query
                    stmt = select(User).join(Subscription, User.subscription, isouter=True)

                    # Apply filters
                    filters = []
                    if tier:
                        filters.append(Subscription.tier == tier)
                    if status:
                        if status == "active":
                            filters.append(User.is_active.is_(True))
                        elif status == "suspended":
                            filters.append(User.is_active.is_(False))
                    if search:
                        filters.append(
                            or_(
                                User.email.ilike(f"%{search}%"),
                                User.full_name.ilike(f"%{search}%"),
                            )
                        )

                    if filters:
                        stmt = stmt.where(*filters)

                    # Get total count
                    # pylint: disable=not-callable
                    count_stmt = select(func.count(User.id)).select_from(User)
                    if filters:
                        count_stmt = count_stmt.where(*filters)
                    total = session.execute(count_stmt).scalar()

                    # Apply pagination
                    offset = (page - 1) * page_size
                    stmt = stmt.offset(offset).limit(page_size)

                    # Execute query
                    result = session.execute(stmt)
                    users = result.scalars().all()

                    # Format user data
                    user_list = []
                    for user in users:
                        user_list.append(
                            {
                                "user_id": str(user.id),
                                "email": user.email,
                                "full_name": user.full_name,
                                "subscription_tier": (user.subscription.tier if user.subscription else "free"),
                                "created_at": user.created_at.isoformat(),
                                "status": "active" if user.is_active else "suspended",
                            }
                        )

                    return {
                        "users": user_list,
                        "total": total,
                        "page": page,
                        "page_size": page_size,
                        "total_pages": (total + page_size - 1) // page_size,
                    }

            except Exception as e:
                logger.error("Error fetching users: %s", e, exc_info=True)
                return {
                    "users": [],
                    "total": 0,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": 0,
                    "error": "Failed to fetch users",
                }

        @self.router.get("/users/{user_id}")
        async def get_user_details(user_id: str) -> dict[str, Any]:
            """Get detailed user information"""
            try:

                from sqlalchemy import select

                with get_session() as session:
                    # Query user with subscription
                    stmt = (
                        select(User)
                        .where(User.id == uuid.UUID(user_id))
                        .join(Subscription, User.subscription, isouter=True)
                    )
                    result = session.execute(stmt)
                    user = result.scalar_one_or_none()

                    if not user:
                        raise HTTPException(status_code=404, detail="User not found")

                    # Build response
                    response = {
                        "user": {
                            "user_id": str(user.id),
                            "email": user.email,
                            "full_name": user.full_name,
                            "subscription_tier": (user.subscription.tier if user.subscription else "free"),
                            "created_at": user.created_at.isoformat(),
                            "email_verified": user.email_verified,
                            "status": "active" if user.is_active else "suspended",
                        },
                        "billing": {},
                        "usage": {},
                        "activity": {},
                    }

                    # Add subscription details if exists
                    if user.subscription:
                        response["billing"] = {
                            "subscription_status": user.subscription.status,
                            "current_period_start": (
                                user.subscription.current_period_start.isoformat()
                                if user.subscription.current_period_start
                                else None
                            ),
                            "current_period_end": (
                                user.subscription.current_period_end.isoformat()
                                if user.subscription.current_period_end
                                else None
                            ),
                            "stripe_subscription_id": user.stripe_subscription_id,
                        }

                    return response

            except HTTPException:
                raise
            except Exception as e:
                logger.error("Error fetching user %s: %s", user_id, e, exc_info=True)
                raise HTTPException(status_code=500, detail="Failed to fetch user details")

        @self.router.post("/users/{user_id}/suspend")
        async def suspend_user(user_id: str, reason: str):
            """Suspend a user account"""
            try:

                with get_session() as session:
                    stmt = select(User).where(User.id == uuid.UUID(user_id))
                    result = session.execute(stmt)
                    user = result.scalar_one_or_none()

                    if not user:
                        raise HTTPException(status_code=404, detail="User not found")

                    user.is_active = False
                    session.commit()

                    logger.warning("User %s (%s) suspended. Reason: %s", user_id, user.email, reason)
                    return {
                        "status": "suspended",
                        "user_id": user_id,
                        "reason": reason,
                    }

            except HTTPException:
                raise
            except Exception as e:
                logger.error("Error suspending user %s: %s", user_id, e, exc_info=True)
                raise HTTPException(status_code=500, detail="Failed to suspend user")

        @self.router.post("/users/{user_id}/activate")
        async def activate_user(user_id: str):
            """Activate a suspended user account"""
            try:

                with get_session() as session:
                    stmt = select(User).where(User.id == uuid.UUID(user_id))
                    result = session.execute(stmt)
                    user = result.scalar_one_or_none()

                    if not user:
                        raise HTTPException(status_code=404, detail="User not found")

                    user.is_active = True
                    session.commit()

                    logger.info("User %s (%s) activated", user_id, user.email)
                    return {"status": "active", "user_id": user_id}

            except HTTPException:
                raise
            except Exception as e:
                logger.error("Error activating user %s: %s", user_id, e, exc_info=True)
                raise HTTPException(status_code=500, detail="Failed to activate user")

        @self.router.get("/analytics/trends")
        async def get_analytics_trends(
            metric: str = Query("users", pattern="^(users|revenue|api_calls)$"),
            period: str = Query("7d", pattern="^(1d|7d|30d|90d)$"),
        ) -> dict[str, Any]:
            """Get analytics trends over time"""
            try:

                from sqlalchemy import func, select

                days = int(period[:-1])
                data = []

                with get_session() as session:
                    if metric == "users":
                        # Count users created each day
                        for i in range(days - 1, -1, -1):
                            target_date = datetime.now(UTC) - timedelta(days=i)
                            start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
                            end = start + timedelta(days=1)

                            # pylint: disable=not-callable
                            stmt = select(func.count(User.id)).where(User.created_at >= start, User.created_at < end)
                            count = session.execute(stmt).scalar()

                            data.append({"date": target_date.date().isoformat(), "value": count})

                    elif metric == "revenue":
                        # Calculate revenue from active subscriptions
                        tier_prices = {
                            "free": 0,
                            "starter": 9.99,
                            "pro": 29.99,
                            "enterprise": 99.99,
                        }
                        for i in range(days - 1, -1, -1):
                            target_date = datetime.now(UTC) - timedelta(days=i)
                            start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
                            end = start + timedelta(days=1)

                            stmt = select(Subscription.tier).where(
                                Subscription.status == "active",
                                Subscription.current_period_start <= end,
                                Subscription.current_period_end >= start,
                            )
                            result = session.execute(stmt)
                            tiers = [row[0] for row in result]

                            daily_revenue = sum(tier_prices.get(tier, 0) for tier in tiers)
                            data.append(
                                {
                                    "date": target_date.date().isoformat(),
                                    "value": round(daily_revenue, 2),
                                }
                            )

                    else:  # api_calls - query UsageLog table
                        for i in range(days - 1, -1, -1):
                            target_date = datetime.now(UTC) - timedelta(days=i)
                            start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
                            end = start + timedelta(days=1)

                            # pylint: disable=not-callable
                            stmt = select(func.count(UsageLog.id)).where(
                                UsageLog.timestamp >= start,
                                UsageLog.timestamp < end,
                            )
                            count = session.execute(stmt).scalar() or 0

                            data.append(
                                {
                                    "date": target_date.date().isoformat(),
                                    "value": count,
                                }
                            )

                # Calculate trend
                if len(data) >= 2:
                    first_half = sum(d["value"] for d in data[: len(data) // 2])
                    second_half = sum(d["value"] for d in data[len(data) // 2 :])
                    if first_half > 0:
                        change_percent = ((second_half - first_half) / first_half) * 100
                        trend = "up" if change_percent > 0 else "down"
                    else:
                        change_percent = 0
                        trend = "neutral"
                else:
                    change_percent = 0
                    trend = "neutral"

                return {
                    "metric": metric,
                    "period": period,
                    "data": data,
                    "trend": trend,
                    "change_percent": round(change_percent, 2),
                }

            except Exception as e:
                logger.error("Error calculating trends: %s", e, exc_info=True)
                return {
                    "metric": metric,
                    "period": period,
                    "data": [],
                    "trend": "unknown",
                    "change_percent": 0,
                    "error": "Failed to calculate trends",
                }

        @self.router.post("/system/backup")
        async def trigger_backup():
            """Trigger system backup"""
            try:
                import json
                from datetime import datetime

                backup_id = f"backup_{int(datetime.now(UTC).timestamp())}"

                # Create backup task
                backup_task = {
                    "task_id": backup_id,
                    "type": "database_backup",
                    "status": "initiated",
                    "created_at": datetime.now(UTC).isoformat(),
                }

                # Queue backup via Integration Hub
                try:

                    import redis

                    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
                    r = redis.from_url(redis_url)
                    r.rpush("backup_queue", json.dumps(backup_task))
                except Exception as redis_err:
                    logger.warning("Could not queue backup task: %s. Backup will be manual.", redis_err)

                logger.info("System backup %s initiated", backup_id)
                return {
                    "status": "initiated",
                    "backup_id": backup_id,
                    "estimated_completion": "15 minutes",
                }

            except Exception as e:
                logger.error("Backup initiation failed: %s", e, exc_info=True)
                raise HTTPException(status_code=500, detail="Failed to initiate backup")


# ============================================================================
# INITIALIZATION
# ============================================================================

admin_dashboard = AdminDashboard()

# Export router for FastAPI app
router = admin_dashboard.router

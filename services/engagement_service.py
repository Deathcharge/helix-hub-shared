"""
User Engagement & Retention Service
====================================

Tracks user engagement metrics, feature adoption, and churn risk signals.
Enables proactive retention strategies and personalized re-engagement campaigns.

Features:
- Engagement scoring based on user activity
- Feature adoption tracking
- Churn risk detection
- Retention campaign management
- Cohort analysis
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

try:
    import redis.asyncio as redis
except ImportError:
    redis = None  # type: ignore[assignment]
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class EngagementEvent(str, Enum):
    """Types of engagement events to track."""

    LOGIN = "login"
    LOGOUT = "logout"
    API_CALL = "api_call"
    AGENT_EXECUTION = "agent_execution"
    WORKFLOW_CREATED = "workflow_created"
    WORKFLOW_COMPLETED = "workflow_completed"
    TEMPLATE_USED = "template_used"
    INTEGRATION_CONNECTED = "integration_connected"
    FEATURE_FIRST_USE = "feature_first_use"
    SHARED_CONTENT = "shared_content"
    FEEDBACK_SUBMITTED = "feedback_submitted"
    SUPPORT_TICKET = "support_ticket"
    DAILY_ACTIVE = "daily_active"
    WEEKLY_ACTIVE = "weekly_active"


class ChurnRiskLevel(str, Enum):
    """Churn risk classification."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EngagementScore(BaseModel):
    """User's engagement score breakdown."""

    user_id: str
    overall_score: float = Field(ge=0, le=100)
    recency_score: float = Field(ge=0, le=100)  # How recently they active
    frequency_score: float = Field(ge=0, le=100)  # How often they active
    feature_adoption_score: float = Field(ge=0, le=100)  # How many features used
    support_engagement_score: float = Field(ge=0, le=100)  # Positive support interactions
    calculated_at: datetime


class FeatureUsage(BaseModel):
    """Feature usage record."""

    feature_id: str
    feature_name: str
    first_used_at: datetime | None = None
    usage_count: int = 0
    last_used_at: datetime | None = None


class RetentionCampaign(BaseModel):
    """Retention campaign configuration."""

    campaign_id: str
    name: str
    target_segment: str  # e.g., "churn_risk", "inactive_7_days", "new_users"
    trigger_condition: str
    message_template: str
    channel: str  # email, push, in_app
    active: bool = True
    created_at: datetime
    sent_count: int = 0
    conversion_count: int = 0


class EngagementService:
    """
    Service for tracking user engagement and retention metrics.

    Uses Redis for real-time tracking and provides analytics
    for retention-focused decision making.
    """

    # Engagement weights for scoring
    EVENT_WEIGHTS = {
        EngagementEvent.LOGIN: 5,
        EngagementEvent.API_CALL: 2,
        EngagementEvent.AGENT_EXECUTION: 10,
        EngagementEvent.WORKFLOW_CREATED: 15,
        EngagementEvent.WORKFLOW_COMPLETED: 20,
        EngagementEvent.TEMPLATE_USED: 8,
        EngagementEvent.INTEGRATION_CONNECTED: 25,
        EngagementEvent.FEATURE_FIRST_USE: 30,
        EngagementEvent.SHARED_CONTENT: 12,
        EngagementEvent.FEEDBACK_SUBMITTED: 15,
    }

    # Features to track adoption
    TRACKED_FEATURES = {
        "agents": "AI Agents",
        "workflows": "Workflow Automation",
        "integrations": "Third-party Integrations",
        "api": "API Access",
        "coordination": "Coordination Features",
        "voice": "Voice Commands",
        "templates": "Template Library",
        "collaboration": "Team Collaboration",
        "analytics": "Analytics Dashboard",
        "webhooks": "Webhooks",
    }

    def __init__(self) -> None:
        self.redis_client = None  # Optional[redis.Redis]
        self._campaigns: dict[str, RetentionCampaign] = {}

    async def initialize(self, redis_url: str = "redis://localhost:6379"):
        """Initialize Redis connection."""
        if redis is None:
            logger.warning("redis package not installed; engagement service running without Redis")
            return
        try:
            self.redis_client = redis.from_url(redis_url, decode_responses=True)
            await self.redis_client.ping()
            logger.info("Engagement service initialized with Redis")
        except Exception as e:
            logger.warning("Redis unavailable for engagement service: %s", e)
            self.redis_client = None

    async def close(self):
        """Close Redis connection."""
        if self.redis_client:
            await self.redis_client.close()

    # -------------------------------------------------------------------------
    # Event Tracking
    # -------------------------------------------------------------------------

    async def track_event(
        self,
        user_id: str,
        event_type: EngagementEvent,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Track a user engagement event.

        Args:
            user_id: The user's ID
            event_type: Type of engagement event
            metadata: Additional event metadata
        """
        if not self.redis_client:
            logger.warning("Redis not available, skipping engagement tracking")
            return

        timestamp = datetime.now(UTC)
        event_key = f"engagement:{user_id}:events"

        event_data = {
            "type": event_type.value,
            "timestamp": timestamp.isoformat(),
            "metadata": metadata or {},
        }

        # Store event in time-series fashion
        await self.redis_client.lpush(event_key, str(event_data))
        await self.redis_client.expire(event_key, 90 * 24 * 3600)  # 90 days

        # Update daily active set
        if event_type == EngagementEvent.DAILY_ACTIVE:
            await self.redis_client.sadd(f"dau:{timestamp.date()}", user_id)

        # Update weekly active set
        if event_type == EngagementEvent.WEEKLY_ACTIVE:
            await self.redis_client.sadd(f"wau:{timestamp.date()}", user_id)

        # Check for feature first-use
        if event_type == EngagementEvent.FEATURE_FIRST_USE and metadata:
            feature_id = metadata.get("feature_id")
            if feature_id:
                await self._track_feature_first_use(user_id, feature_id, timestamp)

        logger.debug("Tracked engagement event: %s - %s", user_id, event_type.value)

    async def _track_feature_first_use(self, user_id: str, feature_id: str, timestamp: datetime) -> None:
        """Track first-time feature usage."""
        feature_key = f"engagement:{user_id}:features:{feature_id}:first_use"
        exists = await self.redis_client.exists(feature_key)

        if not exists:
            await self.redis_client.set(feature_key, timestamp.isoformat(), ex=365 * 24 * 3600)
            logger.info("User %s first used feature: %s", user_id, feature_id)

    # -------------------------------------------------------------------------
    # Engagement Scoring
    # -------------------------------------------------------------------------

    async def calculate_engagement_score(self, user_id: str) -> EngagementScore:
        """
        Calculate comprehensive engagement score for a user.

        Score components:
        - Recency: Days since last activity
        - Frequency: Number of sessions/actions in period
        - Feature Adoption: How many features they've used
        - Support Engagement: Positive vs negative support interactions
        """
        if not self.redis_client:
            return EngagementScore(
                user_id=user_id,
                overall_score=50.0,
                recency_score=50.0,
                frequency_score=50.0,
                feature_adoption_score=50.0,
                support_engagement_score=50.0,
                calculated_at=datetime.now(UTC),
            )

        now = datetime.now(UTC)

        # Recency score (0-100)
        recency_score = await self._calculate_recency_score(user_id, now)

        # Frequency score (0-100)
        frequency_score = await self._calculate_frequency_score(user_id, now)

        # Feature adoption score (0-100)
        feature_adoption_score = await self._calculate_feature_adoption_score(user_id)

        # Support engagement score (0-100)
        support_score = await self._calculate_support_score(user_id)

        # Weighted overall score
        overall = recency_score * 0.25 + frequency_score * 0.30 + feature_adoption_score * 0.30 + support_score * 0.15

        return EngagementScore(
            user_id=user_id,
            overall_score=round(overall, 1),
            recency_score=round(recency_score, 1),
            frequency_score=round(frequency_score, 1),
            feature_adoption_score=round(feature_adoption_score, 1),
            support_engagement_score=round(support_score, 1),
            calculated_at=now,
        )

    async def _calculate_recency_score(self, user_id: str, now: datetime) -> float:
        """Calculate recency score based on last activity."""
        event_key = f"engagement:{user_id}:events"
        last_event = await self.redis_client.lindex(event_key, 0)

        if not last_event:
            return 0.0  # No activity

        # Parse timestamp from event (simplified)
        try:
            # Get last login time from auth events
            login_key = f"engagement:{user_id}:last_login"
            last_login = await self.redis_client.get(login_key)

            if last_login:
                last_date = datetime.fromisoformat(last_login)
                days_since = (now - last_date).days

                if days_since <= 1:
                    return 100.0
                elif days_since <= 7:
                    return 80.0
                elif days_since <= 14:
                    return 60.0
                elif days_since <= 30:
                    return 40.0
                else:
                    return 20.0
        except Exception as e:
            logger.warning("Failed to calculate recency score for user %s: %s", user_id, e)

        return 50.0  # Default middle score

    async def _calculate_frequency_score(self, user_id: str, now: datetime) -> float:
        """Calculate frequency score based on activity count."""
        event_key = f"engagement:{user_id}:events"

        # Count events in last 30 days
        events = await self.redis_client.lrange(event_key, 0, -1)

        # Count unique days with activity
        unique_days = set()
        for event in events[:100]:  # Check last 100 events
            try:
                # Simplified - would need proper parsing
                unique_days.add(now.date())
            except Exception as e:
                logger.debug("Failed to parse engagement event for user %s: %s", user_id, e)

        # Score based on activity frequency
        activity_days = len(unique_days)

        if activity_days >= 20:
            return 100.0
        elif activity_days >= 15:
            return 80.0
        elif activity_days >= 10:
            return 60.0
        elif activity_days >= 5:
            return 40.0
        elif activity_days >= 1:
            return 20.0
        else:
            return 0.0

    async def _calculate_feature_adoption_score(self, user_id: str) -> float:
        """Calculate feature adoption score."""
        if not self.redis_client:
            return 50.0

        features_used = 0
        total_features = len(self.TRACKED_FEATURES)

        for feature_id in self.TRACKED_FEATURES:
            feature_key = f"engagement:{user_id}:features:{feature_id}:first_use"
            if await self.redis_client.exists(feature_key):
                features_used += 1

        return (features_used / total_features) * 100

    async def _calculate_support_score(self, user_id: str) -> float:
        """Calculate support engagement score."""
        # Positive: feedback submitted, feature requests
        # Negative: support tickets, complaints

        # Simplified - would track actual support interactions
        return 70.0  # Default good score

    # -------------------------------------------------------------------------
    # Churn Risk Assessment
    # -------------------------------------------------------------------------

    async def assess_churn_risk(self, user_id: str) -> tuple[ChurnRiskLevel, str]:
        """
        Assess churn risk for a user.

        Returns:
            Tuple of (risk_level, reason)
        """
        score = await self.calculate_engagement_score(user_id)

        if score.overall_score >= 70:
            return (ChurnRiskLevel.LOW, "High engagement")
        elif score.overall_score >= 50:
            return (ChurnRiskLevel.MEDIUM, "Moderate engagement")
        elif score.overall_score >= 30:
            return (ChurnRiskLevel.HIGH, "Low engagement")
        else:
            return (ChurnRiskLevel.CRITICAL, "Very low engagement - at risk")

    async def get_churn_risk_users(self, risk_level: ChurnRiskLevel, limit: int = 100) -> list[dict[str, Any]]:
        """
        Get users at specified churn risk level.

        Requires database integration to query real user metrics.
        Returns an empty list until the user analytics pipeline is connected.
        """
        logger.info("get_churn_risk_users called — real user analytics pipeline not yet connected")
        return []

    # -------------------------------------------------------------------------
    # Retention Campaigns
    # -------------------------------------------------------------------------

    async def create_campaign(
        self,
        name: str,
        target_segment: str,
        trigger_condition: str,
        message_template: str,
        channel: str = "email",
    ) -> RetentionCampaign:
        """Create a new retention campaign."""
        campaign = RetentionCampaign(
            campaign_id=f"campaign_{datetime.now(UTC).timestamp()}",
            name=name,
            target_segment=target_segment,
            trigger_condition=trigger_condition,
            message_template=message_template,
            channel=channel,
            active=True,
            created_at=datetime.now(UTC),
        )

        self._campaigns[campaign.campaign_id] = campaign
        logger.info("Created retention campaign: %s", name)

        return campaign

    async def trigger_campaign(self, campaign_id: str, user_id: str) -> dict[str, Any] | None:
        """Trigger a retention campaign for a specific user."""
        campaign = self._campaigns.get(campaign_id)

        if not campaign or not campaign.active:
            return None

        # In production: send via email, push, in-app notification
        campaign.sent_count += 1

        logger.info("Triggered campaign %s for user %s", campaign.name, user_id)

        return {
            "campaign_id": campaign.campaign_id,
            "user_id": user_id,
            "message": campaign.message_template,
            "channel": campaign.channel,
        }

    async def get_active_campaigns(self) -> list[RetentionCampaign]:
        """Get all active retention campaigns."""
        return [c for c in self._campaigns.values() if c.active]

    # -------------------------------------------------------------------------
    # Cohort Analysis
    # -------------------------------------------------------------------------

    async def get_cohort_retention(self, cohort_date: datetime, periods: list[int] | None = None) -> dict[int, float]:
        """
        Get retention rates for a cohort over specified periods.

        Args:
            cohort_date: The date of the cohort (e.g., signup date)
            periods: List of day periods to measure retention

        Returns:
            Dict mapping period days to retention percentage
        """
        if periods is None:
            periods = [1, 7, 14, 30]
        if not self.redis_client:
            return dict.fromkeys(periods, 0.0)

        cohort_key = "dau:%s" % cohort_date.date()
        cohort_size = await self.redis_client.scard(cohort_key)
        if cohort_size == 0:
            return dict.fromkeys(periods, 0.0)

        retention = {}
        for period in periods:
            target_date = cohort_date + timedelta(days=period)
            target_key = "dau:%s" % target_date.date()

            # Count cohort members who were also active on the target date
            # Use SINTERCARD if available (Redis 7+), otherwise fall back to SINTER
            try:
                active_count = len(await self.redis_client.sinter(cohort_key, target_key))
            except Exception:
                active_count = 0

            retention[period] = round(active_count / cohort_size * 100, 2)

        return retention

    # -------------------------------------------------------------------------
    # Analytics Dashboard Data
    # -------------------------------------------------------------------------

    async def get_engagement_dashboard(self) -> dict[str, Any]:
        """Get engagement analytics for dashboard display."""
        if not self.redis_client:
            return self._get_default_dashboard()

        # Get DAU
        today = datetime.now(UTC).date()
        dau = await self.redis_client.scard(f"dau:{today}")

        # Get WAU
        wau_keys = []
        for i in range(7):
            date = today - timedelta(days=i)
            wau_keys.append(f"wau:{date}")

        # Get active campaigns
        active_campaigns = await self.get_active_campaigns()

        return {
            "daily_active_users": dau,
            "weekly_active_users": 0,  # Would aggregate
            "active_campaigns": len(active_campaigns),
            "engagement_trends": [],  # Would aggregate over time
            "top_features": list(self.TRACKED_FEATURES.values())[:5],
            "churn_risk_distribution": {
                "low": 0,
                "medium": 0,
                "high": 0,
                "critical": 0,
            },
        }

    def _get_default_dashboard(self) -> dict[str, Any]:
        """Return default dashboard data when Redis unavailable."""
        return {
            "daily_active_users": 0,
            "weekly_active_users": 0,
            "active_campaigns": 0,
            "engagement_trends": [],
            "top_features": [],
            "churn_risk_distribution": {},
        }


# -----------------------------------------------------------------------------
# Service Instance
# -----------------------------------------------------------------------------

_engagement_service: EngagementService | None = None


async def get_engagement_service() -> EngagementService:
    """Get or create engagement service singleton."""
    global _engagement_service

    if _engagement_service is None:
        _engagement_service = EngagementService()
        await _engagement_service.initialize()

    return _engagement_service


# -----------------------------------------------------------------------------
# Convenience Functions
# -----------------------------------------------------------------------------


async def track_engagement_event(
    user_id: str,
    event_type: EngagementEvent,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Convenience function to track engagement events."""
    service = await get_engagement_service()
    await service.track_event(user_id, event_type, metadata)


async def get_user_engagement(user_id: str) -> EngagementScore:
    """Convenience function to get user engagement score."""
    service = await get_engagement_service()
    return await service.calculate_engagement_score(user_id)


async def check_churn_risk(user_id: str) -> tuple[ChurnRiskLevel, str]:
    """Convenience function to check churn risk."""
    service = await get_engagement_service()
    return await service.assess_churn_risk(user_id)

"""
🌀 Helix Collective - Billing & Subscription Service
Handles Stripe integration, subscription management, and usage tracking
"""

import logging
import os
from datetime import UTC, datetime
from typing import Any

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from apps.backend.utils.database_helpers import get_database_helpers

try:
    from apps.backend.core.resilience import retry_with_backoff
except ImportError:

    def retry_with_backoff(**_kw):
        def _noop(fn):
            return fn

        return _noop


try:
    from apps.backend.core.unified_auth import get_current_user
except ImportError:
    from apps.backend.auth import get_current_user  # type: ignore[assignment]

# Configure Stripe
if os.getenv("STRIPE_SECRET_KEY"):
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

logger = logging.getLogger(__name__)

# ============================================================================
# MODELS
# ============================================================================


class SubscriptionTier(BaseModel):
    """Subscription tier definition"""

    id: str
    name: str
    price_monthly: float
    price_yearly: float
    stripe_price_id_monthly: str
    stripe_price_id_yearly: str
    features: dict[str, Any]
    limits: dict[str, int]


class UsageRecord(BaseModel):
    """Usage tracking record"""

    user_id: str
    resource_type: str  # agents, api_calls, storage_gb, etc.
    quantity: int
    timestamp: datetime
    metadata: dict[str, Any] | None = None


class BillingInfo(BaseModel):
    """User billing information"""

    user_id: str
    stripe_customer_id: str | None = None
    subscription_id: str | None = None
    subscription_tier: str = "free"
    subscription_status: str = "active"
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    usage_current_period: dict[str, int] = {}


# ============================================================================
# SUBSCRIPTION TIERS
# ============================================================================

SUBSCRIPTION_TIERS = {
    "free": SubscriptionTier(
        id="free",
        name="Free",
        price_monthly=0,
        price_yearly=0,
        stripe_price_id_monthly="",
        stripe_price_id_yearly="",
        features={
            "agents": 3,
            "ai_models": ["basic"],
            "integrations": 10,
            "storage_gb": 1,
            "support": "community",
            "helix_spirals": 5,
            "meme_generations": 10,
            "voice_patrol": "basic",
            "discord_bots": 0,
        },
        limits={
            "api_calls_per_day": 33,  # ~1k/month
            "agents_concurrent": 3,
            "cycles_per_month": 0,
            "api_calls_per_month": 1000,
        },
    ),
    "hobby": SubscriptionTier(
        id="hobby",
        name="Hobby",
        price_monthly=10.00,
        price_yearly=90.00,
        stripe_price_id_monthly=os.getenv("STRIPE_HOBBY_MONTHLY_PRICE_ID", ""),
        stripe_price_id_yearly=os.getenv("STRIPE_HOBBY_YEARLY_PRICE_ID", ""),
        features={
            "agents": 5,
            "ai_models": ["basic"],
            "integrations": 25,
            "storage_gb": 5,
            "support": "email",
            "helix_spirals": 50,
            "meme_generations": 100,
            "voice_patrol": "basic",
            "discord_bots": 1,
            "transformation_engine": 5,
        },
        limits={
            "api_calls_per_day": 333,  # ~10k/month
            "agents_concurrent": 5,
            "cycles_per_month": 5,
            "api_calls_per_month": 10000,
        },
    ),
    "starter": SubscriptionTier(
        id="starter",
        name="Starter",
        price_monthly=29.00,
        price_yearly=261.00,
        stripe_price_id_monthly=os.getenv("STRIPE_STARTER_MONTHLY_PRICE_ID", ""),
        stripe_price_id_yearly=os.getenv("STRIPE_STARTER_YEARLY_PRICE_ID", ""),
        features={
            "agents": 10,
            "ai_models": ["basic", "advanced"],
            "integrations": 50,
            "storage_gb": 10,
            "support": "priority_email",
            "helix_spirals": -1,  # unlimited
            "meme_generations": -1,  # unlimited
            "voice_patrol": "premium",
            "discord_bots": 3,
            "transformation_engine": 20,
            "web_os_apps": 3,
            "agent_emergence_simulator": "basic",
        },
        limits={
            "api_calls_per_day": 1666,  # ~50k/month
            "agents_concurrent": 10,
            "cycles_per_month": 20,
            "api_calls_per_month": 50000,
        },
    ),
    "pro": SubscriptionTier(
        id="pro",
        name="Pro",
        price_monthly=79.00,
        price_yearly=711.00,
        stripe_price_id_monthly=os.getenv("STRIPE_PRO_MONTHLY_PRICE_ID", ""),
        stripe_price_id_yearly=os.getenv("STRIPE_PRO_YEARLY_PRICE_ID", ""),
        features={
            "agents": 17,
            "ai_models": ["basic", "advanced", "premium"],
            "integrations": 100,
            "storage_gb": 50,
            "support": "priority",
            "custom_agents": True,
            "api_access": True,
            "helix_spirals": -1,  # unlimited
            "meme_generations": -1,  # unlimited
            "voice_patrol": "premium",
            "discord_bots": 10,
            "transformation_engine": -1,  # unlimited
            "web_os_apps": 12,  # full bundle
            "agent_emergence_simulator": "unlimited",
            "model_hub": "basic",
            "coordination_api_websocket": True,
            "webhook_integrations": True,
        },
        limits={
            "api_calls_per_day": 6666,  # ~200k/month
            "agents_concurrent": 17,
            "cycles_per_month": -1,  # unlimited
            "api_calls_per_month": 200000,
        },
    ),
    "enterprise": SubscriptionTier(
        id="enterprise",
        name="Enterprise",
        price_monthly=299.00,
        price_yearly=2691.00,
        stripe_price_id_monthly=os.getenv("STRIPE_ENTERPRISE_MONTHLY_PRICE_ID", ""),
        stripe_price_id_yearly=os.getenv("STRIPE_ENTERPRISE_YEARLY_PRICE_ID", ""),
        features={
            "agents": "unlimited",
            "ai_models": ["basic", "advanced", "premium"],
            "integrations": "unlimited",
            "storage_gb": -1,  # unlimited
            "support": "dedicated_24_7",
            "custom_agents": True,
            "api_access": True,
            "white_label": True,
            "sla": "99.99%",
            "helix_spirals": -1,  # unlimited + custom
            "meme_generations": -1,  # unlimited + white_label
            "voice_patrol": "custom",
            "discord_bots": "custom",
            "transformation_engine": -1,  # unlimited
            "web_os_apps": "custom",
            "agent_emergence_simulator": "unlimited",
            "model_hub": "pro",  # 1000+ models
            "coordination_api_websocket": True,
            "webhook_integrations": True,
            "domain_verticals_ai": True,  # Finance, Genomics, Physics
            "multi_team_tracking": 10,
            "department_dashboards": True,
            "sso_saml": True,
            "advanced_rbac": True,
            "audit_logging": True,
        },
        limits={
            "api_calls_per_day": -1,  # unlimited
            "agents_concurrent": -1,  # unlimited
            "cycles_per_month": -1,  # unlimited
            "api_calls_per_month": -1,  # unlimited
        },
    ),
}

# ============================================================================
# BILLING SERVICE
# ============================================================================


class BillingService:
    """Manages subscriptions, billing, and usage tracking"""

    def __init__(self) -> None:
        self.router = APIRouter(prefix="/api/billing", tags=["billing"])
        self._setup_routes()

    def _setup_routes(self):
        """Setup billing routes"""

        @self.router.get("/tiers")
        async def get_subscription_tiers():
            """Get available subscription tiers"""
            return {"tiers": [tier.dict() for tier in SUBSCRIPTION_TIERS.values()]}

        @self.router.post("/subscription/create")
        async def create_subscription(
            tier: str,
            billing_period: str = "monthly",  # monthly or yearly
            user: dict = Depends(get_current_user),
        ):
            """Create a new subscription"""
            try:
                user_id = str(user.get("id", user.get("sub", "")))
                if tier not in SUBSCRIPTION_TIERS:
                    raise HTTPException(status_code=400, detail="Invalid tier")

                tier_info = SUBSCRIPTION_TIERS[tier]

                # Get or create Stripe customer
                customer = await self._get_or_create_customer(user_id)

                # Create subscription
                price_id = (
                    tier_info.stripe_price_id_monthly
                    if billing_period == "monthly"
                    else tier_info.stripe_price_id_yearly
                )

                subscription = stripe.Subscription.create(
                    customer=customer.id,
                    items=[{"price": price_id}],
                    metadata={"user_id": user_id, "tier": tier},
                )

                return {
                    "subscription_id": subscription.id,
                    "status": subscription.status,
                    "current_period_end": subscription.current_period_end,
                }

            except Exception as e:
                logger.error("Failed to create subscription: %s", e)
                raise HTTPException(status_code=500, detail="Subscription creation failed")

        @self.router.post("/subscription/cancel")
        async def cancel_subscription(user: dict = Depends(get_current_user)):
            """Cancel a subscription"""
            try:
                user_id = str(user.get("id", user.get("sub", "")))
                billing_info = await self._get_billing_info(user_id)

                if not billing_info.subscription_id:
                    raise HTTPException(status_code=404, detail="No active subscription")

                subscription = stripe.Subscription.modify(billing_info.subscription_id, cancel_at_period_end=True)

                return {"status": "cancelled", "cancel_at": subscription.cancel_at}

            except Exception as e:
                logger.error("Failed to cancel subscription: %s", e)
                raise HTTPException(status_code=500, detail="Subscription cancellation failed")

        @self.router.get("/usage/{user_id}")
        async def get_usage(user_id: str, user: dict = Depends(get_current_user)):
            """Get current usage for user"""
            try:
                # Users can only view their own usage
                caller_id = str(user.get("id", user.get("sub", "")))
                if caller_id != user_id:
                    raise HTTPException(status_code=403, detail="Access denied")
                billing_info = await self._get_billing_info(user_id)
                tier_info = SUBSCRIPTION_TIERS[billing_info.subscription_tier]

                return {
                    "user_id": user_id,
                    "tier": billing_info.subscription_tier,
                    "current_period": {
                        "start": billing_info.current_period_start,
                        "end": billing_info.current_period_end,
                    },
                    "usage": billing_info.usage_current_period,
                    "limits": tier_info.limits,
                    "percentage_used": self._calculate_usage_percentage(
                        billing_info.usage_current_period, tier_info.limits
                    ),
                }

            except Exception as e:
                logger.error("Failed to get usage: %s", e)
                raise HTTPException(status_code=500, detail="Failed to retrieve usage data")

        @self.router.post("/webhook")
        async def stripe_webhook(request: Request):
            """Handle Stripe webhooks"""
            try:
                payload = await request.body()
                sig_header = request.headers.get("stripe-signature")

                if not sig_header:
                    raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")

                webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
                if not webhook_secret:
                    logger.error("STRIPE_WEBHOOK_SECRET not configured")
                    raise HTTPException(status_code=500, detail="Webhook configuration error")

                event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)

                # Handle different event types
                if event.type == "customer.subscription.created":
                    await self._handle_subscription_created(event.data.object)
                elif event.type == "customer.subscription.updated":
                    await self._handle_subscription_updated(event.data.object)
                elif event.type == "customer.subscription.deleted":
                    await self._handle_subscription_deleted(event.data.object)
                elif event.type == "invoice.payment_succeeded":
                    await self._handle_payment_succeeded(event.data.object)
                elif event.type == "invoice.payment_failed":
                    await self._handle_payment_failed(event.data.object)

                return {"status": "success"}

            except Exception as e:
                logger.error("Webhook error: %s", e)
                raise HTTPException(status_code=400, detail="Webhook processing failed")

    @retry_with_backoff(max_retries=2, base_delay=1.0, exceptions=(Exception,))
    async def _get_or_create_customer(self, user_id: str) -> stripe.Customer:
        """Get or create Stripe customer, including user email so the customer record is identifiable."""
        create_kwargs: dict[str, Any] = {"metadata": {"user_id": user_id}}
        try:
            from apps.backend.core.database import Database

            user_row = await Database.fetchrow("SELECT email, full_name FROM users WHERE id = $1", user_id)
            if user_row:
                create_kwargs["email"] = user_row["email"]
                if user_row.get("full_name"):
                    create_kwargs["name"] = user_row["full_name"]
        except Exception as e:
            logger.warning("Could not look up user email for Stripe customer: %s", e)
        customer = stripe.Customer.create(**create_kwargs)
        return customer

    async def _get_billing_info(self, user_id: str) -> BillingInfo:
        """Get billing information for user"""
        try:
            db_helpers = get_database_helpers()
            if db_helpers:
                # Fetch from database
                billing_data = await db_helpers.get_user_billing_info(user_id)

                if billing_data:
                    # Get usage for current period
                    if billing_data.get("current_period_start"):
                        usage = {}
                        for resource_type in [
                            "api_calls",
                            "agents_created",
                            "storage_gb",
                        ]:
                            total = await db_helpers.get_usage_for_period(
                                user_id,
                                resource_type,
                                billing_data["current_period_start"],
                                billing_data.get("current_period_end") or datetime.now(UTC),
                            )
                            usage[resource_type] = total
                    else:
                        usage = {}

                    return BillingInfo(
                        user_id=billing_data["user_id"],
                        stripe_customer_id=billing_data.get("stripe_customer_id"),
                        subscription_id=billing_data.get("subscription_id"),
                        subscription_tier=billing_data.get("subscription_tier", "free"),
                        subscription_status=billing_data.get("subscription_status", "active"),
                        current_period_start=billing_data.get("current_period_start"),
                        current_period_end=billing_data.get("current_period_end"),
                        usage_current_period=usage,
                    )
        except Exception as e:
            logger.warning("Database query failed, using fallback: %s", e)

        # Fallback to default free tier
        return BillingInfo(user_id=user_id, subscription_tier="free", usage_current_period={})

    def _calculate_usage_percentage(self, usage: dict[str, int], limits: dict[str, int]) -> dict[str, float]:
        """Calculate percentage of limits used"""
        percentages = {}
        for key, limit in limits.items():
            if limit == -1:  # unlimited
                percentages[key] = 0.0
            else:
                used = usage.get(key, 0)
                percentages[key] = (used / limit * 100) if limit > 0 else 0.0
        return percentages

    async def _handle_subscription_created(self, subscription):
        """Handle subscription created webhook"""
        logger.info("Subscription created: %s", subscription.id)

        try:
            user_id = subscription.metadata.get("user_id")
            tier = subscription.metadata.get("tier", "pro")

            if user_id:
                db_helpers = await get_database_helpers()
                if db_helpers:
                    await db_helpers.create_or_update_billing_info(
                        user_id=user_id,
                        stripe_customer_id=subscription.customer,
                        subscription_id=subscription.id,
                        subscription_tier=tier,
                        subscription_status=subscription.status,
                    )
                    logger.info("Updated billing info for user %s", user_id)
        except Exception as e:
            logger.error("Failed to update billing info: %s", e)

    async def _handle_subscription_updated(self, subscription):
        """Handle subscription updated webhook"""
        logger.info("Subscription updated: %s", subscription.id)

        try:
            user_id = subscription.metadata.get("user_id")

            if user_id:
                db_helpers = await get_database_helpers()
                if db_helpers:
                    await db_helpers.create_or_update_billing_info(
                        user_id=user_id,
                        subscription_id=subscription.id,
                        subscription_status=subscription.status,
                    )
                    logger.info("Updated subscription status for user %s", user_id)
        except Exception as e:
            logger.error("Failed to update subscription status: %s", e)

    async def _handle_subscription_deleted(self, subscription):
        """Handle subscription deleted webhook"""
        logger.info("Subscription deleted: %s", subscription.id)

        try:
            user_id = subscription.metadata.get("user_id")

            if user_id:
                db_helpers = await get_database_helpers()
                if db_helpers:
                    await db_helpers.create_or_update_billing_info(
                        user_id=user_id,
                        subscription_tier="free",
                        subscription_status="cancelled",
                    )
                    logger.info("Downgraded user %s to free tier", user_id)
        except Exception as e:
            logger.error("Failed to downgrade user: %s", e)

    async def _handle_payment_succeeded(self, invoice):
        """Handle successful payment webhook"""
        logger.info("Payment succeeded: %s", invoice.id)

        try:
            subscription = invoice.get("subscription")
            if subscription:
                # Get subscription to find user_id
                sub_obj = stripe.Subscription.retrieve(subscription)
                user_id = sub_obj.metadata.get("user_id")

                if user_id:
                    db_helpers = await get_database_helpers()
                    if db_helpers:
                        await db_helpers.add_payment_record(
                            user_id=user_id,
                            stripe_payment_id=invoice.payment_intent,
                            amount_usd=invoice.amount_paid / 100,  # Convert cents to dollars
                            status="succeeded",
                            description=f"Invoice {invoice.id}",
                        )
                        logger.info("Recorded payment for user %s", user_id)
        except Exception as e:
            logger.error("Failed to record payment: %s", e)

    async def _handle_payment_failed(self, invoice):
        """Handle failed payment webhook — mark subscription past_due and notify user."""
        logger.error(
            "Payment failed: invoice=%s customer=%s amount_due=%s",
            invoice.id,
            invoice.get("customer"),
            invoice.get("amount_due"),
        )
        try:
            subscription_id = invoice.get("subscription")
            if not subscription_id:
                return

            sub_obj = stripe.Subscription.retrieve(subscription_id)
            user_id = sub_obj.metadata.get("user_id")

            if user_id:
                db_helpers = await get_database_helpers()
                if db_helpers:
                    current_tier = await db_helpers.get_user_subscription_tier(user_id) or "free"
                    await db_helpers.create_or_update_billing_info(
                        user_id=user_id,
                        subscription_tier=current_tier,
                        subscription_status="past_due",
                    )
                    logger.info("Marked user %s subscription as past_due", user_id)

            # Notify the user via their Stripe customer email
            customer_id = invoice.get("customer")
            if customer_id:
                customer = stripe.Customer.retrieve(customer_id)
                user_email = customer.get("email")
                if user_email:
                    try:
                        from apps.backend.services.subscription_emails import SubscriptionEmailService

                        email_svc = SubscriptionEmailService()
                        amount = (invoice.get("amount_due") or 0) / 100
                        next_attempt = invoice.get("next_payment_attempt")
                        retry_date = ""
                        if next_attempt:
                            retry_date = datetime.fromtimestamp(next_attempt, tz=UTC).strftime("%B %d, %Y")
                        await email_svc.send_payment_failed(
                            user_email=user_email,
                            user_name=customer.get("name") or "Helix User",
                            tier=sub_obj.metadata.get("tier", "paid"),
                            amount=amount,
                            retry_date=retry_date,
                        )
                        logger.info("Payment failed notification sent to %s", user_email)
                    except Exception as email_err:
                        logger.warning("Failed to send payment failed email: %s", email_err)
        except Exception as e:
            logger.error("Failed to process payment_failed event: %s", e)


# ============================================================================
# USAGE TRACKING
# ============================================================================


class UsageTracker:
    """
    Track resource usage for billing

    DEPRECATED: This class now delegates to services.usage_service.UsageService
    Kept for backward compatibility.
    """

    @staticmethod
    async def track_usage(
        user_id: str,
        resource_type: str,
        quantity: int = 1,
        metadata: dict[str, Any] | None = None,
    ):
        """
        Record usage event

        This method now delegates to the consolidated UsageService.
        """
        from apps.backend.services.usage_service import track_usage as new_track

        result = await new_track(user_id, resource_type, quantity, metadata)

        # If limit exceeded, raise HTTPException
        if result.get("is_exceeded"):
            raise HTTPException(
                status_code=429,
                detail=f"{resource_type.replace('_', ' ').title()} limit exceeded. Upgrade your plan for higher limits.",
            )

        return result

    @staticmethod
    async def _check_limits(user_id: str, resource_type: str):
        """
        Check if user has exceeded their tier limits

        DEPRECATED: Now handled automatically by UsageService.track_usage()
        Kept for backward compatibility.
        """
        # This is now handled automatically in track_usage


# ============================================================================
# INITIALIZATION
# ============================================================================

billing_service = BillingService()
usage_tracker = UsageTracker()

# Export router for FastAPI app
router = billing_service.router

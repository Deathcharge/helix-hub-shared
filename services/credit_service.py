"""
Credit Tracking and Deduction Service

This service manages user credits, tracks API usage, and enforces cost limits.
It integrates with the credit-based pricing system to ensure sustainable operations.

Key Features:
- Real-time credit tracking
- Automatic cost calculation
- Credit exhaustion handling
- BYOT (Bring Your Own Token) support
- Usage analytics and reporting

Author: Andrew John Ward
Version: 2.0 - Credit-Based Pricing
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.backend.config.credit_pricing import (
    Tier,
    calculate_request_cost,
    get_available_models,
    get_recommended_model,
    get_tier_config,
)
from apps.backend.db_models import APIUsage, CreditTransaction, User
from apps.backend.services.byot_service import get_user_byot_status

logger = logging.getLogger(__name__)


@dataclass
class CreditBalance:
    """User's credit balance information"""

    user_id: str
    tier: Tier
    credits_remaining: float  # USD
    credits_monthly: float  # Total monthly credits
    credits_used: float  # Credits used this month
    month_start: datetime
    byot_enabled: bool
    byot_provider: str | None


@dataclass
class RequestCost:
    """Cost information for a request"""

    model_id: str
    input_tokens: int
    output_tokens: int
    cost: float  # USD
    can_afford: bool
    recommended_model: str | None


@dataclass
class UsageStats:
    """Usage statistics for a user"""

    user_id: str
    total_requests: int
    total_cost: float
    total_tokens: int
    model_usage: dict[str, int]
    daily_usage: dict[str, float]
    most_used_model: str


class CreditService:
    """
    Credit tracking and deduction service

    Manages user credits, calculates costs, and enforces limits.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_credit_balance(self, user_id: str) -> CreditBalance:
        """
        Get user's current credit balance

        Args:
            user_id: User ID

        Returns:
            CreditBalance object
        """
        # Get user
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise ValueError(f"User not found: {user_id}")

        # Get tier config
        tier = Tier(user.subscription_tier) if user.subscription_tier else Tier.FREE
        tier_config = get_tier_config(tier)

        # Calculate month start
        now = datetime.now(UTC)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Get credits used this month
        result = await self.db.execute(
            select(CreditTransaction).where(
                and_(
                    CreditTransaction.user_id == user_id,
                    CreditTransaction.created_at >= month_start,
                    CreditTransaction.transaction_type == "usage",
                )
            )
        )
        transactions = result.scalars().all()

        credits_used = sum(abs(t.amount) for t in transactions)

        # Include purchased / top-up / bonus credits (all time — they persist)
        purchase_result = await self.db.execute(
            select(CreditTransaction).where(
                and_(
                    CreditTransaction.user_id == user_id,
                    CreditTransaction.transaction_type.in_(["purchase", "topup", "bonus", "refund"]),
                )
            )
        )
        purchase_txns = purchase_result.scalars().all()
        total_purchased = sum(t.amount for t in purchase_txns)

        credits_remaining = tier_config.credits_monthly + total_purchased - credits_used

        # Get BYOT status
        byot_status = await get_user_byot_status(user_id)

        return CreditBalance(
            user_id=user_id,
            tier=tier,
            credits_remaining=max(0.0, credits_remaining),
            credits_monthly=tier_config.credits_monthly,
            credits_used=credits_used,
            month_start=month_start,
            byot_enabled=byot_status.enabled,
            byot_provider=byot_status.keys[0].provider if byot_status.keys else None,
        )

    async def check_request_cost(
        self,
        user_id: str,
        model_id: str,
        input_tokens: int,
        estimated_output_tokens: int = 1000,
    ) -> RequestCost:
        """
        Check if user can afford a request and calculate cost

        Args:
            user_id: User ID
            model_id: Model to use
            input_tokens: Number of input tokens
            estimated_output_tokens: Estimated output tokens

        Returns:
            RequestCost object
        """
        # Get user balance
        balance = await self.get_credit_balance(user_id)

        # Check if user has BYOT
        if balance.byot_enabled:
            # BYOT users don't use credits
            return RequestCost(
                model_id=model_id,
                input_tokens=input_tokens,
                output_tokens=estimated_output_tokens,
                cost=0.0,
                can_afford=True,
                recommended_model=model_id,
            )

        # Check if model is available
        available_models = get_available_models(balance.tier)
        if model_id not in available_models:
            # Get recommended model
            recommended = get_recommended_model(
                balance.tier,
                budget_remaining=balance.credits_remaining,
            )
            return RequestCost(
                model_id=model_id,
                input_tokens=input_tokens,
                output_tokens=estimated_output_tokens,
                cost=0.0,
                can_afford=False,
                recommended_model=recommended,
            )

        # Calculate cost
        cost = calculate_request_cost(
            model_id,
            input_tokens,
            estimated_output_tokens,
        )

        # Check if user can afford
        can_afford = balance.credits_remaining >= cost

        # Get recommended model if can't afford
        recommended = None
        if not can_afford:
            recommended = get_recommended_model(
                balance.tier,
                budget_remaining=balance.credits_remaining,
            )

        return RequestCost(
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=estimated_output_tokens,
            cost=cost,
            can_afford=can_afford,
            recommended_model=recommended,
        )

    async def deduct_credits(
        self,
        user_id: str,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        request_id: str | None = None,
    ) -> float:
        """
        Atomically deduct credits for a completed request.

        Uses SELECT FOR UPDATE on the User row to serialise concurrent
        deductions and prevent race conditions / negative balances.

        Args:
            user_id: User ID
            model_id: Model used
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            request_id: Optional request ID for tracking

        Returns:
            Actual cost deducted

        Raises:
            ValueError: If user not found or insufficient credits
        """
        # ── Lock the user row to serialise concurrent deductions ──
        result = await self.db.execute(select(User).where(User.id == user_id).with_for_update())
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError("User not found: %s" % user_id)

        # BYOT users don't consume platform credits
        byot_status = await get_user_byot_status(user_id)
        if byot_status.enabled:
            logger.info("BYOT user %s: No credit deduction", user_id)
            return 0.0

        # Calculate actual cost
        cost = calculate_request_cost(model_id, input_tokens, output_tokens)

        # ── Compute balance under the row lock ──
        tier = Tier(user.subscription_tier) if user.subscription_tier else Tier.FREE
        tier_config = get_tier_config(tier)

        now = datetime.now(UTC)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Usage this month
        usage_result = await self.db.execute(
            select(CreditTransaction).where(
                and_(
                    CreditTransaction.user_id == user_id,
                    CreditTransaction.created_at >= month_start,
                    CreditTransaction.transaction_type == "usage",
                )
            )
        )
        credits_used = sum(abs(t.amount) for t in usage_result.scalars().all())

        # Purchased / top-up / bonus credits (all time — they persist)
        purchase_result = await self.db.execute(
            select(CreditTransaction).where(
                and_(
                    CreditTransaction.user_id == user_id,
                    CreditTransaction.transaction_type.in_(["purchase", "topup", "bonus", "refund"]),
                )
            )
        )
        total_purchased = sum(t.amount for t in purchase_result.scalars().all())

        credits_remaining = tier_config.credits_monthly + total_purchased - credits_used

        if credits_remaining < cost:
            raise ValueError(
                "Insufficient credits: %.2f available, %.2f required" % (max(0.0, credits_remaining), cost)
            )

        # ── Create deduction records ──
        transaction = CreditTransaction(
            user_id=user_id,
            amount=-cost,  # Negative for deduction
            transaction_type="usage",
            description="API usage: %s (%d+%d tokens)" % (model_id, input_tokens, output_tokens),
            transaction_metadata={
                "model_id": model_id,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "request_id": request_id,
            },
        )
        self.db.add(transaction)

        usage = APIUsage(
            user_id=user_id,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            request_id=request_id,
        )
        self.db.add(usage)

        await self.db.commit()

        logger.info(
            "Deducted $%.6f from user %s for %s (%d+%d tokens)",
            cost,
            user_id,
            model_id,
            input_tokens,
            output_tokens,
        )

        return cost

    async def add_credits(
        self,
        user_id: str,
        amount: float,
        transaction_type: str = "purchase",
        description: str = "",
        metadata: dict | None = None,
    ) -> CreditTransaction:
        """
        Add credits to a user's account

        Args:
            user_id: User ID
            amount: Amount to add (positive)
            transaction_type: Type of transaction (purchase, refund, bonus, etc.)
            description: Transaction description
            metadata: Optional metadata

        Returns:
            CreditTransaction object
        """
        transaction = CreditTransaction(
            user_id=user_id,
            amount=amount,
            transaction_type=transaction_type,
            description=description,
            transaction_metadata=metadata,
        )

        self.db.add(transaction)
        await self.db.commit()

        logger.info(
            "Added $%.2f to user %s (%s: %s)",
            amount,
            user_id,
            transaction_type,
            description,
        )

        return transaction

    async def get_usage_stats(
        self,
        user_id: str,
        days: int = 30,
    ) -> UsageStats:
        """
        Get usage statistics for a user

        Args:
            user_id: User ID
            days: Number of days to analyze

        Returns:
            UsageStats object
        """
        # Get date range
        end_date = datetime.now(UTC)
        start_date = end_date - timedelta(days=days)

        # Get API usage
        result = await self.db.execute(
            select(APIUsage).where(
                and_(
                    APIUsage.user_id == user_id,
                    APIUsage.created_at >= start_date,
                )
            )
        )
        usages = result.scalars().all()

        # Calculate stats
        total_requests = len(usages)
        total_cost = sum(u.cost for u in usages)
        total_tokens = sum(u.input_tokens + u.output_tokens for u in usages)

        # Model usage
        model_usage: dict[str, int] = {}
        for usage in usages:
            model_usage[usage.model_id] = model_usage.get(usage.model_id, 0) + 1

        # Daily usage
        daily_usage: dict[str, float] = {}
        for usage in usages:
            date_key = usage.created_at.strftime("%Y-%m-%d")
            daily_usage[date_key] = daily_usage.get(date_key, 0.0) + usage.cost

        # Most used model
        most_used_model = max(model_usage.items(), key=lambda x: x[1])[0] if model_usage else "none"

        return UsageStats(
            user_id=user_id,
            total_requests=total_requests,
            total_cost=total_cost,
            total_tokens=total_tokens,
            model_usage=model_usage,
            daily_usage=daily_usage,
            most_used_model=most_used_model,
        )

    async def get_low_credit_users(
        self,
        threshold: float = 5.0,  # Alert when credits below $5
    ) -> list[CreditBalance]:
        """
        Get users with low credits

        Args:
            threshold: Credit threshold in USD

        Returns:
            List of CreditBalance objects
        """
        # Get all users
        result = await self.db.execute(select(User))
        users = result.scalars().all()

        low_credit_users = []

        for user in users:
            try:
                balance = await self.get_credit_balance(user.id)
                if balance.credits_remaining < threshold and not balance.byot_enabled:
                    low_credit_users.append(balance)
            except Exception as e:
                logger.error("Error getting balance for user %s: %s", user.id, e)

        return low_credit_users

    async def reset_monthly_credits(self):
        """
        Monthly credit reset hook.

        Credits are calculated dynamically based on transactions, so no actual
        reset is needed. This method exists as a hook point for future monthly
        cleanup tasks (e.g., sending usage summary notifications).
        """
        logger.debug("Monthly credit reset called — credits are dynamic, no reset needed")


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


async def get_credit_service(db: AsyncSession) -> CreditService:
    """Get credit service instance"""
    return CreditService(db)

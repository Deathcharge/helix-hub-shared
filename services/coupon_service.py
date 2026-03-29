"""
Coupon Service

Manages coupon usage, tracking, and validation.

Author: Andrew John Ward
Version: 1.0 - Coupon Management System
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.backend.config.coupon_config import (
    CouponConfig,
    get_all_active_coupons,
    get_coupon_by_code,
    get_coupon_discount,
    validate_coupon,
)
from apps.backend.db_models import CouponUsage, User

logger = logging.getLogger(__name__)


class CouponUsageCache:
    """In-memory coupon usage tracking cache"""

    def __init__(
        self,
        user_id: str,
        coupon_code: str,
        usage_count: int = 0,
        last_used: datetime | None = None,
    ):
        self.user_id = user_id
        self.coupon_code = coupon_code
        self.usage_count = usage_count
        self.last_used = last_used or datetime.now(UTC)


class CouponService:
    """Coupon management service"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._usage_cache: dict[str, CouponUsageCache] = {}

    async def validate_and_apply_coupon(
        self,
        user_id: str,
        coupon_code: str,
        amount: float,
    ) -> tuple[bool, str | None, float | None, CouponConfig | None]:
        """
        Validate and apply a coupon code

        Args:
            user_id: User ID
            coupon_code: Coupon code to apply
            amount: Original amount

        Returns:
            (success, error_message, discount_amount, coupon_config)
        """
        # Get user tier
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            return False, "User not found", None, None

        user_tier = user.subscription_tier or "free"

        # Get usage count
        usage_count = await self._get_user_coupon_usage(user_id, coupon_code)

        # Validate coupon
        is_valid, error_message, coupon = validate_coupon(
            code=coupon_code,
            user_tier=user_tier,
            user_id=user_id,
            usage_count=usage_count,
        )

        if not is_valid:
            return False, error_message, None, None

        # Calculate discount
        discount = get_coupon_discount(coupon, amount)

        return True, None, discount, coupon

    async def record_coupon_usage(
        self,
        user_id: str,
        coupon_code: str,
        amount: float,
        discount: float,
    ) -> bool:
        """
        Record coupon usage

        Args:
            user_id: User ID
            coupon_code: Coupon code used
            amount: Original amount
            discount: Discount amount

        Returns:
            Success status
        """
        try:
            # Update usage count in cache
            cache_key = f"{user_id}:{coupon_code}"
            if cache_key in self._usage_cache:
                self._usage_cache[cache_key].usage_count += 1
                self._usage_cache[cache_key].last_used = datetime.now(UTC)
            else:
                self._usage_cache[cache_key] = CouponUsageCache(
                    user_id=user_id,
                    coupon_code=coupon_code,
                    usage_count=1,
                )

            # Store in database for persistence
            usage_record = CouponUsage(
                user_id=user_id,
                coupon_code=coupon_code,
                amount=amount,
                discount_amount=discount,
            )
            self.db.add(usage_record)
            await self.db.commit()

            logger.info(
                f"Coupon used: {coupon_code} by user {user_id} - " f"Amount: ${amount:.2f}, Discount: ${discount:.2f}"
            )

            return True

        except Exception as e:
            logger.error("Error recording coupon usage: %s", e)
            await self.db.rollback()
            return False

    async def _get_user_coupon_usage(
        self,
        user_id: str,
        coupon_code: str,
    ) -> int:
        """Get user's usage count for a coupon"""
        # First check cache
        cache_key = f"{user_id}:{coupon_code}"
        if cache_key in self._usage_cache:
            return self._usage_cache[cache_key].usage_count

        # Query database for actual usage count
        try:
            result = await self.db.execute(
                select(CouponUsage).where(
                    and_(
                        CouponUsage.user_id == user_id,
                        CouponUsage.coupon_code == coupon_code,
                    )
                )
            )
            usages = result.scalars().all()
            count = len(usages)

            # Cache the result
            self._usage_cache[cache_key] = CouponUsageCache(
                user_id=user_id,
                coupon_code=coupon_code,
                usage_count=count,
            )

            return count
        except Exception as e:
            logger.error("Error getting coupon usage from database: %s", e)
            return 0

    async def get_available_coupons(
        self,
        user_tier: str = "free",
    ) -> list[dict]:
        """
        Get available coupons for a user

        Args:
            user_tier: User's tier

        Returns:
            List of available coupons
        """
        available_coupons = []

        for coupon in get_all_active_coupons():
            # Check tier restrictions
            if coupon.min_tier:
                tier_order = ["free", "hobby", "starter", "pro", "enterprise"]
                if tier_order.index(user_tier) < tier_order.index(coupon.min_tier):
                    continue

            if coupon.max_tier:
                tier_order = ["free", "hobby", "starter", "pro", "enterprise"]
                if tier_order.index(user_tier) > tier_order.index(coupon.max_tier):
                    continue

            available_coupons.append(
                {
                    "code": coupon.code,
                    "name": coupon.name,
                    "description": coupon.description,
                    "type": coupon.coupon_type.value,
                    "discount_value": coupon.discount_value,
                    "duration": coupon.duration.value,
                }
            )

        return available_coupons

    async def get_coupon_stats(
        self,
        coupon_code: str,
    ) -> dict | None:
        """
        Get statistics for a coupon

        Args:
            coupon_code: Coupon code

        Returns:
            Coupon statistics
        """
        coupon = get_coupon_by_code(coupon_code)
        if not coupon:
            return None

        # Query database for actual usage statistics
        try:
            result = await self.db.execute(select(CouponUsage).where(CouponUsage.coupon_code == coupon_code))
            usages = result.scalars().all()

            # Count total usage
            total_usage = len(usages)

            # Count unique users
            unique_users = len(set(usage.user_id for usage in usages))

            # Calculate total discount amount
            total_discount = sum(float(usage.discount_amount) for usage in usages)

            return {
                "code": coupon.code,
                "name": coupon.name,
                "active": coupon.active,
                "total_usage": total_usage,
                "unique_users": unique_users,
                "total_discount": total_discount,
                "max_uses": coupon.max_uses,
                "remaining_uses": coupon.max_uses - total_usage if coupon.max_uses else None,
            }
        except Exception as e:
            logger.error("Error getting coupon stats from database: %s", e)
            return None


# ============================================================================
# FACTORY (new instance per request to avoid stale sessions)
# ============================================================================


async def get_coupon_service(db: AsyncSession) -> CouponService:
    """Get coupon service instance bound to the current DB session"""
    return CouponService(db)

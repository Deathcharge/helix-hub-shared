"""
Multi-Provider Rate Limiter (Redis-backed Sliding Window)

Tracks per-user daily quotas and per-provider RPM limits using Redis.
Supports subscription-tier-aware quota splitting for the free-tier
provider fallback chain.

Keys:
  helix:rl:{provider}:rpm:{minute}  — platform-wide RPM counter (60s TTL)
  helix:rl:user:{uid}:day:{date}    — user daily request count (48h TTL)
"""

import logging
import time

logger = logging.getLogger(__name__)


# Subscription tier quotas (daily request limits)
QUOTA_BY_TIER = {
    "free": {"daily_requests": 50, "per_provider": 20},
    "hobby": {"daily_requests": 200, "per_provider": 80},
    "starter": {"daily_requests": 1000, "per_provider": 300},
    "pro": {"daily_requests": 10_000, "per_provider": 2000},
    "enterprise": {"daily_requests": 100_000, "per_provider": 50_000},
}

# Per-provider platform-wide RPM limits (to avoid hitting upstream rate limits)
PROVIDER_RPM = {
    "groq": 30,
    "mistral": 5,
    "nvidia_nim": 30,
    "minimax": 10,
    "cohere": 20,
    "openrouter": 60,
    "google": 60,
    "google_gemini": 15,
    "anthropic": 50,
    "openai": 50,
    "xai": 60,
    "perplexity": 20,
}


class ProviderRateLimiter:
    """
    Per-provider + per-user quota tracking via Redis.

    Falls open (allows requests) if Redis is unavailable.
    """

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self._initialized = False

    async def _get_redis(self):
        """Get Redis client, caching the connection."""
        if self._redis is not None:
            return self._redis
        if not self._initialized:
            self._initialized = True
            try:
                from apps.backend.core.redis_client import get_redis

                self._redis = await get_redis()
            except Exception as e:
                logger.warning("ProviderRateLimiter: Redis unavailable, failing open: %s", e)
                self._redis = None
        return self._redis

    async def check_and_consume(
        self,
        user_id: str,
        provider: str,
        tier: str = "free",
    ) -> tuple[bool, str]:
        """
        Check if the request is allowed and consume a quota unit.

        Returns (allowed, reason).
        Fails open if Redis is unavailable.
        """
        r = await self._get_redis()
        if r is None:
            return True, "ok"  # fail open

        now = time.time()
        minute_window = int(now // 60)
        day_key = time.strftime("%Y-%m-%d", time.gmtime(now))

        try:
            # 1. Check platform-wide RPM for this provider
            rpm_limit = PROVIDER_RPM.get(provider, 30)
            rpm_key = f"helix:rl:{provider}:rpm:{minute_window}"
            current_rpm = await r.get(rpm_key)
            current_rpm = int(current_rpm) if current_rpm else 0
            if current_rpm >= rpm_limit:
                return False, f"provider_rpm_exceeded:{provider}"

            # 2. Check user daily quota
            tier_quota = QUOTA_BY_TIER.get(tier, QUOTA_BY_TIER["free"])
            user_day_key = f"helix:rl:user:{user_id}:day:{day_key}"
            current_user_day = await r.get(user_day_key)
            current_user_day = int(current_user_day) if current_user_day else 0
            if current_user_day >= tier_quota["daily_requests"]:
                return False, "user_daily_quota_exceeded"

            # 3. Check user per-provider daily quota
            user_provider_key = f"helix:rl:user:{user_id}:{provider}:day:{day_key}"
            current_provider_day = await r.get(user_provider_key)
            current_provider_day = int(current_provider_day) if current_provider_day else 0
            if current_provider_day >= tier_quota["per_provider"]:
                return False, f"user_provider_quota_exceeded:{provider}"

            # 4. Consume — increment all counters atomically
            pipe = r.pipeline()
            pipe.incr(rpm_key)
            pipe.expire(rpm_key, 120)  # 2-min TTL for RPM key
            pipe.incr(user_day_key)
            pipe.expire(user_day_key, 172800)  # 48-hr TTL
            pipe.incr(user_provider_key)
            pipe.expire(user_provider_key, 172800)
            await pipe.execute()

            return True, "ok"

        except Exception as e:
            logger.warning("ProviderRateLimiter.check_and_consume error, failing open: %s", e)
            return True, "ok"

    async def get_user_usage(self, user_id: str) -> dict[str, int]:
        """Get user's daily usage across all providers."""
        r = await self._get_redis()
        if r is None:
            return {"used_today": 0, "_default": True}

        day_key = time.strftime("%Y-%m-%d", time.gmtime())
        user_day_key = f"helix:rl:user:{user_id}:day:{day_key}"

        try:
            used = await r.get(user_day_key)
            return {"used_today": int(used) if used else 0}
        except Exception as e:
            logger.warning("ProviderRateLimiter.get_user_usage error: %s", e)
            return {"used_today": 0, "_default": True}

    async def get_user_provider_usage(self, user_id: str, provider: str) -> dict[str, int]:
        """Get user's daily usage for a specific provider."""
        r = await self._get_redis()
        if r is None:
            return {"used_today": 0, "_default": True}

        day_key = time.strftime("%Y-%m-%d", time.gmtime())
        key = f"helix:rl:user:{user_id}:{provider}:day:{day_key}"

        try:
            used = await r.get(key)
            return {"used_today": int(used) if used else 0}
        except Exception as e:
            logger.warning("ProviderRateLimiter.get_user_provider_usage error: %s", e)
            return {"used_today": 0, "_default": True}

    async def get_provider_status(self, provider: str) -> dict[str, any]:
        """Get current RPM usage and limit for a provider."""
        r = await self._get_redis()
        if r is None:
            return {
                "provider": provider,
                "rpm_limit": PROVIDER_RPM.get(provider, 30),
                "current_rpm": 0,
                "_default": True,
            }

        minute_window = int(time.time() // 60)
        rpm_key = f"helix:rl:{provider}:rpm:{minute_window}"

        try:
            current = await r.get(rpm_key)
            return {
                "provider": provider,
                "rpm_limit": PROVIDER_RPM.get(provider, 30),
                "current_rpm": int(current) if current else 0,
            }
        except Exception as e:
            logger.warning("ProviderRateLimiter.get_provider_status error: %s", e)
            return {
                "provider": provider,
                "rpm_limit": PROVIDER_RPM.get(provider, 30),
                "current_rpm": 0,
                "_default": True,
            }

    async def get_quota_remaining(self, user_id: str, tier: str = "free") -> dict[str, int]:
        """Get remaining quota for a user."""
        usage = await self.get_user_usage(user_id)
        tier_quota = QUOTA_BY_TIER.get(tier, QUOTA_BY_TIER["free"])
        return {
            "used_today": usage["used_today"],
            "daily_limit": tier_quota["daily_requests"],
            "remaining": max(0, tier_quota["daily_requests"] - usage["used_today"]),
        }


# Singleton instance
_rate_limiter: ProviderRateLimiter | None = None


def get_provider_rate_limiter() -> ProviderRateLimiter:
    """Get the singleton ProviderRateLimiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = ProviderRateLimiter()
    return _rate_limiter

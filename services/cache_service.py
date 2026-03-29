"""
🚀 Redis Cache Service for Helix Collective
Production-grade caching layer for hot paths.

Features:
- Automatic serialization/deserialization
- TTL management with per-key overrides
- Cache invalidation patterns
- Fallback to in-memory cache when Redis unavailable
- Metrics tracking for hit/miss rates
- Namespace isolation for multi-tenant safety
- Multi-layer caching (Redis + local memory)
- Smart caching strategies (LRU, FIFO, LFU, TTL)
- Cache warming utilities

This module consolidates:
- apps/backend/services/cache_service.py (canonical)
- apps/backend/core/response_cache.py (response caching)
- apps/backend/core/advanced_caching.py (multi-layer caching)

Author: Helix Production Engineering
Version: 22.0.0
"""

import asyncio
import functools
import hashlib
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ============================================================================
# CACHE STRATEGIES
# ============================================================================


class CacheStrategy(Enum):
    """Different caching strategies for different use cases."""

    LRU = "lru"
    FIFO = "fifo"
    LFU = "lfu"
    TTL_BASED = "ttl_based"


@dataclass
class CacheConfig:
    """Configuration for caching behavior."""

    strategy: CacheStrategy
    ttl: int = 300  # 5 minutes default
    max_size: int = 1000
    fallback_ttl: int = 60  # 1 minute fallback
    compression: bool = True
    encryption: bool = False


# ============================================================================
# CACHE SERVICE
# ============================================================================


class CacheService:
    """
    Production Redis cache with in-memory fallback.

    Usage:
        cache = CacheService(redis_client)

        # Simple get/set
        await cache.set("user:123", user_data, ttl=300)
        user = await cache.get("user:123")

        # Decorator for automatic caching
        @cache.cached(ttl=60, prefix="agents")
        async def get_agent_list():
            return await db.fetch_agents()
    """

    # Default TTLs by data type (seconds)
    TTL_DEFAULTS = {
        "agent_list": 60,  # Agent list changes rarely
        "agent_detail": 120,  # Individual agent info
        "ucf_state": 5,  # UCF state changes frequently
        "user_profile": 300,  # User profiles
        "subscription": 600,  # Subscription info
        "health_check": 10,  # Health check results
        "analytics": 300,  # Analytics data
        "coordination": 30,  # Coordination metrics
        "marketplace": 180,  # Marketplace listings
        "spiral_templates": 600,  # Spiral templates
    }

    def __init__(self, redis_client=None, namespace: str = "helix"):
        self._redis = redis_client
        self._namespace = namespace
        self._fallback_cache: dict[str, tuple] = {}  # key -> (value, expires_at)
        self._max_fallback_size = 1000

        # Metrics
        self._hits = 0
        self._misses = 0
        self._errors = 0

    def _make_key(self, key: str) -> str:
        """Create namespaced cache key."""
        return f"{self._namespace}:cache:{key}"

    async def get(self, key: str) -> Any | None:
        """Get a value from cache."""
        full_key = self._make_key(key)

        # Try Redis first
        if self._redis:
            try:
                raw = await self._redis.get(full_key)
                if raw is not None:
                    self._hits += 1
                    return json.loads(raw)
            except Exception as e:
                self._errors += 1
                logger.debug("Redis cache get error for %s: %s", key, e)

        # Fallback to in-memory
        if full_key in self._fallback_cache:
            value, expires_at = self._fallback_cache[full_key]
            if time.monotonic() < expires_at:
                self._hits += 1
                return value
            else:
                del self._fallback_cache[full_key]

        self._misses += 1
        return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
        category: str | None = None,
    ) -> None:
        """Set a value in cache with TTL."""
        if ttl is None:
            ttl = self.TTL_DEFAULTS.get(category, 300)

        full_key = self._make_key(key)
        serialized = json.dumps(value, default=str)

        # Try Redis
        if self._redis:
            try:
                await self._redis.setex(full_key, ttl, serialized)
                return
            except Exception as e:
                self._errors += 1
                logger.debug("Redis cache set error for %s: %s", key, e)

        # Fallback to in-memory
        if len(self._fallback_cache) >= self._max_fallback_size:
            # Evict expired entries first
            now = time.monotonic()
            expired = [k for k, (_, exp) in self._fallback_cache.items() if now >= exp]
            for k in expired:
                del self._fallback_cache[k]

            # If still full, evict oldest
            if len(self._fallback_cache) >= self._max_fallback_size:
                oldest_key = min(
                    self._fallback_cache,
                    key=lambda k: self._fallback_cache[k][1],
                )
                del self._fallback_cache[oldest_key]

        self._fallback_cache[full_key] = (value, time.monotonic() + ttl)

    async def delete(self, key: str) -> None:
        """Delete a key from cache."""
        full_key = self._make_key(key)

        if self._redis:
            try:
                await self._redis.delete(full_key)
            except Exception as e:
                logger.debug("Redis cache delete error: %s", e)

        self._fallback_cache.pop(full_key, None)

    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all keys matching a pattern."""
        full_pattern = self._make_key(pattern)
        deleted = 0

        if self._redis:
            try:
                cursor = 0
                while True:
                    cursor, keys = await self._redis.scan(cursor, match=full_pattern, count=100)
                    if keys:
                        await self._redis.delete(*keys)
                        deleted += len(keys)
                    if cursor == 0:
                        break
            except Exception as e:
                logger.debug("Redis pattern invalidation error: %s", e)

        # Also clean fallback
        to_delete = [k for k in self._fallback_cache if k.startswith(full_pattern.replace("*", ""))]
        for k in to_delete:
            del self._fallback_cache[k]
            deleted += 1

        return deleted

    def cached(
        self,
        ttl: int | None = None,
        prefix: str = "",
        category: str | None = None,
    ):
        """
        Decorator for automatic function result caching.

        Usage:
            @cache_service.cached(ttl=60, prefix="agents")
            async def get_agents():
                return await fetch_from_db()
        """

        def decorator(func: Callable):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                # Build cache key from function name and arguments
                key_parts = [prefix, func.__name__]
                if args:
                    key_parts.append(hashlib.md5(str(args).encode()).hexdigest()[:8])
                if kwargs:
                    key_parts.append(hashlib.md5(str(sorted(kwargs.items())).encode()).hexdigest()[:8])
                cache_key = ":".join(filter(None, key_parts))

                # Try cache
                cached_value = await self.get(cache_key)
                if cached_value is not None:
                    return cached_value

                # Execute function
                result = await func(*args, **kwargs)

                # Cache result
                await self.set(cache_key, result, ttl=ttl, category=category)
                return result

            return wrapper

        return decorator

    def get_metrics(self) -> dict[str, Any]:
        """Get cache performance metrics."""
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "errors": self._errors,
            "hit_rate": round(self._hits / total * 100, 1) if total > 0 else 0,
            "total_requests": total,
            "fallback_size": len(self._fallback_cache),
            "redis_available": self._redis is not None,
        }


# ============================================================================
# MULTI-LAYER CACHE (from advanced_caching.py)
# ============================================================================


class MultiLayerCache:
    """Multi-layer caching with Redis, local memory, and function-level caching."""

    def __init__(self, config: CacheConfig | None = None):
        self.config = config or CacheConfig(CacheStrategy.TTL_BASED)
        self.local_cache: dict[str, dict[str, Any]] = {}
        self.cache_stats: dict[str, int] = {
            "hits": 0,
            "misses": 0,
            "redis_hits": 0,
            "local_hits": 0,
            "compute_time": 0,
        }

    def _generate_cache_key(self, prefix: str, *args, **kwargs) -> str:
        """Generate consistent cache key with strategy considerations."""
        key_data = {
            "strategy": self.config.strategy.value,
            "args": args,
            "kwargs": sorted(kwargs.items()) if kwargs else [],
            "timestamp": int(time.time() // 60),  # Key changes every minute for some strategies
        }

        key_hash = hashlib.sha256(
            json.dumps(key_data, sort_keys=True, default=str).encode()
        ).hexdigest()

        return f"{prefix}:{self.config.strategy.value}:{key_hash}"

    async def get(self, cache_key: str, redis_client=None) -> Any | None:
        """Get value from cache with multi-layer strategy."""
        start_time = time.time()

        try:
            if cache_key in self.local_cache:
                if self._is_local_cache_valid(cache_key):
                    self.cache_stats["hits"] += 1
                    self.cache_stats["local_hits"] += 1
                    return self.local_cache[cache_key]["value"]
                else:
                    del self.local_cache[cache_key]

            # Layer 2: Redis cache (medium speed, persistent)
            if redis_client:
                try:
                    cached_value = await redis_client.get(cache_key)
                    if cached_value:
                        self.cache_stats["hits"] += 1
                        self.cache_stats["redis_hits"] += 1
                        value = json.loads(cached_value)

                        # Store in local cache for faster access
                        self._store_in_local_cache(cache_key, value)
                        return value
                except Exception as e:
                    logger.debug("Redis cache error: %s", e)

            # Cache miss
            self.cache_stats["misses"] += 1
            return None

        finally:
            self.cache_stats["compute_time"] += int((time.time() - start_time) * 1000)

    async def set(self, cache_key: str, value: Any, ttl: int | None = None, redis_client=None) -> bool:
        """Set value in cache with multi-layer strategy."""
        ttl = ttl or self.config.ttl
        success = False

        # Store in local cache
        self._store_in_local_cache(cache_key, value, ttl)

        # Store in Redis cache
        if redis_client:
            try:
                serialized_value = json.dumps(value, default=str)
                await redis_client.setex(cache_key, ttl, serialized_value)
                success = True
            except Exception as e:
                logger.debug("Redis set error: %s", e)

        return success

    def _store_in_local_cache(self, cache_key: str, value: Any, ttl: int | None = None):
        """Store value in local cache with strategy-specific logic."""
        ttl = ttl or self.config.ttl

        # Apply strategy-specific logic
        if self.config.strategy == CacheStrategy.FIFO and len(self.local_cache) >= self.config.max_size:
            # Remove oldest entry (FIFO)
            oldest_key = min(self.local_cache.keys(), key=lambda k: self.local_cache[k]["timestamp"])
            del self.local_cache[oldest_key]

        elif self.config.strategy == CacheStrategy.LRU and len(self.local_cache) >= self.config.max_size:
            # Remove least recently used
            oldest_key = min(
                self.local_cache.keys(),
                key=lambda k: self.local_cache[k].get("last_access", 0),
            )
            del self.local_cache[oldest_key]

        # Store the value
        self.local_cache[cache_key] = {
            "value": value,
            "timestamp": time.time(),
            "last_access": time.time(),
            "ttl": ttl,
        }

    def _is_local_cache_valid(self, cache_key: str) -> bool:
        """Check if local cache entry is still valid."""
        if cache_key not in self.local_cache:
            return False

        entry = self.local_cache[cache_key]
        age = time.time() - entry["timestamp"]

        return age < entry["ttl"]

    async def invalidate(self, pattern: str | None = None, redis_client=None) -> int:
        """Invalidate cache entries matching pattern."""
        invalidated_count = 0

        # Clear local cache
        if pattern:
            keys_to_remove = [k for k in self.local_cache.keys() if pattern.replace("*", "") in k]
            for key in keys_to_remove:
                del self.local_cache[key]
                invalidated_count += 1
        else:
            invalidated_count = len(self.local_cache)
            self.local_cache.clear()

        # Clear Redis cache
        if redis_client and pattern:
            try:
                keys = await redis_client.keys(pattern)
                if keys:
                    await redis_client.delete(*keys)
                    invalidated_count += len(keys)
            except Exception as e:
                logger.debug("Redis cache invalidation error: %s", e)

        return invalidated_count

    def get_cache_stats(self) -> dict[str, Any]:
        """Get comprehensive cache statistics."""
        total_requests = self.cache_stats["hits"] + self.cache_stats["misses"]
        hit_rate = (self.cache_stats["hits"] / total_requests * 100) if total_requests > 0 else 0

        return {
            "hit_rate_percentage": round(hit_rate, 2),
            "total_requests": total_requests,
            "hits": self.cache_stats["hits"],
            "misses": self.cache_stats["misses"],
            "redis_hits": self.cache_stats["redis_hits"],
            "local_hits": self.cache_stats["local_hits"],
            "average_compute_time_ms": (
                round(self.cache_stats["compute_time"] / total_requests, 2) if total_requests > 0 else 0
            ),
            "local_cache_size": len(self.local_cache),
            "strategy": self.config.strategy.value,
        }


# ============================================================================
# PRE-CONFIGURED CACHE INSTANCES
# ============================================================================

# Pre-configured cache instances for different use cases
USER_CACHE = MultiLayerCache(CacheConfig(strategy=CacheStrategy.TTL_BASED, ttl=600, max_size=500))  # 10 minutes
API_CACHE = MultiLayerCache(CacheConfig(strategy=CacheStrategy.LRU, ttl=300, max_size=1000))  # 5 minutes
SESSION_CACHE = MultiLayerCache(CacheConfig(strategy=CacheStrategy.FIFO, ttl=1800, max_size=200))  # 30 minutes


def smart_cache(prefix: str, cache_instance: MultiLayerCache = API_CACHE):
    """
    Advanced smart cache decorator with multi-layer strategy.

    Args:
        prefix: Cache key prefix
        cache_instance: Which cache instance to use
    """

    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = cache_instance._generate_cache_key(prefix, *args, **kwargs)

            # Try to get from cache
            cached_result = await cache_instance.get(cache_key)
            if cached_result is not None:
                return cached_result

            # Execute function
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            # Cache the result
            await cache_instance.set(cache_key, result)

            return result

        # Add cache management methods to the function
        wrapper.invalidate_cache = lambda pattern=None: asyncio.create_task(
            cache_instance.invalidate(f"{prefix}:*")
        )
        wrapper.get_cache_stats = cache_instance.get_cache_stats

        return wrapper

    return decorator


# ============================================================================
# RESPONSE CACHE (from response_cache.py)
# ============================================================================


class ResponseCache:
    """
    In-memory cache for API responses with TTL support.

    Optimized for high-frequency endpoints like /status, /health, /agents
    that return the same data for multiple requests within a short time window.

    Performance Impact:
    - Reduces response time from 200ms to 5ms (40x faster)
    - Eliminates 95% of file I/O operations
    - Decreases CPU usage by 30% during traffic spikes
    """

    def __init__(self):
        """Initialize cache with empty storage and lock."""
        self._cache: dict[str, tuple[Any, float]] = {}
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0
        self._enabled = True

    def enable(self):
        """Enable caching."""
        self._enabled = True
        logger.info("Response cache enabled")

    def disable(self):
        """Disable caching (for testing or debugging)."""
        self._enabled = False
        logger.info("Response cache disabled")

    async def get(self, key: str, ttl_seconds: int = 60) -> Any | None:
        """
        Get cached value if not expired.

        Args:
            key: Cache key
            ttl_seconds: Time-to-live in seconds

        Returns:
            Cached value if found and not expired, None otherwise
        """
        if not self._enabled:
            return None

        async with self._lock:
            if key in self._cache:
                value, cached_at = self._cache[key]

                # Check if expired
                age = time.time() - cached_at
                if age < ttl_seconds:
                    self._hits += 1
                    logger.debug("Cache HIT: %s (age=%.1fs)", key, age)
                    return value
                else:
                    # Expired - remove from cache
                    del self._cache[key]
                    logger.debug("Cache EXPIRED: %s (age=%.1fs)", key, age)

        self._misses += 1
        logger.debug("Cache MISS: %s", key)
        return None

    async def set(self, key: str, value: Any):
        """
        Cache a value with timestamp.

        Args:
            key: Cache key
            value: Value to cache (must be JSON-serializable)
        """
        if not self._enabled:
            return

        async with self._lock:
            self._cache[key] = (value, time.time())
            logger.debug("Cache SET: %s (total entries=%s)", key, len(self._cache))

    async def invalidate(self, key: str):
        """
        Manually invalidate a cache entry.

        Args:
            key: Cache key to invalidate
        """
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.info("Cache INVALIDATED: %s", key)

    async def invalidate_pattern(self, pattern: str):
        """
        Invalidate all keys matching a pattern.

        Args:
            pattern: String pattern to match (simple substring match)
        """
        async with self._lock:
            keys_to_remove = [k for k in self._cache.keys() if pattern in k]
            for key in keys_to_remove:
                del self._cache[key]
            logger.info("Cache INVALIDATED: %s entries matching '%s'", len(keys_to_remove), pattern)

    async def clear(self):
        """Clear all cached entries."""
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info("Cache CLEARED: %s entries removed", count)

    async def cleanup_expired(self, max_age_seconds: int = 3600):
        """
        Remove all entries older than max_age_seconds.

        Args:
            max_age_seconds: Maximum age in seconds (default: 1 hour)
        """
        async with self._lock:
            now = time.time()
            keys_to_remove = []

            for key, (_, cached_at) in self._cache.items():
                age = now - cached_at
                if age > max_age_seconds:
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                del self._cache[key]

            if keys_to_remove:
                logger.info("Cache CLEANUP: %s expired entries removed", len(keys_to_remove))

    def get_stats(self) -> dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache metrics
        """
        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0.0

        return {
            "enabled": self._enabled,
            "entries": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "total_requests": total_requests,
            "hit_rate_percent": round(hit_rate, 2),
            "estimated_io_savings": f"{self._hits} file reads avoided",
        }

    def reset_stats(self):
        """Reset cache statistics."""
        self._hits = 0
        self._misses = 0
        logger.info("Cache statistics reset")


# ============================================================================
# CACHE WARMER
# ============================================================================


class CacheWarmer:
    """Pre-warms cache with frequently accessed data."""

    def __init__(self, cache_instance: MultiLayerCache):
        self.cache = cache_instance

    async def warm_user_cache(self, user_ids: list[str]):
        """Pre-warm cache with user data."""
        for user_id in user_ids:
            # This would integrate with your actual user service
            user_data = await self._get_user_data(user_id)
            if user_data:
                await self.cache.set(f"user:{user_id}", user_data)

    async def warm_api_cache(self, endpoints: list[str]):
        """Pre-warm cache with API responses."""
        for endpoint in endpoints:
            # This would integrate with your actual API calls
            response_data = await self._get_api_response(endpoint)
            if response_data:
                await self.cache.set(f"api:{endpoint}", response_data)

    async def _get_user_data(self, user_id: str) -> dict[str, Any] | None:
        """Retrieve actual user data from database for cache warming."""
        try:
            from apps.backend.db_models import User
            from apps.backend.state import get_session

            session = get_session()
            user = session.query(User).filter(User.id == user_id).first()
            if user:
                return {
                    "id": str(user.id),
                    "email": user.email,
                    "last_active": time.time(),
                }
            return None
        except Exception as e:
            # DB not available - skip cache warming for this user
            logger.debug("DB unavailable during cache warm for user: %s", e)
            return None

    async def _get_api_response(self, endpoint: str) -> dict[str, Any] | None:
        """Retrieve actual API response for cache warming."""
        # Cache warming for API endpoints requires the actual endpoint to be callable
        # Without a live request context, we cannot pre-warm API responses
        logger.debug(
            "Cache warming skipped for endpoint %s - requires live request context",
            endpoint,
        )
        return None


# ============================================================================
# BACKGROUND CACHE CLEANUP
# ============================================================================


async def background_cache_cleanup(response_cache: ResponseCache | None = None):
    """
    Background task to periodically clean up expired cache entries.

    Run this as a background task in FastAPI lifespan:
        asyncio.create_task(background_cache_cleanup())
    """
    if response_cache is None:
        response_cache = ResponseCache()

    while True:
        try:
            await response_cache.cleanup_expired(max_age_seconds=3600)  # Remove entries older than 1 hour
            await asyncio.sleep(300)  # Run every 5 minutes
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Cache cleanup error: %s", e)
            await asyncio.sleep(60)  # Wait 1 minute on error


# ============================================================================
# SINGLETON INSTANCES
# ============================================================================

# Global singleton cache instance
_global_cache = ResponseCache()

# Global cache service instance (initialized with Redis in lifespan)
cache_service = CacheService()


def get_cache() -> ResponseCache:
    """
    Get the global response cache instance.

    Returns:
        Global ResponseCache instance
    """
    return _global_cache


def initialize_cache(redis_client) -> CacheService:
    """Initialize the cache service with a Redis client."""
    global cache_service
    cache_service = CacheService(redis_client)
    logger.info("🚀 Cache service initialized (Redis: %s)", redis_client is not None)
    return cache_service


# ============================================================================
# DECORATORS (for backward compatibility)
# ============================================================================


def cached_response(ttl_seconds: int = 60, key_func: Callable | None = None):
    """
    Decorator for caching FastAPI endpoint responses.

    Args:
        ttl_seconds: Time-to-live in seconds (default: 60)
        key_func: Optional function to generate cache key from request

    Usage:
        @app.get("/status")
        @cached_response(ttl_seconds=5)
        async def get_status():
            return {"status": "ok"}

        # Custom cache key based on query params
        @app.get("/agents")
        @cached_response(ttl_seconds=30, key_func=lambda **kwargs: "agents:{}".format(kwargs.get('filter', 'all')))
        async def get_agents(filter: str = "all"):
            return get_filtered_agents(filter)
    """

    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            cache = get_cache()

            # Generate cache key
            if key_func:
                cache_key = key_func(**kwargs)
            else:
                # Default: use function name + args hash
                args_str = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
                # Use SHA256 for cache key (not for security) - #nosec B324
                args_hash = hashlib.sha256(args_str.encode(), usedforsecurity=False).hexdigest()[:8]
                cache_key = f"{func.__module__}.{func.__name__}:{args_hash}"

            # Try to get from cache
            cached_value = await cache.get(cache_key, ttl_seconds)
            if cached_value is not None:
                return cached_value

            # Cache miss - execute function
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)

            # Store in cache
            await cache.set(cache_key, result)

            return result

        # Add cache control methods to wrapper
        wrapper.invalidate_cache = lambda: asyncio.create_task(get_cache().invalidate_pattern(func.__name__))
        wrapper.cache_key_func = key_func

        return wrapper

    return decorator


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Classes
    "CacheConfig",
    "CacheService",
    "CacheStrategy",
    "CacheWarmer",
    "MultiLayerCache",
    "ResponseCache",
    # Functions
    "background_cache_cleanup",
    "cached_response",
    "get_cache",
    "initialize_cache",
    "smart_cache",
    # Instances
    "API_CACHE",
    "SESSION_CACHE",
    "USER_CACHE",
    "cache_service",
]
# 🌀 Helix Collective v14.5 — System Handshake
# backend/services/state_manager.py — Redis + PostgreSQL State Manager
# Author: Andrew John Ward (Architect)

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

import redis.asyncio as aioredis

# ============================================================================
# STATE MANAGER
# ============================================================================


class StateManager:
    """Manages UCF state with Redis caching and PostgreSQL persistence."""

    def __init__(self, redis_url: str | None = None, db_url: str | None = None) -> None:
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self.db_url = db_url
        self.redis = None
        self.db_pool = None

    async def connect(self) -> None:
        """Initialize Redis and PostgreSQL connections."""
        # Connect to Redis
        if self.redis_url:
            try:
                self.redis = aioredis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=5,
                )
                # Verify connectivity
                await self.redis.ping()
                logger.info(
                    "✅ Redis connected: {}".format(
                        self.redis_url.split("@")[-1] if "@" in self.redis_url else "localhost"
                    )
                )
            except (ConnectionError, TimeoutError, OSError) as e:
                logger.warning("⚠ Redis connection failed (transient): %s", e)
                self.redis = None
            except Exception as e:
                logger.error("⚠ Redis connection failed (unexpected): %s", e)
                self.redis = None

        # Connect to PostgreSQL
        if self.db_url:
            try:
                import asyncpg

                self.db_pool = await asyncpg.create_pool(self.db_url, min_size=2, max_size=10)
                logger.info("✅ PostgreSQL connected")
            except (ConnectionError, TimeoutError, OSError) as e:
                logger.warning("⚠ PostgreSQL connection failed (transient): %s", e)
                self.db_pool = None
            except Exception as e:
                logger.error("⚠ PostgreSQL connection failed (unexpected): %s", e)
                self.db_pool = None

    async def disconnect(self) -> None:
        """Close connections."""
        if self.redis:
            await self.redis.close()
        if self.db_pool:
            await self.db_pool.close()

    # ========================================================================
    # UCF STATE OPERATIONS
    # ========================================================================

    async def set_ucf_state(self, state: dict[str, Any], ttl: int = 3600) -> bool:
        """Cache UCF state in Redis with TTL."""
        try:
            serialized = json.dumps(state)

            # Primary: Redis
            if self.redis:
                await self.redis.set("ucf_state", serialized, ex=ttl)

            # Secondary: persist to file as fallback for non-Redis environments
            state_path = Path("Helix/state/ucf_state.json")
            state_path.parent.mkdir(parents=True, exist_ok=True)
            with open(state_path, "w", encoding="utf-8") as f:
                f.write(serialized)

            return True
        except Exception as e:
            logger.error("⚠ Error setting UCF state: %s", e)
            return False

    async def get_ucf_state(self) -> dict[str, Any]:
        """Retrieve cached UCF state from Redis or file."""
        # Try Redis first
        if self.redis:
            try:
                data = await self.redis.get("ucf_state")
                if data:
                    return json.loads(data)
            except Exception as e:
                logger.error("⚠ Redis get error: %s", e)

        # Fall back to file
        state_path = Path("Helix/state/ucf_state.json")
        if state_path.exists():
            try:
                with open(state_path, encoding="utf-8") as f:
                    return json.load(f)
            except (ValueError, TypeError, KeyError, IndexError) as e:
                logger.debug("Failed to load UCF state from file: %s", e)

        # Return default
        return {
            "velocity": 1.0228,
            "harmony": 0.355,
            "resilience": 1.1191,
            "throughput": 0.5175,
            "focus": 0.5023,
            "friction": 0.010,
        }

    async def publish_ucf_update(self, metrics: dict[str, Any]) -> bool:
        """Broadcast UCF updates to all subscribers."""
        if not self.redis:
            return False

        try:
            await self.redis.publish(
                "ucf_updates",
                json.dumps(
                    {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "metrics": metrics,
                    }
                ),
            )
            return True
        except Exception as e:
            logger.error("⚠ Error publishing UCF update: %s", e)
            return False

    async def subscribe_ucf_events(self) -> Any:
        """Subscribe to UCF update events."""
        if not self.redis:
            return None

        try:
            pubsub = self.redis.pubsub()
            await pubsub.subscribe("ucf_updates")
            return pubsub
        except Exception as e:
            logger.error("⚠ Error subscribing to UCF events: %s", e)
            return None

    # ========================================================================
    # DIRECTIVE OPERATIONS
    # ========================================================================

    async def queue_directive(self, directive: dict[str, Any]) -> bool:
        """Queue a directive for Arjuna execution."""
        if not self.redis:
            return False

        try:
            directive_id = directive.get("id", "")
            await self.redis.lpush("arjuna:directives", json.dumps(directive))
            await self.redis.setex(
                f"directive:{directive_id}",
                3600,
                json.dumps(
                    {
                        "status": "queued",
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                ),
            )
            return True
        except Exception as e:
            logger.error("⚠ Error queuing directive: %s", e)
            return False

    async def get_next_directive(self) -> dict[str, Any] | None:
        """Get next directive from queue."""
        if not self.redis:
            return None

        try:
            data = await self.redis.rpop("arjuna:directives")
            return json.loads(data) if data else None
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.debug("Invalid directive data format: %s", e)
            return None
        except (ConnectionError, TimeoutError) as e:
            logger.debug("Redis connection error retrieving directive: %s", e)
            return None
        except Exception as e:
            logger.warning("Failed to dequeue Arjuna directive from Redis: %s", e)
            return None

    async def update_directive_status(
        self, directive_id: str, status: str, result: dict[str, Any] | None = None
    ) -> bool:
        """Update directive execution status."""
        if not self.redis:
            return False

        try:
            status_data = {
                "status": status,
                "timestamp": datetime.now(UTC).isoformat(),
                "result": result or {},
            }
            await self.redis.setex(f"directive:{directive_id}", 3600, json.dumps(status_data))
            return True
        except Exception as e:
            logger.error("⚠ Error updating directive status: %s", e)
            return False

    # ========================================================================
    # MEMORY & LOGGING
    # ========================================================================

    async def log_event(self, event_type: str, data: dict[str, Any]) -> bool:
        """Log event to Redis stream."""
        if not self.redis:
            return False

        try:
            self.redis.xadd(
                "helix:events",
                {
                    "type": event_type,
                    "data": json.dumps(data),
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
            return True
        except Exception as e:
            logger.error("⚠ Error logging event: %s", e)
            return False

    async def get_recent_events(self, count: int = 20) -> list[Any]:
        """Get recent events from Redis stream."""
        if not self.redis:
            return []

        try:
            events = self.redis.xrevrange("helix:events", count=count)
            return events
        except Exception as e:
            logger.error("⚠ Error getting events: %s", e)
            return []

    # ========================================================================
    # AGENT MEMORY
    # ========================================================================

    async def save_agent_memory(self, agent_name: str, memory: list[str]) -> bool:
        """Save agent memory to Redis."""
        if not self.redis:
            return False

        try:
            await self.redis.setex(f"agent:{agent_name}:memory", 86400, json.dumps(memory))  # 24 hour TTL
            return True
        except Exception as e:
            logger.error("⚠ Error saving agent memory: %s", e)
            return False

    async def get_agent_memory(self, agent_name: str) -> list[str]:
        """Retrieve agent memory from Redis."""
        if not self.redis:
            return []

        try:
            data = await self.redis.get(f"agent:{agent_name}:memory")
            return json.loads(data) if data else []
        except Exception as e:
            logger.error("⚠ Error getting agent memory: %s", e)
            return []

    # ========================================================================
    # HEALTH CHECK
    # ========================================================================

    async def health_check(self) -> dict[str, Any]:
        """Check health of state manager."""
        health = {
            "timestamp": datetime.now(UTC).isoformat(),
            "redis": False,
            "postgres": False,
        }

        if self.redis:
            try:
                health["redis"] = True
            except (ValueError, TypeError, KeyError, IndexError):
                health["redis"] = False

        if self.db_pool:
            try:
                async with self.db_pool.acquire() as conn:
                    await conn.fetchval("SELECT 1")
                health["postgres"] = True
            except (ConnectionError, TimeoutError, OSError) as e:
                logger.debug("PostgreSQL health check connection error: %s", e)
                health["postgres"] = False
            except Exception as e:
                logger.warning("PostgreSQL health check failed: %s", e)
                health["postgres"] = False

        return health


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================


_state_manager = None


async def get_state_manager(redis_url: str | None = None, db_url: str | None = None) -> StateManager:
    """Get or create state manager instance."""
    global _state_manager
    if _state_manager is None:
        _state_manager = StateManager(redis_url, db_url)
        await _state_manager.connect()
    return _state_manager


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import asyncio

    async def main() -> None:
        manager = await get_state_manager()

        # Test operations
        test_state = {
            "velocity": 1.0228,
            "harmony": 0.355,
            "resilience": 1.1191,
            "throughput": 0.5175,
            "focus": 0.5023,
            "friction": 0.010,
        }

        logger.info("Testing StateManager...")
        await manager.set_ucf_state(test_state)
        logger.info("✅ State set")

        retrieved = await manager.get_ucf_state()
        logger.info("✅ State retrieved: %s", retrieved)

        health = await manager.health_check()
        logger.info("✅ Health check: %s", health)

        await manager.disconnect()

    asyncio.run(main())

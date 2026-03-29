"""
🌀 Helix Collective - Event Bus
Redis-based pub/sub event bus for loose coupling between services
"""

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class EventBus:
    """Redis-based pub/sub event bus for inter-service communication"""

    def __init__(self, redis_client=None) -> None:
        """Initialize event bus

        Args:
            redis_client: Redis client instance (optional, will use unified_auth Cache if not provided)
        """
        self.redis = redis_client
        self.handlers: dict[str, list[Callable]] = {}
        self.running = False
        self.listener_task = None

        # Fallback to in-memory queue if Redis not available
        self.in_memory_queue: list[dict[str, Any]] = []
        self.using_redis = redis_client is not None

        if self.using_redis:
            logger.info("📡 Event bus initialized with Redis pub/sub")
        else:
            logger.warning("⚠️ Event bus using in-memory fallback (no Redis)")

    async def initialize(self):
        """Initialize Redis connection if not provided"""
        if not self.redis:
            try:
                from apps.backend.core.unified_auth import Cache

                # Use Cache's Redis client
                if hasattr(Cache, "redis") and Cache.redis:
                    self.redis = Cache.redis
                    self.using_redis = True
                    logger.info("📡 Event bus connected to unified_auth Redis")
                else:
                    logger.warning("⚠️ Redis not available, using in-memory queue")
                    self.using_redis = False
            except (ConnectionError, TimeoutError) as e:
                logger.warning("⚠️ Redis connection failed (transient): %s", e)
                self.using_redis = False
            except Exception as e:
                logger.error("⚠️ Could not connect to Redis: %s", e)
                self.using_redis = False

    async def publish(self, event_type: str, data: dict[str, Any], source_service: str = "unknown"):
        """Publish event to all subscribers

        Args:
            event_type: Type of event (e.g., "user.logged_in", "agent.task_completed")
            data: Event data payload
            source_service: Name of the service publishing the event
        """
        event = {
            "type": event_type,
            "data": data,
            "source_service": source_service,
            "timestamp": time.time(),
            "event_id": str(uuid.uuid4()),
        }

        if self.using_redis and self.redis:
            try:
                await self.redis.publish(f"events:{event_type}", json.dumps(event))
                logger.info(
                    "📤 [%s] Event published: %s from %s",
                    event["event_id"][:8],
                    event_type,
                    source_service,
                )
            except (ConnectionError, TimeoutError) as e:
                logger.debug("Redis connection error publishing event: %s", e)
                # Fallback to in-memory
                self.in_memory_queue.append(event)
                await self._process_in_memory_events()
            except Exception as e:
                logger.error("❌ Failed to publish event to Redis: %s", e)
                # Fallback to in-memory
                self.in_memory_queue.append(event)
                await self._process_in_memory_events()
        else:
            # Use in-memory queue
            self.in_memory_queue.append(event)
            logger.debug(
                "📤 [%s] Event queued (in-memory): %s",
                event["event_id"][:8],
                event_type,
            )
            await self._process_in_memory_events()

    async def subscribe(self, event_type: str, handler: Callable):
        """Subscribe to events of a specific type

        Args:
            event_type: Type of event to subscribe to
            handler: Async function to call when event received
        """
        if event_type not in self.handlers:
            self.handlers[event_type] = []

        self.handlers[event_type].append(handler)
        logger.info("📥 Subscribed to event type: %s", event_type)

    async def unsubscribe(self, event_type: str, handler: Callable):
        """Unsubscribe from events

        Args:
            event_type: Type of event to unsubscribe from
            handler: Handler function to remove
        """
        if event_type in self.handlers and handler in self.handlers[event_type]:
            self.handlers[event_type].remove(handler)
            logger.info("📤 Unsubscribed from event type: %s", event_type)

    async def _process_in_memory_events(self):
        """Process events from in-memory queue"""
        while self.in_memory_queue:
            event = self.in_memory_queue.pop(0)
            event_type = event["type"]

            if event_type in self.handlers:
                for handler in self.handlers[event_type]:
                    try:
                        await handler(event)
                    except Exception as e:
                        logger.error("❌ Error processing event %s: %s", event["event_id"][:8], e)

    async def start_listening(self):
        """Start listening for Redis pub/sub events"""
        if not self.using_redis or not self.redis:
            logger.info("📡 Event bus in polling mode (no Redis)")
            return

        self.running = True
        logger.info("📡 Event bus started listening for Redis events")

        try:
            pubsub = self.redis.pubsub()

            # Subscribe to all registered event types
            for event_type in self.handlers.keys():
                await pubsub.subscribe(f"events:{event_type}")
                logger.info("   - Subscribed to: events:%s", event_type)

            # Listen for messages
            while self.running:
                try:
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)

                    if message and message["type"] == "message":
                        # Parse event
                        event = json.loads(message["data"])
                        event_type = event["type"]

                        logger.info(
                            "📥 [%s] Event received: %s from %s",
                            event["event_id"][:8],
                            event_type,
                            event.get("source_service", "unknown"),
                        )

                        # Call all registered handlers
                        if event_type in self.handlers:
                            for handler in self.handlers[event_type]:
                                try:
                                    await handler(event)
                                except Exception as e:
                                    logger.error("❌ Error in event handler for %s: %s", event_type, e)

                except TimeoutError:
                    # No message, continue
                    continue
                except Exception as e:
                    logger.error("❌ Error processing Redis message: %s", e)
                    await asyncio.sleep(1)

        except Exception as e:
            logger.error("❌ Event bus listener crashed: %s", e)
        finally:
            self.running = False
            logger.info("📡 Event bus stopped listening")

    async def stop_listening(self):
        """Stop listening for events"""
        self.running = False
        if self.listener_task:
            self.listener_task.cancel()
            try:
                await self.listener_task
            except asyncio.CancelledError:
                pass
        logger.info("📡 Event bus listener stopped")

    def get_subscribed_events(self) -> list[str]:
        """Get list of subscribed event types"""
        return list(self.handlers.keys())

    def get_handler_count(self, event_type: str) -> int:
        """Get number of handlers for an event type"""
        return len(self.handlers.get(event_type, []))


# Global event bus instance (will be initialized per service)
event_bus = EventBus()


# Common event types for convenience
class EventTypes:
    """Common event types used across services"""

    # User events
    USER_LOGGED_IN = "user.logged_in"
    USER_LOGGED_OUT = "user.logged_out"
    USER_REGISTERED = "user.registered"

    # Agent events
    AGENT_TASK_STARTED = "agent.task_started"
    AGENT_TASK_COMPLETED = "agent.task_completed"
    AGENT_TASK_FAILED = "agent.task_failed"
    AGENT_STATUS_CHANGED = "agent.status_changed"

    # Integration events
    WEBHOOK_RECEIVED = "integration.webhook_received"
    VOICE_PROCESSED = "integration.voice_processed"
    DISCORD_COMMAND = "integration.discord_command"

    # System events
    SERVICE_STARTED = "system.service_started"
    SERVICE_STOPPED = "system.service_stopped"
    SERVICE_HEALTH_CHANGED = "system.service_health_changed"

    # Cycle events
    CYCLE_STARTED = "cycle.started"
    CYCLE_COMPLETED = "cycle.completed"

    # Coordination events
    COORDINATION_SYNC = "coordination.sync"
    SYSTEM_STATE_CHANGED = "coordination.system_state_changed"

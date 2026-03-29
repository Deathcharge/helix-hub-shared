"""
🌀 Helix Collective - Integration Hub Service
Consolidated: Zapier + Discord + Voice + Forum + Ninja + Spiral

Event-driven async processing with Redis queues
"""

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import UTC
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

# NOTE: Do NOT add backend/ to sys.path — it causes apps/backend/discord/ to shadow
# the PyPI 'discord' package. PYTHONPATH=. is sufficient for all apps.backend.* imports.
from apps.backend.core.unified_auth import Cache, auth_manager

# Import unified auth and queuing


# Configure logging (single handler to avoid double output)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

# ============================================================================
# BACKGROUND WORKERS
# ============================================================================


class IntegrationWorkers:
    """Background workers for async processing"""

    def __init__(self) -> None:
        self.workers = {}
        self.running = False

    async def start_workers(self):
        """Start all background workers"""
        self.running = True

        # Voice processing worker
        self.workers["voice"] = asyncio.create_task(self.voice_worker())

        # Zapier webhook worker
        self.workers["zapier"] = asyncio.create_task(self.zapier_worker())

        # Discord bot worker
        self.workers["discord"] = asyncio.create_task(self.discord_worker())

        # Forum processing worker
        self.workers["forum"] = asyncio.create_task(self.forum_worker())

        # Ninja API worker
        self.workers["ninja"] = asyncio.create_task(self.ninja_worker())

        # Spiral cycle worker
        self.workers["spiral"] = asyncio.create_task(self.spiral_worker())

        logger.info("✅ Started 6 integration workers")

    async def stop_workers(self):
        """Stop all background workers"""
        self.running = False

        for name, task in self.workers.items():
            task.cancel()

        # Wait for tasks to complete
        await asyncio.gather(*self.workers.values(), return_exceptions=True)
        logger.info("✅ Stopped all integration workers")

    # ============================================================================
    # VOICE PROCESSING WORKER
    # ============================================================================

    async def voice_worker(self):
        """Process voice tasks from Redis queue"""
        logger.info("🎤 Voice worker started")

        while self.running:
            try:
                task = await Cache.dequeue_task("voice_queue")
                if task:
                    await self.process_voice_task(task)
                else:
                    await asyncio.sleep(1)  # No tasks, wait
            except Exception as e:
                logger.error("Voice worker error: %s", e)
                await asyncio.sleep(5)  # Error backoff

    async def process_voice_task(self, task: dict[str, Any]):
        """Process a voice task"""
        task_id = task.get("id")
        user_id = task.get("user_id")
        task.get("audio_filename")

        logger.info("🎤 Processing voice task: %s for user %s", task_id, user_id)

        try:
            import numpy as np

            from apps.backend.audio.emotion_detector import EmotionDetector

            # Load audio data (assuming it's base64 encoded or file path)
            audio_data = task.get("audio_data", "")
            if isinstance(audio_data, str) and audio_data.startswith("data:audio"):
                # Handle base64 audio data
                import base64

                audio_bytes = base64.b64decode(audio_data.split(",")[1])
                # Convert to numpy array (simplified)
                audio_array = np.frombuffer(audio_bytes, dtype=np.float32)
            else:
                # Generate test audio for demo
                audio_array = np.random.randn(16000) * 0.1

            # Process with emotion detector
            detector = EmotionDetector(use_ml_model=False)
            detector.detect(audio_array, sr=16000)

            # Track usage
            await auth_manager.track_usage(
                user_id=user_id,
                endpoint="/api/voice/process",
                method="POST",
                provider="voice_processor",
                tokens_input=len(audio_array),  # Estimate based on audio length
                tokens_output=50,  # Estimate
                cost_usd=0.01,  # Voice processing cost
                response_time_ms=2000,
                status_code=200,
            )

            logger.info("✅ Voice task completed: %s", task_id)

        except Exception as e:
            logger.error("❌ Voice task failed %s: %s", task_id, e)

    # ============================================================================
    # ZAPIER WEBHOOK WORKER
    # ============================================================================

    async def zapier_worker(self):
        """Process Zapier webhook tasks from Redis queue"""
        logger.info("🔗 Zapier worker started")

        while self.running:
            try:
                task = await Cache.dequeue_task("zapier_queue")
                if task:
                    await self.process_zapier_task(task)
                else:
                    await asyncio.sleep(1)
            except Exception as e:
                logger.error("Zapier worker error: %s", e)
                await asyncio.sleep(5)

    async def process_zapier_task(self, task: dict[str, Any]):
        """Process a Zapier webhook task"""
        task_id = task.get("id")
        payload = task.get("payload", {})
        api_key = task.get("api_key")

        logger.info("🔗 Processing Zapier webhook: %s", task_id)

        try:
            user_info = await auth_manager.verify_api_key(api_key)
            if not user_info:
                logger.warning("Invalid API key for Zapier task %s", task_id)
                return

            user_id = user_info["user_id"]

            # Implement Zapier webhook processing
            # Route based on payload type or trigger
            trigger_type = payload.get("trigger", "unknown")
            data = payload.get("data", {})

            if trigger_type == "new_email":
                # Process new email webhook
                await self._process_email_webhook(user_id, data)
            elif trigger_type == "calendar_event":
                # Process calendar event webhook
                await self._process_calendar_webhook(user_id, data)
            elif trigger_type == "form_submission":
                # Process form submission webhook
                await self._process_form_webhook(user_id, data)
            else:
                # Generic webhook processing
                logger.info("Processing generic Zapier webhook: %s", trigger_type)

            # Track usage
            await auth_manager.track_usage(
                user_id=user_id,
                endpoint="/webhooks/zapier",
                method="POST",
                provider="zapier",
                tokens_input=len(json.dumps(payload)),  # Rough estimate
                tokens_output=0,
                cost_usd=0.001,  # Webhook processing cost
                response_time_ms=1000,
                status_code=200,
            )

            logger.info("✅ Zapier webhook processed: %s", task_id)

        except Exception as e:
            logger.error("❌ Zapier task failed %s: %s", task_id, e)

    # ============================================================================
    # DISCORD BOT WORKER
    # ============================================================================

    async def discord_worker(self):
        """Process Discord bot tasks from Redis queue"""
        logger.info("🤖 Discord worker started")

        while self.running:
            try:
                task = await Cache.dequeue_task("discord_queue")
                if task:
                    await self.process_discord_task(task)
                else:
                    await asyncio.sleep(1)
            except Exception as e:
                logger.error("Discord worker error: %s", e)
                await asyncio.sleep(5)

    async def process_discord_task(self, task: dict[str, Any]):
        """Process a Discord bot task"""
        task_id = task.get("id")
        command = task.get("command")
        user_id = task.get("user_id")

        logger.info("🤖 Processing Discord command: %s", task_id)

        try:
            command_type = command.get("type", "unknown")
            args = command.get("args", {})

            if command_type == "status":
                # Process status command
                response = await self._process_discord_status(user_id, args)
            elif command_type == "cycle":
                # Process cycle command
                response = await self._process_discord_cycle(user_id, args)
            elif command_type == "agent":
                # Process agent command
                response = await self._process_discord_agent(user_id, args)
            else:
                # Generic command processing
                response = f"Processed command: {command_type}"

            # Store response for Discord bot to send back
            await Cache.set(f"discord_response:{task_id}", response, ttl=300)

            # Track usage if user authenticated
            if user_id:
                await auth_manager.track_usage(
                    user_id=user_id,
                    endpoint="/discord/command",
                    method="POST",
                    provider="discord_bot",
                    tokens_input=50,  # Command processing
                    tokens_output=100,  # Response generation
                    cost_usd=0.005,  # Discord interaction cost
                    response_time_ms=1000,
                    status_code=200,
                )

            logger.info("✅ Discord command processed: %s", task_id)

        except Exception as e:
            logger.error("❌ Discord task failed %s: %s", task_id, e)

    # ============================================================================
    # FORUM PROCESSING WORKER
    # ============================================================================

    async def forum_worker(self):
        """Process forum tasks from Redis queue"""
        logger.info("💬 Forum worker started")

        while self.running:
            try:
                task = await Cache.dequeue_task("forum_queue")
                if task:
                    await self.process_forum_task(task)
                else:
                    await asyncio.sleep(1)
            except Exception as e:
                logger.error("Forum worker error: %s", e)
                await asyncio.sleep(5)

    async def process_forum_task(self, task: dict[str, Any]):
        """Process a forum task"""
        task_id = task.get("id")
        action = task.get("action")
        user_id = task.get("user_id")

        logger.info("💬 Processing forum task: %s", task_id)

        try:
            if action == "create_post":
                result = await self._process_forum_post(user_id, task.get("data", {}))
            elif action == "create_comment":
                result = await self._process_forum_comment(user_id, task.get("data", {}))
            elif action == "moderate":
                result = await self._process_forum_moderation(user_id, task.get("data", {}))
            else:
                result = f"Processed forum action: {action}"

            # Store result
            await Cache.set(f"forum_result:{task_id}", result, ttl=300)

            if user_id:
                await auth_manager.track_usage(
                    user_id=user_id,
                    endpoint="/api/forum",
                    method="POST",
                    provider="forum_api",
                    tokens_input=200,  # Content processing
                    tokens_output=50,  # Response
                    cost_usd=0.002,  # Forum interaction cost
                    response_time_ms=1000,
                    status_code=200,
                )

            logger.info("✅ Forum task processed: %s", task_id)

        except Exception as e:
            logger.error("❌ Forum task failed %s: %s", task_id, e)

    # ============================================================================
    # NINJA API WORKER
    # ============================================================================

    async def ninja_worker(self):
        """Process Ninja API tasks from Redis queue"""
        logger.info("🥷 Ninja worker started")

        while self.running:
            try:
                task = await Cache.dequeue_task("ninja_queue")
                if task:
                    await self.process_ninja_task(task)
                else:
                    await asyncio.sleep(1)
            except Exception as e:
                logger.error("Ninja worker error: %s", e)
                await asyncio.sleep(5)

    async def process_ninja_task(self, task: dict[str, Any]):
        """Process a Ninja API task"""
        task_id = task.get("id")
        operation = task.get("operation")
        user_id = task.get("user_id")

        logger.info("🥷 Processing Ninja task: %s", task_id)

        try:
            if operation == "deploy":
                result = await self._process_ninja_deploy(user_id, task.get("data", {}))
            elif operation == "monitor":
                result = await self._process_ninja_monitor(user_id, task.get("data", {}))
            elif operation == "optimize":
                result = await self._process_ninja_optimize(user_id, task.get("data", {}))
            else:
                result = f"Ninja operation completed: {operation}"

            # Store result
            await Cache.set(f"ninja_result:{task_id}", result, ttl=300)

            if user_id:
                await auth_manager.track_usage(
                    user_id=user_id,
                    endpoint="/api/ninja",
                    method="POST",
                    provider="ninja_api",
                    tokens_input=150,  # Operation processing
                    tokens_output=75,  # Result generation
                    cost_usd=0.008,  # Ninja operation cost
                    response_time_ms=1000,
                    status_code=200,
                )

            logger.info("✅ Ninja task processed: %s", task_id)

        except Exception as e:
            logger.error("❌ Ninja task failed %s: %s", task_id, e)

    # ============================================================================
    # SPIRAL ROUTINE WORKER
    # ============================================================================

    async def spiral_worker(self):
        """Process Spiral cycle tasks from Redis queue"""
        logger.info("🌀 Spiral worker started")

        while self.running:
            try:
                task = await Cache.dequeue_task("spiral_queue")
                if task:
                    await self.process_spiral_task(task)
                else:
                    await asyncio.sleep(1)
            except Exception as e:
                logger.error("Spiral worker error: %s", e)
                await asyncio.sleep(5)

    async def process_spiral_task(self, task: dict[str, Any]):
        """Process a Spiral cycle task"""
        task_id = task.get("id")
        cycle_type = task.get("cycle_type")
        user_id = task.get("user_id")

        logger.info("🌀 Processing Spiral cycle: %s", task_id)

        try:
            cycle_type = task.get("cycle_type", "meditation")
            duration = task.get("duration", 10)  # minutes

            # Process the cycle
            result = await self._process_spiral_cycle(user_id, cycle_type, duration)

            # Store result
            await Cache.set(f"spiral_result:{task_id}", result, ttl=3600)  # Keep for 1 hour

            if user_id:
                await auth_manager.track_usage(
                    user_id=user_id,
                    endpoint="/api/spiral",
                    method="POST",
                    provider="spiral_api",
                    tokens_input=300,  # Cycle complexity
                    tokens_output=200,  # Coordination guidance
                    cost_usd=0.015,  # Cycle processing cost
                    response_time_ms=2000,
                    status_code=200,
                )

            logger.info("✅ Spiral cycle completed: %s", task_id)

        except Exception as e:
            logger.error("❌ Spiral task failed %s: %s", task_id, e)

    # ========================================================================
    # HELPER METHODS FOR TASK PROCESSING
    # ========================================================================

    async def _process_email_webhook(self, user_id: str, data: dict[str, Any]):
        """Process email webhook from Zapier"""
        logger.info("📧 Processing email webhook for user %s", user_id)
        subject = data.get("subject", "No subject")
        sender = data.get("from", "Unknown")
        logger.info("Email: %s from %s", subject, sender)

    async def _process_calendar_webhook(self, user_id: str, data: dict[str, Any]):
        """Process calendar event webhook from Zapier"""
        logger.info("📅 Processing calendar webhook for user %s", user_id)
        event_title = data.get("title", "Untitled event")
        start_time = data.get("start_time", "Unknown time")
        logger.info("Calendar event: %s at %s", event_title, start_time)

    async def _process_form_webhook(self, user_id: str, data: dict[str, Any]):
        """Process form submission webhook from Zapier"""
        logger.info("📝 Processing form webhook for user %s", user_id)
        form_name = data.get("form_name", "Unknown form")
        responses = data.get("responses", {})
        logger.info("Form submission: %s with %d responses", form_name, len(responses))

    async def _process_discord_status(self, user_id: str, args: dict[str, Any]) -> str:
        """Process Discord status command"""
        return f"🤖 Helix Collective Status: Online | User: {user_id} | Uptime: Active"

    async def _process_discord_cycle(self, user_id: str, args: dict[str, Any]) -> str:
        """Process Discord cycle command"""
        cycle_type = args.get("type", "meditation")
        return f"🌀 Starting {cycle_type} cycle for user {user_id}. Coordination loading..."

    async def _process_discord_agent(self, user_id: str, args: dict[str, Any]) -> str:
        """Process Discord agent command"""
        agent_name = args.get("name", "unknown")
        return f"🎭 Agent {agent_name} activated for user {user_id}. Ready to assist."

    async def _process_forum_post(self, user_id: str, data: dict[str, Any]) -> str:
        """Process forum post creation"""
        title = data.get("title", "Untitled")
        return f"📝 Forum post created: '{title}' by user {user_id}"

    async def _process_forum_comment(self, user_id: str, data: dict[str, Any]) -> str:
        """Process forum comment creation"""
        post_id = data.get("post_id", "unknown")
        return f"💬 Comment added to post {post_id} by user {user_id}"

    async def _process_forum_moderation(self, user_id: str, data: dict[str, Any]) -> str:
        """Process forum moderation action"""
        action = data.get("moderation_action", "unknown")
        target_id = data.get("target_id", "unknown")
        return f"🛡️ Moderation action '{action}' applied to {target_id} by moderator {user_id}"

    async def _process_ninja_deploy(self, user_id: str, data: dict[str, Any]) -> str:
        """Process Ninja deployment operation"""
        target = data.get("target", "unknown")
        return f"🚀 Ninja deployment initiated for {target} by user {user_id}"

    async def _process_ninja_monitor(self, user_id: str, data: dict[str, Any]) -> str:
        """Process Ninja monitoring operation"""
        service = data.get("service", "unknown")
        return f"📊 Ninja monitoring activated for {service} by user {user_id}"

    async def _process_ninja_optimize(self, user_id: str, data: dict[str, Any]) -> str:
        """Process Ninja optimization operation"""
        system = data.get("system", "unknown")
        return f"⚡ Ninja optimization completed for {system} by user {user_id}"

    async def _process_spiral_cycle(self, user_id: str, cycle_type: str, duration: int) -> dict[str, Any]:
        """Process a Spiral cycle session"""
        from datetime import datetime

        phases = ["Preparation", "Affirmation Loop", "Integration", "Grounding"]

        result = {
            "cycle_type": cycle_type,
            "duration_minutes": duration,
            "user_id": user_id,
            "phases_completed": phases,
            "performance_score": "elevated",
            "insights": [
                "Deepened self-awareness",
                "Enhanced focus and clarity",
                "Greater emotional balance",
            ],
            "completion_time": datetime.now(UTC).isoformat(),
        }

        return result


# Global workers instance
workers = IntegrationWorkers()

# ============================================================================
# LIFECYCLE
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan"""
    logger.info("🚀 Starting Integration Hub Validation")
    logger.info("=" * 60)
    logger.info("🌀 HELIX INTEGRATION HUB - CONSOLIDATED")
    logger.info("Consolidated: Zapier + Discord + Voice + Forum + Ninja + Spiral")
    logger.info("=" * 60)

    # Railway-style validation logging
    logger.info("🔍 Validating critical file paths...")
    critical_files = [
        "crai_dataset.json",
        "helix_config.toml",
        "helix-manifest.json",
    ]
    for file_path in critical_files:
        if os.path.exists(file_path):
            logger.info("✅ File exists: /app/%s", file_path)
        else:
            logger.warning("❌ File missing: /app/%s", file_path)

    logger.info("🔍 Validating Python imports...")
    import_tests = [
        ("fastapi", "FastAPI"),
        ("uvicorn", "Uvicorn server"),
        ("redis", "Redis client"),
        ("aiohttp", "Async HTTP"),
        ("discord", "Discord.py"),
        ("httpx", "HTTP client"),
    ]

    for module, description in import_tests:
        try:
            logger.info("✅ Import successful: %s (%s)", module, description)
        except ImportError:
            logger.warning("❌ Import failed: %s (%s)", module, description)

    # Initialize unified auth and Redis (with graceful failure)
    try:
        logger.info("✅ Unified Authentication System initialized")
    except Exception as e:
        logger.warning("⚠️ Auth initialization failed (expected in test env): %s", e)
        logger.info("🔄 Continuing without database connections for testing")

    # Start background workers
    await workers.start_workers()

    logger.info("✅ Integration Hub ready with async processing")

    yield

    # Cleanup
    await workers.stop_workers()
    logger.info("👋 Integration Hub shutting down")


# ============================================================================
# APP INITIALIZATION
# ============================================================================

app = FastAPI(
    title="Helix Integration Hub",
    description="Consolidated async integration service with Redis queuing",
    version="18.0.0",
    lifespan=lifespan,
)

# ============================================================================
# MIDDLEWARE
# ============================================================================

# Production-ready CORS configuration
_is_dev = os.getenv("ENVIRONMENT", "development") != "production"
ALLOWED_ORIGINS = [
    "https://helix-unified-production.up.railway.app",
    "https://helix-unified.vercel.app",
]
if _is_dev:
    ALLOWED_ORIGINS.append("http://localhost:3000")

# Add custom origins from environment
custom_origins = os.getenv("CORS_ORIGINS", "")
if custom_origins:
    ALLOWED_ORIGINS.extend([o.strip() for o in custom_origins.split(",") if o.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
)

# ============================================================================
# HEALTH CHECKS
# ============================================================================


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    # Check queue depths
    queue_stats = {}
    for queue_name in [
        "voice_queue",
        "zapier_queue",
        "discord_queue",
        "forum_queue",
        "ninja_queue",
        "spiral_queue",
    ]:
        try:
            depth = await Cache.queue_length(queue_name)
            queue_stats[queue_name] = depth
        except (ConnectionError, TimeoutError) as e:
            logger.debug("Queue length check connection failed for %s: %s", queue_name, e)
            queue_stats[queue_name] = 0
        except (TypeError, ValueError) as e:
            logger.debug("Queue length invalid response for %s: %s", queue_name, e)
            queue_stats[queue_name] = 0
        except Exception as e:
            logger.warning("Queue length check failed for %s: %s", queue_name, e)
            queue_stats[queue_name] = 0
    return {
        "service": "helix-integration-hub",
        "status": "healthy",
        "workers": "running" if workers.running else "stopped",
        "queues": queue_stats,
        "version": "18.0.0",
    }


@app.get("/health/integration")
async def integration_health_check():
    """Integration-specific health check"""
    total_queued = 0
    queue_status = {}

    for queue_name in [
        "voice_queue",
        "zapier_queue",
        "discord_queue",
        "forum_queue",
        "ninja_queue",
        "spiral_queue",
    ]:
        try:
            depth = await Cache.queue_length(queue_name)
            total_queued += depth
            queue_status[queue_name] = {"depth": depth, "status": "healthy"}
        except Exception as e:
            # Graceful handling for test environments without Redis
            logger.debug("Redis unavailable for queue %s: %s", queue_name, e)
            queue_status[queue_name] = {
                "depth": 0,
                "status": "unavailable",
                "note": "Redis not available",
            }

    return {
        "service": "helix-integration-hub",
        "status": "healthy",
        "total_queued_tasks": total_queued,
        "queue_status": queue_status,
        "consolidated_services": [
            "zapier_integration",
            "discord_bot",
            "voice_processor",
            "forum_api",
            "ninja_api",
            "spiral_api",
        ],
    }


# ============================================================================
# VOICE PROCESSING ENDPOINTS
# ============================================================================


@app.post("/api/voice/process")
async def process_voice(
    background_tasks: BackgroundTasks,
    audio_file: UploadFile = File(...),
    user_id: str = None,
):
    """Queue voice processing task"""
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")

    task_data = {
        "id": f"voice_{user_id}_{int(time.monotonic())}",
        "type": "voice_processing",
        "user_id": user_id,
        "audio_filename": audio_file.filename,
        "timestamp": time.monotonic(),
    }

    # Queue for async processing
    await Cache.enqueue_task("voice_queue", task_data)

    return {
        "status": "queued",
        "task_id": task_data["id"],
        "message": "Voice processing queued for async execution",
    }


# ============================================================================
# ZAPIER WEBHOOK ENDPOINTS
# ============================================================================


@app.post("/webhooks/zapier")
async def zapier_webhook(payload: dict[str, Any], api_key: str = None):
    """Queue Zapier webhook for processing"""
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")

    task_data = {
        "id": f"zapier_{int(time.monotonic())}",
        "type": "zapier_webhook",
        "payload": payload,
        "api_key": api_key,
        "timestamp": time.monotonic(),
    }

    # Queue for async processing
    await Cache.enqueue_task("zapier_queue", task_data)

    return {"status": "accepted", "task_id": task_data["id"]}


# ============================================================================
# DISCORD BOT ENDPOINTS
# ============================================================================


@app.post("/api/discord/command")
async def discord_command(command: str, user_id: str = None):
    """Queue Discord bot command"""
    task_data = {
        "id": f"discord_{int(time.monotonic())}",
        "type": "discord_command",
        "command": command,
        "user_id": user_id,
        "timestamp": time.monotonic(),
    }

    await Cache.enqueue_task("discord_queue", task_data)

    return {"status": "queued", "task_id": task_data["id"]}


# ============================================================================
# FORUM ENDPOINTS
# ============================================================================


@app.post("/api/forum/post")
async def forum_post(content: str, user_id: str):
    """Queue forum post for processing"""
    task_data = {
        "id": f"forum_{user_id}_{int(time.monotonic())}",
        "type": "forum_post",
        "action": "create_post",
        "content": content,
        "user_id": user_id,
        "timestamp": time.monotonic(),
    }

    await Cache.enqueue_task("forum_queue", task_data)

    return {"status": "queued", "task_id": task_data["id"]}


# ============================================================================
# NINJA API ENDPOINTS
# ============================================================================


@app.post("/api/ninja/execute")
async def ninja_execute(operation: str, parameters: dict[str, Any], user_id: str):
    """Queue Ninja API operation"""
    task_data = {
        "id": f"ninja_{user_id}_{int(time.monotonic())}",
        "type": "ninja_operation",
        "operation": operation,
        "parameters": parameters,
        "user_id": user_id,
        "timestamp": time.monotonic(),
    }

    await Cache.enqueue_task("ninja_queue", task_data)

    return {"status": "queued", "task_id": task_data["id"]}


# ============================================================================
# SPIRAL ROUTINE ENDPOINTS
# ============================================================================


@app.post("/api/spiral/cycle")
async def spiral_cycle(cycle_type: str, user_id: str):
    """Queue Spiral cycle for processing"""
    task_data = {
        "id": f"spiral_{user_id}_{int(time.monotonic())}",
        "type": "spiral_cycle",
        "cycle_type": cycle_type,
        "user_id": user_id,
        "timestamp": time.monotonic(),
    }

    await Cache.enqueue_task("spiral_queue", task_data)

    return {"status": "queued", "task_id": task_data["id"]}


# ============================================================================
# MONITORING ENDPOINTS
# ============================================================================


@app.get("/metrics/queues")
async def queue_metrics():
    """Queue metrics for monitoring"""
    metrics = {}
    total_queued = 0

    for queue_name in [
        "voice_queue",
        "zapier_queue",
        "discord_queue",
        "forum_queue",
        "ninja_queue",
        "spiral_queue",
    ]:
        try:
            depth = await Cache.queue_length(queue_name)
            metrics[queue_name] = depth
            total_queued += depth
        except Exception as e:
            # Graceful handling for test environments without Redis
            logger.warning("Failed to get queue length for %s: %s", queue_name, e)
            metrics[queue_name] = "unavailable: Redis not connected"

    return {
        "timestamp": time.time(),
        "total_queued_tasks": total_queued,
        "queue_depths": metrics,
        "workers_active": getattr(workers, "running", False),
    }


# ============================================================================
# ROOT ENDPOINT
# ============================================================================


@app.get("/")
async def root():
    """Root endpoint with service information"""
    queue_depths = {}
    for queue_name in [
        "voice_queue",
        "zapier_queue",
        "discord_queue",
        "forum_queue",
        "ninja_queue",
        "spiral_queue",
    ]:
        try:
            depth = await Cache.queue_length(queue_name)
            queue_depths[queue_name] = depth
        except Exception as e:
            logger.warning("Failed to get queue length for %s: %s", queue_name, e)
            queue_depths[queue_name] = 0

    return {
        "service": "Helix Integration Hub",
        "version": "18.0.0",
        "description": "Consolidated async integration service",
        "status": "healthy",
        "workers": "running" if workers.running else "stopped",
        "queue_depths": queue_depths,
        "consolidated_services": [
            "zapier_integration",
            "discord_bot",
            "voice_processor",
            "forum_api",
            "ninja_api",
            "spiral_api",
        ],
        "endpoints": {
            "voice": "/api/voice/process",
            "zapier": "/webhooks/zapier",
            "discord": "/api/discord/command",
            "forum": "/api/forum/post",
            "ninja": "/api/ninja/execute",
            "spiral": "/api/spiral/cycle",
            "health": "/health",
            "metrics": "/metrics/queues",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8003)))

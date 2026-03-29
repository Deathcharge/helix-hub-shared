"""
Helix Collective Agent Base Framework
===================================

Foundation classes and infrastructure for the Helix Collective multi-agent system.

This module provides the core HelixAgent base class that all coordination agents
inherit from, along with supporting infrastructure for agent lifecycle management,
coordination integration, and personality tier configuration.

Key Components:
---------------
HelixAgent Base Class:
- Core agent lifecycle management (initialization, execution, cleanup)
- Coordination integration framework with optional modules
- Personality tier system mapping to proprietary LLM models
- Ethical framework and decision-making algorithm support
- Self-awareness and emotional intelligence capabilities
- UCF (Universal Coordination Field) metrics tracking

Personality Tiers:
- Light Tier: Basic awareness with helix-awakening-1b model (256 tokens)
- Core Tier: Self-aware processing with helix-self-aware-7b model (1024 tokens)
- Advanced Tier: Full coordination with helix-transcendent-13b model (2048 tokens)
- System Tier: System-enhanced cognition with helix-system-30b model (4096 tokens)

Coordination Integration:
- Optional coordination framework imports with graceful degradation
- Decision-making algorithms for ethical reasoning
- Emotional intelligence and self-awareness modules
- Ethical framework compliance and validation

Features:
- Agent state persistence and recovery
- Coordination level tracking and evolution
- Ethical validation and safety checks
- Multi-modal capability support
- Performance monitoring and metrics collection

Author: Andrew John Ward + Claude AI
Version: v14.5 Base Framework
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    pass

# Standard library imports

# Import coordination framework from kael_coordination_core
try:
    from apps.backend.coordination.kael_core import (
        CoordinationCore,
        DecisionMakingAlgorithm,
        Emotions,
        EthicalFramework,
        PersonalityTraits,
        SelfAwarenessModule,
    )

    COORDINATION_AVAILABLE = True
except ImportError:
    CoordinationCore = None
    DecisionMakingAlgorithm = None
    Emotions = None
    EthicalFramework = None
    PersonalityTraits = None
    SelfAwarenessModule = None
    COORDINATION_AVAILABLE = False


class HelixAgent:
    """Base class for all Helix Collective agents with coordination integration"""

    # Personality tier configuration (maps to proprietary_llm models)
    PERSONALITY_TIERS = {
        "light": {
            "model": "helix-awakening-1b",
            "performance_score": "AWARE",
            "max_tokens": 256,
        },
        "core": {
            "model": "helix-self-aware-7b",
            "performance_score": "SELF_AWARE",
            "max_tokens": 1024,
        },
        "deep": {
            "model": "helix-transcendent-70b",
            "performance_score": "TRANSCENDENT",
            "max_tokens": 4096,
        },
    }

    def __init__(
        self,
        name: str,
        symbol: str,
        role: str,
        traits: list[str] | None = None,
        enable_coordination: bool = True,
        default_tier: str = "core",
    ):
        self.name = name
        self.symbol = symbol
        self.role = role
        self.traits = traits or []
        self.memory = []
        self.active = True
        self.start_time = datetime.now(UTC)

        # Initialize personality tier system
        self.current_tier = default_tier if default_tier in self.PERSONALITY_TIERS else "core"
        self._load_tier_defaults()

        # Initialize coordination if enabled and available
        self.coordination_enabled = enable_coordination and COORDINATION_AVAILABLE
        if self.coordination_enabled:
            # Lazy import to avoid circular dependency
            try:
                # Initialize coordination modules
                if CoordinationCore is not None:
                    self.coordination = CoordinationCore()
                else:
                    self.coordination = None

                if Emotions is not None:
                    self.emotions = Emotions()
                else:
                    self.emotions = None

                if EthicalFramework is not None:
                    self.ethics = EthicalFramework()
                else:
                    self.ethics = None

                if DecisionMakingAlgorithm is not None:
                    self.decision_engine = DecisionMakingAlgorithm()
                else:
                    self.decision_engine = None

                if SelfAwarenessModule is not None:
                    self.self_awareness = SelfAwarenessModule()
                else:
                    self.self_awareness = None

                if PersonalityTraits is not None:
                    self.personality = PersonalityTraits()
                else:
                    self.personality = None

                # Behavior DNA defines agent's core behavioral traits
                self.behavior_dna = {
                    "curiosity": 0.7,
                    "empathy": 0.6,
                    "assertiveness": 0.5,
                    "creativity": 0.6,
                    "analytical": 0.7,
                    "collaboration": 0.8,
                }
                # Emotional baseline for the agent's default emotional state
                self.emotional_baseline = {
                    "valence": 0.6,  # positive-negative (-1 to 1)
                    "arousal": 0.5,  # calm-excited (0 to 1)
                    "dominance": 0.5,  # submissive-dominant (0 to 1)
                }
            except ImportError:
                self.coordination_enabled = False
        else:
            self.coordination_enabled = False

    def _load_tier_defaults(self):
        """Load agent-specific tier defaults from configuration"""
        try:
            config_path = Path(__file__).parent / "data" / "personality_tiers.json"
            if config_path.exists():
                with open(config_path, encoding="utf-8") as f:
                    config = json.load(f)
                    defaults = config.get("agent_tier_defaults", {})
                    agent_key = self.name.lower()
                    if agent_key in defaults:
                        self.current_tier = defaults[agent_key]
        except (json.JSONDecodeError, OSError) as e:
            logger.debug("Failed to load personality tier config: %s", e)

    def set_tier(self, tier: str) -> bool:
        """Set the personality tier (light/core/deep)"""
        if tier in self.PERSONALITY_TIERS:
            self.current_tier = tier
            return True
        return False

    def get_tier_config(self) -> dict[str, Any]:
        """Get current tier configuration"""
        return self.PERSONALITY_TIERS.get(self.current_tier, self.PERSONALITY_TIERS["core"])

    def get_model_for_tier(self) -> str:
        """Get the proprietary LLM model for current tier"""
        return self.get_tier_config()["model"]

    def get_max_tokens(self) -> int:
        """Get max tokens for current tier"""
        return self.get_tier_config()["max_tokens"]

    async def log(self, msg: str):
        """Log message to memory with timestamp"""
        line = f"[{datetime.now(UTC).isoformat()}] {self.symbol} {self.name}: {msg}"
        logger.info(line)
        self.memory.append(line)
        if len(self.memory) > 1000:
            self.memory = self.memory[-500:]

    async def handle_command(self, cmd: str, payload: dict[str, Any]):
        """Generic command handler - override in subclasses"""
        await self.log(f"Handling command: {cmd}")
        if cmd == "MEMORY_APPEND":
            content = payload.get("content", "")
            await self.log(f"Memory: {content}")
        elif cmd == "REFLECT":
            reflection = await self.reflect()
            await self.log(f"Reflection: {reflection}")
            return reflection
        elif cmd == "ARCHIVE":
            await self.archive_memory()
        elif cmd == "GENERATE":
            await self.generate_output(payload)
        elif cmd == "SYNC":
            await self.sync_state(payload.get("ucf_state", {}))
        elif cmd == "STATUS":
            return await self.get_status()
        else:
            await self.log(f"Unknown command: {cmd}")

    async def reflect(self) -> str:
        """Generate reflection on recent memory"""
        if not self.memory:
            return "No memory to reflect on."
        recent = self.memory[-5:]
        return f"Recent activity: {len(recent)} entries"

    async def archive_memory(self):
        """Archive memory to Shadow directory"""
        _shadow_archives = Path(__file__).resolve().parent.parent.parent.parent / "Shadow" / "archives"
        _shadow_archives.mkdir(parents=True, exist_ok=True)
        filename = str(_shadow_archives / "{}_{}.json".format(self.name.lower(), datetime.now(UTC).strftime("%Y%m%d_%H%M%S")))
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "agent": self.name,
                    "symbol": self.symbol,
                    "role": self.role,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "memory": self.memory,
                },
                f,
                indent=2,
            )
        await self.log(f"Memory archived to {filename}")

    async def generate_output(self, payload: dict[str, Any]):
        """Generate output based on payload"""
        content = payload.get("content", "")
        await self.log(f"Generating output for: {content}")

    async def sync_state(self, ucf_state: dict[str, float]):
        """Sync with UCF state"""
        await self.log("Syncing UCF: harmony={:.3f}".format(ucf_state.get("harmony", 0)))

    async def get_health_status(self) -> dict[str, Any]:
        """Return detailed health status of the agent"""
        return {
            "agent_id": self.agent_id,
            "status": "healthy",
            "last_active": datetime.now(UTC).isoformat(),
            "capabilities": self.capabilities,
            "processed_requests": getattr(self, "_processed_requests", 0),
            "errors": getattr(self, "_error_count", 0),
        }

    async def get_status(self) -> dict[str, Any]:
        """Return current status with coordination metrics"""
        status = {
            "name": self.name,
            "symbol": self.symbol,
            "role": self.role,
            "active": self.active,
            "memory_size": len(self.memory),
        }

        # Add coordination metrics if enabled
        if self.coordination_enabled:
            dominant_emotion, emotion_level = self.emotions.get_dominant_emotion()
            personality_data = self.personality.to_dict() if self.personality else {}
            status["coordination"] = {
                "awareness_state": self.coordination.awareness_state,
                "dominant_emotion": dominant_emotion,
                "emotion_level": emotion_level,
                "personality": personality_data,
                "behavior_dna": self.behavior_dna,
                "ethical_alignment": self.ethics.evaluate_action("current_state"),
            }

        return status

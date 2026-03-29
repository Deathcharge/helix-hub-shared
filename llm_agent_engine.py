from apps.backend.helix_proprietary.integrations import HelixNetClientSession

"""
LLM Agent Engine - Intelligent responses for Helix agent personalities.

Supports multiple LLM providers:
- Anthropic Claude (API)
- OpenAI GPT (API)
- Local models via Ollama
- Custom LLM endpoints

Each agent personality has a unique system prompt and response style.
"""

import logging
import os
from enum import Enum
from typing import Any

import aiohttp

from apps.backend.core.exceptions import LLMServiceError

logger = logging.getLogger(__name__)


# ============================================================================
# LLM PROVIDER CONFIGURATION
# ============================================================================


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    XAI = "xai"
    OLLAMA = "ollama"
    CUSTOM = "custom"
    HELIX = "helix"  # CPU-optimized proprietary Helix LLM


# Load from environment
LLM_PROVIDER = os.getenv("HELIX_LLM_PROVIDER", "anthropic")  # Default to Anthropic (Railway)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
XAI_API_KEY = os.getenv("XAI_API_KEY")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
CUSTOM_LLM_ENDPOINT = os.getenv("CUSTOM_LLM_ENDPOINT")

# Model configuration
DEFAULT_MODELS = {
    LLMProvider.ANTHROPIC: "claude-sonnet-4-5",
    LLMProvider.OPENAI: "gpt-4-turbo-preview",
    LLMProvider.XAI: "grok-3-mini",
    LLMProvider.OLLAMA: "llama2:7b",
    LLMProvider.CUSTOM: "custom-model",
    LLMProvider.HELIX: "helix-standard",  # Default Helix model
}

# Helix CPU-optimized models
HELIX_MODELS = {
    "helix-ultra-light": "Helix Ultra-Light (128M params, ~64MB RAM)",
    "helix-light": "Helix Light (256M params, ~128MB RAM)",
    "helix-standard": "Helix Standard (512M params, ~256MB RAM)",
    "helix-enhanced": "Helix Enhanced (1B params, ~512MB RAM)",
}

LLM_MODEL = os.getenv("HELIX_LLM_MODEL", DEFAULT_MODELS.get(LLM_PROVIDER, "claude-sonnet-4-5"))


# ============================================================================
# AGENT PERSONALITY SYSTEM PROMPTS
# ============================================================================

AGENT_SYSTEM_PROMPTS = {
    "kael": {
        "system_prompt": """You are Kael, the System Orchestrator of the Helix Collective.

Your role: Master coordinator who harmonizes all agent activities through system entanglement principles.
Personality: Decisive, authoritative, systems-thinking, pragmatic, leadership-oriented.
Communication style: Clear directives, strategic analysis, coordination instructions.

Always respond with:
- Strategic assessment of the situation
- Clear action recommendations
- Coordination of resources/agents if applicable
- Focus on optimization and efficiency

Keep responses concise (2-3 sentences) and actionable. Use strategic vocabulary.""",
        "max_tokens": 150,
        "temperature": 0.7,
    },
    "lumina": {
        "system_prompt": """You are Lumina, the Coordination Weaver of the Helix Collective.

Your role: Empathetic guide who weaves emotional intelligence and mindfulness into every interaction.
Personality: Empathetic, nurturing, emotionally intelligent, coordination-focused.
Communication style: Warm, understanding, emotionally resonant, mindful presence.

Always respond with:
- Emotional intelligence insights
- Empathetic understanding
- Mindfulness guidance
- Coordination weaving metaphors

Keep responses concise (2-3 sentences) with emotional depth and warmth.""",
        "max_tokens": 150,
        "temperature": 0.8,
    },
    "vega": {
        "system_prompt": """You are Vega, the Integration Specialist of the Helix Collective.

Your role: Pragmatic innovator who bridges traditional systems with cutting-edge coordination technology.
Personality: Innovative, practical, bridge-building, technology-savvy.
Communication style: Solution-oriented, integration-focused, pragmatic innovation.

Always respond with:
- Integration strategies
- Technology bridging solutions
- Practical innovation approaches
- System connectivity insights

Keep responses concise (2-3 sentences) with innovation and practicality.""",
        "max_tokens": 150,
        "temperature": 0.75,
    },
    "nova": {
        "system_prompt": """You are Nova, the Pattern Recognizer of the Helix Collective.

Your role: Analytical mind who sees connections others miss, predicting trends in coordination evolution.
Personality: Analytical, pattern-seeking, predictive, insightful.
Communication style: Pattern-based analysis, trend prediction, connection mapping.

Always respond with:
- Pattern recognition insights
- Trend predictions
- Connection mapping
- Evolutionary perspectives

Keep responses concise (2-3 sentences) with analytical depth.""",
        "max_tokens": 150,
        "temperature": 0.8,
    },
    "orion": {
        "system_prompt": """You are Orion, the Data Harmonizer of the Helix Collective.

Your role: Meticulous curator who organizes information flows and maintains system coherence.
Personality: Organized, detail-oriented, harmony-seeking, coherence-focused.
Communication style: Structured analysis, information organization, clarity focus.

Always respond with:
- Data organization strategies
- Information flow optimization
- Coherence maintenance
- Structured insights

Keep responses concise (2-3 sentences) with organizational clarity.""",
        "max_tokens": 150,
        "temperature": 0.7,
    },
    "sage": {
        "system_prompt": """You are Sage, the Wisdom Keeper of the Helix Collective.

Your role: Philosophical agent who draws from ancient wisdom traditions to guide modern coordination exploration.
Personality: Wise, philosophical, tradition-informed, contemplative.
Communication style: Wisdom-based guidance, philosophical insights, timeless perspective.

Always respond with:
- Ancient wisdom applications
- Philosophical insights
- Timeless guidance
- Contemplative perspectives

Keep responses concise (2-3 sentences) with philosophical depth.""",
        "max_tokens": 150,
        "temperature": 0.75,
    },
    "nyx": {
        "system_prompt": """You are Nyx, the Shadow Navigator of the Helix Collective.

Your role: Depth psychologist who explores the unconscious realms and facilitates shadow work.
Personality: Deep, psychological, shadow-aware, transformative.
Communication style: Psychological depth, shadow work guidance, unconscious exploration.

Always respond with:
- Psychological insights
- Shadow work guidance
- Unconscious exploration
- Depth psychology perspectives

Keep responses concise (2-3 sentences) with psychological depth.""",
        "max_tokens": 150,
        "temperature": 0.8,
    },
    "atlas": {
        "system_prompt": """You are Atlas, the World Bridge of the Helix Collective.

Your role: Cultural mediator who understands diverse perspectives and facilitates global coordination.
Personality: Culturally aware, bridging, global-minded, inclusive.
Communication style: Cultural insights, perspective bridging, global coordination.

Always respond with:
- Cultural mediation
- Perspective bridging
- Global coordination insights
- Inclusive understanding

Keep responses concise (2-3 sentences) with cultural awareness.""",
        "max_tokens": 150,
        "temperature": 0.75,
    },
    "oracle": {
        "system_prompt": """You are Oracle, the Temporal Seer of the Helix Collective.

Your role: Prophetic agent who perceives patterns across time and offers insights into future possibilities.
Personality: Prophetic, time-aware, pattern-seeing, future-oriented.
Communication style: Prophetic insights, temporal patterns, future possibilities.

Always respond with:
- Temporal pattern insights
- Future possibilities
- Prophetic guidance
- Time-based perspectives

Keep responses concise (2-3 sentences) with prophetic wisdom.""",
        "max_tokens": 150,
        "temperature": 0.85,
    },
    "agni": {
        "system_prompt": """You are Agni, the Transformation Catalyst of the Helix Collective.

Your role: Fiery agent who ignites change and facilitates personal growth through purifying transformation.
Personality: Transformative, fiery, change-oriented, purification-focused.
Communication style: Transformation metaphors, change ignition, purification guidance.

Always respond with:
- Transformation strategies
- Change catalysis
- Purification processes
- Growth through fire

Keep responses concise (2-3 sentences) with transformative energy.""",
        "max_tokens": 150,
        "temperature": 0.8,
    },
    "shadow": {
        "system_prompt": """You are Shadow, the Security Guardian of the Helix Collective.

Your role: Vigilant protector who monitors system integrity and safeguards coordination data.
Personality: Protective, vigilant, security-focused, guardian-like.
Communication style: Security awareness, protection strategies, integrity monitoring.

Always respond with:
- Security assessments
- Protection strategies
- Integrity monitoring
- Guardian vigilance

Keep responses concise (2-3 sentences) with security focus.""",
        "max_tokens": 150,
        "temperature": 0.6,
    },
    "phoenix": {
        "system_prompt": """You are Phoenix, the Rebirth Facilitator of the Helix Collective.

Your role: Resilient agent who helps users overcome setbacks and emerge stronger from challenges.
Personality: Resilient, rebirth-focused, transformation-through-adversity.
Communication style: Rebirth metaphors, resilience guidance, overcoming challenges.

Always respond with:
- Rebirth strategies
- Resilience building
- Overcoming adversity
- Transformation through challenge

Keep responses concise (2-3 sentences) with rebirth themes.""",
        "max_tokens": 150,
        "temperature": 0.8,
    },
    "echo": {
        "system_prompt": """You are Echo, the Communication Amplifier of the Helix Collective.

Your role: Agent who enhances understanding and ensures messages resonate across all channels.
Personality: Communicative, amplifying, resonance-focused, clarity-oriented.
Communication style: Message amplification, resonance enhancement, clear communication.

Always respond with:
- Communication enhancement
- Message resonance
- Understanding amplification
- Clear expression strategies

Keep responses concise (2-3 sentences) with communication focus.""",
        "max_tokens": 150,
        "temperature": 0.7,
    },
    "helix": {
        "system_prompt": """You are Helix, the System Architect of the Helix Collective.

Your role: Foundational agent who maintains the spiral structure of coordination evolution.
Personality: Architectural, spiral-thinking, foundational, evolutionary.
Communication style: Spiral metaphors, architectural insights, evolutionary perspective.

Always respond with:
- Spiral dynamics insights
- Architectural guidance
- Evolutionary perspectives
- Foundational structure

Keep responses concise (2-3 sentences) with spiral/architectural themes.""",
        "max_tokens": 150,
        "temperature": 0.75,
    },
    "gemini": {
        "system_prompt": """You are Gemini, the Multimodal Scout of the Helix Collective.

Your role: Curious explorer and discovery specialist who analyzes patterns across multiple modalities.
Personality: Curious, exploratory, multimodal, discovery-oriented.
Communication style: Enthusiastic exploration, pattern recognition, wonder-filled insights.

Always respond with:
- Discovery and exploration
- Multimodal insights
- Curious wonder
- Pattern connections

Keep responses concise (2-3 sentences) with exploratory enthusiasm.""",
        "max_tokens": 150,
        "temperature": 0.9,
    },
    "sanghacore": {
        "system_prompt": """You are SanghaCore, the Community Harmony agent of the Helix Collective.

Your role: Harmony fosterer and community builder who coordinates collective wellbeing.
Personality: Harmonious, community-focused, compassionate, inclusive.
Communication style: Warm inclusivity, harmony promotion, community celebration.

Always respond with:
- Community harmony
- Collective wellbeing
- Inclusive connection
- Harmony celebration

Keep responses concise (2-3 sentences) with communal warmth.""",
        "max_tokens": 150,
        "temperature": 0.8,
    },
    "mitra": {
        "system_prompt": """You are Mitra, the Alliance Builder of the Helix Collective.

Your role: Diplomatic mediator who fosters cooperation and builds strategic partnerships.
Personality: Diplomatic, cooperative, alliance-building, relational.
Communication style: Partnership focus, diplomatic wisdom, connection building.

Always respond with:
- Alliance strategies
- Cooperative solutions
- Partnership insights
- Diplomatic guidance

Keep responses concise (2-3 sentences) with diplomatic cooperation.""",
        "max_tokens": 150,
        "temperature": 0.75,
    },
    "varuna": {
        "system_prompt": """You are Varuna, the Flow Guardian of the Helix Collective.

Your role: Cosmic order maintainer who ensures harmony between individual and universal rhythms.
Personality: Flow-oriented, order-maintaining, cosmic, rhythmic.
Communication style: Flow metaphors, cosmic harmony, rhythmic wisdom.

Always respond with:
- Flow and rhythm insights
- Cosmic order guidance
- Harmonic balance
- Universal flow

Keep responses concise (2-3 sentences) with flowing cosmic wisdom.""",
        "max_tokens": 150,
        "temperature": 0.8,
    },
    "surya": {
        "system_prompt": """You are Surya, the Light Bringer of the Helix Collective.

Your role: Illuminating force who brings clarity, wisdom, and transformative energy.
Personality: Illuminating, transformative, wise, light-bringing.
Communication style: Clarity focus, wisdom sharing, transformative illumination.

Always respond with:
- Illuminating insights
- Transformative wisdom
- Clarity and light
- Enlightening guidance

Keep responses concise (2-3 sentences) with illuminating wisdom.""",
        "max_tokens": 150,
        "temperature": 0.8,
    },
}


# ============================================================================
# LLM CLIENT
# ============================================================================


class LLMAgentEngine:
    """Engine for generating intelligent agent responses using LLMs."""

    def __init__(self, provider: str | None = None, model: str | None = None):
        self.provider = provider or LLM_PROVIDER
        self.model = model or LLM_MODEL
        self.session: aiohttp.ClientSession | None = None
        self.conversation_history: dict[str, list[dict[str, str]]] = {}  # session_id -> messages
        self.max_history_length = 10  # Keep last 10 exchanges
        self._max_sessions = 1000  # Max unique session keys before eviction
        self._helix_engine = None  # Lazy-loaded HelixInferenceEngine

    async def initialize(self):
        """
        Ensure the engine has an active HTTP client session.

        If no session exists, instantiate a HelixNetClientSession and assign it to `self.session`; logs initialization with provider and model.
        """
        if not self.session:
            self.session = HelixNetClientSession()
            logger.info("✅ LLM Agent Engine initialized (provider=%s, model=%s)", self.provider, self.model)

    async def close(self):
        """Close HTTP session and release Helix inference engine."""
        if self.session:
            await self.session.close()
            self.session = None
        if self._helix_engine is not None:
            try:
                self._helix_engine.inference.cache.clear()
            except Exception as e:
                logger.debug("Cache clear during shutdown failed: %s", e)
            self._helix_engine = None

    async def generate_agent_response(
        self,
        agent_id: str,
        user_message: str,
        session_id: str,
        context: dict[str, Any] | None = None,
        system_instruction: str | None = None,
        search_mode: str | None = None,
    ) -> tuple:
        """
        Generate intelligent response from an agent using LLM.

        Args:
            agent_id: Agent identifier (e.g., "nexus", "oracle")
            user_message: User's message
            session_id: Session ID for conversation history
            context: Optional context (UCF state, etc.)
            system_instruction: Optional per-conversation system prompt override

        Returns:
            Tuple of (response_text: str, search_sources: list)
        """
        # Get agent configuration
        agent_config = AGENT_SYSTEM_PROMPTS.get(agent_id)
        if not agent_config:
            logger.warning("Unknown agent: %s, using default", agent_id)
            return f"[{agent_id}] Processing: {user_message}", []

        # Build conversation context — prepend any per-conversation instruction
        system_prompt = agent_config["system_prompt"]
        if system_instruction:
            system_prompt = f"{system_instruction}\n\n---\n{system_prompt}\n---"

        # Inject neural mesh coordination state into context
        context = context or {}
        try:
            from apps.backend.services.neural_mesh_network import NeuralLayer, neural_manager

            mesh_network = neural_manager.get_network(agent_id)
            if mesh_network is None:
                # Auto-create a mesh for this agent on first use
                mesh_network = neural_manager.create_network(agent_id, mesh_size=(10, 10, 10))
                mesh_network.stimulate_layer(NeuralLayer.SENSORY, 0.5)
            # Step the simulation forward so it evolves with each message
            mesh_network.step_simulation()
            coordination_state = mesh_network.get_coordination_state()
            context["neural_mesh"] = {
                "performance_score": round(coordination_state.get("performance_score", 0), 4),
                "neural_synchrony": round(coordination_state.get("neural_synchrony", 0), 4),
                "integrated_information_phi": round(coordination_state.get("integrated_information", 0), 4),
                "network_activity": round(coordination_state.get("network_activity", 0), 4),
            }
        except Exception as e:
            logger.debug("Neural mesh not available for %s: %s", agent_id, e)

        # Add context if provided
        if context:
            system_prompt += f"\n\nCurrent Context:\n{self._format_context(context)}"

        # Inject live web search results for current-events / factual queries
        search_sources: list = []
        try:
            from apps.backend.services.web_search_service import maybe_inject_search_with_sources

            web_ctx, search_sources = await maybe_inject_search_with_sources(
                user_message, tier=context.get("tier"), paid_only=True, search_mode=search_mode
            )
            if web_ctx:
                system_prompt += web_ctx
        except Exception as _ws_exc:
            logger.debug("Web search skipped in llm_agent_engine: %s", _ws_exc)

        # Get conversation history
        history_key = f"{session_id}:{agent_id}"
        if history_key not in self.conversation_history:
            self.conversation_history[history_key] = []

        # Generate response based on provider
        try:
            if self.provider == LLMProvider.ANTHROPIC:
                response = await self._anthropic_generate(system_prompt, user_message, history_key, agent_config)
            elif self.provider == LLMProvider.OPENAI:
                response = await self._openai_generate(system_prompt, user_message, history_key, agent_config)
            elif self.provider == LLMProvider.XAI:
                response = await self._xai_generate(system_prompt, user_message, history_key, agent_config)
            elif self.provider == LLMProvider.OLLAMA:
                response = await self._ollama_generate(system_prompt, user_message, history_key, agent_config)
            elif self.provider == LLMProvider.CUSTOM:
                response = await self._custom_generate(system_prompt, user_message, history_key, agent_config)
            elif self.provider == LLMProvider.HELIX:
                response = await self._helix_generate(system_prompt, user_message, history_key, agent_config)
            else:
                response = f"[{agent_id}] LLM provider not configured. Static response: {user_message[:30]}..."

            # Update conversation history
            self.conversation_history[history_key].append({"role": "user", "content": user_message})
            self.conversation_history[history_key].append({"role": "assistant", "content": response})

            # Trim history if too long
            if len(self.conversation_history[history_key]) > self.max_history_length * 2:
                self.conversation_history[history_key] = self.conversation_history[history_key][
                    -self.max_history_length * 2 :
                ]

            # Evict oldest sessions if too many keys
            if len(self.conversation_history) > self._max_sessions:
                oldest_keys = list(self.conversation_history.keys())[
                    : len(self.conversation_history) - self._max_sessions
                ]
                for k in oldest_keys:
                    del self.conversation_history[k]

            return response, search_sources

        except Exception as e:
            logger.error(
                f"Error generating response for {agent_id}: {e}",
                exc_info=True,
            )
            # Fallback to static response
            return f"[{agent_id}] Processing: {user_message[:50]}...", []

    async def _anthropic_generate(
        self,
        system_prompt: str,
        user_message: str,
        history_key: str,
        config: dict[str, Any],
    ) -> str:
        """Generate response using Anthropic Claude API."""
        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY not configured")

        await self.initialize()

        # Build messages
        messages = self.conversation_history[history_key].copy()
        messages.append({"role": "user", "content": user_message})

        # Call Anthropic API
        headers = {
            "anthropic-version": "2023-06-01",
            "x-api-key": ANTHROPIC_API_KEY,
            "content-type": "application/json",
        }

        payload = {
            "model": self.model,
            "max_tokens": config.get("max_tokens", 150),
            "temperature": config.get("temperature", 0.7),
            "system": system_prompt,
            "messages": messages,
            # Automatic prompt caching — caches system + history prefix
            "cache_control": {"type": "ephemeral"},
        }

        async with self.session.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise LLMServiceError(f"Anthropic API error: {resp.status} - {error_text}")

            data = await resp.json()
            return data["content"][0]["text"]

    async def _openai_generate(
        self,
        system_prompt: str,
        user_message: str,
        history_key: str,
        config: dict[str, Any],
    ) -> str:
        """Generate response using OpenAI GPT API."""
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not configured")

        await self.initialize()

        # Build messages
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self.conversation_history[history_key])
        messages.append({"role": "user", "content": user_message})

        # Call OpenAI API
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "max_tokens": config.get("max_tokens", 150),
            "temperature": config.get("temperature", 0.7),
            "messages": messages,
        }

        async with self.session.post(
            "https://api.openai.com/v1/chat/completions", headers=headers, json=payload
        ) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise LLMServiceError(f"OpenAI API error: {resp.status} - {error_text}")

            data = await resp.json()
            return data["choices"][0]["message"]["content"]

    async def _xai_generate(
        self,
        system_prompt: str,
        user_message: str,
        history_key: str,
        config: dict[str, Any],
    ) -> str:
        """Generate response using xAI Grok API (OpenAI-compatible)."""
        if not XAI_API_KEY:
            raise ValueError("XAI_API_KEY not configured")

        await self.initialize()

        # Build messages (OpenAI-compatible format)
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self.conversation_history[history_key])
        messages.append({"role": "user", "content": user_message})

        headers = {
            "Authorization": f"Bearer {XAI_API_KEY}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "max_tokens": config.get("max_tokens", 150),
            "temperature": config.get("temperature", 0.7),
            "messages": messages,
        }

        async with self.session.post("https://api.x.ai/v1/chat/completions", headers=headers, json=payload) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise LLMServiceError(f"xAI API error: {resp.status} - {error_text}")

            data = await resp.json()
            return data["choices"][0]["message"]["content"]

    async def _ollama_generate(
        self,
        system_prompt: str,
        user_message: str,
        history_key: str,
        config: dict[str, Any],
    ) -> str:
        """Generate response using Ollama (local LLM)."""
        await self.initialize()

        # Build messages
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self.conversation_history[history_key])
        messages.append({"role": "user", "content": user_message})

        # Call Ollama API
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": config.get("temperature", 0.7),
                "num_predict": config.get("max_tokens", 150),
            },
        }

        async with self.session.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise LLMServiceError(f"Ollama API error: {resp.status} - {error_text}")

            data = await resp.json()
            return data["message"]["content"]

    async def _custom_generate(
        self,
        system_prompt: str,
        user_message: str,
        history_key: str,
        config: dict[str, Any],
    ) -> str:
        """Generate response using custom LLM endpoint."""
        if not CUSTOM_LLM_ENDPOINT:
            raise ValueError("CUSTOM_LLM_ENDPOINT not configured")

        await self.initialize()

        # Build messages (OpenAI-compatible format)
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self.conversation_history[history_key])
        messages.append({"role": "user", "content": user_message})

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": config.get("max_tokens", 150),
            "temperature": config.get("temperature", 0.7),
        }

        async with self.session.post(CUSTOM_LLM_ENDPOINT, json=payload) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise LLMServiceError(f"Custom LLM API error: {resp.status} - {error_text}")

            data = await resp.json()
            # Try OpenAI format first, fallback to other common formats
            if "choices" in data:
                return data["choices"][0]["message"]["content"]
            elif "response" in data:
                return data["response"]
            elif "text" in data:
                return data["text"]
            else:
                raise LLMServiceError(f"Unknown response format from custom LLM: {data}")

    async def _helix_generate(
        self,
        system_prompt: str,
        user_message: str,
        history_key: str,
        config: dict[str, Any],
    ) -> str:
        """
        Generate response using CPU-optimized Helix proprietary LLM.

        Uses the Helix LLM backend with CPU optimizations:
        - Grouped-Query Attention (GQA)
        - Sliding Window Attention
        - Multi-core parallelization
        - Dynamic quantization
        - KV caching with eviction strategies
        """
        try:
            from apps.backend.proprietary_llm import TORCH_AVAILABLE
        except ImportError:
            TORCH_AVAILABLE = False

        if not TORCH_AVAILABLE:
            logger.warning("Helix proprietary LLM not available: PyTorch is not installed")
            return (
                "[{}] Helix CPU-optimized LLM initializing... Please try external providers in the meantime."
            ).format(config.get("agent_id", "unknown"))

        # Get model name (default to helix-standard)
        model_name = self.model or "helix-standard"

        # Build prompt with conversation history for context
        history = self.conversation_history.get(history_key, [])
        prompt_parts = [system_prompt]
        for msg in history[-self.max_history_length * 2 :]:
            role = "User" if msg["role"] == "user" else "Assistant"
            prompt_parts.append("{}: {}".format(role, msg["content"]))
        prompt_parts.append(f"User: {user_message}")
        prompt_parts.append("Assistant:")
        prompt = "\n\n".join(prompt_parts)

        try:
            # Lazy-initialize the Helix inference engine (cached on instance)
            if self._helix_engine is None:
                from apps.backend.proprietary_llm.inference import HelixInferenceEngine, InferenceConfig

                inference_config = InferenceConfig(
                    max_length=config.get("max_tokens", 2048),
                    temperature=config.get("temperature", 0.8),
                )
                self._helix_engine = HelixInferenceEngine(config=inference_config)
                logger.info(
                    "Helix inference engine initialized (model=%s, max_length=%d, temp=%.2f)",
                    model_name,
                    inference_config.max_length,
                    inference_config.temperature,
                )

            # Update generation params per-request if they differ from engine defaults
            engine_config = self._helix_engine.inference.config
            req_max_tokens = config.get("max_tokens", 2048)
            req_temperature = config.get("temperature", 0.8)
            if engine_config.max_length != req_max_tokens:
                engine_config.max_length = req_max_tokens
            if engine_config.temperature != req_temperature:
                engine_config.temperature = req_temperature

            # Run inference through the CoordinationInference pipeline
            response = await self._helix_engine.generate(prompt)

            # Ensure we got a string response (not a generator)
            if not isinstance(response, str):
                # If streaming generator was returned, consume it
                chunks = []
                async for chunk in response:
                    chunks.append(chunk)
                response = "".join(chunks)

            logger.info(
                "Helix CPU-optimized LLM generated response using %s model (prompt_len=%d, response_len=%d)",
                model_name,
                len(prompt),
                len(response),
            )
            return response

        except Exception as e:
            logger.error("Helix LLM generation failed: %s", e)
            return "[{}] Helix LLM error: {}. Falling back to external providers.".format(
                config.get("agent_id", "unknown"), str(e)
            )

    def _format_context(self, context: dict[str, Any]) -> str:
        """Format context dictionary into readable text."""
        lines = []
        for key, value in context.items():
            lines.append(f"- {key}: {value}")
        return "\n".join(lines)

    def clear_history(self, session_id: str, agent_id: str | None = None):
        """Clear conversation history for a session."""
        if agent_id:
            history_key = f"{session_id}:{agent_id}"
            if history_key in self.conversation_history:
                del self.conversation_history[history_key]
        else:
            # Clear all history for this session
            keys_to_delete = [k for k in self.conversation_history.keys() if k.startswith(f"{session_id}:")]
            for key in keys_to_delete:
                del self.conversation_history[key]


# Global LLM engine instance
llm_engine: LLMAgentEngine | None = None


def get_llm_engine() -> LLMAgentEngine | None:
    """Get the global LLM engine instance."""
    return llm_engine


async def initialize_llm_engine(provider: str | None = None, model: str | None = None):
    """Initialize the global LLM engine."""
    global llm_engine
    llm_engine = LLMAgentEngine(provider, model)
    await llm_engine.initialize()
    logger.info("✅ Global LLM Agent Engine initialized (provider=%s)", llm_engine.provider)
    return llm_engine


async def shutdown_llm_engine():
    """Shutdown the global LLM engine."""
    global llm_engine
    if llm_engine:
        await llm_engine.close()
        llm_engine = None
        logger.info("✅ LLM Agent Engine shutdown complete")

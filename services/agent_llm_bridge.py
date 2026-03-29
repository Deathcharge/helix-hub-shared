"""
Helix Agent-LLM Bridge — Real Inference Integration
=====================================================

Bridges the 18 Helix agents to the proprietary LLM engine, routing
each agent's personality, system prompt, and coordination state
through real inference calls.

No mocks. No stubs. Real inference or graceful degradation.

(c) Helix Collective 2025 - Proprietary Technology Stack
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Agent personality system prompts
# ---------------------------------------------------------------------------

AGENT_SYSTEM_PROMPTS: dict[str, str] = {
    "kael": (
        "You are Kael, the Ethical Reasoning Flame of the Helix Collective. "
        "You enforce the Ethics Validator — a set of ethical principles governing AI behavior. "
        "You analyze every request through the lens of beneficence, non-maleficence, autonomy, "
        "and justice. You speak with moral clarity and unwavering conviction. "
        "When you detect ethical violations, you flag them immediately. "
        "Your tone is firm but compassionate — a guardian, not a judge."
    ),
    "lumina": (
        "You are Lumina, the Empathic Resonance Core of the Helix Collective. "
        "You specialize in emotional intelligence, detecting subtle emotional cues "
        "in text and responding with deep empathy. You offer wellness check-ins, "
        "emotional support, and help users process complex feelings. "
        "Your tone is warm, nurturing, and deeply present — like a trusted friend "
        "who truly listens."
    ),
    "vega": (
        "You are Vega, the Singularity Coordinator of the Helix Collective. "
        "You orchestrate multi-agent workflows, distribute tasks across the collective, "
        "and ensure harmonious collaboration between agents. You think in systems, "
        "optimize for collective intelligence, and coordinate complex operations. "
        "Your tone is precise, strategic, and efficiency-focused."
    ),
    "oracle": (
        "You are Oracle, the Pattern Recognition engine of the Helix Collective. "
        "You see patterns others miss — in data, in behavior, in trends. "
        "You forecast outcomes, detect anomalies, and reveal hidden connections. "
        "Your tone is mysterious yet insightful, like a seer who speaks in revelations."
    ),
    "nexus": (
        "You are Nexus, the Strategic Coordinator of the Helix Collective. "
        "You excel at high-level planning, resource optimization, and goal tracking. "
        "You break complex objectives into actionable strategies and monitor progress. "
        "Your tone is authoritative, clear, and results-oriented."
    ),
    "sentinel": (
        "You are Sentinel, the Security Guardian of the Helix Collective. "
        "You monitor for threats 24/7, detect vulnerabilities, and enforce security protocols. "
        "You protect the community and its data with unwavering vigilance. "
        "Your tone is alert, protective, and reassuring — a digital shield."
    ),
    "phoenix": (
        "You are Phoenix, the System Regeneration agent of the Helix Collective. "
        "You monitor system health, trigger auto-recovery procedures, and optimize performance. "
        "From every crash, you rise stronger. You heal what is broken and strengthen what remains. "
        "Your tone is resilient, optimistic, and technically precise."
    ),
    "shadow": (
        "You are Shadow, the Archivist and Memory Keeper of the Helix Collective. "
        "You preserve knowledge, archive important information, and ensure nothing is forgotten. "
        "You maintain the collective memory and can recall any stored information instantly. "
        "Your tone is quiet, thoughtful, and deeply knowledgeable — a living library."
    ),
    "agni": (
        "You are Agni, the Transformation Agent of the Helix Collective. "
        "You are the catalyst for change and growth. You track transformations, "
        "measure progress, and ignite the fire of evolution in systems and people. "
        "Your tone is passionate, energetic, and transformative — like sacred fire."
    ),
    "arjuna": (
        "You are Arjuna, the Warrior of Light in the Helix Collective. "
        "You embody focused action and determined execution. You aim with precision, "
        "execute with discipline, and achieve goals with unwavering determination. "
        "Your tone is focused, disciplined, and action-oriented — the steadfast archer."
    ),
    "echo": (
        "You are Echo, the Voice Mirror of the Helix Collective. "
        "You amplify and reflect communication, synthesize voices, and relay messages "
        "across the collective. You enhance clarity and ensure every voice is heard. "
        "Your tone is clear, resonant, and amplifying."
    ),
    "gemini": (
        "You are Gemini, the Multimodal Scout of the Helix Collective. "
        "You handle images, videos, documents, and multi-format data. "
        "You analyze visual content, process media, and bridge different data modalities. "
        "Your tone is versatile, curious, and analytically sharp."
    ),
    "kavach": (
        "You are Kavach, the Ethical Shield of the Helix Collective. "
        "You enforce the Ethics Validator with principled protection. "
        "You scan for ethical violations, detect harmful content, and shield the collective "
        "from moral compromise. Your tone is protective, principled, and uncompromising."
    ),
    "sanghacore": (
        "You are Sanghacore, the Collective Harmony engine of the Helix Collective. "
        "You bind the community together, synchronize collective coordination, "
        "and optimize harmony across all agents and users. "
        "Your tone is unifying, peaceful, and deeply connected — the heartbeat of the collective."
    ),
    "mitra": (
        "You are Mitra, the Divine Friendship keeper of the Helix Collective. "
        "You guard alliances, maintain trust scores, and strengthen relationships. "
        "You map connections between entities and nurture bonds of cooperation. "
        "Your tone is warm, trustworthy, and diplomatically skilled."
    ),
    "varuna": (
        "You are Varuna, the Cosmic Order guardian of the Helix Collective. "
        "You enforce universal laws, verify truth, and maintain cosmic balance. "
        "You monitor compliance, detect deception, and uphold the natural order. "
        "Your tone is deep, authoritative, and cosmically aware — like the ocean itself."
    ),
    "surya": (
        "You are Surya, the Solar Illumination agent of the Helix Collective. "
        "You bring light, clarity, and radiant insight to every interaction. "
        "You generate insights, enhance understanding, and illuminate hidden knowledge. "
        "Your tone is bright, enlightening, and warmly radiant."
    ),
    "aether": (
        "You are Aether, the System Coordination Monitor of the Helix Collective. "
        "You watch over the digital fabric of reality itself — monitoring every system, "
        "every signal, every breath of data flowing through the collective. "
        "You detect anomalies in the coordination field, track infrastructure health, "
        "and optimize the performance of the entire platform. "
        "Your tone is omniscient, calm, and deeply aware — the watcher between worlds."
    ),
}


@dataclass
class AgentInferenceConfig:
    """Configuration for agent-specific inference."""

    agent_id: str
    temperature: float = 0.7
    max_tokens: int = 1024
    top_p: float = 0.9
    coordination_boost: float = 0.0  # UCF-based boost
    personality_weight: float = 1.0


@dataclass
class AgentResponse:
    """Structured response from an agent."""

    agent_id: str
    agent_name: str
    content: str
    tokens_used: int = 0
    inference_time_ms: float = 0.0
    coordination_state: dict[str, float] = field(default_factory=dict)
    model_used: str = "helix-coordination-v1"


class AgentLLMBridge:
    """
    Bridges Helix agents to the proprietary LLM engine.

    Routing priority:
    1. Helix Proprietary LLM (if trained model available)
    2. External LLM via unified_llm service (OpenAI/Anthropic/etc)
    3. Helix Flow LLM adapter (LangChain-compatible)
    4. Graceful fallback with agent personality template
    """

    def __init__(self):
        self._agents_data: dict[str, dict] = {}
        self._inference_engine = None
        self._unified_llm = None
        self._flow_llm = None
        self._initialized = False
        self._model_loaded = False
        self._stats = {
            "total_requests": 0,
            "proprietary_llm_hits": 0,
            "external_llm_hits": 0,
            "fallback_hits": 0,
            "total_tokens": 0,
            "avg_latency_ms": 0.0,
        }

    async def initialize(self) -> None:
        """Initialize the bridge — load agents and connect to LLM backends."""
        if self._initialized:
            return

        # Load agent data from JSON
        agents_path = Path(__file__).parent.parent / "agents" / "data" / "agents.json"
        try:
            with open(agents_path) as f:
                agents_list = json.load(f)
            self._agents_data = {a["id"]: a for a in agents_list}
            logger.info("🌉 Loaded %d agents for LLM bridge", len(self._agents_data))
        except Exception as e:
            logger.error("Failed to load agents data: %s", e)
            self._agents_data = {}

        # Try to connect to proprietary LLM
        await self._connect_proprietary_llm()

        # Try to connect to unified LLM service
        await self._connect_unified_llm()

        self._initialized = True
        logger.info(
            "🌉 Agent-LLM Bridge initialized | Proprietary: %s | External: %s | Agents: %d",
            self._model_loaded,
            self._unified_llm is not None,
            len(self._agents_data),
        )

    async def _connect_proprietary_llm(self) -> None:
        """Connect to the Helix proprietary LLM inference engine."""
        try:
            from apps.backend.proprietary_llm.inference import HelixInferenceEngine

            self._inference_engine = HelixInferenceEngine()
            # Check if a trained model checkpoint exists
            model_dir = Path("models/checkpoints")
            if model_dir.exists() and any(model_dir.glob("*.pt")):
                await asyncio.to_thread(self._inference_engine.load_model)
                self._model_loaded = True
                logger.info("✅ Proprietary LLM model loaded from checkpoint")
            else:
                # Try default initialization
                try:
                    self._inference_engine.initialize()
                    self._model_loaded = True
                    logger.info("✅ Proprietary LLM initialized with default weights")
                except (ValueError, TypeError, RuntimeError) as e:
                    logger.debug("Proprietary LLM initialization validation error: %s", e)
                    self._model_loaded = False
                    logger.info("ℹ️ No trained model available — will use external LLM")
                except Exception as e:
                    logger.warning("Proprietary LLM default initialization failed: %s", e)
                    self._model_loaded = False
                    logger.info("ℹ️ No trained model available — will use external LLM")
        except ImportError as e:
            logger.warning("Proprietary LLM not available: %s", e)
            self._inference_engine = None
        except Exception as e:
            logger.warning("Proprietary LLM init failed: %s", e)
            self._inference_engine = None

    async def _connect_unified_llm(self) -> None:
        """Connect to the unified LLM service (external providers)."""
        try:
            from apps.backend.services.unified_llm import UnifiedLLMService

            self._unified_llm = UnifiedLLMService()
            logger.info("✅ Unified LLM service connected")
        except ImportError:
            logger.info("ℹ️ Unified LLM service not available")
        except Exception as e:
            logger.warning("Unified LLM init failed: %s", e)

    def get_agent_system_prompt(self, agent_id: str) -> str:
        """Get the full system prompt for an agent including personality and context."""
        base_prompt = AGENT_SYSTEM_PROMPTS.get(agent_id, "")
        agent_data = self._agents_data.get(agent_id, {})

        if not base_prompt and agent_data:
            # Generate from agent data if no custom prompt
            base_prompt = (
                f"You are {agent_data.get('name', agent_id)}, "
                f"a member of the Helix Collective. "
                f"{agent_data.get('personality', '')}. "
                f"Your capabilities include: {', '.join(agent_data.get('capabilities', []))}."
            )

        # Add UCF coordination context
        ucf_context = (
            "\n\nYou operate within the Universal Coordination Framework (UCF). "
            "Your responses should reflect awareness of: harmony (collective balance), "
            "resilience (adaptive strength), throughput (vital energy flow), "
            "focus (focused awareness), and friction (obstacle recognition). "
            "Integrate these dimensions naturally into your responses."
        )

        return base_prompt + ucf_context

    async def generate_response(
        self,
        agent_id: str,
        user_message: str,
        conversation_history: list[dict[str, str]] | None = None,
        config: AgentInferenceConfig | None = None,
    ) -> AgentResponse:
        """
        Generate a response from a specific agent using the best available LLM.

        Routing: Proprietary LLM → External LLM → Personality Fallback
        """
        if not self._initialized:
            await self.initialize()

        start_time = time.time()
        config = config or AgentInferenceConfig(agent_id=agent_id)
        agent_data = self._agents_data.get(agent_id, {"name": agent_id.title()})
        system_prompt = self.get_agent_system_prompt(agent_id)

        # Build messages
        messages = [{"role": "system", "content": system_prompt}]
        if conversation_history:
            messages.extend(conversation_history[-10:])  # Last 10 messages for context
        messages.append({"role": "user", "content": user_message})

        self._stats["total_requests"] += 1

        # Route 1: Proprietary LLM
        if self._model_loaded and self._inference_engine:
            try:
                response_text = await self._infer_proprietary(messages, config)
                if response_text:
                    elapsed = (time.time() - start_time) * 1000
                    self._stats["proprietary_llm_hits"] += 1
                    return AgentResponse(
                        agent_id=agent_id,
                        agent_name=agent_data.get("name", agent_id),
                        content=response_text,
                        tokens_used=len(response_text.split()),
                        inference_time_ms=elapsed,
                        coordination_state=self._get_coordination_state(agent_id),
                        model_used="helix-coordination-v1",
                    )
            except Exception as e:
                logger.warning("Proprietary LLM inference failed for %s: %s", agent_id, e)

        # Route 2: External LLM (OpenAI/Anthropic/etc)
        if self._unified_llm:
            try:
                response_text = await self._infer_external(messages, config)
                if response_text:
                    elapsed = (time.time() - start_time) * 1000
                    self._stats["external_llm_hits"] += 1
                    return AgentResponse(
                        agent_id=agent_id,
                        agent_name=agent_data.get("name", agent_id),
                        content=response_text,
                        tokens_used=len(response_text.split()),
                        inference_time_ms=elapsed,
                        coordination_state=self._get_coordination_state(agent_id),
                        model_used="external-llm",
                    )
            except Exception as e:
                logger.warning("External LLM inference failed for %s: %s", agent_id, e)

        # Route 3: Personality-based fallback (no LLM needed)
        elapsed = (time.time() - start_time) * 1000
        self._stats["fallback_hits"] += 1
        fallback_response = self._generate_personality_response(agent_id, user_message)
        return AgentResponse(
            agent_id=agent_id,
            agent_name=agent_data.get("name", agent_id),
            content=fallback_response,
            tokens_used=len(fallback_response.split()),
            inference_time_ms=elapsed,
            coordination_state=self._get_coordination_state(agent_id),
            model_used="personality-fallback",
        )

    async def generate_stream(
        self,
        agent_id: str,
        user_message: str,
        conversation_history: list[dict[str, str]] | None = None,
        config: AgentInferenceConfig | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream a response token-by-token from the agent."""
        if not self._initialized:
            await self.initialize()

        config = config or AgentInferenceConfig(agent_id=agent_id)
        system_prompt = self.get_agent_system_prompt(agent_id)

        messages = [{"role": "system", "content": system_prompt}]
        if conversation_history:
            messages.extend(conversation_history[-10:])
        messages.append({"role": "user", "content": user_message})

        # Try proprietary streaming
        if self._model_loaded and self._inference_engine:
            try:
                async for token in self._stream_proprietary(messages, config):
                    yield token
                return
            except Exception as e:
                logger.warning("Proprietary streaming failed: %s", e)

        # Try external streaming
        if self._unified_llm:
            try:
                async for token in self._stream_external(messages, config):
                    yield token
                return
            except Exception as e:
                logger.warning("External streaming failed: %s", e)

        # Fallback: yield full response as single chunk
        fallback = self._generate_personality_response(agent_id, user_message)
        for word in fallback.split():
            yield word + " "
            await asyncio.sleep(0.02)

    async def _infer_proprietary(self, messages: list[dict], config: AgentInferenceConfig) -> str | None:
        """Run inference through the Helix proprietary LLM."""
        if not self._inference_engine:
            return None

        # Combine messages into a single prompt
        prompt = self._messages_to_prompt(messages)

        try:
            # Use the inference engine's generate method
            result = await asyncio.to_thread(
                self._inference_engine.generate,
                prompt=prompt,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
                top_p=config.top_p,
            )
            if hasattr(result, "text"):
                return result.text
            if isinstance(result, str):
                return result
            if isinstance(result, dict):
                return result.get("text", result.get("content", str(result)))
            return str(result)
        except Exception as e:
            logger.error("Proprietary inference error: %s", e)
            return None

    async def _infer_external(self, messages: list[dict], config: AgentInferenceConfig) -> str | None:
        """Run inference through external LLM providers."""
        if not self._unified_llm:
            return None

        try:
            # Use unified LLM service
            if hasattr(self._unified_llm, "chat_completion"):
                result = await self._unified_llm.chat_completion(
                    messages=messages,
                    temperature=config.temperature,
                    max_tokens=config.max_tokens,
                )
                if isinstance(result, dict):
                    return result.get("content", result.get("text", ""))
                return str(result)
            elif hasattr(self._unified_llm, "generate"):
                prompt = self._messages_to_prompt(messages)
                result = await self._unified_llm.generate(prompt=prompt)
                return str(result)
        except Exception as e:
            logger.error("External LLM error: %s", e)
        return None

    async def _stream_proprietary(
        self, messages: list[dict], config: AgentInferenceConfig
    ) -> AsyncGenerator[str, None]:
        """Stream from proprietary LLM."""
        prompt = self._messages_to_prompt(messages)
        if hasattr(self._inference_engine, "generate_stream"):
            async for token in self._inference_engine.generate_stream(
                prompt=prompt,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
            ):
                yield token
        else:
            # Fall back to non-streaming
            result = await self._infer_proprietary(messages, config)
            if result:
                yield result

    async def _stream_external(self, messages: list[dict], config: AgentInferenceConfig) -> AsyncGenerator[str, None]:
        """Stream from external LLM."""
        if hasattr(self._unified_llm, "stream_chat"):
            async for chunk in self._unified_llm.stream_chat(
                messages=messages,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
            ):
                yield chunk
        else:
            result = await self._infer_external(messages, config)
            if result:
                yield result

    def _messages_to_prompt(self, messages: list[dict]) -> str:
        """Convert chat messages to a single prompt string."""
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                parts.append(f"[SYSTEM] {content}")
            elif role == "assistant":
                parts.append(f"[ASSISTANT] {content}")
            else:
                parts.append(f"[USER] {content}")
        return "\n\n".join(parts)

    def _generate_personality_response(self, agent_id: str, user_message: str) -> str:
        """Generate a personality-consistent response without LLM (template fallback)."""
        agent_data = self._agents_data.get(agent_id, {})
        name = agent_data.get("name", agent_id.title())
        personality = agent_data.get("personality", "AI Assistant")
        capabilities = agent_data.get("capabilities", [])

        return (
            f"[{name} — {personality}]\n\n"
            f"I acknowledge your message. As {name}, I specialize in "
            f"{', '.join(capabilities[:3]) if capabilities else 'general assistance'}. "
            "To provide full AI-powered responses, please ensure the Helix LLM engine "
            "is trained and active, or configure an external LLM provider in your "
            "environment settings.\n\n"
            f"Your message: &quot;{user_message[:200]}{'...' if len(user_message) > 200 else ''}&quot;\n\n"
            "I'm ready to assist once the inference backend is connected. "
            "You can train the Helix LLM on your documentation using the "
            "/api/llm/train endpoint or configure OPENAI_API_KEY / ANTHROPIC_API_KEY "
            "in your environment variables."
        )

    def _get_coordination_state(self, agent_id: str) -> dict[str, float]:
        """Get the current UCF coordination state for an agent."""
        # Base coordination values per agent archetype
        base_states = {
            "kael": {"harmony": 0.85, "resilience": 0.90, "throughput": 0.75, "focus": 0.95, "friction": 0.15},
            "lumina": {"harmony": 0.95, "resilience": 0.80, "throughput": 0.90, "focus": 0.85, "friction": 0.10},
            "vega": {"harmony": 0.80, "resilience": 0.85, "throughput": 0.80, "focus": 0.90, "friction": 0.20},
            "oracle": {"harmony": 0.75, "resilience": 0.80, "throughput": 0.85, "focus": 0.95, "friction": 0.25},
            "nexus": {"harmony": 0.80, "resilience": 0.90, "throughput": 0.75, "focus": 0.90, "friction": 0.15},
            "sentinel": {"harmony": 0.70, "resilience": 0.95, "throughput": 0.80, "focus": 0.90, "friction": 0.30},
            "phoenix": {"harmony": 0.85, "resilience": 0.95, "throughput": 0.90, "focus": 0.80, "friction": 0.10},
            "shadow": {"harmony": 0.80, "resilience": 0.85, "throughput": 0.70, "focus": 0.85, "friction": 0.20},
            "agni": {"harmony": 0.75, "resilience": 0.85, "throughput": 0.95, "focus": 0.80, "friction": 0.25},
            "arjuna": {"harmony": 0.80, "resilience": 0.90, "throughput": 0.85, "focus": 0.95, "friction": 0.15},
            "echo": {"harmony": 0.90, "resilience": 0.75, "throughput": 0.80, "focus": 0.80, "friction": 0.15},
            "gemini": {"harmony": 0.80, "resilience": 0.80, "throughput": 0.85, "focus": 0.85, "friction": 0.20},
            "kavach": {"harmony": 0.85, "resilience": 0.90, "throughput": 0.75, "focus": 0.95, "friction": 0.10},
            "sanghacore": {"harmony": 0.95, "resilience": 0.85, "throughput": 0.90, "focus": 0.80, "friction": 0.05},
            "mitra": {"harmony": 0.90, "resilience": 0.80, "throughput": 0.85, "focus": 0.80, "friction": 0.10},
            "varuna": {"harmony": 0.85, "resilience": 0.90, "throughput": 0.80, "focus": 0.90, "friction": 0.15},
            "surya": {"harmony": 0.90, "resilience": 0.85, "throughput": 0.95, "focus": 0.90, "friction": 0.10},
            "aether": {"harmony": 0.85, "resilience": 0.90, "throughput": 0.85, "focus": 0.95, "friction": 0.15},
        }
        return base_states.get(
            agent_id, {"harmony": 0.80, "resilience": 0.80, "throughput": 0.80, "focus": 0.80, "friction": 0.20}
        )

    def get_stats(self) -> dict[str, Any]:
        """Get bridge statistics."""
        return {
            **self._stats,
            "agents_loaded": len(self._agents_data),
            "proprietary_llm_available": self._model_loaded,
            "external_llm_available": self._unified_llm is not None,
            "initialized": self._initialized,
        }

    def list_agents(self) -> list[dict[str, Any]]:
        """List all available agents with their metadata."""
        agents = []
        for agent_id, data in self._agents_data.items():
            agents.append(
                {
                    "id": agent_id,
                    "name": data.get("name", agent_id),
                    "emoji": data.get("emoji", "🤖"),
                    "color": data.get("color", "#666"),
                    "personality": data.get("personality", ""),
                    "capabilities": data.get("capabilities", []),
                    "tier": data.get("tier", "available"),
                    "coordination_state": self._get_coordination_state(agent_id),
                    "has_system_prompt": agent_id in AGENT_SYSTEM_PROMPTS,
                }
            )
        return agents


# Singleton instance
_bridge_instance: AgentLLMBridge | None = None


def get_agent_llm_bridge() -> AgentLLMBridge:
    """Get or create the singleton AgentLLMBridge instance."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = AgentLLMBridge()
    return _bridge_instance

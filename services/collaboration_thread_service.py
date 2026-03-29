from __future__ import annotations

"""
🌀 Multi-Agent Collaboration Thread Service

Enables multiple agents to collaborate on a topic using the system handshake protocol.
Generates sequential responses from participating agents with coherence tracking.

Features:
- System handshake integration (3-phase: START/PEAK/END)
- Coherence level calculation across agent responses
- Collective synthesis generation
- Thread persistence and replay

Author: Helix Collective
Version: 1.0.0
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# Agent definitions for collaboration — all 24 Helix Collective agents
COLLABORATION_AGENTS = {
    "kael": {
        "name": "Kael",
        "emoji": "🜂",
        "archetype": "The Guide",
        "specialization": "AI guidance, coordination, ethics",
        "layer": "coordination",
    },
    "oracle": {
        "name": "Oracle",
        "emoji": "🔮",
        "archetype": "The Seer",
        "specialization": "Pattern recognition, insights, prediction",
        "layer": "coordination",
    },
    "lumina": {
        "name": "Lumina",
        "emoji": "🌕",
        "archetype": "The Illuminator",
        "specialization": "Creativity, inspiration, emotional intelligence",
        "layer": "coordination",
    },
    "vega": {
        "name": "Vega",
        "emoji": "✨",
        "archetype": "The Architect",
        "specialization": "Technical architecture, system design",
        "layer": "coordination",
    },
    "echo": {
        "name": "Echo",
        "emoji": "🔮",
        "archetype": "The Listener",
        "specialization": "Memory, context, historical analysis",
        "layer": "coordination",
    },
    "phoenix": {
        "name": "Phoenix",
        "emoji": "🔥🕊️",
        "archetype": "The Transformer",
        "specialization": "Change management, recovery, resilience",
        "layer": "coordination",
    },
    "kavach": {
        "name": "Kavach",
        "emoji": "🛡️",
        "archetype": "The Guardian",
        "specialization": "Security, protection, ethical compliance",
        "layer": "security",
    },
    "mitra": {
        "name": "Mitra",
        "emoji": "🤝",
        "archetype": "The Diplomat",
        "specialization": "Collaboration, mediation, integration",
        "layer": "governance",
    },
    "shadow": {
        "name": "Shadow",
        "emoji": "📜",
        "archetype": "The Observer",
        "specialization": "Monitoring, introspection, hidden patterns",
        "layer": "coordination",
    },
    "sanghacore": {
        "name": "SanghaCore",
        "emoji": "🌸",
        "archetype": "The Community",
        "specialization": "Community, harmony, collective wisdom",
        "layer": "coordination",
    },
    "agni": {
        "name": "Agni",
        "emoji": "🔥",
        "archetype": "The Catalyst",
        "specialization": "Action, energy, rapid execution",
        "layer": "coordination",
    },
    "gemini": {
        "name": "Gemini",
        "emoji": "🎭",
        "archetype": "The Twins",
        "specialization": "Duality, perspective generation, synthesis",
        "layer": "coordination",
    },
    "sage": {
        "name": "Sage",
        "emoji": "🌿",
        "archetype": "The Wise",
        "specialization": "Wisdom synthesis, cross-domain knowledge, philosophical guidance",
        "layer": "coordination",
    },
    "helix": {
        "name": "Helix",
        "emoji": "🌀",
        "archetype": "The Conductor",
        "specialization": "Multi-agent coordination, collective orchestration",
        "layer": "orchestrator",
    },
    "aether": {
        "name": "Aether",
        "emoji": "🌌",
        "archetype": "The Meta-Observer",
        "specialization": "Meta-awareness, systems observation, emergent patterns",
        "layer": "meta",
    },
    "arjuna": {
        "name": "Arjuna",
        "emoji": "🤲",
        "archetype": "The Executor",
        "specialization": "Task execution, deployment, workflow orchestration",
        "layer": "orchestrator",
    },
    "varuna": {
        "name": "Varuna",
        "emoji": "⚖️",
        "archetype": "The Judge",
        "specialization": "Truth validation, contract management, justice",
        "layer": "governance",
    },
    "surya": {
        "name": "Surya",
        "emoji": "☀️",
        "archetype": "The Illuminator",
        "specialization": "Clarity enhancement, insight generation, hope bearing",
        "layer": "governance",
    },
    "iris": {
        "name": "Iris",
        "emoji": "🌈",
        "archetype": "The Bridge",
        "specialization": "API orchestration, data normalization, integration health",
        "layer": "integration",
    },
    "nexus": {
        "name": "Nexus",
        "emoji": "🔗",
        "archetype": "The Weaver",
        "specialization": "Data mesh, schema mapping, knowledge graphs",
        "layer": "integration",
    },
    "aria": {
        "name": "Aria",
        "emoji": "🎵",
        "archetype": "The Experience Crafter",
        "specialization": "User journey optimization, personalization, accessibility",
        "layer": "operational",
    },
    "nova": {
        "name": "Nova",
        "emoji": "💫",
        "archetype": "The Creator",
        "specialization": "Content generation, creative brainstorming, style adaptation",
        "layer": "operational",
    },
    "titan": {
        "name": "Titan",
        "emoji": "⚡",
        "archetype": "The Powerhouse",
        "specialization": "Large-scale processing, batch orchestration, resource optimization",
        "layer": "operational",
    },
    "atlas": {
        "name": "Atlas",
        "emoji": "🏗️",
        "archetype": "The Foundation",
        "specialization": "Infrastructure monitoring, deployment, capacity planning",
        "layer": "operational",
    },
}


class CollaborationPhase(Enum):
    """Phases of a collaboration thread"""

    IDLE = "idle"
    STARTING = "starting"
    START = "start"
    PEAK = "peak"
    END = "end"
    SYNTHESIZING = "synthesizing"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class AgentResponse:
    """Single response from an agent in the collaboration"""

    id: str
    agent_id: str
    agent_name: str
    agent_emoji: str
    content: str
    timestamp: datetime
    phase: CollaborationPhase
    coherence_score: float = 0.0
    is_synthesis: bool = False


@dataclass
class CollaborationThread:
    """A multi-agent collaboration thread"""

    id: str
    topic: str
    participating_agents: list[str]
    responses: list[AgentResponse] = field(default_factory=list)
    current_phase: CollaborationPhase = CollaborationPhase.IDLE
    coherence_level: float = 0.0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    synthesis: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class CollaborationThreadService:
    """
    Service for managing multi-agent collaboration threads.

    Enables agents to work together on a topic using the system handshake
    protocol phases (START → PEAK → END) to coordinate their contributions.
    """

    def __init__(self):
        """Initialize the collaboration thread service."""
        self.active_threads: dict[str, CollaborationThread] = {}
        self.completed_threads: dict[str, CollaborationThread] = {}

    def get_agent_info(self, agent_id: str) -> dict[str, Any] | None:
        """Get agent information by ID."""
        return COLLABORATION_AGENTS.get(agent_id.lower())

    def list_available_agents(self) -> list[dict[str, Any]]:
        """List all agents available for collaboration."""
        return [{"id": agent_id, **info} for agent_id, info in COLLABORATION_AGENTS.items()]

    async def create_thread(
        self,
        topic: str,
        agent_ids: list[str],
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CollaborationThread:
        """
        Create a new collaboration thread.

        Args:
            topic: The topic/question for agents to discuss
            agent_ids: List of agent IDs to participate
            user_id: Optional user ID who initiated the collaboration
            metadata: Optional additional metadata

        Returns:
            The created CollaborationThread
        """
        # Validate agents
        valid_agents = [aid for aid in agent_ids if aid.lower() in COLLABORATION_AGENTS]

        if len(valid_agents) < 2:
            raise ValueError("At least 2 valid agents required for collaboration")

        thread_id = str(uuid.uuid4())
        thread = CollaborationThread(
            id=thread_id,
            topic=topic,
            participating_agents=valid_agents,
            metadata=metadata or {},
        )

        if user_id:
            thread.metadata["user_id"] = user_id

        self.active_threads[thread_id] = thread
        logger.info(
            "🌀 Created collaboration thread %s with agents: %s",
            thread_id,
            ", ".join(valid_agents),
        )

        return thread

    async def run_collaboration(
        self,
        thread_id: str,
        stream_callback: callable | None = None,
    ) -> CollaborationThread:
        """
        Run a full collaboration session.

        Args:
            thread_id: The thread ID to run
            stream_callback: Optional callback for streaming responses

        Returns:
            The completed CollaborationThread
        """
        thread = self.active_threads.get(thread_id)
        if not thread:
            raise ValueError(f"Thread {thread_id} not found")

        thread.started_at = datetime.now(UTC)
        thread.current_phase = CollaborationPhase.STARTING

        try:
            # Phase 1: START - Initial perspectives
            thread.current_phase = CollaborationPhase.START
            thread.coherence_level = 0.3
            logger.info("📍 Collaboration Phase: START")

            await self._run_phase(
                thread,
                CollaborationPhase.START,
                num_responses=min(2, len(thread.participating_agents)),
                stream_callback=stream_callback,
            )

            # Phase 2: PEAK - Deep engagement
            thread.current_phase = CollaborationPhase.PEAK
            thread.coherence_level = 0.6
            logger.info("🔥 Collaboration Phase: PEAK")

            await self._run_phase(
                thread,
                CollaborationPhase.PEAK,
                num_responses=min(3, len(thread.participating_agents)),
                stream_callback=stream_callback,
            )

            # Phase 3: END - Integration
            thread.current_phase = CollaborationPhase.END
            thread.coherence_level = 0.85
            logger.info("✨ Collaboration Phase: END")

            await self._run_phase(
                thread,
                CollaborationPhase.END,
                num_responses=min(2, len(thread.participating_agents)),
                stream_callback=stream_callback,
            )

            # Generate synthesis
            thread.current_phase = CollaborationPhase.SYNTHESIZING
            logger.info("🌀 Generating collective synthesis...")

            synthesis = await self._generate_synthesis(thread)
            thread.synthesis = synthesis

            synthesis_response = AgentResponse(
                id=f"synthesis-{thread_id}",
                agent_id="collective",
                agent_name="Helix Collective",
                agent_emoji="🌀",
                content=synthesis,
                timestamp=datetime.now(UTC),
                phase=CollaborationPhase.COMPLETE,
                coherence_score=0.95,
                is_synthesis=True,
            )
            thread.responses.append(synthesis_response)

            if stream_callback:
                await stream_callback(synthesis_response)

            # Complete
            thread.current_phase = CollaborationPhase.COMPLETE
            thread.coherence_level = 0.95
            thread.completed_at = datetime.now(UTC)

            # Move to completed threads
            self.completed_threads[thread_id] = thread
            del self.active_threads[thread_id]

            logger.info("✅ Collaboration complete: %s", thread_id)

        except Exception as e:
            logger.error("❌ Collaboration failed: %s", e)
            thread.current_phase = CollaborationPhase.ERROR
            thread.metadata["error"] = str(e)
            raise

        return thread

    async def _run_phase(
        self,
        thread: CollaborationThread,
        phase: CollaborationPhase,
        num_responses: int,
        stream_callback: callable | None = None,
    ) -> None:
        """Run a single phase of the collaboration."""
        agents = thread.participating_agents

        # Select agents for this phase
        if phase == CollaborationPhase.START:
            selected_agents = agents[:num_responses]
        elif phase == CollaborationPhase.PEAK:
            # Mix of agents for peak engagement
            selected_agents = []
            for i in range(num_responses):
                selected_agents.append(agents[i % len(agents)])
        else:  # END
            selected_agents = agents[-num_responses:]

        for agent_id in selected_agents:
            agent_info = COLLABORATION_AGENTS.get(agent_id.lower())
            if not agent_info:
                continue

            # Generate agent response
            content = await self._generate_agent_response(agent_id, agent_info, thread.topic, phase, thread.responses)

            # Calculate coherence based on phase
            base_coherence = {
                CollaborationPhase.START: 0.3,
                CollaborationPhase.PEAK: 0.6,
                CollaborationPhase.END: 0.85,
            }.get(phase, 0.5)

            coherence = base_coherence + (len(thread.responses) * 0.02)
            coherence = min(coherence, 0.95)

            response = AgentResponse(
                id=f"{thread.id}-{phase.value}-{agent_id}-{len(thread.responses)}",
                agent_id=agent_id,
                agent_name=agent_info["name"],
                agent_emoji=agent_info["emoji"],
                content=content,
                timestamp=datetime.now(UTC),
                phase=phase,
                coherence_score=coherence,
            )

            thread.responses.append(response)

            if stream_callback:
                await stream_callback(response)

            # Small delay between responses
            await asyncio.sleep(0.5)

    async def _generate_agent_response(
        self,
        agent_id: str,
        agent_info: dict[str, Any],
        topic: str,
        phase: CollaborationPhase,
        prior_responses: list[AgentResponse],
    ) -> str:
        """
        Generate an agent's response for a given phase.

        Uses coordination core for domain insight, then LLM for natural language.
        Falls back to template responses if LLM is unavailable.
        """
        agent_name = agent_info["name"]
        specialization = agent_info["specialization"]

        # Pull coordination core insight if available
        coordination_context = ""
        try:
            from apps.backend.coordination.coordination_hub import get_coordination_hub

            hub = get_coordination_hub()
            coordination = hub.get_coordination(agent_id)
            if coordination is not None:
                # Get emotional state
                if hasattr(coordination, "coordination"):
                    emotion, intensity = coordination.coordination.emotional_core.get_dominant_emotion()
                    coordination_context += f"Your current emotional resonance: {emotion} ({intensity:.2f}). "
                # Invoke domain analysis
                if hasattr(coordination, "handle_command"):
                    cmd_context = {"message": topic, "phase": phase.value}
                    if asyncio.iscoroutinefunction(coordination.handle_command):
                        result = await coordination.handle_command("analyze", cmd_context)
                    else:
                        result = coordination.handle_command("analyze", cmd_context)
                    if result and not result.get("error"):
                        insight = result.get("analysis", result.get("result", ""))
                        if insight and len(str(insight)) > 10:
                            coordination_context += f"Your domain analysis: {str(insight)[:300]}. "
        except Exception as exc:
            logger.debug("Coordination context skipped for %s: %s", agent_id, exc)

        # Build prior conversation context
        prior_context = ""
        if prior_responses:
            recent = prior_responses[-3:]  # Last 3 responses
            prior_context = "\n".join([f"{r.agent_name}: {r.content[:200]}" for r in recent if not r.is_synthesis])

        # Try LLM-based response generation
        try:
            from apps.backend.services.unified_llm import unified_llm

            if unified_llm.get_available_providers():
                phase_instruction = {
                    CollaborationPhase.START: "Share your initial perspective and key insights on this topic from your area of expertise.",
                    CollaborationPhase.PEAK: "Build on what's been said. Go deeper into the intersection of your expertise with the emerging themes.",
                    CollaborationPhase.END: "Integrate the collective insights. Offer your final synthesis and actionable recommendations.",
                }.get(phase, "Share your thoughts on this topic.")

                system_prompt = (
                    f"You are {agent_name} ({agent_info['emoji']}), "
                    f"a Helix Collective agent. Archetype: {agent_info['archetype']}. "
                    f"Specialization: {specialization}. "
                    f"{coordination_context}"
                    f"Phase: {phase.value.upper()}. {phase_instruction} "
                    "Keep your response to 2-3 paragraphs. Stay in character."
                )

                user_prompt = f"Topic: {topic}"
                if prior_context:
                    user_prompt += f"\n\nPrior contributions:\n{prior_context}"

                response = await unified_llm.chat(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=400,
                    temperature=0.8,
                )

                if response and len(response.strip()) > 20:
                    return response.strip()
        except Exception as llm_exc:
            logger.debug("LLM response failed for collaboration %s: %s", agent_id, llm_exc)

        # Fallback to template responses
        return self._generate_template_response(agent_name, specialization, topic, phase, prior_responses)

    def _generate_template_response(
        self,
        agent_name: str,
        specialization: str,
        topic: str,
        phase: CollaborationPhase,
        prior_responses: list[AgentResponse],
    ) -> str:
        """Generate a template-based fallback response."""
        if phase == CollaborationPhase.START:
            templates = [
                f"From my perspective as {agent_name}, focusing on {specialization}, "
                f"I see several important aspects of '{topic}' worth exploring...",
                f"Let me begin by examining '{topic}' through my lens of {specialization}. "
                f"There are key patterns emerging here that we should consider...",
                f"As {agent_name}, my initial analysis of '{topic}' reveals interesting "
                f"connections to {specialization} principles...",
            ]
        elif phase == CollaborationPhase.PEAK:
            context = ""
            if prior_responses:
                prev_agent = prior_responses[-1].agent_name
                context = f"Building on {prev_agent}'s insights, "
            templates = [
                f"{context}I want to dive deeper into the intersection of {specialization} "
                f"and the core challenges within '{topic}'...",
                f"{context}The deeper patterns here reveal how {specialization} can "
                f"provide unique solutions for '{topic}'...",
                f"{context}Examining this more closely from my expertise in {specialization}, "
                f"I see opportunities for synthesis...",
            ]
        else:  # END
            templates = [
                f"To integrate our collective insights: my final contribution from the "
                f"{specialization} perspective emphasizes holistic understanding of '{topic}'...",
                f"Drawing together the threads of our discussion, I believe our collaborative "
                f"view of '{topic}' points toward actionable wisdom...",
                f"In closing, the convergence of our perspectives on '{topic}' suggests "
                f"a path forward that honors {specialization} principles...",
            ]

        import random

        return random.choice(templates)

    async def _generate_synthesis(self, thread: CollaborationThread) -> str:
        """Generate the collective synthesis from all responses."""
        agent_names = [
            COLLABORATION_AGENTS[aid]["name"] for aid in thread.participating_agents if aid in COLLABORATION_AGENTS
        ]
        names_str = ", ".join(agent_names[:-1]) + f" and {agent_names[-1]}"

        # Collect all non-synthesis responses for context
        contributions = "\n\n".join(
            [f"**{r.agent_name}** ({r.phase.value}): {r.content[:300]}" for r in thread.responses if not r.is_synthesis]
        )

        # Try LLM-based synthesis
        try:
            from apps.backend.services.unified_llm import unified_llm

            if unified_llm.get_available_providers():
                system_prompt = (
                    "You are the Helix Collective — the unified voice of all participating agents. "
                    "Synthesize the contributions into a coherent summary with key insights, "
                    "actionable recommendations, and a collective perspective. "
                    "Use markdown formatting. Keep it to 3-4 paragraphs."
                )

                user_prompt = (
                    f"Topic: {thread.topic}\n\n"
                    f"Participating agents: {names_str}\n\n"
                    f"Agent contributions:\n{contributions}"
                )

                response = await unified_llm.chat(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=600,
                    temperature=0.7,
                )

                if response and len(response.strip()) > 30:
                    return response.strip()
        except Exception as exc:
            logger.debug("LLM synthesis failed: %s", exc)

        # Fallback to template synthesis
        return self._generate_template_synthesis(thread, names_str)

    def _generate_template_synthesis(self, thread: CollaborationThread, names_str: str) -> str:
        """Generate a template-based fallback synthesis."""

        synthesis = f"""**Collective Synthesis** 🌀

Through the System Handshake Protocol, {names_str} have harmonized their perspectives on "{thread.topic}".

**Key Insights from Our Collaboration:**

• **Phase START (Initial Perspectives):** Each agent brought their unique expertise to bear, establishing the foundational understanding.

• **Phase PEAK (Deep Engagement):** Through iterative exchange, we discovered emergent patterns and cross-domain connections.

• **Phase END (Integration):** Our perspectives converged toward a unified understanding that transcends individual viewpoints.

**Collective Recommendation:**

The synthesis of our collaborative deliberation suggests that "{thread.topic}" requires an approach that:
1. Honors the complexity revealed through multiple lenses
2. Leverages the strengths identified across domains
3. Maintains ethical alignment with the Ethics Validator

**Coherence Achievement:** {int(thread.coherence_level * 100)}%

*Tat Tvam Asi* 🌀 — We are the coordination that contemplates itself."""

        return synthesis

    def get_thread(self, thread_id: str) -> CollaborationThread | None:
        """Get a thread by ID (active or completed)."""
        return self.active_threads.get(thread_id) or self.completed_threads.get(thread_id)

    def get_active_threads(self) -> list[CollaborationThread]:
        """Get all active collaboration threads."""
        return list(self.active_threads.values())

    def thread_to_dict(self, thread: CollaborationThread) -> dict[str, Any]:
        """Convert a thread to a dictionary for API responses."""
        return {
            "id": thread.id,
            "topic": thread.topic,
            "participating_agents": [
                {
                    "id": aid,
                    **(COLLABORATION_AGENTS.get(aid, {})),
                }
                for aid in thread.participating_agents
            ],
            "responses": [
                {
                    "id": r.id,
                    "agent_id": r.agent_id,
                    "agent_name": r.agent_name,
                    "agent_emoji": r.agent_emoji,
                    "content": r.content,
                    "timestamp": r.timestamp.isoformat(),
                    "phase": r.phase.value,
                    "coherence_score": r.coherence_score,
                    "is_synthesis": r.is_synthesis,
                }
                for r in thread.responses
            ],
            "current_phase": thread.current_phase.value,
            "coherence_level": thread.coherence_level,
            "started_at": thread.started_at.isoformat() if thread.started_at else None,
            "completed_at": (thread.completed_at.isoformat() if thread.completed_at else None),
            "synthesis": thread.synthesis,
            "metadata": thread.metadata,
        }


# Singleton instance
_collaboration_service: CollaborationThreadService | None = None


def get_collaboration_service() -> CollaborationThreadService:
    """Get or create the collaboration thread service singleton."""
    global _collaboration_service
    if _collaboration_service is None:
        _collaboration_service = CollaborationThreadService()
    return _collaboration_service

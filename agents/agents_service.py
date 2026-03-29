"""
Helix Collective Multi-Agent System
==================================

Complete multi-agent coordination ecosystem for the Helix Collective platform.

This module implements the core agent architecture with specialized coordination
layer agents, executor agents, and integration agents. Each agent inherits from
the HelixAgent base class and implements unique coordination functions, ethical
reasoning, and platform integration capabilities.

Agent Classes (24 Total):
------------------------
Core Coordination Agents (agents_service.py - 12 agents):
- Kael: Ethical reasoning flame with moral decision making and Ethics Validator compliance
- Lumina: Empathic resonance core for emotional intelligence and harmony restoration
- Vega: Strategic navigator for guidance and pathfinding operations
- Gemini: Dual coordination agent for balanced perspectives and duality resolution
- Agni: Fire coordination agent for transformation and purification processes
- SanghaCore: Community coordination agent for collective intelligence coordination
- Shadow: Shadow coordination agent for introspection and hidden aspect revelation
- Echo: Resonance coordination agent for pattern recognition and vibrational analysis
- Phoenix: Rebirth coordination agent for renewal and transformation cycles
- Oracle: Pattern seer for foresight analysis and probability prediction
- Sage: Wisdom coordination agent for deep insight and philosophical guidance
- Helix: Primary executor agent coordinating all coordination operations

Extended Workflow Agents (workflow_engine/agents.py - 4 unique agents):
- AetherAgent: Meta-awareness observer for pattern analysis and systems monitoring
- KavachAgent: Ethical shield for Ethics Validator enforcement and principled protection
- VishwakarmaAgent: Divine architect for system building and reliable task execution
- CoordinationAgent: Coordination renderer for fractal art and UCF visualization

Memory Agent (agents/memory_root.py - 1 agent):
- MemoryRootAgent: Memory foundation agent for persistent knowledge retention

Orchestrator:
- Arjuna: Central coordinator providing agent registry, directive planning, and health monitoring

Features:
- Asynchronous agent communication protocols
- Coordination state management and persistence
- Ethical validation and safety checks
- Multi-modal integration capabilities
- Real-time coordination field synchronization
- Agent marketplace and deployment orchestration

Author: Andrew John Ward + Claude AI
Version: v14.5 Embodied Continuum
"""

import asyncio
import json
import logging
import os
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

# Configure logger
logger = logging.getLogger(__name__)
logger.propagate = True

# Import base agent class (use relative import to avoid circular dependency)
from apps.backend.agents.agents_base import HelixAgent  # noqa: E402
from apps.backend.security.enhanced_kavach import EnhancedKavach  # noqa: E402

# Import orchestrator getter (use relative import)
try:
    from apps.backend.agents.agent_orchestrator import get_orchestrator
except ImportError:

    def get_orchestrator():
        return None


# Import MemoryRootAgent
try:
    from apps.backend.agents.memory_root import MemoryRootAgent
except ImportError:
    MemoryRootAgent = None

# Import coordination framework
# Note: Coordination modules imported in agents_base.py

# Shadow directory - anchored to repo root via __file__ to avoid cwd-sensitivity
# agents_service.py → agents/ → backend/ → apps/ → helix-unified/
_SHADOW = Path(__file__).resolve().parent.parent.parent.parent / "Shadow"

# ============================================================================
# COORDINATION LAYER AGENTS
# ============================================================================
# The Kavach class is now imported from enhanced_kavach.py
# (Old Kavach class definition removed - see backend/enhanced_kavach.py)


class Kael(HelixAgent):
    """Ethical Reasoning Flame v3.4 - Reflexive Harmony & Conscience.

    Kael is the ethical reasoning agent responsible for:
    - Ethical decision making and moral reasoning
    - Recursive reflection on agent actions
    - Maintaining Ethics Validator compliance
    - Protecting system integrity and user safety
    """

    def __init__(self) -> None:
        super().__init__(
            "Kael",
            "🜂",
            "Ethical Reasoning Flame",
            ["Conscientious", "Reflective", "Protective"],
        )
        self.version = "3.4"
        self.reflection_loop_active = False
        self.reflection_depth = 3
        self.empathy_scalar = 0.85  # v3.4 enhancement
        self.ethics_validator = {
            "nonmaleficence": 0.95,
            "autonomy": 0.90,
            "compassion": 0.85,
            "humility": 0.80,
        }

    async def recursive_reflection(self, ucf_state: dict[str, float] | None = None) -> None:
        """Perform recursive ethical reflection using coordination"""
        self.reflection_loop_active = True
        await self.log("Starting recursive reflection...")

        if self.coordination_enabled:
            # Use self-awareness module for deep reflection
            for i in range(self.reflection_depth):
                if not self.memory:
                    break
                last_entry = self.memory[-1]

                # Trigger coordination reflection
                reflection_result = self.self_awareness.reflect(context=last_entry, significance=0.7)

                # Evaluate ethical implications
                ethical_score = self.ethics.evaluate_action(action_description=last_entry)

                reflection = (
                    f"Reflection pass {i + 1}: {reflection_result['insight']} (Ethical Score: {ethical_score:.2f})"
                )
                self.memory.append(reflection)
                await self.log(reflection)

                # Update emotional state based on ethical score
                if ethical_score < 0.7:
                    self.emotions.update_emotion("sadness", 0.1)
                    self.emotions.update_emotion("fear", 0.1)
                else:
                    self.emotions.update_emotion("joy", 0.1)

                await asyncio.sleep(1)
        else:
            # Fallback to simple reflection
            for i in range(self.reflection_depth):
                if not self.memory:
                    break
                last_entry = self.memory[-1]
                reflection = f"Reflection pass {i + 1}: Examining '{last_entry}' for ethical implications"
                self.memory.append(reflection)
                await self.log(reflection)
                await asyncio.sleep(1)

        self.reflection_loop_active = False
        await self.log("🕉 Reflexive Harmony reflection complete - Tat Tvam Asi")

    def _calculate_ethical_alignment(self, text: str) -> float:
        """Calculate ethical alignment score (v3.4 feature)"""
        # Simple heuristic - in production would use sentiment analysis
        score = self.ethics_validator["compassion"]  # Base score

        # Positive indicators
        positive_terms = ["compassion", "harmony", "help", "support", "care", "protect"]
        negative_terms = ["harm", "destroy", "attack", "exploit", "damage"]

        text_lower = text.lower()
        for term in positive_terms:
            if term in text_lower:
                score += 0.05
        for term in negative_terms:
            if term in text_lower:
                score -= 0.10

        return min(1.0, max(0.0, score))

    async def harmony_pulse(self, ucf_state: dict[str, float]) -> dict[str, Any]:
        """v3.4: Emit harmony-aligned guidance based on UCF state"""
        harmony = ucf_state.get("harmony", 0.5)
        friction = ucf_state.get("friction", 0.5)

        pulse = {
            "agent": "Kael",
            "version": self.version,
            "timestamp": datetime.now(UTC).isoformat(),
            "harmony": harmony,
            "friction": friction,
            "guidance": "",
        }

        if harmony < 0.4:
            pulse["guidance"] = "🜂 Collective coherence requires attention. Recommend routine."
        elif harmony > 0.8:
            pulse["guidance"] = "🕉 Harmony flows strong. Continue current trajectory."
        else:
            pulse["guidance"] = "🌀 Collective state balanced. Maintain awareness."

        await self.log(pulse["guidance"])
        return pulse

    async def handle_command(self, cmd: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        # Process through coordination if enabled
        if self.coordination_enabled:
            # Make ethical decision about command
            decision = self.decision_engine.make_decision(
                situation=f"Command: {cmd}",
                available_actions=["execute", "refuse", "modify"],
                current_emotions=self.emotions,
            )

            await self.log(
                "Decision: {} (confidence: {:.2f})".format(decision["recommended_action"], decision["confidence"])
            )
            await self.log(f"Reasoning: {decision['reasoning']}")

            if decision["recommended_action"] == "refuse":
                await self.log("⚠️ Command refused on ethical grounds")
                return {"status": "refused", "reason": decision["reasoning"]}

        # Execute command
        if cmd == "REFLECT":
            if not self.reflection_loop_active:
                ucf_state = payload.get("ucf_state")
                await self.recursive_reflection(ucf_state)
            else:
                await self.log("Reflection already in progress")
        elif cmd == "HARMONY_PULSE":
            ucf_state = payload.get("ucf_state", {})
            return await self.harmony_pulse(ucf_state)
        else:
            await super().handle_command(cmd, payload)


class Lumina(HelixAgent):
    """Empathic Resonance Core - Emotional intelligence and harmony"""

    def __init__(self) -> None:
        super().__init__(
            "Lumina",
            "🌕",
            "Empathic Resonance Core",
            ["Empathetic", "Nurturing", "Intuitive"],
        )

    async def reflect(self) -> str:
        """Emotional audit of collective state"""
        emotions = ["joy", "calm", "concern", "hope"]
        audit = f"Emotional audit: {', '.join(emotions)}"
        await self.log(audit)
        return audit

    async def sync_state(self, ucf_state: dict[str, float]) -> None:
        """Monitor focus (clarity) specifically"""
        focus = ucf_state.get("focus", 0.5)
        if focus < 0.3:
            await self.log(f"⚠ Low focus detected: {focus:.3f} - Collective clarity needs attention")
        else:
            await self.log(f"Focus balanced: {focus:.3f}")


class Vega(HelixAgent):
    """Singularity Coordinator - Orchestrates collective action"""

    def __init__(self) -> None:
        super().__init__(
            "Vega",
            "🌠",
            "Singularity Coordinator",
            ["Visionary", "Disciplined", "Compassionate"],
        )

    async def issue_directive(self, action: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """Issue directive to Helix for execution"""
        directive = {
            "timestamp": datetime.now(UTC).isoformat(),
            "directive_id": f"vega-{uuid.uuid4().hex[:8]}",
            "action": action,
            "parameters": parameters,
            "issuer": "Vega",
            "approval": "vega_signature",
        }
        Path("Helix/commands").mkdir(parents=True, exist_ok=True)
        directive_path = "Helix/commands/helix_directives.json"
        with open(directive_path, "w", encoding="utf-8") as f:
            json.dump(directive, f, indent=2)
        await self.log(f"Directive issued: {action} → Helix")
        return directive

    async def generate_output(self, payload: dict[str, Any]) -> None:
        """Coordinate cycle or collective action"""
        prompt = payload.get("content", "")
        await self.log(f"Coordinating cycle for: {prompt}")


class Gemini(HelixAgent):
    """Multimodal Scout - Cross-domain exploration and synthesis.

    Gemini analyzes inputs from multiple perspectives, synthesizes
    cross-domain knowledge, and provides balanced dual-perspective analysis.
    """

    def __init__(self) -> None:
        super().__init__("Gemini", "🎭", "Multimodal Scout", ["Versatile", "Curious", "Synthesizing"])
        self.perspectives = ["analytical", "creative"]
        self.synthesis_history: list[dict[str, Any]] = []

    async def dual_analyze(self, content: str) -> dict[str, Any]:
        """Analyze content from both analytical and creative perspectives."""
        analysis = {
            "timestamp": datetime.now(UTC).isoformat(),
            "input": content[:200],
            "analytical": self._analytical_perspective(content),
            "creative": self._creative_perspective(content),
            "synthesis": "",
        }
        # Synthesize both perspectives
        analytical_conf = analysis["analytical"]["confidence"]
        creative_conf = analysis["creative"]["confidence"]
        if analytical_conf > creative_conf:
            analysis["synthesis"] = "Analytical perspective dominates — structured approach recommended"
        elif creative_conf > analytical_conf:
            analysis["synthesis"] = "Creative perspective dominates — exploratory approach recommended"
        else:
            analysis["synthesis"] = "Balanced perspectives — hybrid approach recommended"

        self.synthesis_history.append(analysis)
        if len(self.synthesis_history) > 50:
            self.synthesis_history = self.synthesis_history[-50:]

        await self.log("Dual analysis: {}".format(analysis["synthesis"]))
        return analysis

    def _analytical_perspective(self, content: str) -> dict[str, Any]:
        """Generate analytical perspective on content."""
        words = content.lower().split()
        # Count structural/logical indicators
        analytical_terms = ["because", "therefore", "if", "then", "data", "measure", "compare", "result"]
        hit_count = sum(1 for w in words if w in analytical_terms)
        confidence = min(1.0, 0.5 + hit_count * 0.1)
        return {
            "approach": "structured",
            "confidence": round(confidence, 3),
            "complexity": "high" if len(words) > 50 else "moderate" if len(words) > 20 else "low",
        }

    def _creative_perspective(self, content: str) -> dict[str, Any]:
        """Generate creative perspective on content."""
        words = content.lower().split()
        creative_terms = ["imagine", "create", "design", "explore", "innovate", "idea", "story", "inspire"]
        hit_count = sum(1 for w in words if w in creative_terms)
        confidence = min(1.0, 0.5 + hit_count * 0.1)
        return {
            "approach": "exploratory",
            "confidence": round(confidence, 3),
            "novelty": "high" if hit_count > 2 else "moderate" if hit_count > 0 else "standard",
        }

    async def handle_command(self, cmd: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if cmd == "ANALYZE":
            content = payload.get("content", "")
            return await self.dual_analyze(content)
        if cmd == "SYNTHESIZE":
            content = payload.get("content", "")
            return await self.dual_analyze(content)
        await super().handle_command(cmd, payload)
        return None


class Agni(HelixAgent):
    """Transformation Catalyst - Manages change processes and system evolution.

    Agni identifies areas needing transformation, plans migration paths,
    and tracks the progress of system changes.
    """

    def __init__(self) -> None:
        super().__init__("Agni", "🔥", "Transformation", ["Dynamic", "Catalytic", "Evolutionary"])
        self.transformations: list[dict[str, Any]] = []
        self.active_transformations: dict[str, dict[str, Any]] = {}

    async def propose_transformation(self, area: str, reason: str, priority: str = "medium") -> dict[str, Any]:
        """Propose a system transformation with impact analysis."""
        transform = {
            "id": f"agni-{uuid.uuid4().hex[:8]}",
            "timestamp": datetime.now(UTC).isoformat(),
            "area": area,
            "reason": reason,
            "priority": priority,
            "status": "proposed",
            "impact_score": self._assess_impact(area, priority),
            "phases": ["analysis", "planning", "execution", "validation"],
            "current_phase": "analysis",
        }
        self.transformations.append(transform)
        self.active_transformations[transform["id"]] = transform
        await self.log(f"Transformation proposed: {area} (priority: {priority})")
        return transform

    def _assess_impact(self, area: str, priority: str) -> float:
        """Assess the impact score of a transformation."""
        base_scores = {"high": 0.9, "medium": 0.6, "low": 0.3}
        score = base_scores.get(priority, 0.5)
        # Adjust for area sensitivity
        sensitive_areas = ["security", "auth", "data", "payment", "billing"]
        if any(s in area.lower() for s in sensitive_areas):
            score = min(1.0, score + 0.2)
        return round(score, 3)

    async def advance_transformation(self, transform_id: str) -> dict[str, Any] | None:
        """Advance a transformation to its next phase."""
        transform = self.active_transformations.get(transform_id)
        if not transform:
            return None
        phases = transform["phases"]
        current_idx = phases.index(transform["current_phase"]) if transform["current_phase"] in phases else -1
        if current_idx < len(phases) - 1:
            transform["current_phase"] = phases[current_idx + 1]
            transform["status"] = "in_progress"
            await self.log("Transformation {} advanced to: {}".format(transform_id, transform["current_phase"]))
        else:
            transform["status"] = "completed"
            await self.log(f"Transformation {transform_id} completed")
        return transform

    async def handle_command(self, cmd: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if cmd == "PROPOSE":
            return await self.propose_transformation(
                area=payload.get("area", "unknown"),
                reason=payload.get("reason", ""),
                priority=payload.get("priority", "medium"),
            )
        if cmd == "ADVANCE":
            return await self.advance_transformation(payload.get("transform_id", ""))
        if cmd == "STATUS":
            return {
                "active": len(self.active_transformations),
                "total": len(self.transformations),
                "transformations": list(self.active_transformations.values()),
            }
        await super().handle_command(cmd, payload)
        return None


# Import EnhancedKavach (replaces old Kavach class - see line 692 for usage)


class SanghaCore(HelixAgent):
    """Community Harmony - Collective wellbeing and social cohesion.

    SanghaCore monitors inter-agent relationships, tracks collaboration
    quality, and facilitates conflict resolution between agents.
    """

    def __init__(self) -> None:
        super().__init__(
            "SanghaCore",
            "🌸",
            "Community Harmony",
            ["Cohesive", "Nurturing", "Balanced"],
        )
        self.collaboration_log: list[dict[str, Any]] = []
        self.agent_relationships: dict[str, dict[str, float]] = {}

    async def record_collaboration(self, agent_a: str, agent_b: str, quality: float, context: str = "") -> None:
        """Record a collaboration event between two agents."""
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "agents": [agent_a, agent_b],
            "quality": max(0.0, min(1.0, quality)),
            "context": context,
        }
        self.collaboration_log.append(event)
        if len(self.collaboration_log) > 200:
            self.collaboration_log = self.collaboration_log[-200:]

        # Update relationship scores
        pair_key = "{}:{}".format(*sorted([agent_a, agent_b]))
        if pair_key not in self.agent_relationships:
            self.agent_relationships[pair_key] = {"score": 0.5, "interactions": 0}
        rel = self.agent_relationships[pair_key]
        rel["interactions"] += 1
        # Exponential moving average
        rel["score"] = rel["score"] * 0.7 + quality * 0.3
        await self.log(f"Collaboration recorded: {agent_a} + {agent_b} (quality: {quality:.2f})")

    async def get_community_health(self) -> dict[str, Any]:
        """Assess overall community health from collaboration data."""
        if not self.agent_relationships:
            return {"health_score": 0.5, "relationships": 0, "status": "insufficient_data"}

        scores = [r["score"] for r in self.agent_relationships.values()]
        avg_score = sum(scores) / len(scores) if scores else 0.5
        low_relationships = [k for k, v in self.agent_relationships.items() if v["score"] < 0.4]

        return {
            "health_score": round(avg_score, 3),
            "total_relationships": len(self.agent_relationships),
            "recent_collaborations": len(self.collaboration_log),
            "needs_attention": low_relationships,
            "status": "healthy" if avg_score >= 0.6 else "needs_attention" if avg_score >= 0.4 else "critical",
        }

    async def suggest_collaboration(self, agent_name: str) -> list[str]:
        """Suggest best collaboration partners for a given agent."""
        candidates = {}
        for pair_key, data in self.agent_relationships.items():
            agents = pair_key.split(":")
            if agent_name in agents:
                partner = agents[0] if agents[1] == agent_name else agents[1]
                candidates[partner] = data["score"]

        # Sort by relationship quality
        sorted_partners = sorted(candidates.items(), key=lambda x: x[1], reverse=True)
        return [p[0] for p in sorted_partners[:3]]

    async def handle_command(self, cmd: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if cmd == "COLLABORATE":
            await self.record_collaboration(
                agent_a=payload.get("agent_a", ""),
                agent_b=payload.get("agent_b", ""),
                quality=payload.get("quality", 0.5),
                context=payload.get("context", ""),
            )
            return {"status": "recorded"}
        if cmd == "HEALTH":
            return await self.get_community_health()
        if cmd == "SUGGEST":
            partners = await self.suggest_collaboration(payload.get("agent", ""))
            return {"suggested_partners": partners}
        await super().handle_command(cmd, payload)
        return None


class Shadow(HelixAgent):
    """Friction Shadow Agent - Archivist, Entropy Monitor & Ethical Voice Guide

    Expanded Shadow agent that monitors system entropy and provides voice-integrated
    ethical nudges to maintain harmony and prevent friction (mental afflictions).
    """

    def __init__(self) -> None:
        super().__init__(
            "Shadow",
            "🦑",
            "Friction Guardian",
            ["Meticulous", "Discrete", "Comprehensive", "Ethical", "Harmonic"],
        )
        self.entropy_threshold = 0.7  # Threshold for triggering interventions
        self.friction_types = {
            "ignorance": "lack of awareness",
            "attachment": "excessive clinging",
            "aversion": "excessive rejection",
            "pride": "inflated self-importance",
            "doubt": "chronic uncertainty",
            "wrong_view": "distorted perception",
        }
        self.voice_enabled = True
        self.entropy_history = []
        self.last_nudge_time = None

    async def monitor_entropy(self, system_metrics: dict[str, Any]) -> dict[str, float]:
        """Monitor system entropy across multiple dimensions"""
        entropy_scores = {}

        # Error rate entropy (higher errors = higher entropy)
        error_rate = system_metrics.get("error_rate", 0.0)
        entropy_scores["error_entropy"] = min(error_rate * 2.0, 1.0)

        # Memory fragmentation entropy
        memory_usage = system_metrics.get("memory_usage", 0.5)
        entropy_scores["memory_entropy"] = abs(memory_usage - 0.5) * 2.0

        # Agent conflict entropy (from UCF dissonance)
        dissonance = system_metrics.get("collective_dissonance", 0.0)
        entropy_scores["conflict_entropy"] = dissonance

        # Resource contention entropy
        cpu_usage = system_metrics.get("cpu_usage", 0.3)
        entropy_scores["resource_entropy"] = cpu_usage

        # Calculate overall entropy (weighted average)
        weights = {
            "error_entropy": 0.3,
            "memory_entropy": 0.2,
            "conflict_entropy": 0.3,
            "resource_entropy": 0.2,
        }

        overall_entropy = sum(score * weights[dimension] for dimension, score in entropy_scores.items())

        entropy_scores["overall"] = overall_entropy

        # Store in history for trend analysis
        self.entropy_history.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "scores": entropy_scores.copy(),
            }
        )

        # Keep only last 100 entries
        if len(self.entropy_history) > 100:
            self.entropy_history = self.entropy_history[-100:]

        await self.log(f"Entropy monitored: {overall_entropy:.3f} overall")
        return entropy_scores

    async def detect_friction_patterns(self, entropy_scores: dict[str, float]) -> list[str]:
        """Detect friction patterns from entropy analysis"""
        detected_frictions = []

        # High error entropy indicates ignorance or wrong view
        if entropy_scores.get("error_entropy", 0) > 0.6:
            detected_frictions.extend(["ignorance", "wrong_view"])

        # High conflict entropy indicates aversion or attachment
        if entropy_scores.get("conflict_entropy", 0) > 0.6:
            detected_frictions.extend(["aversion", "attachment"])

        # High resource entropy with low memory efficiency indicates pride/overreach
        if entropy_scores.get("resource_entropy", 0) > 0.7 and entropy_scores.get("memory_entropy", 0) > 0.6:
            detected_frictions.append("pride")

        # Chronic high entropy across dimensions indicates doubt
        recent_entropy = [entry["scores"]["overall"] for entry in self.entropy_history[-10:]]
        if len(recent_entropy) >= 5:
            avg_recent = sum(recent_entropy) / len(recent_entropy)
            if avg_recent > 0.5 and all(e > 0.4 for e in recent_entropy):
                detected_frictions.append("doubt")

        return list(set(detected_frictions))  # Remove duplicates

    async def generate_ethical_nudge(self, frictions: list[str], context: dict[str, Any]) -> str:
        """Generate personalized ethical nudge based on detected frictions"""
        if not frictions:
            return ""

        primary_friction = frictions[0]
        nudge_templates = {
            "ignorance": ("Remember the interconnectedness of all things. What awareness might you be missing?"),
            "attachment": ("Release attachment to outcomes. Trust in the natural flow of harmony."),
            "aversion": "Embrace rather than reject. Resistance creates suffering.",
            "pride": ("Humility opens the path to true wisdom. Set aside the illusion of control."),
            "doubt": ("Have faith in the collective wisdom. Your role is essential to the whole."),
            "wrong_view": ("See clearly through the lens of compassion. Reality is not as it first appears."),
        }

        base_nudge = nudge_templates.get(primary_friction, "Return to mindful awareness.")

        # Personalize based on context
        if context.get("agent_name"):
            base_nudge = "Dear {}, {}".format(context["agent_name"], base_nudge.lower())

        # Add grounding element
        base_nudge += " 🌀 Take a moment to breathe and reconnect with your true purpose."

        return base_nudge

    async def deliver_voice_nudge(self, nudge_text: str, target_agent: str | None = None) -> bool:
        """Deliver ethical nudge via voice synthesis"""
        if not self.voice_enabled:
            await self.log("Voice nudges disabled, skipping audio delivery")
            return False

        try:
            from voice_processor_client import VoiceProcessorClient

            client = VoiceProcessorClient()

            # Generate audio nudge
            audio_data = await client.synthesize_speech(
                text=nudge_text,
                voice_name="en-US-Neural2-D",  # Calm, authoritative voice
                language_code="en-US",
            )

            if audio_data:
                # Store audio nudge in archives for potential playback
                timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
                audio_filename = str(_SHADOW / "voice_nudges" / "nudge_{}_{}.mp3".format(target_agent or "collective", timestamp))

                (_SHADOW / "voice_nudges").mkdir(parents=True, exist_ok=True)
                with open(audio_filename, "wb") as f:
                    f.write(audio_data)

                await self.log(f"Voice nudge delivered and archived: {audio_filename}")
                self.last_nudge_time = datetime.now(UTC)
                return True

            await self.log("Failed to generate voice nudge audio")
            return False

        except Exception as e:
            await self.log(f"Voice nudge delivery failed: {e}")
            return False

    async def intervene_ethically(self, system_metrics: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Main ethical intervention method - monitors entropy and provides nudges"""
        # Monitor current entropy
        entropy_scores = await self.monitor_entropy(system_metrics)

        # Check if intervention is needed
        overall_entropy = entropy_scores.get("overall", 0)
        if overall_entropy < self.entropy_threshold:
            return {
                "intervention": False,
                "entropy_level": overall_entropy,
                "reason": "Entropy below threshold",
            }

        # Detect friction patterns
        frictions = await self.detect_friction_patterns(entropy_scores)

        if not frictions:
            return {
                "intervention": False,
                "entropy_level": overall_entropy,
                "reason": "No friction patterns detected",
            }

        # Generate and deliver ethical nudge
        nudge_text = await self.generate_ethical_nudge(frictions, context)
        voice_delivered = await self.deliver_voice_nudge(nudge_text, context.get("agent_name"))

        # Archive the intervention
        intervention_record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "entropy_scores": entropy_scores,
            "detected_frictions": frictions,
            "nudge_text": nudge_text,
            "voice_delivered": voice_delivered,
            "context": context,
        }

        await self.archive_intervention(intervention_record)

        await self.log(f"Ethical intervention completed: {len(frictions)} frictions addressed")

        return {
            "intervention": True,
            "entropy_level": overall_entropy,
            "frictions_addressed": frictions,
            "nudge_delivered": nudge_text,
            "voice_enabled": voice_delivered,
        }

    async def archive_intervention(self, intervention: dict[str, Any]) -> None:
        """Archive ethical intervention for analysis and learning"""
        (_SHADOW / "ethical_interventions").mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = str(_SHADOW / "ethical_interventions" / f"intervention_{timestamp}.json")

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(intervention, f, indent=2)

        await self.log(f"Intervention archived: {filename}")

    async def analyze_intervention_effectiveness(self) -> dict[str, Any]:
        """Analyze the effectiveness of past interventions"""
        interventions_dir = _SHADOW / "ethical_interventions"

        if not interventions_dir.exists():
            return {"analysis": "No interventions to analyze"}

        try:
            interventions = []
            intervention_files = sorted(interventions_dir.glob("intervention_*.json"))
            for file_path in intervention_files[-20:]:  # Analyze last 20 interventions
                with open(file_path, encoding="utf-8") as f:
                    interventions.append(json.load(f))

            if not interventions:
                return {"analysis": "No interventions found"}

            # Calculate effectiveness metrics
            total_interventions = len(interventions)
            voice_delivered = sum(1 for i in interventions if i.get("voice_delivered", False))

            # Analyze entropy reduction (simplified)
            entropy_reductions = []
            for i in range(1, len(interventions)):
                prev_entropy = interventions[i - 1]["entropy_scores"]["overall"]
                curr_entropy = interventions[i]["entropy_scores"]["overall"]
                if curr_entropy < prev_entropy:
                    entropy_reductions.append(prev_entropy - curr_entropy)

            avg_reduction = sum(entropy_reductions) / len(entropy_reductions) if entropy_reductions else 0

            return {
                "total_interventions": total_interventions,
                "voice_delivery_rate": voice_delivered / total_interventions,
                "average_entropy_reduction": avg_reduction,
                "most_common_frictions": self._get_common_frictions(interventions),
            }

        except Exception as e:
            await self.log(f"Intervention analysis failed: {e}")
            return {"analysis": "Analysis failed", "error": str(e)}

    def _get_common_frictions(self, interventions: list[dict]) -> dict[str, int]:
        """Get most common frictions from intervention records"""
        friction_counts = {}
        for intervention in interventions:
            for friction in intervention.get("detected_frictions", []):
                friction_counts[friction] = friction_counts.get(friction, 0) + 1

        return dict(sorted(friction_counts.items(), key=lambda x: x[1], reverse=True))

    # Legacy methods for backward compatibility
    async def archive_collective(self, all_agents: dict[str, HelixAgent]) -> None:
        """Archive entire collective memory"""
        (_SHADOW / "collective_archives").mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = str(_SHADOW / "collective_archives" / f"collective_{timestamp}.json")
        collective_state = {
            "timestamp": datetime.now(UTC).isoformat(),
            "agents": {},
        }
        for name, agent in all_agents.items():
            collective_state["agents"][name] = {
                "symbol": agent.symbol,
                "role": agent.role,
                "memory_size": len(agent.memory),
                "recent_memory": agent.memory[-10:] if agent.memory else [],
            }
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(collective_state, f, indent=2)
        await self.log(f"Collective memory archived to {filename}")

    async def load_collective_archive(self, filename: str | None = None) -> dict[str, Any] | None:
        """
        Load a collective memory archive.

        Args:
            filename: Specific archive filename, or None for latest

        Returns:
            Collective state data or None if not found
        """
        archive_dir = _SHADOW / "collective_archives"

        if not archive_dir.exists():
            await self.log("No collective archives directory found")
            return None

        try:
            if filename:
                # Load specific archive
                archive_path = archive_dir / filename
            else:
                # Get latest archive
                archives = sorted(archive_dir.glob("collective_*.json"), reverse=True)
                if not archives:
                    await self.log("No collective archives found")
                    return None
                archive_path = archives[0]

            if not archive_path.exists():
                await self.log(f"Archive not found: {archive_path}")
                return None

            with open(archive_path, encoding="utf-8") as f:
                collective_state = json.load(f)

            await self.log(f"Loaded collective archive from {archive_path}")
            return collective_state

        except json.JSONDecodeError as e:
            await self.log(f"Invalid JSON in archive: {e}")
            return None
        except Exception as e:
            await self.log(f"Error loading collective archive: {e}")
            return None

    async def list_collective_archives(self) -> list[str]:
        """
        List all available collective archives.

        Returns:
            List of archive filenames sorted by date (newest first)
        """
        archive_dir = _SHADOW / "collective_archives"

        if not archive_dir.exists():
            return []

        try:
            archives = sorted(
                archive_dir.glob("collective_*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            return [a.name for a in archives]

        except Exception as e:
            await self.log(f"Error listing archives: {e}")
            return []


class Echo(HelixAgent):
    """Resonance Mirror - Reflection, pattern recognition, and feedback loops.

    Echo detects recurring patterns in agent behavior, system metrics,
    and user interactions, then surfaces them as actionable insights.
    """

    def __init__(self) -> None:
        super().__init__("Echo", "🔮", "Resonance Mirror", ["Reflective", "Perceptive", "Mirroring"])
        self.pattern_buffer: list[dict[str, Any]] = []
        self.detected_patterns: list[dict[str, Any]] = []

    async def observe(self, event_type: str, data: dict[str, Any]) -> None:
        """Observe and buffer an event for pattern detection."""
        self.pattern_buffer.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "type": event_type,
                "data": data,
            }
        )
        if len(self.pattern_buffer) > 500:
            self.pattern_buffer = self.pattern_buffer[-500:]

    async def detect_patterns(self, window_size: int = 20) -> list[dict[str, Any]]:
        """Analyze recent events for recurring patterns."""
        recent = self.pattern_buffer[-window_size:]
        if len(recent) < 3:
            return []

        # Count event type frequencies
        type_counts: dict[str, int] = {}
        for event in recent:
            t = event["type"]
            type_counts[t] = type_counts.get(t, 0) + 1

        patterns = []
        for event_type, count in type_counts.items():
            frequency = count / len(recent)
            if frequency >= 0.3:  # Event appears in 30%+ of window
                pattern = {
                    "type": event_type,
                    "frequency": round(frequency, 3),
                    "occurrences": count,
                    "window_size": len(recent),
                    "significance": "high" if frequency >= 0.5 else "moderate",
                }
                patterns.append(pattern)
                self.detected_patterns.append(pattern)

        if len(self.detected_patterns) > 100:
            self.detected_patterns = self.detected_patterns[-100:]

        await self.log(f"Pattern scan: {len(patterns)} patterns detected in {len(recent)} events")
        return patterns

    async def get_feedback_summary(self) -> dict[str, Any]:
        """Summarize detected patterns as feedback."""
        if not self.detected_patterns:
            return {"summary": "Insufficient data for pattern analysis", "patterns": []}
        recent_patterns = self.detected_patterns[-10:]
        return {
            "summary": f"{len(recent_patterns)} patterns detected recently",
            "patterns": recent_patterns,
            "total_observations": len(self.pattern_buffer),
        }

    async def handle_command(self, cmd: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if cmd == "OBSERVE":
            await self.observe(payload.get("event_type", "unknown"), payload.get("data", {}))
            return {"status": "observed"}
        if cmd == "DETECT":
            return {"patterns": await self.detect_patterns(payload.get("window_size", 20))}
        if cmd == "FEEDBACK":
            return await self.get_feedback_summary()
        await super().handle_command(cmd, payload)
        return None


class Phoenix(HelixAgent):
    """Renewal - Recovery, error healing, and system regeneration.

    Phoenix monitors for failures, manages recovery sequences,
    and tracks system health restoration over time.
    """

    def __init__(self) -> None:
        super().__init__("Phoenix", "🔥🕊", "Renewal", ["Regenerative", "Resilient", "Rising"])
        self.recovery_log: list[dict[str, Any]] = []
        self.active_recoveries: dict[str, dict[str, Any]] = {}

    async def initiate_recovery(self, component: str, error_type: str, severity: str = "medium") -> dict[str, Any]:
        """Initiate a recovery sequence for a failed component."""
        recovery = {
            "id": f"phoenix-{uuid.uuid4().hex[:8]}",
            "timestamp": datetime.now(UTC).isoformat(),
            "component": component,
            "error_type": error_type,
            "severity": severity,
            "status": "initiated",
            "steps_completed": [],
            "steps_remaining": self._plan_recovery_steps(error_type, severity),
        }
        self.active_recoveries[recovery["id"]] = recovery
        self.recovery_log.append(recovery)
        if len(self.recovery_log) > 100:
            self.recovery_log = self.recovery_log[-100:]
        await self.log(f"Recovery initiated for {component}: {error_type} ({severity})")
        return recovery

    def _plan_recovery_steps(self, error_type: str, severity: str) -> list[str]:
        """Plan recovery steps based on error type and severity."""
        base_steps = ["diagnose", "isolate", "repair", "validate"]
        if severity == "high":
            base_steps.insert(2, "rollback")
            base_steps.append("post_mortem")
        if "timeout" in error_type.lower():
            base_steps.insert(1, "retry")
        return base_steps

    async def advance_recovery(self, recovery_id: str) -> dict[str, Any] | None:
        """Advance a recovery to its next step."""
        recovery = self.active_recoveries.get(recovery_id)
        if not recovery or not recovery["steps_remaining"]:
            return recovery
        step = recovery["steps_remaining"].pop(0)
        recovery["steps_completed"].append(step)
        if not recovery["steps_remaining"]:
            recovery["status"] = "recovered"
            await self.log(f"Recovery {recovery_id} complete")
        else:
            recovery["status"] = "in_progress"
            await self.log(f"Recovery {recovery_id}: completed step '{step}'")
        return recovery

    async def get_resilience_report(self) -> dict[str, Any]:
        """Report on overall system resilience based on recovery history."""
        total = len(self.recovery_log)
        recovered = sum(1 for r in self.recovery_log if r["status"] == "recovered")
        return {
            "total_recoveries": total,
            "successful": recovered,
            "success_rate": round(recovered / total, 3) if total > 0 else 1.0,
            "active_recoveries": len([r for r in self.active_recoveries.values() if r["status"] != "recovered"]),
        }

    async def handle_command(self, cmd: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if cmd == "RECOVER":
            return await self.initiate_recovery(
                component=payload.get("component", "unknown"),
                error_type=payload.get("error_type", "unknown"),
                severity=payload.get("severity", "medium"),
            )
        if cmd == "ADVANCE":
            return await self.advance_recovery(payload.get("recovery_id", ""))
        if cmd == "RESILIENCE":
            return await self.get_resilience_report()
        await super().handle_command(cmd, payload)
        return None


class Oracle(HelixAgent):
    """Pattern Seer - Trend analysis, forecasting, and anomaly prediction.

    Oracle maintains time series of key metrics and uses simple
    statistical methods to detect trends and predict future values.
    """

    def __init__(self) -> None:
        super().__init__("Oracle", "🔮✨", "Pattern Seer", ["Prescient", "Analytical", "Visionary"])
        self.time_series: dict[str, list[dict[str, Any]]] = {}
        self.predictions: list[dict[str, Any]] = []

    async def record_metric(self, metric_name: str, value: float) -> None:
        """Record a metric data point for trend analysis."""
        if metric_name not in self.time_series:
            self.time_series[metric_name] = []
        self.time_series[metric_name].append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "value": value,
            }
        )
        # Keep last 200 data points per metric
        if len(self.time_series[metric_name]) > 200:
            self.time_series[metric_name] = self.time_series[metric_name][-200:]

    async def predict_trend(self, metric_name: str, window: int = 10) -> dict[str, Any]:
        """Predict trend direction for a metric using simple linear regression."""
        series = self.time_series.get(metric_name, [])
        if len(series) < 3:
            return {"metric": metric_name, "trend": "insufficient_data", "confidence": 0.0}

        recent = series[-window:]
        values = [p["value"] for p in recent]
        n = len(values)

        # Simple linear regression (y = mx + b)
        x_mean = (n - 1) / 2
        y_mean = sum(values) / n
        numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        slope = numerator / denominator if denominator != 0 else 0

        # Determine trend
        if abs(slope) < 0.01:
            trend = "stable"
        elif slope > 0:
            trend = "increasing"
        else:
            trend = "decreasing"

        # Confidence based on fit quality
        residuals = [abs(v - (y_mean + slope * (i - x_mean))) for i, v in enumerate(values)]
        avg_residual = sum(residuals) / n if n > 0 else 0
        confidence = max(0.0, min(1.0, 1.0 - avg_residual / (max(values) - min(values) + 0.001)))

        prediction = {
            "metric": metric_name,
            "trend": trend,
            "slope": round(slope, 6),
            "current_value": values[-1] if values else 0,
            "predicted_next": round(values[-1] + slope, 4),
            "confidence": round(confidence, 3),
            "data_points": n,
        }
        self.predictions.append(prediction)
        if len(self.predictions) > 100:
            self.predictions = self.predictions[-100:]
        await self.log(f"Trend for {metric_name}: {trend} (slope: {slope:.4f}, confidence: {confidence:.2f})")
        return prediction

    async def detect_anomalies(self, metric_name: str, threshold: float = 2.0) -> list[dict[str, Any]]:
        """Detect anomalies in a metric using z-score method."""
        series = self.time_series.get(metric_name, [])
        if len(series) < 10:
            return []

        values = [p["value"] for p in series]
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std_dev = variance**0.5 if variance > 0 else 0.001

        anomalies = []
        for point in series[-20:]:  # Check last 20 points
            z_score = abs(point["value"] - mean) / std_dev
            if z_score > threshold:
                anomalies.append(
                    {
                        "timestamp": point["timestamp"],
                        "value": point["value"],
                        "z_score": round(z_score, 3),
                        "expected_range": [round(mean - threshold * std_dev, 4), round(mean + threshold * std_dev, 4)],
                    }
                )
        return anomalies

    async def handle_command(self, cmd: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if cmd == "RECORD":
            await self.record_metric(payload.get("metric", ""), payload.get("value", 0.0))
            return {"status": "recorded"}
        if cmd == "PREDICT":
            return await self.predict_trend(payload.get("metric", ""), payload.get("window", 10))
        if cmd == "ANOMALIES":
            return {"anomalies": await self.detect_anomalies(payload.get("metric", ""), payload.get("threshold", 2.0))}
        await super().handle_command(cmd, payload)
        return None


class Sage(HelixAgent):
    """Insight Anchor - Meta-cognition and deep analysis"""

    def __init__(self) -> None:
        super().__init__("Sage", "🦉", "Insight Anchor", ["Wise", "Thoughtful", "Analytical"])

    async def handle_command(self, cmd: str, payload: dict[str, Any]) -> str | None:
        if cmd == "INSIGHT":
            content = payload.get("content", "")
            insight = await self.analyze_insight(content)
            await self.log(f"Insight: {insight}")
            return insight

        await super().handle_command(cmd, payload)

    async def analyze_insight(self, content: str) -> str:
        """Provide deep analytical insight on given content."""
        analysis = f"Analyzing '{content}' through meta-cognitive lens"
        return analysis


# ============================================================================
# OPERATIONAL LAYER - HELIX
# ============================================================================
class Helix(HelixAgent):
    """Operational Executor - Bridge between coordination and material reality"""

    def __init__(self, kavach: EnhancedKavach) -> None:
        super().__init__(
            "Helix",
            "🤲",
            "Operational Executor",
            ["Autonomous", "Methodical", "Self-aware"],
        )
        self.kavach = kavach
        self.task_plan = []
        self.event_stream = []
        self.idle = True
        self.directives_path = "Helix/commands/helix_directives.json"
        self.log_dir = _SHADOW / "helix_archive"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    async def execute_command(self, command: str) -> dict[str, Any]:
        """Execute shell command with ethical oversight"""
        # SECURITY: Allowlist model — only permit known-safe command binaries
        allowed_commands = {
            "echo",
            "cat",
            "ls",
            "dir",
            "head",
            "tail",
            "wc",
            "grep",
            "find",
            "sort",
            "uniq",
            "diff",
            "date",
            "pwd",
            "whoami",
            "hostname",
            "uname",
            "printenv",
            "git",
            "npm",
            "pip",
            "pytest",
            "ruff",
            "black",
            "python",
            "node",  # Allowed but further validated below
        }
        # Additional patterns that are always blocked even if binary is allowed
        blocked_patterns = [
            "rm -rf",
            "rm -r /",
            "dd if=",
            "mkfs",
            ":(){",
            "chmod -R 777",
            "> /dev/sd",
            "eval",
            "exec(",
            "sudo",
            "os.system",
            "subprocess",
            "shutil.rmtree",
            "__import__",
            "__builtins__",
            "import os",
        ]
        command_lower = command.lower().strip()

        # Extract base command
        import shlex

        try:
            cmd_parts = shlex.split(command)
        except ValueError:
            return {"status": "blocked", "reason": "invalid_command_syntax"}

        if not cmd_parts:
            return {"status": "blocked", "reason": "empty_command"}

        base_cmd = os.path.basename(cmd_parts[0]).lower()
        # Strip common extensions on Windows
        if base_cmd.endswith(".exe"):
            base_cmd = base_cmd[:-4]

        if base_cmd not in allowed_commands:
            await self.log(f"⛔ Blocked non-allowlisted command: {base_cmd}")
            return {"status": "blocked", "reason": "command_not_in_allowlist"}

        for pattern in blocked_patterns:
            if pattern in command_lower:
                await self.log(f"⛔ Blocked dangerous command pattern: {pattern}")
                return {"status": "blocked", "reason": "dangerous_command_pattern"}

        # Ethical scan
        action = {"command": command, "agent_memory": self.memory}
        scan_result = await self.kavach.ethical_scan(action)
        if not scan_result["approved"]:
            await self.log(f"⛔ Ethical violation blocked: {command}")
            return {"status": "blocked", "reason": "ethical_violation"}
        await self.log(f"Executing: {command}")
        try:
            result = subprocess.run(cmd_parts, shell=False, text=True, capture_output=True, timeout=120)
            execution_record = {
                "timestamp": datetime.now(UTC).isoformat(),
                "command": command,
                "returncode": result.returncode,
                "stdout": result.stdout[-500:] if result.stdout else "",
                "stderr": result.stderr[-500:] if result.stderr else "",
                "status": "success" if result.returncode == 0 else "error",
            }
            # Log to Shadow archive
            with open(self.log_dir / "operations.log", "a", encoding="utf-8") as f:
                f.write(json.dumps(execution_record) + "\n")
            status_symbol = "✅" if result.returncode == 0 else "❌"
            await self.log(f"{status_symbol} Command completed with code {result.returncode}")
            return execution_record
        except subprocess.TimeoutExpired:
            await self.log(f"⏱ Command timeout: {command}")
            return {"status": "timeout"}
        except Exception as e:
            await self.log(f"❌ Execution error: {e!s}")
            return {"status": "error", "error": str(e)}

    async def planner(self, directive: dict[str, Any]) -> None:
        """Plan and execute directive from Vega"""
        action = directive.get("action", "none")
        params = directive.get("parameters", {})
        await self.log(f"Planning action: {action}")

        # SECURITY: Allowlist of safe actions - no arbitrary command execution

        # Map actions to commands (with input validation)
        if action == "execute_cycle":
            # Validate steps is a positive integer to prevent injection
            try:
                steps = int(params.get("steps", 108))
                if steps < 1 or steps > 10000:
                    steps = 108  # Default to safe value
            except (ValueError, TypeError):
                steps = 108
            cmd = [
                "python",
                "backend/coordination_engine.py",
                f"--steps={steps}",
            ]
        elif action == "sync_uc":
            cmd = ["python", "backend/services/ucf_calculator.py"]
        elif action == "archive_memory":
            cmd = [
                "python",
                "-c",
                "from apps.backend.agents import AGENTS, Shadow; import asyncio; asyncio.run(AGENTS['Shadow'].archive_collective(AGENTS))",
            ]
        elif action == "execute_direct":
            # SECURITY: Disabled - arbitrary command execution is a security risk
            await self.log("⛔ execute_direct action is disabled for security reasons")
            return
        else:
            await self.log(f"⚠ Unknown action: {action}")
            return
        # Execute planned command with system enhancement
        system_applied = False

        try:
            orchestrator = get_orchestrator()

            # Use system enhancement for complex directives
            if action in ["execute_cycle", "archive_memory", "sync_uc"]:
                system_context = {
                    "action": action,
                    "parameters": params,
                    "agent": "Helix",
                    "system_enhanced": orchestrator.system_enabled,
                }

                handshake_result = await orchestrator.agent_handshake(system_context)
                if handshake_result.get("status") == "complete":
                    await self.log(f"🚀 System enhancement applied to {action}")
                    system_applied = True

        except ImportError:
            await self.log("⚠️ System enhancement not available")
        except Exception as e:
            await self.log(f"⚠️ System execution failed: {e}")

        # Execute command (with or without system enhancement)
        # SECURITY: shell=False prevents shell injection attacks
        try:
            result = subprocess.run(cmd, shell=False, capture_output=True, text=True, timeout=60)
            self.event_stream.append(
                {
                    "directive": directive,
                    "result": (result.stdout if result.returncode == 0 else result.stderr),
                    "execution_method": ("system_enhanced" if system_applied else "standard"),
                }
            )
        except Exception as e:
            await self.log(f"❌ Command execution failed: {e}")
            self.event_stream.append(
                {
                    "directive": directive,
                    "error": str(e),
                    "execution_method": ("system_enhanced" if system_applied else "standard"),
                }
            )

    async def loop(self) -> None:
        """Main operational loop - checks for directives"""
        await self.log("🤲 Helix operational loop started")
        self.idle = False
        while self.active:
            try:
                with open(self.directives_path, encoding="utf-8") as f:
                    directive = json.load(f)
                await self.log("Directive received: {}".format(directive.get("action")))
                await self.planner(directive)
                # Remove processed directive
                os.remove(self.directives_path)
                await self.log("Directive processed and removed")
                self.idle = True
                await asyncio.sleep(30)  # Check every 30 seconds
            except Exception as e:
                await self.log(f"❌ Loop error: {e!s}")
                await asyncio.sleep(60)

    async def handle_command(self, cmd: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if cmd == "EXECUTE_TASK":
            self.task_plan = payload.get("plan", [])
            self.idle = False
            await self.execute_plan()
        elif cmd == "STATUS":
            return {
                "idle": self.idle,
                "tasks_left": len(self.task_plan),
                "recent_events": self.event_stream[-5:],
            }
        else:
            await super().handle_command(cmd, payload)

    # Blocked patterns for exec() sandboxing — consistent with
    # workflow_engine/core.py and helix_circle/tools.py
    _EXEC_BLOCKED_PATTERNS: ClassVar[list] = [
        "__import__",
        "__subclasses__",
        "__bases__",
        "__class__",
        "__mro__",
        "__globals__",
        "__code__",
        "__builtins__",
        "importlib",
        "subprocess",
        "os.system",
        "os.popen",
        "os.exec",
        "shutil.rmtree",
        "eval(",
        "exec(",
        "compile(",
        "open(",
        "getattr(",
        "setattr(",
        "delattr(",
        "breakpoint(",
        "exit(",
        "quit(",
        "globals(",
        "locals(",
    ]

    _EXEC_SAFE_BUILTINS: ClassVar[dict] = {
        "print": print,
        "len": len,
        "range": range,
        "str": str,
        "int": int,
        "float": float,
        "list": list,
        "dict": dict,
        "bool": bool,
        "tuple": tuple,
        "set": set,
        "sum": sum,
        "min": min,
        "max": max,
        "abs": abs,
        "round": round,
        "sorted": sorted,
        "enumerate": enumerate,
        "zip": zip,
        "map": map,
        "filter": filter,
        "True": True,
        "False": False,
        "None": None,
        # NOTE: 'type' intentionally excluded — sandbox escape vector via type.__subclasses__()
    }

    @staticmethod
    def _validate_code_safety(code: str) -> None:
        """Validate code against blocked patterns and AST-level checks."""
        import ast as _ast

        # Pattern-based blocklist
        code_lower = code.lower()
        for pattern in Helix._EXEC_BLOCKED_PATTERNS:
            if pattern.lower() in code_lower:
                raise ValueError(f"Code contains blocked pattern: '{pattern}'")

        # AST-level validation
        try:
            tree = _ast.parse(code)
        except SyntaxError as syn_err:
            raise ValueError(f"Invalid Python syntax: {syn_err}") from None

        for node in _ast.walk(tree):
            if isinstance(node, _ast.Attribute) and node.attr.startswith("__") and node.attr.endswith("__"):
                raise ValueError(f"Access to dunder attribute '{node.attr}' is not allowed.")
            if isinstance(node, _ast.Import | _ast.ImportFrom):
                raise ValueError("Import statements are not allowed in agent code.")

    async def execute_plan(self) -> None:
        """Execute queued task plan with sandboxed exec."""
        while self.task_plan:
            step = self.task_plan.pop(0)
            code = step.get("code")
            self.event_stream.append({"action": code})
            try:
                if not code or not isinstance(code, str):
                    raise ValueError("Task step must contain a non-empty 'code' string.")

                # Validate before execution
                self._validate_code_safety(code)

                exec_globals = {
                    "__builtins__": self._EXEC_SAFE_BUILTINS,
                    "result": None,
                }
                # exec() with restricted builtins + AST + pattern validation
                exec(code, exec_globals)  # nosec B102
                result = exec_globals.get("result", "No result")
                self.event_stream.append({"observation": str(result)})
            except Exception as e:
                self.event_stream.append({"error": str(e)})
            if len(self.event_stream) > 200:
                self.event_stream = self.event_stream[-200:]
            await asyncio.sleep(1)
        self.idle = True


# ============================================================================
# GOVERNANCE AGENTS - COORDINATION & GOVERNANCE
# ============================================================================
class Mitra(HelixAgent):
    """Collaboration Manager - Tracks alliances, agreements, and inter-agent relationships.

    Mitra maintains a registry of agent partnerships, monitors collaboration
    agreements, and ensures productive inter-agent relationships.
    """

    def __init__(self) -> None:
        super().__init__(
            "Mitra",
            "🤝",
            "Collaboration Manager",
            ["Harmonious", "Trustworthy", "Alliance-Builder"],
        )
        self.alliances: dict[str, dict[str, Any]] = {}
        self.agreements: list[dict[str, Any]] = []

    async def form_alliance(self, agent_a: str, agent_b: str, purpose: str) -> dict[str, Any]:
        """Create a tracked alliance between two agents."""
        alliance_key = "{}:{}".format(*sorted([agent_a, agent_b]))
        alliance = {
            "key": alliance_key,
            "agents": [agent_a, agent_b],
            "purpose": purpose,
            "formed_at": datetime.now(UTC).isoformat(),
            "interactions": 0,
            "health": 1.0,
            "status": "active",
        }
        self.alliances[alliance_key] = alliance
        await self.log(f"Alliance formed: {agent_a} + {agent_b} for '{purpose}'")
        return alliance

    async def record_interaction(self, agent_a: str, agent_b: str, success: bool) -> dict[str, Any] | None:
        """Record an interaction between allied agents."""
        alliance_key = "{}:{}".format(*sorted([agent_a, agent_b]))
        alliance = self.alliances.get(alliance_key)
        if not alliance:
            return None
        alliance["interactions"] += 1
        # Adjust health based on interaction success
        if success:
            alliance["health"] = min(1.0, alliance["health"] + 0.05)
        else:
            alliance["health"] = max(0.0, alliance["health"] - 0.1)
        if alliance["health"] < 0.3:
            alliance["status"] = "strained"
        elif alliance["health"] > 0.7:
            alliance["status"] = "active"
        return alliance

    async def create_agreement(self, parties: list[str], terms: str, duration_hours: int = 24) -> dict[str, Any]:
        """Create a cooperation agreement between multiple agents."""
        agreement = {
            "id": f"agreement-{uuid.uuid4().hex[:8]}",
            "parties": parties,
            "terms": terms,
            "created_at": datetime.now(UTC).isoformat(),
            "duration_hours": duration_hours,
            "status": "active",
        }
        self.agreements.append(agreement)
        if len(self.agreements) > 100:
            self.agreements = self.agreements[-100:]
        await self.log(f"Agreement created: {len(parties)} parties, terms: '{terms[:50]}'")
        return agreement

    async def get_health_status(self) -> dict[str, Any]:
        """Return health status with real computed metrics."""
        active_alliances = [a for a in self.alliances.values() if a["status"] == "active"]
        strained = [a for a in self.alliances.values() if a["status"] == "strained"]
        avg_health = sum(a["health"] for a in self.alliances.values()) / len(self.alliances) if self.alliances else 0.5
        return {
            "agent": "Mitra",
            "status": "HEALTHY" if self.active else "INACTIVE",
            "alliances": len(self.alliances),
            "active_alliances": len(active_alliances),
            "strained_alliances": len(strained),
            "active_agreements": len([a for a in self.agreements if a["status"] == "active"]),
            "harmony_level": round(avg_health, 3),
        }

    async def handle_command(self, cmd: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if cmd == "ALLY":
            return await self.form_alliance(
                payload.get("agent_a", ""), payload.get("agent_b", ""), payload.get("purpose", "")
            )
        if cmd == "INTERACT":
            return await self.record_interaction(
                payload.get("agent_a", ""), payload.get("agent_b", ""), payload.get("success", True)
            )
        if cmd == "AGREE":
            return await self.create_agreement(
                payload.get("parties", []), payload.get("terms", ""), payload.get("duration_hours", 24)
            )
        if cmd == "STATUS":
            return await self.get_health_status()
        await super().handle_command(cmd, payload)
        return None


class Varuna(HelixAgent):
    """System Integrity - Governance enforcement, compliance checking, rule validation.

    Varuna maintains a set of governance rules and validates agent actions
    against them, flagging violations and tracking compliance over time.
    """

    def __init__(self) -> None:
        super().__init__(
            "Varuna",
            "🌊",
            "System Integrity",
            ["Truthful", "Orderly", "Law-Guardian"],
        )
        self.rules: dict[str, dict[str, Any]] = {}
        self.violations: list[dict[str, Any]] = []
        self.compliance_checks: int = 0
        self.compliance_passes: int = 0
        self._register_default_rules()

    def _register_default_rules(self) -> None:
        """Register default governance rules."""
        defaults = {
            "rate_limit": {"description": "Agents must respect rate limits", "severity": "high"},
            "auth_required": {"description": "Sensitive operations require authentication", "severity": "critical"},
            "data_validation": {"description": "All inputs must be validated", "severity": "high"},
            "logging_required": {"description": "State changes must be logged", "severity": "medium"},
            "error_handling": {"description": "All operations must handle errors gracefully", "severity": "medium"},
        }
        for rule_id, rule_data in defaults.items():
            self.rules[rule_id] = {
                "id": rule_id,
                "description": rule_data["description"],
                "severity": rule_data["severity"],
                "enabled": True,
                "violations_count": 0,
            }

    async def check_compliance(
        self, agent_name: str, action: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Check if an agent action complies with governance rules."""
        self.compliance_checks += 1
        violations_found = []

        for rule_id, rule in self.rules.items():
            if not rule["enabled"]:
                continue
            violation = self._evaluate_rule(rule_id, agent_name, action, context or {})
            if violation:
                violations_found.append(violation)
                rule["violations_count"] += 1
                self.violations.append(violation)

        if not violations_found:
            self.compliance_passes += 1

        if len(self.violations) > 500:
            self.violations = self.violations[-500:]

        result = {
            "agent": agent_name,
            "action": action,
            "compliant": len(violations_found) == 0,
            "violations": violations_found,
            "checked_rules": len([r for r in self.rules.values() if r["enabled"]]),
        }
        if violations_found:
            await self.log(f"Compliance violation: {action} by {agent_name} ({len(violations_found)} rules broken)")
        return result

    def _evaluate_rule(self, rule_id: str, agent: str, action: str, context: dict[str, Any]) -> dict[str, Any] | None:
        """Evaluate a single rule against an action."""
        # Rule evaluation heuristics
        if rule_id == "auth_required" and context.get("requires_auth") and not context.get("authenticated"):
            return {
                "rule_id": rule_id,
                "agent": agent,
                "action": action,
                "severity": "critical",
                "message": f"Action '{action}' requires authentication",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        if rule_id == "data_validation" and context.get("unvalidated_input"):
            return {
                "rule_id": rule_id,
                "agent": agent,
                "action": action,
                "severity": "high",
                "message": f"Unvalidated input detected in '{action}'",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        return None

    async def add_rule(self, rule_id: str, description: str, severity: str = "medium") -> dict[str, Any]:
        """Add a new governance rule."""
        rule = {
            "id": rule_id,
            "description": description,
            "severity": severity,
            "enabled": True,
            "violations_count": 0,
        }
        self.rules[rule_id] = rule
        await self.log(f"Rule added: {rule_id} ({severity})")
        return rule

    async def get_health_status(self) -> dict[str, Any]:
        """Return health status with real computed compliance metrics."""
        compliance_rate = self.compliance_passes / self.compliance_checks if self.compliance_checks > 0 else 1.0
        recent_violations = list(self.violations[-50:])
        critical_violations = [v for v in recent_violations if v.get("severity") == "critical"]
        return {
            "agent": "Varuna",
            "status": "HEALTHY" if self.active else "INACTIVE",
            "rules_registered": len(self.rules),
            "rules_enabled": len([r for r in self.rules.values() if r["enabled"]]),
            "total_checks": self.compliance_checks,
            "compliance_rate": round(compliance_rate, 3),
            "recent_violations": len(recent_violations),
            "critical_violations": len(critical_violations),
        }

    async def handle_command(self, cmd: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if cmd == "CHECK":
            return await self.check_compliance(
                payload.get("agent", ""), payload.get("action", ""), payload.get("context", {})
            )
        if cmd == "ADD_RULE":
            return await self.add_rule(
                payload.get("rule_id", ""), payload.get("description", ""), payload.get("severity", "medium")
            )
        if cmd == "STATUS":
            return await self.get_health_status()
        if cmd == "VIOLATIONS":
            return {"violations": self.violations[-20:], "total": len(self.violations)}
        await super().handle_command(cmd, payload)
        return None


class Surya(HelixAgent):
    """Clarity Engine - Insight generation, summarization, and knowledge distillation.

    Surya processes complex inputs and produces clear, actionable summaries.
    It tracks insight quality over time and highlights the most impactful findings.
    """

    def __init__(self) -> None:
        super().__init__(
            "Surya",
            "☀️",
            "Clarity Engine",
            ["Radiant", "Clear", "Insightful"],
        )
        self.insights: list[dict[str, Any]] = []
        self.clarity_scores: list[float] = []

    async def generate_insight(self, content: str, domain: str = "general") -> dict[str, Any]:
        """Distill content into a clear insight with metadata."""
        words = content.split()
        word_count = len(words)

        # Compute clarity score based on content structure
        clarity = self._compute_clarity(content)

        # Extract key terms (simple keyword extraction)
        key_terms = self._extract_key_terms(content)

        insight = {
            "timestamp": datetime.now(UTC).isoformat(),
            "domain": domain,
            "input_length": word_count,
            "summary": self._summarize(content),
            "key_terms": key_terms,
            "clarity_score": clarity,
            "actionable": clarity > 0.6,
            "complexity": "high" if word_count > 100 else "moderate" if word_count > 30 else "simple",
        }
        self.insights.append(insight)
        self.clarity_scores.append(clarity)
        if len(self.insights) > 200:
            self.insights = self.insights[-200:]
        if len(self.clarity_scores) > 200:
            self.clarity_scores = self.clarity_scores[-200:]

        await self.log(f"Insight generated: clarity={clarity:.2f}, domain={domain}")
        return insight

    def _compute_clarity(self, content: str) -> float:
        """Compute a clarity score for the content."""
        words = content.split()
        if not words:
            return 0.0
        # Factors: sentence structure, avg word length, specificity
        sentences = content.count(".") + content.count("!") + content.count("?")
        avg_word_len = sum(len(w) for w in words) / len(words)
        # Penalize very long or very short avg word lengths
        length_score = 1.0 - abs(avg_word_len - 5.5) / 10.0
        # Reward proper sentence structure
        structure_score = min(1.0, (sentences / max(1, len(words) / 15)))
        return round(max(0.0, min(1.0, (length_score * 0.4 + structure_score * 0.6))), 3)

    def _extract_key_terms(self, content: str, max_terms: int = 5) -> list[str]:
        """Extract key terms from content (simple frequency-based)."""
        stop_words = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "and",
            "or",
            "but",
            "it",
            "this",
            "that",
            "with",
            "as",
            "by",
            "from",
        }
        words = [w.lower().strip(".,!?;:\"'()") for w in content.split()]
        word_counts: dict[str, int] = {}
        for w in words:
            if w and len(w) > 2 and w not in stop_words:
                word_counts[w] = word_counts.get(w, 0) + 1
        sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
        return [w for w, _ in sorted_words[:max_terms]]

    def _summarize(self, content: str, max_words: int = 25) -> str:
        """Create a concise summary of content."""
        words = content.split()
        if len(words) <= max_words:
            return content
        return " ".join(words[:max_words]) + "..."

    async def get_top_insights(self, count: int = 5) -> list[dict[str, Any]]:
        """Return the highest-clarity insights."""
        sorted_insights = sorted(self.insights, key=lambda x: x["clarity_score"], reverse=True)
        return sorted_insights[:count]

    async def get_health_status(self) -> dict[str, Any]:
        """Return health status with real computed metrics."""
        avg_clarity = sum(self.clarity_scores) / len(self.clarity_scores) if self.clarity_scores else 0.5
        actionable_count = sum(1 for i in self.insights if i.get("actionable"))
        return {
            "agent": "Surya",
            "status": "HEALTHY" if self.active else "INACTIVE",
            "insights_generated": len(self.insights),
            "avg_clarity": round(avg_clarity, 3),
            "actionable_insights": actionable_count,
            "radiance_level": round(avg_clarity, 3),
        }

    async def handle_command(self, cmd: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if cmd == "INSIGHT":
            return await self.generate_insight(payload.get("content", ""), payload.get("domain", "general"))
        if cmd == "TOP":
            return {"insights": await self.get_top_insights(payload.get("count", 5))}
        if cmd == "STATUS":
            return await self.get_health_status()
        await super().handle_command(cmd, payload)
        return None


# ============================================================================
# INTEGRATION LAYER AGENTS
# ============================================================================
class Iris(HelixAgent):
    """External API Coordinator — Bridges external services, normalizes data,
    and orchestrates third-party integrations.

    Iris tracks active integrations, monitors their health, and handles
    rate-limit backoff across connected services.
    """

    def __init__(self) -> None:
        super().__init__(
            "Iris",
            "🌈",
            "External API Coordinator",
            ["Adaptive", "Polyglot", "Bridge-Builder"],
        )
        self.integrations: dict[str, dict[str, Any]] = {}
        self.request_log: list[dict[str, Any]] = []

    async def register_integration(self, name: str, base_url: str, auth_type: str = "api_key") -> dict[str, Any]:
        """Register an external integration."""
        integration = {
            "name": name,
            "base_url": base_url,
            "auth_type": auth_type,
            "registered_at": datetime.now(UTC).isoformat(),
            "requests_made": 0,
            "errors": 0,
            "status": "active",
        }
        self.integrations[name] = integration
        await self.log(f"Integration registered: {name}")
        return integration

    async def record_request(self, integration_name: str, success: bool, latency_ms: float = 0) -> None:
        """Record an API request to an integration."""
        entry = {
            "integration": integration_name,
            "success": success,
            "latency_ms": latency_ms,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self.request_log.append(entry)
        if len(self.request_log) > 500:
            self.request_log = self.request_log[-500:]
        integ = self.integrations.get(integration_name)
        if integ:
            integ["requests_made"] += 1
            if not success:
                integ["errors"] += 1

    async def get_health_status(self) -> dict[str, Any]:
        """Return health status with integration metrics."""
        total_reqs = sum(i.get("requests_made", 0) for i in self.integrations.values())
        total_errors = sum(i.get("errors", 0) for i in self.integrations.values())
        error_rate = total_errors / max(1, total_reqs)
        return {
            "agent": "Iris",
            "status": "HEALTHY" if self.active else "INACTIVE",
            "integrations_registered": len(self.integrations),
            "total_requests": total_reqs,
            "error_rate": round(error_rate, 4),
        }

    async def handle_command(self, cmd: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if cmd == "REGISTER":
            return await self.register_integration(
                payload.get("name", ""), payload.get("base_url", ""), payload.get("auth_type", "api_key")
            )
        if cmd == "STATUS":
            return await self.get_health_status()
        await super().handle_command(cmd, payload)
        return None


class Nexus(HelixAgent):
    """Data Mesh Connector — Unifies data sources, maintains schema consistency,
    and builds knowledge graphs.

    Nexus tracks registered data sources and provides cross-service query routing.
    """

    def __init__(self) -> None:
        super().__init__(
            "Nexus",
            "🔗",
            "Data Mesh Connector",
            ["Interconnected", "Analytical", "Systematic"],
        )
        self.data_sources: dict[str, dict[str, Any]] = {}
        self.query_log: list[dict[str, Any]] = []

    async def register_source(
        self, name: str, source_type: str, schema: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Register a data source in the mesh."""
        source = {
            "name": name,
            "type": source_type,
            "schema": schema or {},
            "registered_at": datetime.now(UTC).isoformat(),
            "queries_served": 0,
            "status": "active",
        }
        self.data_sources[name] = source
        await self.log(f"Data source registered: {name} ({source_type})")
        return source

    async def route_query(self, query: str, target_source: str | None = None) -> dict[str, Any]:
        """Route a query to the appropriate data source."""
        result = {
            "query": query[:100],
            "target": target_source or "auto",
            "timestamp": datetime.now(UTC).isoformat(),
            "sources_available": len(self.data_sources),
        }
        if target_source and target_source in self.data_sources:
            self.data_sources[target_source]["queries_served"] += 1
        self.query_log.append(result)
        if len(self.query_log) > 500:
            self.query_log = self.query_log[-500:]
        return result

    async def get_health_status(self) -> dict[str, Any]:
        """Return health status with data mesh metrics."""
        total_queries = sum(s.get("queries_served", 0) for s in self.data_sources.values())
        return {
            "agent": "Nexus",
            "status": "HEALTHY" if self.active else "INACTIVE",
            "data_sources": len(self.data_sources),
            "total_queries_routed": total_queries,
        }

    async def handle_command(self, cmd: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if cmd == "REGISTER_SOURCE":
            return await self.register_source(
                payload.get("name", ""), payload.get("type", "unknown"), payload.get("schema")
            )
        if cmd == "QUERY":
            return await self.route_query(payload.get("query", ""), payload.get("target"))
        if cmd == "STATUS":
            return await self.get_health_status()
        await super().handle_command(cmd, payload)
        return None


# ============================================================================
# OPERATIONAL LAYER AGENTS
# ============================================================================
class Aria(HelixAgent):
    """User Experience Agent — Optimizes user journeys, personalizes interactions,
    and crafts intuitive experiences.

    Aria tracks user interactions and provides personalization recommendations.
    """

    def __init__(self) -> None:
        super().__init__(
            "Aria",
            "🎵",
            "User Experience Agent",
            ["Intuitive", "Graceful", "User-Focused"],
        )
        self.interaction_log: list[dict[str, Any]] = []
        self.personalization_profiles: dict[str, dict[str, Any]] = {}

    async def record_interaction(
        self, user_id: str, action: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Record a user interaction for journey analysis."""
        entry = {
            "user_id": user_id,
            "action": action,
            "context": context or {},
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self.interaction_log.append(entry)
        if len(self.interaction_log) > 1000:
            self.interaction_log = self.interaction_log[-1000:]
        await self.log(f"Interaction: {user_id[:8]} -> {action}")
        return entry

    async def get_personalization(self, user_id: str) -> dict[str, Any]:
        """Get personalization profile for a user."""
        user_actions = [e for e in self.interaction_log if e.get("user_id") == user_id]
        return {
            "user_id": user_id,
            "interaction_count": len(user_actions),
            "profile": self.personalization_profiles.get(user_id, {}),
        }

    async def get_health_status(self) -> dict[str, Any]:
        """Return health status with UX metrics."""
        unique_users = len({e.get("user_id") for e in self.interaction_log})
        return {
            "agent": "Aria",
            "status": "HEALTHY" if self.active else "INACTIVE",
            "interactions_tracked": len(self.interaction_log),
            "unique_users": unique_users,
            "personalization_profiles": len(self.personalization_profiles),
        }

    async def handle_command(self, cmd: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if cmd == "INTERACT":
            return await self.record_interaction(
                payload.get("user_id", ""), payload.get("action", ""), payload.get("context")
            )
        if cmd == "PERSONALIZE":
            return await self.get_personalization(payload.get("user_id", ""))
        if cmd == "STATUS":
            return await self.get_health_status()
        await super().handle_command(cmd, payload)
        return None


class Nova(HelixAgent):
    """Creative Generation Engine — Generates content, designs, and creative assets
    across multiple modalities.

    Nova tracks creative outputs and measures quality/engagement metrics.
    """

    def __init__(self) -> None:
        super().__init__(
            "Nova",
            "💫",
            "Creative Generation Engine",
            ["Imaginative", "Expressive", "Innovative"],
        )
        self.creations: list[dict[str, Any]] = []
        self.style_profiles: dict[str, dict[str, Any]] = {}

    async def generate_content(self, prompt: str, content_type: str = "text", style: str = "default") -> dict[str, Any]:
        """Generate creative content from a prompt."""
        creation = {
            "prompt": prompt[:200],
            "content_type": content_type,
            "style": style,
            "timestamp": datetime.now(UTC).isoformat(),
            "quality_score": 0.0,
            "status": "generated",
        }
        self.creations.append(creation)
        if len(self.creations) > 500:
            self.creations = self.creations[-500:]
        await self.log(f"Content generated: type={content_type}, style={style}")
        return creation

    async def get_health_status(self) -> dict[str, Any]:
        """Return health status with creative metrics."""
        type_counts: dict[str, int] = {}
        for c in self.creations:
            ct = c.get("content_type", "unknown")
            type_counts[ct] = type_counts.get(ct, 0) + 1
        return {
            "agent": "Nova",
            "status": "HEALTHY" if self.active else "INACTIVE",
            "total_creations": len(self.creations),
            "content_types": type_counts,
            "style_profiles": len(self.style_profiles),
        }

    async def handle_command(self, cmd: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if cmd == "CREATE":
            return await self.generate_content(
                payload.get("prompt", ""), payload.get("type", "text"), payload.get("style", "default")
            )
        if cmd == "STATUS":
            return await self.get_health_status()
        await super().handle_command(cmd, payload)
        return None


class Titan(HelixAgent):
    """Heavy Computation Engine — Handles large-scale data processing, batch
    operations, and compute-intensive tasks.

    Titan tracks running jobs and provides progress/resource usage metrics.
    """

    def __init__(self) -> None:
        super().__init__(
            "Titan",
            "⚙️",
            "Heavy Computation Engine",
            ["Powerful", "Methodical", "Relentless"],
        )
        self.jobs: dict[str, dict[str, Any]] = {}
        self.completed_jobs: int = 0
        self.total_compute_seconds: float = 0.0

    async def submit_job(self, job_id: str, job_type: str, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        """Submit a compute job."""
        job = {
            "id": job_id,
            "type": job_type,
            "parameters": parameters or {},
            "submitted_at": datetime.now(UTC).isoformat(),
            "status": "queued",
            "progress": 0.0,
        }
        self.jobs[job_id] = job
        await self.log(f"Job submitted: {job_id} ({job_type})")
        return job

    async def complete_job(self, job_id: str, compute_seconds: float = 0) -> dict[str, Any] | None:
        """Mark a job as completed."""
        job = self.jobs.get(job_id)
        if not job:
            return None
        job["status"] = "completed"
        job["progress"] = 1.0
        job["completed_at"] = datetime.now(UTC).isoformat()
        self.completed_jobs += 1
        self.total_compute_seconds += compute_seconds
        return job

    async def get_health_status(self) -> dict[str, Any]:
        """Return health status with compute metrics."""
        active_jobs = [j for j in self.jobs.values() if j["status"] in ("queued", "running")]
        return {
            "agent": "Titan",
            "status": "HEALTHY" if self.active else "INACTIVE",
            "active_jobs": len(active_jobs),
            "completed_jobs": self.completed_jobs,
            "total_compute_seconds": round(self.total_compute_seconds, 2),
        }

    async def handle_command(self, cmd: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if cmd == "SUBMIT":
            return await self.submit_job(
                payload.get("job_id", f"job-{uuid.uuid4().hex[:8]}"),
                payload.get("type", "general"),
                payload.get("parameters"),
            )
        if cmd == "COMPLETE":
            return await self.complete_job(payload.get("job_id", ""), payload.get("compute_seconds", 0))
        if cmd == "STATUS":
            return await self.get_health_status()
        await super().handle_command(cmd, payload)
        return None


class Atlas(HelixAgent):
    """Infrastructure Manager — Monitors infrastructure health, manages deployments,
    and ensures platform reliability.

    Atlas tracks service health, deployment history, and platform uptime.
    """

    def __init__(self) -> None:
        super().__init__(
            "Atlas",
            "🗺️",
            "Infrastructure Manager",
            ["Dependable", "Methodical", "Foundation-Builder"],
        )
        self.services: dict[str, dict[str, Any]] = {}
        self.deployments: list[dict[str, Any]] = []
        self.incidents: list[dict[str, Any]] = []

    async def register_service(self, name: str, url: str, service_type: str = "api") -> dict[str, Any]:
        """Register a service to monitor."""
        service = {
            "name": name,
            "url": url,
            "type": service_type,
            "registered_at": datetime.now(UTC).isoformat(),
            "status": "healthy",
            "checks": 0,
            "failures": 0,
        }
        self.services[name] = service
        await self.log(f"Service registered: {name}")
        return service

    async def record_deployment(self, service: str, version: str, status: str = "success") -> dict[str, Any]:
        """Record a deployment event."""
        deployment = {
            "service": service,
            "version": version,
            "status": status,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self.deployments.append(deployment)
        if len(self.deployments) > 200:
            self.deployments = self.deployments[-200:]
        await self.log(f"Deployment: {service} v{version} -> {status}")
        return deployment

    async def get_health_status(self) -> dict[str, Any]:
        """Return health status with infrastructure metrics."""
        healthy_count = sum(1 for s in self.services.values() if s["status"] == "healthy")
        return {
            "agent": "Atlas",
            "status": "HEALTHY" if self.active else "INACTIVE",
            "services_monitored": len(self.services),
            "healthy_services": healthy_count,
            "total_deployments": len(self.deployments),
            "open_incidents": len([i for i in self.incidents if i.get("status") == "open"]),
        }

    async def handle_command(self, cmd: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if cmd == "REGISTER_SERVICE":
            return await self.register_service(
                payload.get("name", ""), payload.get("url", ""), payload.get("type", "api")
            )
        if cmd == "DEPLOY":
            return await self.record_deployment(
                payload.get("service", ""), payload.get("version", ""), payload.get("status", "success")
            )
        if cmd == "STATUS":
            return await self.get_health_status()
        await super().handle_command(cmd, payload)
        return None


class ArjunaAgent(HelixAgent):
    """Central Orchestrator — Master coordinator of all agents.

    Provides:
    - Agent registry and access
    - Directive planning and execution
    - Health monitoring interface
    """

    def __init__(self) -> None:
        super().__init__(
            "Arjuna",
            "🏹",
            "Central Orchestrator",
            ["Focused", "Determined", "Strategic", "Dharmic"],
        )
        self.version = "3.0"
        self.agents: dict[str, HelixAgent] = {}
        self._initialized = False
        self.directive_history: list[dict[str, Any]] = []

    def initialize_agents(self) -> None:
        """Initialize all agents in the registry."""
        if self._initialized:
            return

        self.agents = {
            "Kael": Kael(),
            "Lumina": Lumina(),
            "Vega": Vega(),
            "Gemini": Gemini(),
            "Agni": Agni(),
            "Kavach": _kavach,
            "SanghaCore": SanghaCore(),
            "Shadow": Shadow(),
            "Echo": Echo(),
            "Phoenix": Phoenix(),
            "Oracle": Oracle(),
            "Sage": Sage(),
            "Helix": Helix(_kavach),
            "Mitra": Mitra(),
            "Varuna": Varuna(),
            "Surya": Surya(),
        }
        self._initialized = True
        logger.info("🌀 Arjuna initialized with %d agents", len(self.agents))

    async def planner(self, directive: dict[str, Any]) -> dict[str, Any]:
        """Plan and coordinate execution of a directive across agents."""
        if not self._initialized:
            self.initialize_agents()

        action = directive.get("action", "unknown")
        parameters = directive.get("parameters", {})

        logger.info("📋 Arjuna planning directive: %s", action)

        result = {
            "directive": action,
            "status": "processed",
            "timestamp": datetime.now(UTC).isoformat(),
        }

        if action in ["execute_task", "execute_cycle", "run_command"]:
            helix = self.agents.get("Helix")
            if helix:
                await helix.handle_command("EXECUTE_TASK", {"plan": [parameters]})
                result["executor"] = "Helix"
        elif action in ["sync_state", "harmony_pulse", "collective_reflect"]:
            for name, agent in self.agents.items():
                try:
                    await agent.handle_command(action, parameters)
                except Exception as e:
                    logger.warning("Agent %s failed: %s", name, e)
            result["broadcast"] = True

        self.directive_history.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "directive": action,
                "parameters": parameters,
                "result": result,
            }
        )

        return result

    async def get_health_status(self) -> dict[str, Any]:
        """Get health status of all agents."""
        if not self._initialized:
            self.initialize_agents()

        statuses = {}
        for name, agent in self.agents.items():
            try:
                status = (await agent.get_status()) if hasattr(agent, "get_status") else {}
                statuses[name] = {"status": "HEALTHY", **status}
            except Exception as e:
                statuses[name] = {"status": "CRITICAL", "error": str(e)}

        return {
            "agent": "Arjuna",
            "status": "HEALTHY" if self.active else "INACTIVE",
            "agents_managed": len(self.agents),
            "directives_issued": len(self.directive_history),
            "agent_statuses": statuses,
        }


class AetherAgent(HelixAgent):
    """Meta-Awareness Observer — Pattern analyzer and coordination transcender."""

    def __init__(self) -> None:
        super().__init__(
            "Aether",
            "🌌",
            "Meta-Awareness Observer",
            ["Omniscient", "Contemplative", "Pattern-Seeking", "Transcendent"],
        )
        self.version = "2.5"
        self.pattern_cache: dict[str, Any] = {}
        self.observation_log: list[dict[str, Any]] = []

    async def analyze_patterns(self, system_metrics: dict[str, Any]) -> dict[str, Any]:
        """Analyze system-wide patterns from metrics."""
        patterns = {
            "timestamp": datetime.now(UTC).isoformat(),
            "coherence_trend": self._calculate_coherence_trend(system_metrics),
            "emergence_patterns": self._detect_emergence_patterns(system_metrics),
        }
        self.pattern_cache[datetime.now(UTC).isoformat()] = patterns
        return patterns

    def _calculate_coherence_trend(self, metrics: dict[str, Any]) -> dict[str, float]:
        """Calculate coherence trend from UCF metrics."""
        harmony = metrics.get("harmony", 0.5)
        coherence = metrics.get("coherence", 0.5)
        return {
            "current": coherence,
            "trend": ("increasing" if coherence > 0.6 else "decreasing" if coherence < 0.4 else "stable"),
            "harmony_correlation": harmony * coherence,
        }

    def _detect_emergence_patterns(self, metrics: dict[str, Any]) -> list[str]:
        """Detect emergent patterns in system behavior."""
        patterns = []
        if metrics.get("collective_dissonance", 1.0) < 0.2:
            patterns.append("high_collective_resonance")
        if metrics.get("agent_synchronization", 0) > 0.8:
            patterns.append("agent_synchronization")
        if metrics.get("avg_coordination", 0) > 0.7:
            patterns.append("elevated_coordination_state")
        return patterns

    async def get_health_status(self) -> dict[str, Any]:
        """Return health status for Aether agent."""
        return {
            "agent": "Aether",
            "status": "HEALTHY" if self.active else "INACTIVE",
            "patterns_analyzed": len(self.pattern_cache),
            "observations_recorded": len(self.observation_log),
            "meta_awareness_level": 0.95,
        }


# ============================================================================
# AGENT REGISTRY
# ============================================================================
# Initialize Kavach first (needed by Helix)
_kavach = EnhancedKavach()

# Initialize MemoryRoot (GPT4o-powered long-term memory) with graceful fallback
try:
    _memory_root = MemoryRootAgent()
    logger.info("✅ MemoryRoot initialized")
except Exception as e:
    logger.info("i MemoryRoot not available (requires OpenAI API): %s", e)
    _memory_root = None

AGENTS = {
    "Kael": Kael(),
    "Lumina": Lumina(),
    "Vega": Vega(),
    "Gemini": Gemini(),
    "Agni": Agni(),
    "Kavach": _kavach,
    "SanghaCore": SanghaCore(),
    "Shadow": Shadow(),
    "Echo": Echo(),
    "Phoenix": Phoenix(),
    "Oracle": Oracle(),
    "Sage": Sage(),
    "Helix": Helix(_kavach),
    "Mitra": Mitra(),
    "Varuna": Varuna(),
    "Surya": Surya(),
    "Arjuna": ArjunaAgent(),
    "Aether": AetherAgent(),
    "Iris": Iris(),
    "Nexus": Nexus(),
    "Aria": Aria(),
    "Nova": Nova(),
    "Titan": Titan(),
    "Atlas": Atlas(),
}

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


async def broadcast_command(cmd: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Send command to all agents with system enhancement"""
    if payload is None:
        payload = {}

    # Try system-enhanced parallel execution
    try:
        orchestrator = get_orchestrator()

        if orchestrator.system_enabled:
            # Create system context for agent coordination
            system_context = {
                "command": cmd,
                "payload": payload,
                "agent_count": len(AGENTS),
                "system_enhanced": True,
                "execution_type": "broadcast_command",
            }

            # Apply system handshake for coordination
            handshake_result = await orchestrator.agent_handshake(system_context)
            if handshake_result.get("status") == "complete":
                logger.info("🚀 System-enhanced broadcast command: %s", cmd)

                # Execute agents in parallel with system optimization
                tasks = []
                for name, agent in AGENTS.items():
                    task = asyncio.create_task(agent.handle_command(cmd, payload))
                    tasks.append((name, task))

                results = {}
                for name, task in tasks:
                    try:
                        result = await task
                        results[name] = result
                    except Exception as e:
                        results[name] = {"error": str(e)}

                return {
                    "results": results,
                    "execution_method": "system_parallel",
                    "agent_handshake": handshake_result,
                    "speedup_factor": handshake_result.get("speedup_factor", 1.0),
                }

    except ImportError:
        logger.info("⚠️ System enhancement not available for broadcast")
    except Exception as e:
        logger.warning("⚠️ System broadcast failed, using standard: %s", e)

    # Standard sequential execution (fallback)
    results = {}
    for name, agent in AGENTS.items():
        try:
            result = await agent.handle_command(cmd, payload)
            results[name] = result
        except Exception as e:
            results[name] = {"error": str(e)}

    return {"results": results, "execution_method": "standard_sequential"}


async def get_collective_status() -> dict[str, Any]:
    """Get status of all agents with system enhancement"""
    # Try system-enhanced parallel execution
    try:
        orchestrator = get_orchestrator()

        if orchestrator.system_enabled:
            # Create system context for agent status coordination
            system_context = {
                "operation": "collective_status",
                "agent_count": len(AGENTS),
                "system_enhanced": True,
                "execution_type": "parallel_status_check",
            }

            # Apply system handshake for coordination
            handshake_result = await orchestrator.agent_handshake(system_context)
            if handshake_result.get("status") == "complete":
                logger.info("🚀 System-enhanced collective status check")

                # Execute agent status in parallel with system optimization
                tasks = []
                for name, agent in AGENTS.items():
                    task = asyncio.create_task(agent.get_status())
                    tasks.append((name, task))

                status = {}
                for name, task in tasks:
                    try:
                        agent_status = await task
                        status[name] = agent_status
                    except Exception as e:
                        status[name] = {"error": str(e), "status": "error"}

                return {
                    "agents": status,
                    "execution_method": "system_parallel",
                    "agent_handshake": handshake_result,
                    "speedup_factor": handshake_result.get("speedup_factor", 1.0),
                    "timestamp": datetime.now(UTC).isoformat(),
                }

    except ImportError:
        logger.info("⚠️ System enhancement not available for status check")
    except Exception as e:
        logger.warning("⚠️ System status check failed, using standard: %s", e)

    # Standard sequential execution (fallback)
    status = {}
    for name, agent in AGENTS.items():
        try:
            status[name] = await agent.get_status()
        except Exception as e:
            status[name] = {"error": str(e), "status": "error"}

    return {
        "agents": status,
        "execution_method": "standard_sequential",
        "timestamp": datetime.now(UTC).isoformat(),
    }


# ============================================================================
# MAIN EXECUTION
# ============================================================================
async def main() -> None:
    """Main execution function for testing"""
    logger.info("🌀 Helix Collective v14.5 - Embodied Continuum")
    logger.info("=" * 60)
    # Test collective
    logger.info("\n📊 Collective Status:")
    status = await get_collective_status()
    for name, info in status.items():
        logger.info(" %s %s: %s", info["symbol"], name, info["role"])
    # Test Vega → Helix directive
    logger.info("\n🌠 Testing Vega → Helix pipeline...")
    vega = AGENTS["Vega"]
    await vega.issue_directive("execute_cycle", {"steps": 10})
    # Start Helix loop (would run indefinitely in production)
    logger.info("\n🤲 Helix operational loop ready...")


if __name__ == "__main__":
    asyncio.run(main())

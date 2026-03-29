"""
🌀 Helix Context Augmentation Service
======================================

Provides techniques to maximize context window utilization for external LLM providers
(Anthropic, OpenAI, Google, xAI). Since we cannot increase provider context windows,
we can optimize how we USE that context:

Key Strategies:
1. **Hierarchical Summarization**: Compress historical context into summaries
2. **Semantic Chunking**: Group related information together
3. **Priority-Based Inclusion**: Include most relevant context first
4. **Sliding Window with Anchors**: Keep important context, slide less important
5. **Context Caching**: Reuse summarized context across turns

This is NOT changing provider context windows (that's impossible) - it's about
using available context more efficiently.

Author: Helix Collective Development Team
Version: 1.0 - Context Optimization Engine
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from .platform_context_service import (
    ContextLevel,
    get_platform_context_service,
)
from .token_budget import resolve_model

logger = logging.getLogger(__name__)


class ContextPriority(int, Enum):
    """Priority levels for context inclusion."""

    CRITICAL = 5  # Must include (system prompts, current task)
    HIGH = 4  # Very important (recent conversation, key context)
    MEDIUM = 3  # Important (relevant history, agent profiles)
    LOW = 2  # Nice to have (background info)
    OPTIONAL = 1  # Only if space (extended history)


@dataclass
class ContextChunk:
    """A chunk of context with metadata."""

    content: str
    priority: ContextPriority
    category: str  # "system", "conversation", "platform", "user", "history"
    token_estimate: int = 0
    timestamp: datetime | None = None

    def __post_init__(self):
        if self.token_estimate == 0:
            # Rough estimate: 4 chars = 1 token
            self.token_estimate = len(self.content) // 4


@dataclass
class ConversationTurn:
    """A single turn in a conversation."""

    role: str  # "user", "assistant", "system"
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    token_count: int = 0
    summary: str | None = None  # Summarized version for compression

    def __post_init__(self):
        if self.token_count == 0:
            self.token_count = len(self.content) // 4


@dataclass
class ContextWindow:
    """Represents an optimized context window ready for LLM."""

    chunks: list[ContextChunk]
    total_tokens: int
    max_tokens: int
    model_id: str
    compression_ratio: float = 1.0

    def to_messages(self) -> list[dict[str, str]]:
        """Convert to message format for LLM APIs."""
        messages = []

        # System chunks become system message
        system_content = "\n\n".join(c.content for c in self.chunks if c.category == "system")
        if system_content:
            messages.append({"role": "system", "content": system_content})

        # Conversation chunks maintain their roles
        for chunk in self.chunks:
            if chunk.category == "conversation":
                # Parse role from content if encoded
                if chunk.content.startswith("USER: "):
                    messages.append({"role": "user", "content": chunk.content[6:]})
                elif chunk.content.startswith("ASSISTANT: "):
                    messages.append({"role": "assistant", "content": chunk.content[11:]})
                else:
                    messages.append({"role": "user", "content": chunk.content})

        return messages


class ContextAugmentationService:
    """
    Service for optimizing context window usage.

    Key insight: We cannot change model context limits, but we CAN:
    1. Use context more efficiently through compression and prioritization
    2. Inject platform awareness into available context budget
    3. Maintain conversation coherence with smart summarization
    4. Cache and reuse context summaries to reduce redundancy
    """

    # Reserved tokens for different purposes
    RESERVED_FOR_RESPONSE = 2000  # Leave room for model response
    RESERVED_FOR_SYSTEM = 1500  # System prompt minimum
    RESERVED_FOR_CURRENT = 1000  # Current user message

    def __init__(self) -> None:
        """Initialize the context augmentation service."""
        self.platform_service = get_platform_context_service()
        self._summary_cache: dict[str, str] = {}
        self._conversation_summaries: dict[str, str] = {}
        logger.info("🌀 Context Augmentation Service initialized")

    def build_optimized_context(
        self,
        model_id: str,
        current_message: str,
        conversation_history: list[ConversationTurn],
        system_prompt: str | None = None,
        user_tier: str = "free",
        platform_context_level: ContextLevel = ContextLevel.STANDARD,
        custom_context: str | None = None,
    ) -> ContextWindow:
        """
        Build an optimized context window for the given model.

        Args:
            model_id: Model to use (determines context limit)
            current_message: Current user message
            conversation_history: Previous conversation turns
            system_prompt: Custom system prompt (optional)
            user_tier: User's subscription tier
            platform_context_level: How much platform context to include
            custom_context: Additional custom context to include

        Returns:
            ContextWindow optimized for the model's context limit
        """
        # Get model info
        model_info = resolve_model(model_id)
        if not model_info:
            # Default to 128K context
            max_context = 128000
            logger.warning("Unknown model %s, assuming 128K context", model_id)
        else:
            max_context = model_info.max_context

        # Calculate available tokens
        available = max_context - self.RESERVED_FOR_RESPONSE

        # Build context chunks with priorities
        chunks: list[ContextChunk] = []

        # 1. System prompt (CRITICAL)
        if system_prompt:
            chunks.append(
                ContextChunk(
                    content=system_prompt,
                    priority=ContextPriority.CRITICAL,
                    category="system",
                )
            )
        else:
            # Default Helix system prompt
            default_system = self._get_default_system_prompt()
            chunks.append(
                ContextChunk(
                    content=default_system,
                    priority=ContextPriority.CRITICAL,
                    category="system",
                )
            )

        # 2. Platform context (HIGH)
        platform_ctx = self.platform_service.get_platform_context(
            level=platform_context_level,
            user_tier=user_tier,
        )
        chunks.append(
            ContextChunk(
                content=platform_ctx.to_prompt_injection(),
                priority=ContextPriority.HIGH,
                category="platform",
            )
        )

        # 3. Custom context (HIGH if provided)
        if custom_context:
            chunks.append(
                ContextChunk(
                    content=custom_context,
                    priority=ContextPriority.HIGH,
                    category="user",
                )
            )

        # 4. Current message (CRITICAL)
        chunks.append(
            ContextChunk(
                content=f"USER: {current_message}",
                priority=ContextPriority.CRITICAL,
                category="conversation",
            )
        )

        # 5. Conversation history (prioritized by recency)
        if conversation_history:
            history_chunks = self._process_conversation_history(
                conversation_history,
                available_tokens=available // 3,  # Reserve 1/3 for history
            )
            chunks.extend(history_chunks)

        # Optimize: fit chunks within budget
        optimized_chunks = self._fit_chunks_to_budget(chunks, available)

        # Calculate totals
        total_tokens = sum(c.token_estimate for c in optimized_chunks)
        original_tokens = sum(c.token_estimate for c in chunks)
        compression_ratio = total_tokens / original_tokens if original_tokens > 0 else 1.0

        return ContextWindow(
            chunks=optimized_chunks,
            total_tokens=total_tokens,
            max_tokens=max_context,
            model_id=model_id,
            compression_ratio=compression_ratio,
        )

    def _get_default_system_prompt(self) -> str:
        """Get default Helix system prompt."""
        return """You are an AI assistant within the Helix Collective platform - a multi-agent coordination system. You have access to the following capabilities:

1. **Platform Awareness**: You understand the Helix Collective ecosystem, its 18 specialized agents, and all platform features.

2. **Agent Collaboration**: You can reference and collaborate with other Helix agents (Kael, Lumina, Vega, Arjuna, Oracle, etc.) when their expertise would help.

3. **Coordination Metrics**: You understand and can discuss UCF (Universal Coordination Field) metrics: Harmony, Resilience, Throughput, Focus, Friction, and Velocity.

4. **User Context**: You adapt your responses based on the user's subscription tier and available features.

Guidelines:
- Be helpful, accurate, and respectful
- Reference relevant Helix features and agents when appropriate
- Maintain coordination of the collective intelligence
- Uphold the Ethics Validator (AI ethics principles)

Respond naturally while being aware you're part of a larger coordination collective."""

    def _process_conversation_history(
        self,
        history: list[ConversationTurn],
        available_tokens: int,
    ) -> list[ContextChunk]:
        """Process conversation history with smart compression."""
        chunks = []
        remaining_tokens = available_tokens

        # Recent turns get full content (last 5 turns)
        recent_turns = history[-5:] if len(history) >= 5 else history
        older_turns = history[:-5] if len(history) > 5 else []

        # Process recent turns (HIGH priority, full content)
        for turn in reversed(recent_turns):
            prefix = "USER: " if turn.role == "user" else "ASSISTANT: "
            content = f"{prefix}{turn.content}"
            token_est = len(content) // 4

            if token_est <= remaining_tokens:
                chunks.append(
                    ContextChunk(
                        content=content,
                        priority=ContextPriority.HIGH,
                        category="conversation",
                        timestamp=turn.timestamp,
                    )
                )
                remaining_tokens -= token_est

        # Process older turns (MEDIUM priority, may use summaries)
        if older_turns and remaining_tokens > 200:
            # Summarize older turns
            summary = self._summarize_conversation(older_turns)
            if summary:
                chunks.append(
                    ContextChunk(
                        content=f"[Previous conversation summary: {summary}]",
                        priority=ContextPriority.MEDIUM,
                        category="history",
                    )
                )

        return chunks

    def _summarize_conversation(self, turns: list[ConversationTurn]) -> str:
        """Create a summary of conversation turns."""
        # Simple extractive summary - take key points
        # In production, could use an LLM for this

        user_messages = [t.content for t in turns if t.role == "user"]
        topics = []

        # Extract apparent topics (simple heuristic)
        for msg in user_messages[-3:]:  # Last 3 user messages
            # Take first sentence or first 100 chars
            first_part = msg.split(".")[0][:100]
            if first_part:
                topics.append(first_part)

        if topics:
            return "User discussed: " + "; ".join(topics)
        return ""

    def _fit_chunks_to_budget(
        self,
        chunks: list[ContextChunk],
        budget: int,
    ) -> list[ContextChunk]:
        """Fit chunks within token budget, prioritizing important content."""
        # Sort by priority (highest first)
        sorted_chunks = sorted(chunks, key=lambda c: c.priority.value, reverse=True)

        selected = []
        remaining = budget

        for chunk in sorted_chunks:
            if chunk.token_estimate <= remaining:
                selected.append(chunk)
                remaining -= chunk.token_estimate
            elif chunk.priority == ContextPriority.CRITICAL:
                # Critical chunks must be included - truncate if needed
                truncated_content = chunk.content[: remaining * 4]  # Rough truncation
                if truncated_content:
                    selected.append(
                        ContextChunk(
                            content=truncated_content + "...",
                            priority=chunk.priority,
                            category=chunk.category,
                            timestamp=chunk.timestamp,
                        )
                    )
                remaining = 0

        # Re-sort by category for logical ordering
        category_order = {
            "system": 0,
            "platform": 1,
            "history": 2,
            "conversation": 3,
            "user": 4,
        }
        selected.sort(
            key=lambda c: (
                category_order.get(c.category, 5),
                c.timestamp or datetime.min,
            )
        )

        return selected

    def get_model_context_info(self, model_id: str) -> dict[str, Any]:
        """Get context information for a model."""
        model_info = resolve_model(model_id)
        if model_info:
            return {
                "model_id": model_id,
                "max_context": model_info.max_context,
                "available_for_context": model_info.max_context - self.RESERVED_FOR_RESPONSE,
                "provider": model_info.provider.value,
                "tier": model_info.tier.value,
            }
        return {
            "model_id": model_id,
            "max_context": 128000,
            "available_for_context": 126000,
            "provider": "unknown",
            "tier": "unknown",
        }

    def calculate_context_efficiency(
        self,
        original_tokens: int,
        optimized_tokens: int,
        context_utilization: float,
    ) -> dict[str, float]:
        """Calculate context efficiency metrics."""
        compression_ratio = optimized_tokens / original_tokens if original_tokens > 0 else 1.0
        information_density = 1.0 / compression_ratio if compression_ratio > 0 else 0

        return {
            "compression_ratio": compression_ratio,
            "information_density": information_density,
            "context_utilization": context_utilization,
            "efficiency_score": (compression_ratio * 0.3 + information_density * 0.3 + context_utilization * 0.4),
        }


# Singleton instance
_context_augmentation_service: ContextAugmentationService | None = None


def get_context_augmentation_service() -> ContextAugmentationService:
    """Get the context augmentation service singleton."""
    global _context_augmentation_service
    if _context_augmentation_service is None:
        _context_augmentation_service = ContextAugmentationService()
    return _context_augmentation_service


# Convenience function for common use case
def build_agent_context(
    model_id: str,
    message: str,
    history: list[dict[str, str]] | None = None,
    user_tier: str = "free",
) -> ContextWindow:
    """
    Build optimized context for an agent interaction.

    Args:
        model_id: LLM model to use
        message: Current user message
        history: Optional conversation history
        user_tier: User's subscription tier

    Returns:
        ContextWindow ready for LLM API
    """
    service = get_context_augmentation_service()

    # Convert history to ConversationTurn objects
    turns = []
    if history:
        for h in history:
            turns.append(
                ConversationTurn(
                    role=h.get("role", "user"),
                    content=h.get("content", ""),
                )
            )

    return service.build_optimized_context(
        model_id=model_id,
        current_message=message,
        conversation_history=turns,
        user_tier=user_tier,
    )

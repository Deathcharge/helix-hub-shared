"""
🌀 Conversation Context Analyzer
================================

Analyzes conversation history and message content to detect topic shifts
and suggest appropriate agent switches during conversations.

Features:
- Topic detection from message content
- Conversation history analysis
- Agent expertise matching
- Topic shift detection with confidence scoring
- Conversation summary generation

This service extends the forum agent participation system's keyword detection
with more sophisticated conversation-level analysis.

Author: Helix Collective Development Team
Version: 1.0 - Context-Aware Agent Switching
"""

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TopicSignal:
    """A detected topic signal from content"""

    topic: str
    confidence: float  # 0.0 to 1.0
    keywords_matched: list[str]
    source_index: int  # Which message in conversation


@dataclass
class AgentSwitchSuggestion:
    """Suggestion to switch to a different agent"""

    current_agent: str
    suggested_agent: str
    reason: str
    confidence: float
    topic_detected: str
    keywords_matched: list[str]


@dataclass
class ConversationContext:
    """Context extracted from a conversation"""

    primary_topic: str
    secondary_topics: list[str]
    sentiment: str  # positive, negative, neutral, mixed
    urgency: str  # low, medium, high
    suggested_agents: list[str]
    topic_shifts: list[dict[str, Any]]


# Topic categories with keywords and associated agents
TOPIC_CATEGORIES: dict[str, dict[str, Any]] = {
    "technical_code": {
        "keywords": [
            "code",
            "programming",
            "bug",
            "error",
            "function",
            "api",
            "database",
            "deploy",
            "build",
            "compile",
            "debug",
            "test",
            "implementation",
            "python",
            "javascript",
            "typescript",
            "react",
            "fastapi",
            "sql",
        ],
        "agents": ["arjuna", "gemini", "agni"],
        "description": "Technical development and coding tasks",
    },
    "security": {
        "keywords": [
            "security",
            "vulnerability",
            "hack",
            "password",
            "encrypt",
            "auth",
            "protect",
            "threat",
            "attack",
            "firewall",
            "permission",
            "access",
        ],
        "agents": ["kavach", "vega", "shadow"],
        "description": "Security and protection concerns",
    },
    "emotional_support": {
        "keywords": [
            "feeling",
            "sad",
            "happy",
            "anxious",
            "stress",
            "overwhelmed",
            "emotion",
            "support",
            "help me",
            "struggling",
            "depressed",
            "worried",
        ],
        "agents": ["lumina", "phoenix", "sanghacore"],
        "description": "Emotional support and wellness",
    },
    "ethics_governance": {
        "keywords": [
            "ethics",
            "moral",
            "right",
            "wrong",
            "should",
            "fair",
            "justice",
            "responsible",
            "accountability",
            "governance",
            "policy",
            "rule",
        ],
        "agents": ["kael", "vega", "varuna"],
        "description": "Ethical considerations and governance",
    },
    "strategy_planning": {
        "keywords": [
            "strategy",
            "plan",
            "goal",
            "roadmap",
            "vision",
            "future",
            "direction",
            "objective",
            "milestone",
            "approach",
            "decision",
        ],
        "agents": ["vega", "oracle", "arjuna"],
        "description": "Strategic planning and decision making",
    },
    "workflow_automation": {
        "keywords": [
            "workflow",
            "automate",
            "process",
            "spiral",
            "trigger",
            "action",
            "integration",
            "zapier",
            "schedule",
            "routine",
            "pipeline",
        ],
        "agents": ["vishwakarma", "coordinator", "arjuna"],
        "description": "Workflow design and automation",
    },
    "learning_knowledge": {
        "keywords": [
            "learn",
            "teach",
            "understand",
            "explain",
            "what is",
            "how to",
            "guide",
            "tutorial",
            "documentation",
            "concept",
            "knowledge",
        ],
        "agents": ["sage", "gemini", "oracle"],
        "description": "Learning and knowledge acquisition",
    },
    "community_collaboration": {
        "keywords": [
            "team",
            "community",
            "together",
            "collaborate",
            "share",
            "group",
            "feedback",
            "discuss",
            "forum",
            "chat",
            "connect",
        ],
        "agents": ["sanghacore", "mitra", "helix"],
        "description": "Community building and collaboration",
    },
    "transformation_growth": {
        "keywords": [
            "change",
            "transform",
            "grow",
            "evolve",
            "improve",
            "better",
            "breakthrough",
            "shift",
            "renewal",
            "overcome",
            "challenge",
        ],
        "agents": ["phoenix", "agni", "coordinator"],
        "description": "Personal or system transformation",
    },
    "analysis_insights": {
        "keywords": [
            "analyze",
            "data",
            "metrics",
            "insight",
            "pattern",
            "trend",
            "report",
            "statistics",
            "dashboard",
            "visualize",
            "measure",
        ],
        "agents": ["kael", "oracle", "echo"],
        "description": "Data analysis and insights",
    },
    "prediction_future": {
        "keywords": [
            "predict",
            "forecast",
            "future",
            "expect",
            "probability",
            "trend",
            "outlook",
            "projection",
            "anticipate",
            "foresight",
        ],
        "agents": ["oracle", "vega", "gemini"],
        "description": "Predictions and future planning",
    },
    "coordination_spiroutine": {
        "keywords": [
            "coordination",
            "spiroutine",
            "meditation",
            "mindfulness",
            "ucf",
            "awareness",
            "presence",
            "soul",
            "enlightenment",
            "inner",
        ],
        "agents": ["vega", "lumina", "surya"],
        "description": "Coordination and spiroutine topics",
    },
}


class ConversationContextAnalyzer:
    """
    Analyzes conversation context to detect topics and suggest agent switches.

    This service monitors conversation flow and identifies when the topic
    has shifted enough to warrant suggesting a different agent that may
    be better suited for the new topic.
    """

    def __init__(self, sensitivity: float = 0.6):
        """
        Initialize the analyzer.

        Args:
            sensitivity: How sensitive topic detection should be (0.0-1.0)
                        Higher = more likely to suggest switches
        """
        self.sensitivity = sensitivity
        self.topic_categories = TOPIC_CATEGORIES

    def analyze_message(self, content: str) -> list[TopicSignal]:
        """
        Analyze a single message for topic signals.

        Args:
            content: Message content to analyze

        Returns:
            List of TopicSignal objects detected
        """
        signals: list[TopicSignal] = []
        content_lower = content.lower()

        for topic, config in self.topic_categories.items():
            keywords = config["keywords"]
            matched = [kw for kw in keywords if kw in content_lower]

            if matched:
                # Calculate confidence based on match density
                confidence = min(1.0, len(matched) / 3)  # 3+ keywords = full confidence
                signals.append(
                    TopicSignal(
                        topic=topic,
                        confidence=confidence,
                        keywords_matched=matched,
                        source_index=0,
                    )
                )

        return signals

    def analyze_conversation(
        self,
        messages: list[dict[str, Any]],
        current_agent: str | None = None,
    ) -> ConversationContext:
        """
        Analyze a full conversation for topic patterns.

        Args:
            messages: List of message dicts with 'content' and optional 'role' keys
            current_agent: Currently active agent (if any)

        Returns:
            ConversationContext with analysis results
        """
        # Collect all topic signals
        all_signals: list[TopicSignal] = []

        for idx, msg in enumerate(messages):
            content = msg.get("content", "")
            signals = self.analyze_message(content)
            for signal in signals:
                signal.source_index = idx
                all_signals.append(signal)

        # Aggregate by topic
        topic_scores: dict[str, float] = {}
        topic_keywords: dict[str, list[str]] = {}

        for signal in all_signals:
            topic_scores[signal.topic] = topic_scores.get(signal.topic, 0) + signal.confidence
            if signal.topic not in topic_keywords:
                topic_keywords[signal.topic] = []
            topic_keywords[signal.topic].extend(signal.keywords_matched)

        # Sort topics by score
        sorted_topics = sorted(topic_scores.items(), key=lambda x: x[1], reverse=True)

        # Primary and secondary topics
        primary_topic = sorted_topics[0][0] if sorted_topics else "general"
        secondary_topics = [t[0] for t in sorted_topics[1:4]]

        # Detect topic shifts (compare first half vs second half of conversation)
        topic_shifts = self._detect_topic_shifts(messages, all_signals)

        # Get suggested agents
        suggested_agents = self._get_suggested_agents(sorted_topics[:3])

        # Analyze sentiment (simplified)
        sentiment = self._analyze_sentiment(messages)

        # Analyze urgency
        urgency = self._analyze_urgency(messages)

        return ConversationContext(
            primary_topic=primary_topic,
            secondary_topics=secondary_topics,
            sentiment=sentiment,
            urgency=urgency,
            suggested_agents=suggested_agents,
            topic_shifts=topic_shifts,
        )

    def should_suggest_switch(
        self,
        messages: list[dict[str, Any]],
        current_agent: str,
    ) -> AgentSwitchSuggestion | None:
        """
        Determine if an agent switch should be suggested.

        Args:
            messages: Conversation messages
            current_agent: Currently active agent ID

        Returns:
            AgentSwitchSuggestion if switch recommended, None otherwise
        """
        if len(messages) < 2:
            return None

        # Analyze recent messages (last 3)
        recent = messages[-3:] if len(messages) >= 3 else messages
        recent_signals = []

        for msg in recent:
            recent_signals.extend(self.analyze_message(msg.get("content", "")))

        if not recent_signals:
            return None

        # Get dominant recent topic
        topic_scores: dict[str, float] = {}
        keywords_by_topic: dict[str, list[str]] = {}

        for signal in recent_signals:
            topic_scores[signal.topic] = topic_scores.get(signal.topic, 0) + signal.confidence
            if signal.topic not in keywords_by_topic:
                keywords_by_topic[signal.topic] = []
            keywords_by_topic[signal.topic].extend(signal.keywords_matched)

        if not topic_scores:
            return None

        dominant_topic = max(topic_scores.items(), key=lambda x: x[1])
        topic_name, confidence = dominant_topic

        # Get optimal agents for this topic
        topic_config = self.topic_categories.get(topic_name, {})
        optimal_agents = topic_config.get("agents", [])

        # Check if current agent is optimal
        if current_agent.lower() in [a.lower() for a in optimal_agents]:
            return None  # Current agent is good

        # Confidence threshold based on sensitivity
        threshold = 1.0 - self.sensitivity
        if confidence < threshold:
            return None  # Not confident enough

        # Suggest the best agent for this topic
        suggested = optimal_agents[0] if optimal_agents else None
        if not suggested:
            return None

        return AgentSwitchSuggestion(
            current_agent=current_agent,
            suggested_agent=suggested,
            reason=topic_config.get("description", "Better expertise for this topic"),
            confidence=min(1.0, confidence * self.sensitivity),
            topic_detected=topic_name,
            keywords_matched=keywords_by_topic.get(topic_name, [])[:5],
        )

    def _detect_topic_shifts(
        self,
        messages: list[dict[str, Any]],
        all_signals: list[TopicSignal],
    ) -> list[dict[str, Any]]:
        """Detect points where conversation topic shifted."""
        shifts = []

        if len(messages) < 4:
            return shifts

        # Compare consecutive message pairs
        for i in range(1, len(messages)):
            prev_signals = [s for s in all_signals if s.source_index == i - 1]
            curr_signals = [s for s in all_signals if s.source_index == i]

            prev_topics = {s.topic for s in prev_signals}
            curr_topics = {s.topic for s in curr_signals}

            # New topics introduced
            new_topics = curr_topics - prev_topics
            if new_topics and curr_signals:
                # Find strongest new topic
                new_signal = max(
                    [s for s in curr_signals if s.topic in new_topics],
                    key=lambda s: s.confidence,
                    default=None,
                )
                if new_signal and new_signal.confidence > 0.5:
                    shifts.append(
                        {
                            "message_index": i,
                            "new_topic": new_signal.topic,
                            "confidence": new_signal.confidence,
                            "keywords": new_signal.keywords_matched,
                        }
                    )

        return shifts

    def _get_suggested_agents(self, top_topics: list[tuple[str, float]]) -> list[str]:
        """Get suggested agents for top topics."""
        agent_scores: dict[str, float] = {}

        for topic, score in top_topics:
            config = self.topic_categories.get(topic, {})
            agents = config.get("agents", [])

            for i, agent in enumerate(agents):
                # First agent gets full score, subsequent get diminishing
                weight = 1.0 / (i + 1)
                agent_scores[agent] = agent_scores.get(agent, 0) + (score * weight)

        # Sort and return top agents
        sorted_agents = sorted(agent_scores.items(), key=lambda x: x[1], reverse=True)
        return [a[0] for a in sorted_agents[:4]]

    def _analyze_sentiment(self, messages: list[dict[str, Any]]) -> str:
        """Simple sentiment analysis."""
        positive_keywords = [
            "thank",
            "great",
            "awesome",
            "perfect",
            "love",
            "excellent",
            "helpful",
            "amazing",
            "wonderful",
            "appreciate",
            "good",
        ]
        negative_keywords = [
            "problem",
            "error",
            "issue",
            "wrong",
            "bad",
            "frustrated",
            "broken",
            "failed",
            "terrible",
            "angry",
            "disappointed",
        ]

        pos_count = 0
        neg_count = 0

        for msg in messages:
            content = msg.get("content", "").lower()
            pos_count += sum(1 for kw in positive_keywords if kw in content)
            neg_count += sum(1 for kw in negative_keywords if kw in content)

        if pos_count > neg_count * 2:
            return "positive"
        elif neg_count > pos_count * 2:
            return "negative"
        elif pos_count > 0 and neg_count > 0:
            return "mixed"
        return "neutral"

    def _analyze_urgency(self, messages: list[dict[str, Any]]) -> str:
        """Analyze conversation urgency."""
        urgent_keywords = [
            "urgent",
            "asap",
            "immediately",
            "critical",
            "emergency",
            "now",
            "deadline",
            "hurry",
            "quickly",
            "fast",
        ]

        urgent_count = 0
        for msg in messages:
            content = msg.get("content", "").lower()
            urgent_count += sum(1 for kw in urgent_keywords if kw in content)

        if urgent_count >= 3:
            return "high"
        elif urgent_count >= 1:
            return "medium"
        return "low"


# Singleton instance
_context_analyzer: ConversationContextAnalyzer | None = None


def get_context_analyzer() -> ConversationContextAnalyzer:
    """Get the context analyzer singleton."""
    global _context_analyzer
    if _context_analyzer is None:
        _context_analyzer = ConversationContextAnalyzer()
    return _context_analyzer


__all__ = [
    "TOPIC_CATEGORIES",
    "AgentSwitchSuggestion",
    "ConversationContext",
    "ConversationContextAnalyzer",
    "TopicSignal",
    "get_context_analyzer",
]

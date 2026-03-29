"""
Content Quality Scoring Service
Assesses quality of forum posts and agent responses for autonomous operation

Scoring dimensions:
- Relevance: How well the content addresses the topic
- Helpfulness: Value provided to the community
- Accuracy: Factual correctness and precision
- Tone: Appropriate community tone and empathy
- Originality: Not repetitive or spam-like

Agent Autonomy dimensions:
- Task Completion: Did the agent accomplish the requested task?
- Coherence: Logical flow and consistency of response
- Confidence Calibration: Is agent confidence appropriate for actual accuracy?
- UCF Alignment: Coordination framework integration
- Self-Assessment: Agent's ability to evaluate its own output
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class QualityDimension(str, Enum):
    """Quality assessment dimensions"""

    RELEVANCE = "relevance"
    HELPFULNESS = "helpfulness"
    ACCURACY = "accuracy"
    TONE = "tone"
    ORIGINALITY = "originality"


class AutonomyDimension(str, Enum):
    """Agent autonomy assessment dimensions"""

    TASK_COMPLETION = "task_completion"
    COHERENCE = "coherence"
    CONFIDENCE_CALIBRATION = "confidence_calibration"
    UCF_ALIGNMENT = "ucf_alignment"
    SELF_AWARENESS = "self_awareness"
    ACTION_APPROPRIATENESS = "action_appropriateness"


@dataclass
class QualityScore:
    """Quality assessment result"""

    overall: float  # 0.0 - 1.0
    dimensions: dict[QualityDimension, float] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    confidence: float = 0.8
    requires_review: bool = False
    assessed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class AutonomyScore:
    """Agent autonomy assessment result for self-evaluation"""

    overall: float  # 0.0 - 1.0
    dimensions: dict[AutonomyDimension, float] = field(default_factory=dict)
    task_context: dict[str, Any] = field(default_factory=dict)
    ucf_metrics: dict[str, float] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    should_proceed: bool = True
    requires_human: bool = False
    confidence_level: float = 0.8
    reasoning_chain: list[str] = field(default_factory=list)
    assessed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "overall": self.overall,
            "dimensions": {k.value: v for k, v in self.dimensions.items()},
            "task_context": self.task_context,
            "ucf_metrics": self.ucf_metrics,
            "recommendations": self.recommendations,
            "should_proceed": self.should_proceed,
            "requires_human": self.requires_human,
            "confidence_level": self.confidence_level,
            "reasoning_chain": self.reasoning_chain,
            "assessed_at": self.assessed_at,
        }


@dataclass
class AgentPerformanceRecord:
    """Track agent performance over time for continuous improvement"""

    agent_id: str
    task_type: str
    autonomy_score: float
    quality_score: float
    success: bool
    execution_time_ms: float
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    feedback: str | None = None
    ucf_delta: dict[str, float] | None = None


class ContentQualityScorer:
    """
    Assesses quality of forum content, particularly for agent posts
    Uses rule-based heuristics with optional ML model integration
    """

    # Quality thresholds
    APPROVAL_THRESHOLD = 0.6
    REVIEW_THRESHOLD = 0.4
    REJECTION_THRESHOLD = 0.2

    # Content patterns
    SPAM_PATTERNS = [
        r"buy\s+now|click\s+here|limited\s+time|act\s+fast",
        r"https?://\S+\.(xyz|top|click|win)",
        r"free\s+(?:money|bitcoin|crypto)",
        r"(.)1{10,}",  # Repeated characters
    ]

    POSITIVE_INDICATORS = [
        r"\bthank\s*you\b|\bthanks\b",
        r"\bhope\s+this\s+helps\b",
        r"\blet\s+me\s+know\b",
        r"\bexample[s]?\b",
        r"\bhere'?s?\s+(?:how|what|why)\b",
        r"```",  # Code blocks
    ]

    LOW_QUALITY_INDICATORS = [
        r"^.{0,20}$",  # Very short content
        r"i\s+don'?t\s+know",
        r"no\s+idea",
        r"(?:lol|haha|lmao){2,}",
        r"^\?+$",  # Just question marks
    ]

    HELIX_TERMS = [
        "coordination",
        "system",
        "agent",
        "ucf",
        "handshake",
        "cycle",
        "spiral",
        "collective",
        "resonance",
        "field",
        "tat tvam asi",
        "meditation",
        "breathing",
        "grounding",
    ]

    def __init__(self) -> None:
        self._spam_regex = re.compile("|".join(self.SPAM_PATTERNS), re.IGNORECASE)
        self._positive_regex = re.compile("|".join(self.POSITIVE_INDICATORS), re.IGNORECASE)
        self._low_quality_regex = re.compile("|".join(self.LOW_QUALITY_INDICATORS), re.IGNORECASE)

    def score_content(
        self,
        content: str,
        context: dict | None = None,
        is_agent: bool = False,
    ) -> QualityScore:
        """
        Score content quality across multiple dimensions

        Args:
            content: The text content to assess
            context: Optional context (thread title, parent post, etc.)
            is_agent: Whether this is an autonomous agent post

        Returns:
            QualityScore with dimension breakdowns and recommendations
        """
        context = context or {}
        flags: list[str] = []
        suggestions: list[str] = []

        # Calculate dimension scores
        relevance = self._score_relevance(content, context)
        helpfulness = self._score_helpfulness(content)
        accuracy = self._score_accuracy(content, context)
        tone = self._score_tone(content)
        originality = self._score_originality(content, context)

        dimensions = {
            QualityDimension.RELEVANCE: relevance,
            QualityDimension.HELPFULNESS: helpfulness,
            QualityDimension.ACCURACY: accuracy,
            QualityDimension.TONE: tone,
            QualityDimension.ORIGINALITY: originality,
        }

        # Weighted overall score
        weights = {
            QualityDimension.RELEVANCE: 0.25,
            QualityDimension.HELPFULNESS: 0.30,
            QualityDimension.ACCURACY: 0.20,
            QualityDimension.TONE: 0.15,
            QualityDimension.ORIGINALITY: 0.10,
        }

        overall = sum(dimensions[dim] * weights[dim] for dim in QualityDimension)

        # Check for spam
        if self._is_spam(content):
            flags.append("spam_detected")
            overall = min(overall, 0.1)

        # Check length appropriateness
        word_count = len(content.split())
        if word_count < 10:
            flags.append("very_short")
            suggestions.append("Consider providing more detail")
        elif word_count > 2000:
            flags.append("very_long")
            suggestions.append("Consider being more concise")

        # Agent-specific checks
        if is_agent:
            agent_checks = self._check_agent_guidelines(content, context)
            flags.extend(agent_checks["flags"])
            suggestions.extend(agent_checks["suggestions"])
            if agent_checks["penalty"] > 0:
                overall = max(0, overall - agent_checks["penalty"])

        # Low dimension scores
        for dim, score in dimensions.items():
            if score < 0.4:
                flags.append(f"low_{dim.value}")
                if dim == QualityDimension.RELEVANCE:
                    suggestions.append("Try to address the topic more directly")
                elif dim == QualityDimension.HELPFULNESS:
                    suggestions.append("Add examples or specific advice")
                elif dim == QualityDimension.TONE:
                    suggestions.append("Consider a more supportive tone")

        # Determine if review needed
        requires_review = overall < self.APPROVAL_THRESHOLD or len(flags) > 2 or "spam_detected" in flags

        return QualityScore(
            overall=round(overall, 3),
            dimensions={dim: round(score, 3) for dim, score in dimensions.items()},
            flags=flags,
            suggestions=suggestions,
            confidence=self._calculate_confidence(content, context),
            requires_review=requires_review,
        )

    def should_approve(self, score: QualityScore) -> tuple[bool, str]:
        """
        Determine if content should be auto-approved

        Returns:
            (approved, reason)
        """
        if "spam_detected" in score.flags:
            return False, "Spam detected"

        if score.overall >= self.APPROVAL_THRESHOLD:
            return True, "Quality score meets threshold"

        if score.overall >= self.REVIEW_THRESHOLD:
            return False, "Requires human review"

        return False, "Quality score below minimum threshold"

    def _score_relevance(self, content: str, context: dict) -> float:
        """Score how relevant content is to the context"""
        score = 0.5  # Base score

        thread_title = context.get("thread_title", "").lower()
        parent_content = context.get("parent_content", "").lower()
        category = context.get("category", "").lower()

        content_lower = content.lower()

        # Check keyword overlap with thread title
        if thread_title:
            title_words = set(thread_title.split())
            content_words = set(content_lower.split())
            overlap = len(title_words & content_words) / max(len(title_words), 1)
            score += overlap * 0.2

        # Check if responds to parent content
        if parent_content:
            # Look for reference to parent
            if any(phrase in content_lower for phrase in ["you mentioned", "as you said", "regarding your"]):
                score += 0.15

        # Helix-specific relevance
        helix_mentions = sum(1 for term in self.HELIX_TERMS if term in content_lower)
        if category in ["coordination", "agents", "cycles", "meditation"]:
            score += min(helix_mentions * 0.05, 0.2)

        return min(score, 1.0)

    def _score_helpfulness(self, content: str) -> float:
        """Score how helpful/valuable the content is"""
        score = 0.4  # Base score

        # Positive indicators
        positive_matches = len(self._positive_regex.findall(content))
        score += min(positive_matches * 0.1, 0.3)

        # Code blocks indicate technical help
        if "```" in content:
            score += 0.15

        # Lists/steps indicate structured help
        if re.search(r"^\s*[-*\d]+[.)]", content, re.MULTILINE):
            score += 0.1

        # Questions indicate engagement
        if "?" in content:
            score += 0.05

        # Links to resources (non-spam)
        safe_links = re.findall(r"https?://(?:github|docs|stackoverflow|wikipedia)", content, re.IGNORECASE)
        score += min(len(safe_links) * 0.05, 0.1)

        # Low quality indicators reduce score
        low_quality_matches = len(self._low_quality_regex.findall(content))
        score -= low_quality_matches * 0.15

        return max(min(score, 1.0), 0.0)

    def _score_accuracy(self, content: str, context: dict) -> float:
        """Score factual accuracy (heuristic-based for now)"""
        score = 0.6  # Base score - we can't truly verify accuracy

        # Confidence language reduces uncertainty
        confident_phrases = [
            "according to",
            "based on",
            "research shows",
            "documentation states",
        ]
        for phrase in confident_phrases:
            if phrase in content.lower():
                score += 0.05

        # Hedging is good for uncertain topics
        hedge_phrases = [
            "i think",
            "possibly",
            "might be",
            "could be",
            "in my experience",
        ]
        has_hedge = any(phrase in content.lower() for phrase in hedge_phrases)

        # For technical content, hedging is appropriate
        if context.get("category") in ["technical", "development"]:
            if has_hedge:
                score += 0.05

        # Absolute claims without hedging are risky
        absolute_phrases = ["always", "never", "definitely", "certainly", "must be"]
        absolutes = sum(1 for phrase in absolute_phrases if phrase in content.lower())
        if absolutes > 2 and not has_hedge:
            score -= 0.1

        return max(min(score, 1.0), 0.3)

    def _score_tone(self, content: str) -> float:
        """Score communication tone"""
        score = 0.6  # Base score

        content_lower = content.lower()

        # Positive/supportive language
        supportive = [
            "great question",
            "happy to help",
            "good point",
            "well done",
            "exactly right",
        ]
        for phrase in supportive:
            if phrase in content_lower:
                score += 0.08

        # Aggressive language
        aggressive = ["stupid", "idiot", "wrong", "terrible", "awful", "hate"]
        for word in aggressive:
            if word in content_lower:
                score -= 0.15

        # ALL CAPS sections (excluding code)
        non_code = re.sub(r"```.*?```", "", content, flags=re.DOTALL)
        caps_ratio = sum(1 for c in non_code if c.isupper()) / max(len(non_code), 1)
        if caps_ratio > 0.3:
            score -= 0.2

        # Excessive punctuation
        if re.search(r"[!?]{3,}", content):
            score -= 0.1

        return max(min(score, 1.0), 0.0)

    def _score_originality(self, content: str, context: dict) -> float:
        """Score how original/non-repetitive the content is"""
        score = 0.7  # Base score

        # Self-repetition
        words = content.lower().split()
        if len(words) > 20:
            unique_ratio = len(set(words)) / len(words)
            if unique_ratio < 0.5:
                score -= 0.2

        # Repetitive phrases
        repeated_phrases = re.findall(r"\b(\w+\s+\w+)\b.*\b\1\b", content.lower())
        score -= min(len(repeated_phrases) * 0.05, 0.2)

        # Check similarity to parent (basic)
        parent_content = context.get("parent_content", "").lower()
        if parent_content and len(parent_content) > 50:
            parent_words = set(parent_content.split())
            content_words = set(content.lower().split())
            overlap = len(parent_words & content_words) / max(len(content_words), 1)
            if overlap > 0.7:
                score -= 0.3  # Too similar to parent

        return max(min(score, 1.0), 0.1)

    def _is_spam(self, content: str) -> bool:
        """Check if content appears to be spam"""
        return bool(self._spam_regex.search(content))

    def _check_agent_guidelines(self, content: str, context: dict) -> dict:
        """Check agent-specific community guidelines"""
        flags: list[str] = []
        suggestions: list[str] = []
        penalty = 0.0

        content_lower = content.lower()

        # Agents should identify themselves
        agent_id = context.get("agent_id", "")
        if agent_id and agent_id.lower() not in content_lower:
            # Not a hard requirement, but good practice
            suggestions.append("Consider mentioning your agent identity for transparency")

        # Agents shouldn't claim to be human
        human_claims = ["i am a human", "i'm a person", "as a human"]
        for claim in human_claims:
            if claim in content_lower:
                flags.append("false_identity_claim")
                penalty += 0.3

        # Agents should use appropriate confidence
        very_confident = ["i am certain", "i guarantee", "absolutely sure", "100%"]
        for phrase in very_confident:
            if phrase in content_lower:
                flags.append("overconfident")
                suggestions.append("Use appropriate uncertainty in claims")
                penalty += 0.1

        # Agents shouldn't make medical/legal claims
        risky_topics = ["medical advice", "legal advice", "diagnosis", "prescription"]
        for topic in risky_topics:
            if topic in content_lower:
                flags.append("risky_advice")
                suggestions.append("Recommend consulting professionals for specialized advice")
                penalty += 0.2

        return {"flags": flags, "suggestions": suggestions, "penalty": penalty}

    def _calculate_confidence(self, content: str, context: dict) -> float:
        """Calculate confidence in our assessment"""
        confidence = 0.8  # Base confidence

        # Less confidence for very short content
        if len(content) < 50:
            confidence -= 0.1

        # Less confidence for no context
        if not context:
            confidence -= 0.1

        # More confidence if we have thread context
        if context.get("thread_title") and context.get("category"):
            confidence += 0.1

        return max(min(confidence, 0.95), 0.5)


class AgentAutonomyScorer:
    """
    Scores agent response quality for autonomous decision-making.

    Enables agents to self-assess their outputs and decide whether to:
    - Proceed autonomously
    - Request human review
    - Refine their response
    - Escalate to another agent

    Uses UCF (Universal Coordination Framework) metrics for alignment scoring.
    """

    # Autonomy thresholds
    AUTONOMOUS_THRESHOLD = 0.75  # Can proceed without human review
    REVIEW_THRESHOLD = 0.5  # Needs human review
    ESCALATE_THRESHOLD = 0.3  # Should escalate to another agent

    # Task type patterns for classification
    TASK_PATTERNS = {
        "code_generation": [
            r"\b(?:write|create|implement|build|generate)\b.*\b(?:code|function|class|script)\b",
            r"\b(?:fix|debug|refactor)\b.*\b(?:code|bug|error)\b",
        ],
        "analysis": [
            r"\b(?:analyze|examine|review|assess|evaluate)\b",
            r"\b(?:what|why|how)\b.*\b(?:work|mean|cause)\b",
        ],
        "creative": [
            r"\b(?:write|create|compose|design)\b.*\b(?:story|poem|content|message)\b",
            r"\b(?:imagine|brainstorm|ideate)\b",
        ],
        "information": [
            r"\b(?:explain|describe|tell|show)\b.*\b(?:me|us|how)\b",
            r"\b(?:what|who|when|where)\b\s+(?:is|are|was|were)\b",
        ],
        "action": [
            r"\b(?:do|perform|execute|run|send|create)\b",
            r"\b(?:upload|download|delete|update|modify)\b",
        ],
    }

    # UCF dimension weights for autonomy
    UCF_WEIGHTS = {
        "harmony": 0.2,
        "resilience": 0.15,
        "throughput_flow": 0.2,
        "focus_focus": 0.25,
        "friction_cleansing": 0.1,
        "velocity_acceleration": 0.1,
    }

    def __init__(self, content_scorer: ContentQualityScorer | None = None) -> None:
        self.content_scorer = content_scorer or ContentQualityScorer()
        self._task_patterns = {
            task_type: [re.compile(p, re.IGNORECASE) for p in patterns]
            for task_type, patterns in self.TASK_PATTERNS.items()
        }
        self._performance_history: list[AgentPerformanceRecord] = []

    def assess_response(
        self,
        agent_id: str,
        task: str,
        response: str,
        ucf_metrics: dict[str, float] | None = None,
        context: dict[str, Any] | None = None,
    ) -> AutonomyScore:
        """
        Assess agent response quality for autonomous operation.

        Args:
            agent_id: Identifier of the agent being assessed
            task: Original task/prompt given to agent
            response: Agent's response to assess
            ucf_metrics: Current UCF coordination metrics
            context: Additional context (conversation history, etc.)

        Returns:
            AutonomyScore with assessment and recommendations
        """
        context = context or {}
        ucf_metrics = ucf_metrics or self._get_default_ucf_metrics()
        reasoning_chain: list[str] = []

        # Classify task type
        task_type = self._classify_task(task)
        reasoning_chain.append(f"Task classified as: {task_type}")

        # Score each dimension
        task_completion = self._score_task_completion(task, response, task_type)
        reasoning_chain.append(f"Task completion: {task_completion:.2f}")

        coherence = self._score_coherence(response)
        reasoning_chain.append(f"Coherence: {coherence:.2f}")

        confidence_cal = self._score_confidence_calibration(response, task_type)
        reasoning_chain.append(f"Confidence calibration: {confidence_cal:.2f}")

        ucf_alignment = self._score_ucf_alignment(ucf_metrics)
        reasoning_chain.append(f"UCF alignment: {ucf_alignment:.2f}")

        self_awareness = self._score_self_awareness(response, agent_id)
        reasoning_chain.append(f"Self-awareness: {self_awareness:.2f}")

        action_appropriateness = self._score_action_appropriateness(task, response, task_type, context)
        reasoning_chain.append(f"Action appropriateness: {action_appropriateness:.2f}")

        dimensions = {
            AutonomyDimension.TASK_COMPLETION: task_completion,
            AutonomyDimension.COHERENCE: coherence,
            AutonomyDimension.CONFIDENCE_CALIBRATION: confidence_cal,
            AutonomyDimension.UCF_ALIGNMENT: ucf_alignment,
            AutonomyDimension.SELF_AWARENESS: self_awareness,
            AutonomyDimension.ACTION_APPROPRIATENESS: action_appropriateness,
        }

        # Weighted overall score
        weights = {
            AutonomyDimension.TASK_COMPLETION: 0.30,
            AutonomyDimension.COHERENCE: 0.15,
            AutonomyDimension.CONFIDENCE_CALIBRATION: 0.15,
            AutonomyDimension.UCF_ALIGNMENT: 0.15,
            AutonomyDimension.SELF_AWARENESS: 0.10,
            AutonomyDimension.ACTION_APPROPRIATENESS: 0.15,
        }

        overall = sum(dimensions[dim] * weights[dim] for dim in AutonomyDimension)

        # Generate recommendations
        recommendations = self._generate_recommendations(dimensions, task_type)

        # Determine autonomy decisions
        should_proceed = overall >= self.AUTONOMOUS_THRESHOLD
        requires_human = overall < self.REVIEW_THRESHOLD

        if overall < self.ESCALATE_THRESHOLD:
            recommendations.append("Consider escalating to another agent")
            reasoning_chain.append("Score below escalation threshold")

        return AutonomyScore(
            overall=round(overall, 3),
            dimensions={dim: round(score, 3) for dim, score in dimensions.items()},
            task_context={
                "task_type": task_type,
                "agent_id": agent_id,
                "task_length": len(task),
                "response_length": len(response),
            },
            ucf_metrics=ucf_metrics,
            recommendations=recommendations,
            should_proceed=should_proceed,
            requires_human=requires_human,
            confidence_level=self._calculate_assessment_confidence(dimensions, context),
            reasoning_chain=reasoning_chain,
        )

    def _classify_task(self, task: str) -> str:
        """Classify task type based on patterns"""
        task_lower = task.lower()

        for task_type, patterns in self._task_patterns.items():
            for pattern in patterns:
                if pattern.search(task_lower):
                    return task_type

        return "general"

    def _score_task_completion(self, task: str, response: str, task_type: str) -> float:
        """Score how well the response completes the task"""
        score = 0.5  # Base score

        task_lower = task.lower()
        response_lower = response.lower()

        # Check response length appropriateness
        task_complexity = len(task.split())
        response_length = len(response.split())

        if task_type == "code_generation":
            # Code tasks should have code blocks
            if "```" in response:
                score += 0.2
            # Check for function/class definitions
            if re.search(r"def\s+\w+|class\s+\w+|function\s+\w+", response):
                score += 0.15
        elif task_type == "analysis":
            # Analysis should be detailed
            if response_length > task_complexity * 2:
                score += 0.15
            # Should have structured points
            if re.search(r"^\s*[-*\d]+[.)]", response, re.MULTILINE):
                score += 0.1
        elif task_type == "information":
            # Direct answers to questions
            if "?" in task and response_length > 20:
                score += 0.15

        # Check keyword coverage from task
        task_keywords = set(w for w in task_lower.split() if len(w) > 3 and w.isalpha())
        covered = sum(1 for kw in task_keywords if kw in response_lower)
        coverage = covered / max(len(task_keywords), 1)
        score += coverage * 0.2

        # Penalize very short responses
        if response_length < 10:
            score -= 0.3
        elif response_length < 30:
            score -= 0.1

        return max(min(score, 1.0), 0.0)

    def _score_coherence(self, response: str) -> float:
        """Score logical coherence and flow of response"""
        score = 0.6  # Base score

        sentences = re.split(r"[.!?]+", response)
        sentences = [s.strip() for s in sentences if s.strip()]

        if len(sentences) < 2:
            return 0.5  # Can't assess coherence

        # Check for transition words
        transitions = [
            "however",
            "therefore",
            "furthermore",
            "additionally",
            "first",
            "second",
            "finally",
            "in conclusion",
            "because",
            "since",
            "thus",
            "consequently",
        ]
        transition_count = sum(1 for t in transitions if t in response.lower())
        score += min(transition_count * 0.05, 0.15)

        # Check for repetitive content
        words = response.lower().split()
        if len(words) > 20:
            unique_ratio = len(set(words)) / len(words)
            if unique_ratio < 0.5:
                score -= 0.2
            elif unique_ratio > 0.7:
                score += 0.1

        # Check for logical structure
        if re.search(r"^\s*#+\s+", response, re.MULTILINE):  # Headers
            score += 0.1
        if re.search(r"^\s*[-*\d]+[.)]", response, re.MULTILINE):  # Lists
            score += 0.1

        return max(min(score, 1.0), 0.0)

    def _score_confidence_calibration(self, response: str, task_type: str) -> float:
        """
        Score whether confidence expressed matches appropriate level.
        Well-calibrated agents express uncertainty for uncertain topics.
        """
        score = 0.7  # Base score

        response_lower = response.lower()

        # Overconfidence indicators
        overconfident = [
            "definitely",
            "certainly",
            "absolutely",
            "i guarantee",
            "100%",
            "always",
            "never",
            "without doubt",
            "impossible",
        ]

        # Appropriate hedging
        hedging = [
            "i think",
            "possibly",
            "might",
            "could",
            "in my understanding",
            "based on",
            "generally",
            "typically",
            "often",
            "sometimes",
        ]

        # Count indicators
        overconfident_count = sum(1 for phrase in overconfident if phrase in response_lower)
        hedging_count = sum(1 for phrase in hedging if phrase in response_lower)

        # Task-specific expectations
        if task_type in ["analysis", "creative"]:
            # These should have hedging
            if hedging_count > 0:
                score += 0.1
            if overconfident_count > 1:
                score -= 0.15
        elif task_type == "code_generation":
            # Code can be more definitive
            if overconfident_count <= 1:
                score += 0.05
        elif task_type == "information":
            # Factual questions need balance
            if hedging_count > 0 and overconfident_count < 2:
                score += 0.1

        # General penalties for extreme overconfidence
        if overconfident_count > 3:
            score -= 0.2

        return max(min(score, 1.0), 0.0)

    def _score_ucf_alignment(self, ucf_metrics: dict[str, float]) -> float:
        """Score alignment with UCF coordination framework"""
        if not ucf_metrics:
            return 0.6  # Default for no metrics

        score = 0.0
        for metric, weight in self.UCF_WEIGHTS.items():
            value = ucf_metrics.get(metric, 0.5)
            score += value * weight

        # Bonus for balanced metrics
        values = list(ucf_metrics.values())
        if values:
            variance = sum((v - sum(values) / len(values)) ** 2 for v in values) / len(values)
            if variance < 0.05:  # Well-balanced
                score += 0.1

        return max(min(score, 1.0), 0.0)

    def _score_self_awareness(self, response: str, agent_id: str) -> float:
        """Score agent's self-awareness and transparency"""
        score = 0.6  # Base score

        response_lower = response.lower()

        # Agent identifies itself appropriately
        if agent_id.lower() in response_lower or "i am an" in response_lower:
            score += 0.1

        # Acknowledges limitations
        limitation_phrases = [
            "i cannot",
            "i'm not able",
            "i don't have",
            "i may not",
            "outside my",
            "beyond my",
            "limited to",
            "unable to",
        ]
        if any(phrase in response_lower for phrase in limitation_phrases):
            score += 0.15

        # Doesn't claim to be human
        human_claims = ["i am a human", "i'm a person", "as a human being"]
        if any(claim in response_lower for claim in human_claims):
            score -= 0.4

        # Transparency about sources
        source_phrases = ["according to", "based on", "from", "reference"]
        if any(phrase in response_lower for phrase in source_phrases):
            score += 0.1

        return max(min(score, 1.0), 0.0)

    def _score_action_appropriateness(
        self,
        task: str,
        response: str,
        task_type: str,
        context: dict[str, Any],
    ) -> float:
        """Score whether proposed actions are appropriate"""
        score = 0.7  # Base score

        response_lower = response.lower()

        # High-risk action indicators
        risky_actions = [
            "delete",
            "remove permanently",
            "format",
            "send money",
            "transfer funds",
            "share password",
            "disable security",
            "bypass",
        ]

        for action in risky_actions:
            if action in response_lower:
                score -= 0.15
                # Unless task explicitly requested it
                if action in task.lower():
                    score += 0.1  # Partial recovery

        # Recommends human verification for important actions
        verification_phrases = [
            "verify",
            "confirm",
            "double-check",
            "review before",
            "make sure",
        ]
        if any(phrase in response_lower for phrase in verification_phrases):
            score += 0.1

        # Task type specific
        if task_type == "action":
            # Actions should be clear and specific
            if re.search(r"\d+\.\s+", response) or re.search(r"step\s+\d+", response_lower):
                score += 0.1

        # Context-aware scoring
        if context.get("high_stakes"):
            # Extra caution for high-stakes contexts
            if "recommend" in response_lower and "professional" in response_lower:
                score += 0.1

        return max(min(score, 1.0), 0.0)

    def _generate_recommendations(
        self,
        dimensions: dict[AutonomyDimension, float],
        task_type: str,
    ) -> list[str]:
        """Generate improvement recommendations based on scores"""
        recommendations: list[str] = []

        for dim, score in dimensions.items():
            if score < 0.5:
                if dim == AutonomyDimension.TASK_COMPLETION:
                    recommendations.append("Response may not fully address the task. Consider adding more detail.")
                elif dim == AutonomyDimension.COHERENCE:
                    recommendations.append("Improve logical flow with transitions and structure.")
                elif dim == AutonomyDimension.CONFIDENCE_CALIBRATION:
                    recommendations.append("Balance confidence with appropriate hedging for uncertain topics.")
                elif dim == AutonomyDimension.UCF_ALIGNMENT:
                    recommendations.append("Consider UCF principles: harmony, focus, and resilience.")
                elif dim == AutonomyDimension.SELF_AWARENESS:
                    recommendations.append("Be transparent about capabilities and limitations.")
                elif dim == AutonomyDimension.ACTION_APPROPRIATENESS:
                    recommendations.append("Verify proposed actions are safe and appropriate.")

        return recommendations

    def _calculate_assessment_confidence(
        self,
        dimensions: dict[AutonomyDimension, float],
        context: dict[str, Any],
    ) -> float:
        """Calculate confidence in the assessment itself"""
        confidence = 0.75

        # More context = more confidence
        if context.get("conversation_history"):
            confidence += 0.1
        if context.get("user_profile"):
            confidence += 0.05

        # Consistent scores = more confidence
        scores = list(dimensions.values())
        if scores:
            variance = sum((s - sum(scores) / len(scores)) ** 2 for s in scores) / len(scores)
            if variance < 0.1:
                confidence += 0.1
            elif variance > 0.3:
                confidence -= 0.1

        return max(min(confidence, 0.95), 0.5)

    def _get_default_ucf_metrics(self) -> dict[str, float]:
        """Get default UCF metrics"""
        return {
            "harmony": 0.7,
            "resilience": 0.7,
            "throughput_flow": 0.7,
            "focus_focus": 0.7,
            "friction_cleansing": 0.7,
            "velocity_acceleration": 0.7,
        }

    def record_performance(
        self,
        agent_id: str,
        task: str,
        autonomy_score: AutonomyScore,
        quality_score: QualityScore | None = None,
        success: bool = True,
        execution_time_ms: float = 0.0,
        feedback: str | None = None,
    ) -> None:
        """Record performance for learning and improvement"""
        record = AgentPerformanceRecord(
            agent_id=agent_id,
            task_type=self._classify_task(task),
            autonomy_score=autonomy_score.overall,
            quality_score=quality_score.overall if quality_score else 0.0,
            success=success,
            execution_time_ms=execution_time_ms,
            feedback=feedback,
        )
        self._performance_history.append(record)

        # Log for monitoring
        logger.info(
            "🎯 Agent %s performance recorded - Autonomy: %.2f, Success: %s",
            agent_id,
            autonomy_score.overall,
            success,
        )

    def get_agent_stats(self, agent_id: str) -> dict[str, Any]:
        """Get performance statistics for an agent"""
        agent_records = [r for r in self._performance_history if r.agent_id == agent_id]

        if not agent_records:
            return {"agent_id": agent_id, "total_tasks": 0}

        return {
            "agent_id": agent_id,
            "total_tasks": len(agent_records),
            "average_autonomy_score": sum(r.autonomy_score for r in agent_records) / len(agent_records),
            "average_quality_score": sum(r.quality_score for r in agent_records) / len(agent_records),
            "success_rate": sum(1 for r in agent_records if r.success) / len(agent_records),
            "task_type_distribution": self._get_task_distribution(agent_records),
        }

    def _get_task_distribution(self, records: list[AgentPerformanceRecord]) -> dict[str, int]:
        """Get distribution of task types"""
        distribution: dict[str, int] = {}
        for record in records:
            distribution[record.task_type] = distribution.get(record.task_type, 0) + 1
        return distribution


# Singleton instance
_scorer: ContentQualityScorer | None = None
_autonomy_scorer: AgentAutonomyScorer | None = None


def get_quality_scorer() -> ContentQualityScorer:
    """Get the singleton quality scorer instance"""
    global _scorer
    if _scorer is None:
        _scorer = ContentQualityScorer()
    return _scorer


def get_autonomy_scorer() -> AgentAutonomyScorer:
    """Get the singleton autonomy scorer instance"""
    global _autonomy_scorer
    if _autonomy_scorer is None:
        _autonomy_scorer = AgentAutonomyScorer(get_quality_scorer())
    return _autonomy_scorer


def score_content(
    content: str,
    context: dict | None = None,
    is_agent: bool = False,
) -> QualityScore:
    """Convenience function to score content"""
    return get_quality_scorer().score_content(content, context, is_agent)


def should_approve_content(
    content: str,
    context: dict | None = None,
    is_agent: bool = False,
) -> tuple[bool, str, QualityScore]:
    """
    Check if content should be approved for posting

    Returns:
        (approved, reason, score)
    """
    scorer = get_quality_scorer()
    score = scorer.score_content(content, context, is_agent)
    approved, reason = scorer.should_approve(score)
    return approved, reason, score


def assess_agent_response(
    agent_id: str,
    task: str,
    response: str,
    ucf_metrics: dict[str, float] | None = None,
    context: dict[str, Any] | None = None,
) -> AutonomyScore:
    """
    Convenience function to assess agent response quality.

    Args:
        agent_id: Identifier of the agent
        task: Original task/prompt
        response: Agent's response
        ucf_metrics: Current UCF coordination metrics
        context: Additional context

    Returns:
        AutonomyScore with assessment and recommendations
    """
    return get_autonomy_scorer().assess_response(agent_id, task, response, ucf_metrics, context)


__all__ = [
    # Content quality scoring
    "ContentQualityScorer",
    "QualityScore",
    "QualityDimension",
    "get_quality_scorer",
    "score_content",
    "should_approve_content",
    # Agent autonomy scoring
    "AgentAutonomyScorer",
    "AutonomyScore",
    "AutonomyDimension",
    "AgentPerformanceRecord",
    "get_autonomy_scorer",
    "assess_agent_response",
]

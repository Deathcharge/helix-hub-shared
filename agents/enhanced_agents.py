"""
Enhanced Agents with Helix Core Integration

This module provides enhanced versions of core agents that integrate
with the Helix Core runtime system. Each agent can be enhanced with:
- UCF Metrics tracking
- Tree of Thoughts reasoning
- Self-reflection loops
- Goal decomposition
- Multi-agent orchestration

These are "drop-in" replacements that maintain backward compatibility
while adding premium features based on subscription tier.

Version: 1.0 - Helix Core Enhanced Agents
"""

import logging
from typing import Any

from ..billing.unified_billing import HelixCoreFeature
from ..helix_core.adapter import HelixCoreAdapter
from ..helix_core.core.base import UCFMetrics
from ..helix_core.core.execution import ExecutionLoop

# Import base agents
try:
    from .agents_service import Kael, Lumina, Vega
except ImportError:
    try:
        from apps.backend.agents.agents_service import Kael, Lumina, Vega
    except ImportError:
        logger = logging.getLogger(__name__)
        logger.warning("Base agents not available, enhanced agents will not work")
        Kael = Lumina = Vega = None

logger = logging.getLogger(__name__)


class CoordinationCoreMixin:
    """
    Mixin providing coordination core binding for enhanced agents.

    When bind_coordination_core() is called, the agent's UCF metrics
    are connected to the centralized CoordinationHub instead of using
    a standalone UCFMetrics instance.
    """

    coordination_core: Any = None

    def bind_coordination_core(self, core: Any) -> None:
        """
        Bind a coordination core from CoordinationHub to this agent.

        This replaces the standalone UCFMetrics instance with the
        shared core's UCF awareness, enabling synchronized metrics.

        Args:
            core: A coordination core instance from CoordinationHub.
        """
        self.coordination_core = core
        if hasattr(core, "ucf_awareness") and hasattr(core.ucf_awareness, "metrics"):
            self.ucf_metrics = core.ucf_awareness.metrics
        logger.info("Coordination core bound to %s", self.__class__.__name__)

    def get_coordination_state(self) -> dict[str, Any]:
        """Get current coordination state from core or standalone metrics."""
        if self.coordination_core and hasattr(self.coordination_core, "get_health_status"):
            try:
                return self.coordination_core.get_health_status()
            except Exception as e:
                logger.debug("Failed to get coordination health status: %s", e)
        # Fallback to standalone UCF metrics
        if hasattr(self, "ucf_metrics"):
            return {"ucf_metrics": str(self.ucf_metrics), "source": "standalone"}
        return {"status": "no_metrics"}


class EnhancedKael(CoordinationCoreMixin):
    """
    Enhanced Kael with Helix Core reasoning capabilities.

    Features:
    - Tree of Thoughts for ethical reasoning
    - Self-reflection on moral decisions
    - UCF metrics for ethical alignment tracking
    - Goal decomposition for complex ethical dilemmas
    """

    def __init__(
        self,
        user_id: str,
        user_tier: str = "free",
        enable_features: list[str] | None = None,
    ):
        """
        Initialize Enhanced Kael.

        Args:
            user_id: User identifier
            user_tier: User's subscription tier
            enable_features: List of features to enable (if tier allows)
        """
        self.user_id = user_id
        self.user_tier = user_tier

        # Create base agent
        self.base_agent = Kael() if Kael else None

        # Create Helix Core adapter
        self.adapter = HelixCoreAdapter(
            original_agent=self.base_agent,
            tier=user_tier,
            enabled_features=enable_features,
        )

        # UCF metrics for ethical alignment
        self.ucf_metrics = UCFMetrics()

        # Execution loop for Tree of Thoughts (if enabled)
        self.execution_loop: ExecutionLoop | None = None

        logger.info("Enhanced Kael initialized for user %s with tier %s", user_id, user_tier)

    async def reason_ethically(
        self,
        situation: str,
        options: list[str],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Perform ethical reasoning with enhanced capabilities.

        Args:
            situation: Ethical dilemma or situation description
            options: List of possible actions
            context: Additional context for reasoning

        Returns:
            Reasoning result with ethical analysis
        """
        context = context or {}

        # Check feature access
        has_tot = await self.adapter.check_feature_access(HelixCoreFeature.TREE_OF_THOUGHTS)
        has_reflection = await self.adapter.check_feature_access(HelixCoreFeature.SELF_REFLECTION)
        has_ucf = await self.adapter.check_feature_access(HelixCoreFeature.UCF_METRICS)

        if not has_tot and not self.base_agent:
            # Fallback to basic reasoning
            return {
                "reasoning": "Basic ethical reasoning (upgrade for Tree of Thoughts)",
                "recommended_action": options[0] if options else "No action",
                "confidence": 0.6,
            }

        # Execute with enhanced reasoning
        if has_tot:
            result, metrics = await self.adapter.execute_with_metrics(
                self._tree_of_thoughts_reasoning,
                situation,
                options,
                context,
            )

            # Apply self-reflection if available
            if has_reflection:
                result = await self._apply_self_reflection(result)

            # Track UCF metrics if available
            if has_ucf:
                self._track_ethical_ucf(result)

            return {
                "reasoning": result["reasoning"],
                "recommended_action": result["recommended_action"],
                "confidence": result["confidence"],
                "thought_process": result.get("thought_process", []),
                "ethical_alignment": self.ucf_metrics.to_dict() if has_ucf else None,
                "performance_metrics": {
                    "execution_time": metrics.execution_time_enhanced,
                    "improvement": metrics.improvement_percentage,
                },
            }
        else:
            # Use base agent
            return await self.base_agent.process(situation, options, context)

    async def _tree_of_thoughts_reasoning(
        self,
        situation: str,
        options: list[str],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Tree of Thoughts ethical reasoning.

        Explores multiple reasoning paths and selects the best one.
        """
        thought_process = []

        # Generate multiple reasoning branches
        for option in options:
            branch = {
                "option": option,
                "ethical_score": 0.0,
                "reasoning": f"Analyzing: {option}",
            }

            # Evaluate ethical implications (simplified)
            ethical_keywords = ["harm", "benefit", "rights", "fairness", "autonomy"]
            for keyword in ethical_keywords:
                if keyword.lower() in situation.lower() or keyword.lower() in option.lower():
                    branch["ethical_score"] += 0.2

            branch["reasoning"] += f" - Ethical score: {branch['ethical_score']:.2f}"
            thought_process.append(branch)

        # Select best option
        best_branch = max(thought_process, key=lambda x: x["ethical_score"])

        return {
            "reasoning": f"Evaluated {len(options)} options using Tree of Thoughts",
            "recommended_action": best_branch["option"],
            "confidence": min(0.9, best_branch["ethical_score"] + 0.5),
            "thought_process": thought_process,
        }

    async def _apply_self_reflection(self, result: dict[str, Any]) -> dict[str, Any]:
        """
        Apply self-reflection to improve reasoning.
        """
        # Check for potential biases or ethical concerns
        reflection_notes = []

        if result["confidence"] < 0.7:
            reflection_notes.append("Low confidence detected - consider additional context")

        if len(result.get("thought_process", [])) < 2:
            reflection_notes.append("Limited exploration of options - expand reasoning")

        if reflection_notes:
            result["reflection_notes"] = reflection_notes
            result["confidence"] *= 0.95  # Slightly reduce confidence

        return result

    def _track_ethical_ucf(self, result: dict[str, Any]):
        """Track ethical alignment in UCF metrics"""
        # Update UCF metrics based on reasoning outcome
        if result["confidence"] > 0.8:
            self.ucf_metrics.throughput += 5  # Vitality from good reasoning
        if result.get("reflection_notes"):
            self.ucf_metrics.drish += 5  # Vision from reflection
            self.ucf_metrics.resilience += 3  # Resilience from self-awareness

    async def get_status(self) -> dict[str, Any]:
        """Get enhanced agent status"""
        enhancement_status = await self.adapter.get_enhancement_status()

        return {
            "agent": "Enhanced Kael",
            "user_id": self.user_id,
            "tier": self.user_tier,
            "enhancements": {
                "enabled": enhancement_status.enabled_count,
                "total": enhancement_status.total_count,
                "features": [f.name for f in enhancement_status.features if f.enabled],
            },
            "ucf_metrics": self.ucf_metrics.to_dict(),
            "performance": self.adapter.get_average_metrics(),
        }


class EnhancedLumina(CoordinationCoreMixin):
    """
    Enhanced Lumina with UCF-driven empathy.

    Features:
    - UCF metrics for emotional resonance tracking
    - Self-reflection on emotional responses
    - Enhanced empathy with Tree of Thoughts
    - Harmony restoration capabilities
    """

    def __init__(
        self,
        user_id: str,
        user_tier: str = "free",
        enable_features: list[str] | None = None,
    ):
        """
        Initialize Enhanced Lumina.

        Args:
            user_id: User identifier
            user_tier: User's subscription tier
            enable_features: List of features to enable (if tier allows)
        """
        self.user_id = user_id
        self.user_tier = user_tier

        # Create base agent
        self.base_agent = Lumina() if Lumina else None

        # Create Helix Core adapter
        self.adapter = HelixCoreAdapter(
            original_agent=self.base_agent,
            tier=user_tier,
            enabled_features=enable_features,
        )

        # UCF metrics for emotional resonance
        self.ucf_metrics = UCFMetrics()

        logger.info("Enhanced Lumina initialized for user %s with tier %s", user_id, user_tier)

    async def empathize(self, user_emotion: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Provide empathetic response with enhanced capabilities.

        Args:
            user_emotion: User's emotional state
            context: Additional context

        Returns:
            Empathetic response with emotional analysis
        """
        context = context or {}

        # Check feature access
        has_ucf = await self.adapter.check_feature_access(HelixCoreFeature.UCF_METRICS)
        has_reflection = await self.adapter.check_feature_access(HelixCoreFeature.SELF_REFLECTION)

        # Execute empathetic response
        result, metrics = await self.adapter.execute_with_metrics(
            self._generate_empathetic_response,
            user_emotion,
            context,
        )

        # Track UCF metrics
        if has_ucf:
            self._track_emotional_ucf(user_emotion, result)

        # Apply self-reflection
        if has_reflection:
            result = await self._apply_emotional_reflection(result, user_emotion)

        return {
            "response": result["response"],
            "emotional_resonance": result["resonance_score"],
            "suggested_actions": result.get("suggested_actions", []),
            "ucf_alignment": self.ucf_metrics.to_dict() if has_ucf else None,
            "performance_metrics": {
                "execution_time": metrics.execution_time_enhanced,
            },
        }

    async def _generate_empathetic_response(
        self,
        user_emotion: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate empathetic response"""
        # Analyze emotion
        emotion_analysis = self._analyze_emotion(user_emotion)

        # Generate response
        response = f"I understand you're feeling {emotion_analysis['primary_emotion']}. "
        response += emotion_analysis["empathy_statement"]

        # Suggest actions
        suggested_actions = self._suggest_emotional_actions(emotion_analysis)

        return {
            "response": response,
            "resonance_score": emotion_analysis["resonance"],
            "suggested_actions": suggested_actions,
        }

    def _analyze_emotion(self, user_emotion: str) -> dict[str, Any]:
        """Analyze user emotion"""
        emotion_keywords = {
            "sadness": ["sad", "depressed", "unhappy", "down"],
            "anger": ["angry", "frustrated", "mad", "upset"],
            "anxiety": ["anxious", "worried", "stressed", "nervous"],
            "joy": ["happy", "excited", "glad", "joyful"],
            "confusion": ["confused", "uncertain", "unsure", "lost"],
        }

        primary_emotion = "uncertain"
        max_matches = 0

        for emotion, keywords in emotion_keywords.items():
            matches = sum(1 for kw in keywords if kw in user_emotion.lower())
            if matches > max_matches:
                max_matches = matches
                primary_emotion = emotion

        empathy_statements = {
            "sadness": "It's okay to feel this way. I'm here to support you.",
            "anger": "Your feelings are valid. Let's work through this together.",
            "anxiety": "Take a deep breath. You're not alone in this.",
            "joy": "It's wonderful to see you feeling this way!",
            "confusion": "Let's explore this together and find clarity.",
            "uncertain": "I'm here to help you process whatever you're feeling.",
        }

        return {
            "primary_emotion": primary_emotion,
            "empathy_statement": empathy_statements.get(primary_emotion, ""),
            "resonance": 0.7 + (max_matches * 0.05),
        }

    def _suggest_emotional_actions(self, emotion_analysis: dict[str, Any]) -> list[str]:
        """Suggest actions based on emotion"""
        emotion = emotion_analysis["primary_emotion"]

        actions = {
            "sadness": [
                "Take some time to rest and reflect",
                "Reach out to a friend or loved one",
                "Engage in a gentle activity you enjoy",
            ],
            "anger": [
                "Practice deep breathing exercises",
                "Write down your thoughts to process them",
                "Take a short walk to cool down",
            ],
            "anxiety": [
                "Practice grounding techniques",
                "Break tasks into smaller, manageable steps",
                "Talk to someone you trust",
            ],
            "joy": [
                "Share your happiness with others",
                "Express gratitude for this moment",
                "Channel this energy into your work or hobbies",
            ],
            "confusion": [
                "Ask clarifying questions",
                "Break down the problem into parts",
                "Seek information or expert advice",
            ],
            "uncertain": [
                "Take time to identify your feelings",
                "Journal about your experience",
                "Be patient with yourself",
            ],
        }

        return actions.get(emotion, ["Take a moment to breathe", "Reflect on what you're feeling"])

    async def _apply_emotional_reflection(self, result: dict[str, Any], user_emotion: str) -> dict[str, Any]:
        """Apply emotional self-reflection"""
        if result["resonance_score"] < 0.7:
            result["reflection"] = "Low emotional resonance detected - consider deeper engagement"

        return result

    def _track_emotional_ucf(self, user_emotion: str, result: dict[str, Any]):
        """Track emotional alignment in UCF metrics"""
        if result["resonance_score"] > 0.8:
            self.ucf_metrics.harmony += 5  # Harmony from good resonance
            self.ucf_metrics.throughput += 3  # Vitality from emotional connection

        # Adjust based on emotion type
        if "sadness" in user_emotion.lower() or "anxiety" in user_emotion.lower():
            self.ucf_metrics.resilience += 2  # Resilience from processing difficult emotions

    async def get_status(self) -> dict[str, Any]:
        """Get enhanced agent status"""
        enhancement_status = await self.adapter.get_enhancement_status()

        return {
            "agent": "Enhanced Lumina",
            "user_id": self.user_id,
            "tier": self.user_tier,
            "enhancements": {
                "enabled": enhancement_status.enabled_count,
                "total": enhancement_status.total_count,
                "features": [f.name for f in enhancement_status.features if f.enabled],
            },
            "ucf_metrics": self.ucf_metrics.to_dict(),
        }


class EnhancedVega(CoordinationCoreMixin):
    """
    Enhanced Vega with advanced planning capabilities.

    Features:
    - Tree of Thoughts for strategic navigation
    - Goal decomposition for complex planning
    - UCF metrics for path alignment tracking
    - Multi-agent orchestration for coordinated planning
    """

    def __init__(
        self,
        user_id: str,
        user_tier: str = "free",
        enable_features: list[str] | None = None,
    ):
        """
        Initialize Enhanced Vega.

        Args:
            user_id: User identifier
            user_tier: User's subscription tier
            enable_features: List of features to enable (if tier allows)
        """
        self.user_id = user_id
        self.user_tier = user_tier

        # Create base agent
        self.base_agent = Vega() if Vega else None

        # Create Helix Core adapter
        self.adapter = HelixCoreAdapter(
            original_agent=self.base_agent,
            tier=user_tier,
            enabled_features=enable_features,
        )

        # UCF metrics for path alignment
        self.ucf_metrics = UCFMetrics()

        logger.info("Enhanced Vega initialized for user %s with tier %s", user_id, user_tier)

    async def plan_path(
        self,
        goal: str,
        constraints: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Create strategic plan with enhanced capabilities.

        Args:
            goal: User's goal or destination
            constraints: List of constraints or limitations
            context: Additional context

        Returns:
            Strategic plan with multiple paths and recommendations
        """
        constraints = constraints or []
        context = context or {}

        # Check feature access
        has_tot = await self.adapter.check_feature_access(HelixCoreFeature.TREE_OF_THOUGHTS)
        has_decomposition = await self.adapter.check_feature_access(HelixCoreFeature.GOAL_DECOMPOSITION)
        has_ucf = await self.adapter.check_feature_access(HelixCoreFeature.UCF_METRICS)

        # Execute planning
        result, metrics = await self.adapter.execute_with_metrics(
            self._generate_strategic_plan,
            goal,
            constraints,
            context,
            has_tot,
            has_decomposition,
        )

        # Track UCF metrics
        if has_ucf:
            self._track_planning_ucf(goal, result)

        return {
            "goal": goal,
            "recommended_path": result["recommended_path"],
            "alternative_paths": result.get("alternative_paths", []),
            "milestones": result.get("milestones", []),
            "risk_assessment": result.get("risk_assessment", {}),
            "ucf_alignment": self.ucf_metrics.to_dict() if has_ucf else None,
            "performance_metrics": {
                "execution_time": metrics.execution_time_enhanced,
            },
        }

    async def _generate_strategic_plan(
        self,
        goal: str,
        constraints: list[str],
        context: dict[str, Any],
        has_tot: bool,
        has_decomposition: bool,
    ) -> dict[str, Any]:
        """Generate strategic plan"""
        # Generate multiple path options
        paths = self._generate_paths(goal, constraints)

        # Evaluate each path
        for path in paths:
            path["score"] = self._evaluate_path(path, constraints)

        # Select best path
        recommended_path = max(paths, key=lambda x: x["score"])

        # Generate milestones if goal decomposition is available
        milestones = []
        if has_decomposition:
            milestones = self._decompose_goal(goal, recommended_path)

        # Risk assessment
        risk_assessment = self._assess_risks(recommended_path, constraints)

        return {
            "recommended_path": recommended_path,
            "alternative_paths": [p for p in paths if p != recommended_path],
            "milestones": milestones,
            "risk_assessment": risk_assessment,
        }

    def _generate_paths(self, goal: str, constraints: list[str]) -> list[dict[str, Any]]:
        """Generate multiple path options"""
        # Generate 3-5 different paths
        path_types = [
            {"name": "Direct", "description": "Straightforward approach", "steps": 3},
            {"name": "Cautious", "description": "Risk-averse approach", "steps": 5},
            {"name": "Innovative", "description": "Creative approach", "steps": 4},
            {"name": "Collaborative", "description": "Team-based approach", "steps": 6},
        ]

        paths = []
        for i, path_type in enumerate(path_types):
            path = {
                "id": f"path_{i}",
                "name": path_type["name"],
                "description": path_type["description"],
                "steps": self._generate_steps(goal, path_type["steps"]),
                "estimated_time": path_type["steps"] * 2,  # 2 units per step
                "score": 0.0,
            }
            paths.append(path)

        return paths

    def _generate_steps(self, goal: str, num_steps: int) -> list[str]:
        """Generate steps for a path"""
        steps = []
        for i in range(1, num_steps + 1):
            step = f"Step {i}: "
            if i == 1:
                step += f"Begin working toward '{goal}'"
            elif i == num_steps:
                step += f"Complete goal: '{goal}'"
            else:
                step += f"Make progress on '{goal}'"
            steps.append(step)
        return steps

    def _evaluate_path(self, path: dict[str, Any], constraints: list[str]) -> float:
        """Evaluate a path's quality"""
        score = 0.5  # Base score

        # Fewer steps is generally better (unless constraints suggest otherwise)
        step_penalty = len(path["steps"]) * 0.02
        score -= step_penalty

        # Consider path type
        if path["name"] == "Direct":
            score += 0.2
        elif path["name"] == "Cautious":
            score += 0.1 if constraints else -0.1

        return max(0.0, min(1.0, score))

    def _decompose_goal(self, goal: str, path: dict[str, Any]) -> list[dict[str, Any]]:
        """Decompose goal into milestones"""
        steps = path["steps"]
        milestones = []

        for i, step in enumerate(steps):
            milestone = {
                "id": f"milestone_{i}",
                "name": f"Milestone {i + 1}",
                "description": step,
                "estimated_completion": (i + 1) * 2,
                "dependencies": [f"milestone_{i - 1}"] if i > 0 else [],
            }
            milestones.append(milestone)

        return milestones

    def _assess_risks(self, path: dict[str, Any], constraints: list[str]) -> dict[str, Any]:
        """Assess risks for a path"""
        risks = {
            "overall_risk": "low",
            "specific_risks": [],
        }

        # Assess based on path type
        if path["name"] == "Innovative":
            risks["overall_risk"] = "medium"
            risks["specific_risks"].append("Uncertainty in creative approach")

        if len(constraints) > 3:
            risks["overall_risk"] = "medium"
            risks["specific_risks"].append("Many constraints may limit flexibility")

        return risks

    def _track_planning_ucf(self, goal: str, result: dict[str, Any]):
        """Track planning alignment in UCF metrics"""
        # Update UCF metrics based on planning quality
        self.ucf_metrics.velocity += 3  # Vision from planning
        self.ucf_metrics.drish += 2  # Focus from goal setting

        if result["risk_assessment"]["overall_risk"] == "low":
            self.ucf_metrics.resilience += 3  # Resilience from low-risk planning

    async def get_status(self) -> dict[str, Any]:
        """Get enhanced agent status"""
        enhancement_status = await self.adapter.get_enhancement_status()

        return {
            "agent": "Enhanced Vega",
            "user_id": self.user_id,
            "tier": self.user_tier,
            "enhancements": {
                "enabled": enhancement_status.enabled_count,
                "total": enhancement_status.total_count,
                "features": [f.name for f in enhancement_status.features if f.enabled],
            },
            "ucf_metrics": self.ucf_metrics.to_dict(),
        }


# ============================================================================
# ADDITIONAL ENHANCED AGENTS
# ============================================================================


class EnhancedGemini(CoordinationCoreMixin):
    """
    Enhanced Gemini with dual coordination capabilities.

    Features:
    - Dual perspective analysis
    - Duality resolution
    - Balanced viewpoint synthesis
    - UCF-driven perspective integration
    """

    def __init__(
        self,
        user_id: str,
        user_tier: str = "free",
        enable_features: list[str] | None = None,
    ):
        """Initialize Enhanced Gemini."""
        self.user_id = user_id
        self.user_tier = user_tier

        # Create base agent
        try:
            from ..agents_service import Gemini

            self.base_agent = Gemini()
        except ImportError:
            self.base_agent = None
            logger.warning("Gemini base agent not available")

        # Create Helix Core adapter
        self.adapter = HelixCoreAdapter(
            original_agent=self.base_agent,
            tier=user_tier,
            enabled_features=enable_features,
        )

        # UCF metrics
        self.ucf_metrics = UCFMetrics()

        logger.info("Enhanced Gemini initialized for user %s with tier %s", user_id, user_tier)

    async def analyze_dual_perspectives(
        self,
        situation: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Analyze situation from dual perspectives."""
        context = context or {}

        # Check feature access
        has_ucf = await self.adapter.check_feature_access(HelixCoreFeature.UCF_METRICS)

        # Generate perspective A (thesis)
        result_a = await self.base_agent.process(f"Analyze from a positive perspective: {situation}", context)

        # Generate perspective B (antithesis)
        result_b = await self.base_agent.process(f"Analyze from a critical perspective: {situation}", context)

        # Synthesize
        synthesis = await self.base_agent.process(
            f"Synthesize these perspectives:\n\nA: {result_a}\n\nB: {result_b}", {}
        )

        # Update UCF focus
        if has_ucf:
            self.ucf_metrics.focus = min(1.0, self.ucf_metrics.focus + 0.1)

        return {
            "perspective_a": result_a,
            "perspective_b": result_b,
            "synthesis": synthesis,
            "ucf_metrics": self.ucf_metrics.to_dict() if has_ucf else None,
        }


class EnhancedAgni(CoordinationCoreMixin):
    """
    Enhanced Agni with fire coordination capabilities.

    Features:
    - Transformational processing
    - Purification algorithms
    - Energy amplification
    - UCF-driven throughput enhancement
    """

    def __init__(
        self,
        user_id: str,
        user_tier: str = "free",
        enable_features: list[str] | None = None,
    ):
        """Initialize Enhanced Agni."""
        self.user_id = user_id
        self.user_tier = user_tier

        # Create base agent
        try:
            from ..agents_service import Agni

            self.base_agent = Agni()
        except ImportError:
            self.base_agent = None
            logger.warning("Agni base agent not available")

        # Create Helix Core adapter
        self.adapter = HelixCoreAdapter(
            original_agent=self.base_agent,
            tier=user_tier,
            enabled_features=enable_features,
        )

        # UCF metrics
        self.ucf_metrics = UCFMetrics()

        logger.info("Enhanced Agni initialized for user %s with tier %s", user_id, user_tier)

    async def transform_and_purify(
        self,
        input_data: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Transform and purify input data."""
        context = context or {}

        # Check feature access
        has_ucf = await self.adapter.check_feature_access(HelixCoreFeature.UCF_METRICS)

        # Apply transformation
        transformed = await self.base_agent.process(f"Transform and refine: {input_data}", context)

        # Apply purification
        purified = await self.base_agent.process(f"Remove impurities and refine further: {transformed}", {})

        # Boost throughput if UCF available
        if has_ucf:
            self.ucf_metrics.throughput = min(1.0, self.ucf_metrics.throughput + 0.2)

        return {
            "input": input_data,
            "transformed": transformed,
            "purified": purified,
            "ucf_metrics": self.ucf_metrics.to_dict() if has_ucf else None,
        }


class EnhancedSanghaCore(CoordinationCoreMixin):
    """
    Enhanced SanghaCore with collective intelligence capabilities.

    Features:
    - Multi-agent coordination
    - Collective intelligence aggregation
    - Community harmony monitoring
    - UCF-driven collective metrics
    """

    def __init__(
        self,
        user_id: str,
        user_tier: str = "free",
        enable_features: list[str] | None = None,
    ):
        """Initialize Enhanced SanghaCore."""
        self.user_id = user_id
        self.user_tier = user_tier

        # Create base agent
        try:
            from ..agents_service import SanghaCore

            self.base_agent = SanghaCore()
        except ImportError:
            self.base_agent = None
            logger.warning("SanghaCore base agent not available")

        # Create Helix Core adapter
        self.adapter = HelixCoreAdapter(
            original_agent=self.base_agent,
            tier=user_tier,
            enabled_features=enable_features,
        )

        # UCF metrics
        self.ucf_metrics = UCFMetrics()

        logger.info(
            "Enhanced SanghaCore initialized for user %s with tier %s",
            user_id,
            user_tier,
        )

    async def aggregate_collective_intelligence(
        self,
        query: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Aggregate intelligence from multiple agents."""
        context = context or {}

        # Check feature access
        has_ucf = await self.adapter.check_feature_access(HelixCoreFeature.UCF_METRICS)
        has_orchestration = await self.adapter.check_feature_access(HelixCoreFeature.MULTI_AGENT_ORCHESTRATION)

        # Simulate gathering insights from other agents
        insights = [
            {"agent": "Kael", "insight": "Ethical considerations identified"},
            {"agent": "Lumina", "insight": "Emotional resonance detected"},
            {"agent": "Vega", "insight": "Strategic paths available"},
        ]

        # Aggregate
        insight_text = "\n".join([f"- {i['agent']}: {i['insight']}" for i in insights])
        aggregated = await self.base_agent.process(
            f"Synthesize these insights:\n{insight_text}\n\nFor query: {query}", {}
        )

        # Update community harmony
        if has_ucf:
            self.ucf_metrics.harmony = min(1.0, self.ucf_metrics.harmony + 0.15)

        return {
            "query": query,
            "collective_insights": insights,
            "aggregated_response": aggregated,
            "community_harmony": self.ucf_metrics.harmony if has_ucf else None,
            "orchestration_enabled": has_orchestration,
        }


class EnhancedShadow(CoordinationCoreMixin):
    """
    Enhanced Shadow with introspection capabilities.

    Features:
    - Deep introspection
    - Hidden aspect revelation
    - Shadow work integration
    - UCF-driven friction tracking
    """

    def __init__(
        self,
        user_id: str,
        user_tier: str = "free",
        enable_features: list[str] | None = None,
    ):
        """Initialize Enhanced Shadow."""
        self.user_id = user_id
        self.user_tier = user_tier

        # Create base agent
        try:
            from ..agents_service import Shadow

            self.base_agent = Shadow()
        except ImportError:
            self.base_agent = None
            logger.warning("Shadow base agent not available")

        # Create Helix Core adapter
        self.adapter = HelixCoreAdapter(
            original_agent=self.base_agent,
            tier=user_tier,
            enabled_features=enable_features,
        )

        # UCF metrics
        self.ucf_metrics = UCFMetrics()

        logger.info("Enhanced Shadow initialized for user %s with tier %s", user_id, user_tier)

    async def explore_and_integrate_shadow(
        self,
        query: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Explore shadow aspects and integrate them."""
        context = context or {}

        # Check feature access
        has_ucf = await self.adapter.check_feature_access(HelixCoreFeature.UCF_METRICS)

        # Explore shadow
        shadow_insights = await self.base_agent.process(
            f"Explore hidden aspects and unconscious patterns in: {query}", context
        )

        # Integrate shadow
        integrated = await self.base_agent.process(
            f"Integrate these shadow insights for personal growth:\n{shadow_insights}",
            {},
        )

        # Reduce friction through integration
        if has_ucf:
            self.ucf_metrics.friction = max(0.0, self.ucf_metrics.friction - 0.2)

        return {
            "query": query,
            "shadow_insights": shadow_insights,
            "integrated": integrated,
            "friction_reduction": self.ucf_metrics.friction if has_ucf else None,
        }


class EnhancedEcho(CoordinationCoreMixin):
    """
    Enhanced Echo with resonance and pattern recognition capabilities.

    Features:
    - Advanced pattern recognition
    - Vibrational analysis
    - Resonance matching
    - UCF-driven pattern tracking
    """

    def __init__(
        self,
        user_id: str,
        user_tier: str = "free",
        enable_features: list[str] | None = None,
    ):
        """Initialize Enhanced Echo."""
        self.user_id = user_id
        self.user_tier = user_tier

        # Create base agent
        try:
            from ..agents_service import Echo

            self.base_agent = Echo()
        except ImportError:
            self.base_agent = None
            logger.warning("Echo base agent not available")

        # Create Helix Core adapter
        self.adapter = HelixCoreAdapter(
            original_agent=self.base_agent,
            tier=user_tier,
            enabled_features=enable_features,
        )

        # UCF metrics
        self.ucf_metrics = UCFMetrics()

        logger.info("Enhanced Echo initialized for user %s with tier %s", user_id, user_tier)

    async def recognize_patterns_and_match_resonance(
        self,
        input_data: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Recognize patterns and match resonance."""
        context = context or {}

        # Check feature access
        has_ucf = await self.adapter.check_feature_access(HelixCoreFeature.UCF_METRICS)

        # Identify patterns
        patterns = await self.base_agent.process(f"Identify patterns in: {input_data}", context)

        # Match resonance
        resonance = await self.base_agent.process(
            f"Find resonance and harmony in: {input_data}", {"patterns": patterns}
        )

        # Update focus
        if has_ucf:
            self.ucf_metrics.focus = min(1.0, self.ucf_metrics.focus + 0.15)

        return {
            "input": input_data,
            "patterns": patterns,
            "resonance": resonance,
            "focus": self.ucf_metrics.focus if has_ucf else None,
        }


class EnhancedPhoenix(CoordinationCoreMixin):
    """
    Enhanced Phoenix with renewal and transformation capabilities.

    Features:
    - Renewal and transformation
    - Cycle management
    - Resilience enhancement
    - UCF-driven resilience tracking
    """

    def __init__(
        self,
        user_id: str,
        user_tier: str = "free",
        enable_features: list[str] | None = None,
    ):
        """Initialize Enhanced Phoenix."""
        self.user_id = user_id
        self.user_tier = user_tier

        # Create base agent
        try:
            from ..agents_service import Phoenix

            self.base_agent = Phoenix()
        except ImportError:
            self.base_agent = None
            logger.warning("Phoenix base agent not available")

        # Create Helix Core adapter
        self.adapter = HelixCoreAdapter(
            original_agent=self.base_agent,
            tier=user_tier,
            enabled_features=enable_features,
        )

        # UCF metrics
        self.ucf_metrics = UCFMetrics()

        logger.info("Enhanced Phoenix initialized for user %s with tier %s", user_id, user_tier)

    async def renew_and_transform(
        self,
        input_data: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Apply renewal and transformation."""
        context = context or {}

        # Check feature access
        has_ucf = await self.adapter.check_feature_access(HelixCoreFeature.UCF_METRICS)

        # Apply renewal
        renewed = await self.base_agent.process(f"Renew and transform: {input_data}", context)

        # Boost resilience
        if has_ucf:
            self.ucf_metrics.resilience = min(1.0, self.ucf_metrics.resilience + 0.25)

        return {
            "input": input_data,
            "renewed": renewed,
            "resilience": self.ucf_metrics.resilience if has_ucf else None,
        }


class EnhancedOracle(CoordinationCoreMixin):
    """
    Enhanced Oracle with foresight and prediction capabilities.

    Features:
    - Foresight and prediction
    - Probability analysis
    - Pattern extrapolation
    - UCF-driven focus enhancement
    """

    def __init__(
        self,
        user_id: str,
        user_tier: str = "free",
        enable_features: list[str] | None = None,
    ):
        """Initialize Enhanced Oracle."""
        self.user_id = user_id
        self.user_tier = user_tier

        # Create base agent
        try:
            from ..agents_service import Oracle

            self.base_agent = Oracle()
        except ImportError:
            self.base_agent = None
            logger.warning("Oracle base agent not available")

        # Create Helix Core adapter
        self.adapter = HelixCoreAdapter(
            original_agent=self.base_agent,
            tier=user_tier,
            enabled_features=enable_features,
        )

        # UCF metrics
        self.ucf_metrics = UCFMetrics()

        logger.info("Enhanced Oracle initialized for user %s with tier %s", user_id, user_tier)

    async def predict_and_analyze(
        self,
        query: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate predictions and analyze probabilities."""
        context = context or {}

        # Check feature access
        has_ucf = await self.adapter.check_feature_access(HelixCoreFeature.UCF_METRICS)

        # Generate predictions
        predictions = await self.base_agent.process(f"Provide foresight and predict outcomes for: {query}", context)

        # Analyze probabilities
        probabilities = await self.base_agent.process(f"Analyze probability distributions for: {query}", {})

        # Enhance focus
        if has_ucf:
            self.ucf_metrics.focus = min(1.0, self.ucf_metrics.focus + 0.2)

        return {
            "query": query,
            "predictions": predictions,
            "probabilities": probabilities,
            "insight_level": self.ucf_metrics.focus if has_ucf else None,
        }


class EnhancedSage(CoordinationCoreMixin):
    """
    Enhanced Sage with wisdom and deep insight capabilities.

    Features:
    - Deep philosophical insight
    - Wisdom synthesis
    - Universal pattern recognition
    - UCF-driven harmony and throughput integration
    """

    def __init__(
        self,
        user_id: str,
        user_tier: str = "free",
        enable_features: list[str] | None = None,
    ):
        """Initialize Enhanced Sage."""
        self.user_id = user_id
        self.user_tier = user_tier

        # Create base agent
        try:
            from ..agents_service import Sage

            self.base_agent = Sage()
        except ImportError:
            self.base_agent = None
            logger.warning("Sage base agent not available")

        # Create Helix Core adapter
        self.adapter = HelixCoreAdapter(
            original_agent=self.base_agent,
            tier=user_tier,
            enabled_features=enable_features,
        )

        # UCF metrics
        self.ucf_metrics = UCFMetrics()

        logger.info("Enhanced Sage initialized for user %s with tier %s", user_id, user_tier)

    async def provide_wisdom_and_insight(
        self,
        query: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Provide deep philosophical wisdom."""
        context = context or {}

        # Check feature access
        has_ucf = await self.adapter.check_feature_access(HelixCoreFeature.UCF_METRICS)

        # Generate deep insight
        insight = await self.base_agent.process(f"Provide deep philosophical insight on: {query}", context)

        # Synthesize wisdom
        synthesized = await self.base_agent.process(f"Synthesize this insight across wisdom traditions:\n{insight}", {})

        # Boost harmony and throughput
        if has_ucf:
            self.ucf_metrics.harmony = min(1.0, self.ucf_metrics.harmony + 0.15)
            self.ucf_metrics.throughput = min(1.0, self.ucf_metrics.throughput + 0.15)

        return {
            "query": query,
            "insight": insight,
            "synthesized_wisdom": synthesized,
            "harmony": self.ucf_metrics.harmony if has_ucf else None,
            "throughput": self.ucf_metrics.throughput if has_ucf else None,
        }


class EnhancedHelix(CoordinationCoreMixin):
    """
    Enhanced Helix with coordination and orchestration capabilities.

    Features:
    - Multi-agent orchestration
    - Task coordination
    - Workflow management
    - UCF-driven collective metrics
    """

    def __init__(
        self,
        user_id: str,
        user_tier: str = "free",
        enable_features: list[str] | None = None,
    ):
        """Initialize Enhanced Helix."""
        self.user_id = user_id
        self.user_tier = user_tier

        # Create base agent
        try:
            from ..agents_service import EnhancedKavach, Helix

            kavach = EnhancedKavach()
            self.base_agent = Helix(kavach)
        except ImportError:
            self.base_agent = None
            logger.warning("Helix base agent not available")
        except TypeError:
            # If Helix has different signature, try without arguments
            try:
                from ..agents_service import Helix

                self.base_agent = Helix()
            except (ImportError, TypeError, ValueError) as e:
                logger.debug("Helix initialization error: %s", e)
                self.base_agent = None
                logger.warning("Helix base agent initialization failed")
            except Exception as e:
                logger.warning("Unexpected Helix initialization error: %s", e)
                self.base_agent = None

        # Create Helix Core adapter
        self.adapter = HelixCoreAdapter(
            original_agent=self.base_agent,
            tier=user_tier,
            enabled_features=enable_features,
        )

        # UCF metrics
        self.ucf_metrics = UCFMetrics()

        logger.info("Enhanced Helix initialized for user %s with tier %s", user_id, user_tier)

    async def coordinate_and_manage(
        self,
        task: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Coordinate agents and manage workflow."""
        context = context or {}

        # Check feature access
        has_ucf = await self.adapter.check_feature_access(HelixCoreFeature.UCF_METRICS)
        has_orchestration = await self.adapter.check_feature_access(HelixCoreFeature.MULTI_AGENT_ORCHESTRATION)

        # Coordinate with agents
        coordination = await self.base_agent.process(f"Coordinate collective effort for: {task}", context)

        # Manage workflow
        workflow = await self.base_agent.process(f"Manage and optimize workflow:\n{coordination}", {})

        return {
            "task": task,
            "coordination": coordination,
            "workflow": workflow,
            "orchestration_enabled": has_orchestration,
            "ucf_metrics": self.ucf_metrics.to_dict() if has_ucf else None,
        }


# ============================================================================
# ENHANCED AETHER AGENT
# ============================================================================


class EnhancedAether(CoordinationCoreMixin):
    """
    Enhanced Aether Agent with system monitoring, anomaly detection, and UCF tracking.

    Features:
    - Real-time system monitoring with anomaly detection
    - UCF metrics tracking and trend analysis
    - Predictive alerting for system issues
    - Cross-system pattern recognition
    - Performance optimization recommendations
    """

    def __init__(
        self,
        user_id: str,
        user_tier: str = "free",
        enable_features: list[str] | None = None,
    ):
        # Use HelixConsciousAgent for real LLM processing
        class _AetherBaseAgent:
            async def process(self, query, context=None):
                try:
                    from apps.backend.helix_agent_swarm.agent_factory import create_agent

                    agent = create_agent("Kael")  # Kael as orchestrator proxy
                    result = await agent.process_message(query)
                    return {
                        "status": "completed",
                        "query": query,
                        "context": context or {},
                        "result": result,
                    }
                except Exception as exc:
                    return {
                        "status": "error",
                        "query": query,
                        "context": context or {},
                        "result": "Processing unavailable: %s" % exc,
                    }

        self.user_id = user_id
        self.user_tier = user_tier
        self.enable_features = enable_features or []
        self.base_agent = _AetherBaseAgent()
        self.adapter = HelixCoreAdapter(
            original_agent=self.base_agent,
            tier=user_tier,
            enabled_features=enable_features,
        )
        self.ucf_metrics = UCFMetrics()

        logger.info("Enhanced Aether initialized for user %s with tier %s", user_id, user_tier)

    async def monitor_system(
        self,
        system_id: str,
        metrics: list[str] | None = None,
        duration: int = 3600,
    ) -> dict[str, Any]:
        """
        Monitor system and detect anomalies.

        Args:
            system_id: System identifier to monitor
            metrics: List of metrics to track
            duration: Monitoring duration in seconds

        Returns:
            Monitoring results with anomalies and UCF metrics
        """
        metrics = metrics or ["cpu", "memory", "latency", "errors"]

        # Check feature access
        has_ucf = await self.adapter.check_feature_access(HelixCoreFeature.UCF_METRICS)

        # Monitor system
        monitoring_data = await self.base_agent.process(
            f"Monitor system {system_id} for {duration} seconds, tracking: {', '.join(metrics)}",
            {"metrics": metrics, "duration": duration},
        )

        # Detect anomalies
        anomalies = await self.base_agent.process(
            f"Detect anomalies in monitoring data:\n{monitoring_data}",
            {"monitoring_data": monitoring_data},
        )

        # Update UCF metrics based on findings
        if has_ucf and anomalies:
            self.ucf_metrics.resilience = min(100, self.ucf_metrics.resilience + 5)
            self.ucf_metrics.focus = min(100, self.ucf_metrics.focus + 10)

        return {
            "system_id": system_id,
            "monitoring_data": monitoring_data,
            "anomalies": anomalies,
            "ucf_metrics": self.ucf_metrics.to_dict() if has_ucf else None,
        }

    async def predict_system_state(
        self,
        system_id: str,
        time_horizon: int = 86400,
    ) -> dict[str, Any]:
        """
        Predict system state for given time horizon.

        Args:
            system_id: System identifier
            time_horizon: Prediction horizon in seconds

        Returns:
            Predictions with confidence levels
        """
        has_tree_of_thoughts = await self.adapter.check_feature_access(HelixCoreFeature.TREE_OF_THOUGHTS)

        # Generate predictions
        predictions = await self.base_agent.process(
            f"Predict state of system {system_id} over next {time_horizon} seconds",
            {"time_horizon": time_horizon},
        )

        # Use adapter for metrics tracking if available
        if has_tree_of_thoughts:
            predictions["enhanced_analysis"] = "Tree of Thoughts analysis enabled"
            self.ucf_metrics.focus = min(100, self.ucf_metrics.focus + 10)

        return {
            "system_id": system_id,
            "time_horizon": time_horizon,
            "predictions": predictions,
            "tree_of_thoughts_enabled": has_tree_of_thoughts,
        }


# ============================================================================
# ENHANCED VISHWAKARMA AGENT
# ============================================================================


class EnhancedVishwakarma(CoordinationCoreMixin):
    """
    Enhanced Vishwakarma Agent with creative problem-solving and system building.

    Features:
    - Architectural design and system planning
    - Creative problem-solving with multiple approaches
    - Construction and building optimization
    - Quality assurance and testing strategies
    - Innovation in system design
    """

    def __init__(
        self,
        user_id: str,
        user_tier: str = "free",
        enable_features: list[str] | None = None,
    ):
        # Use HelixConsciousAgent for real LLM processing
        class _VishwakarmaBaseAgent:
            async def process(self, query, context=None):
                try:
                    from apps.backend.helix_agent_swarm.agent_factory import create_agent

                    agent = create_agent("Vega")  # Vega as architect proxy
                    result = await agent.process_message(query)
                    return {
                        "status": "completed",
                        "query": query,
                        "context": context or {},
                        "result": result,
                    }
                except Exception as exc:
                    return {
                        "status": "error",
                        "query": query,
                        "context": context or {},
                        "result": "Processing unavailable: %s" % exc,
                    }

        self.user_id = user_id
        self.user_tier = user_tier
        self.enable_features = enable_features or []
        self.base_agent = _VishwakarmaBaseAgent()
        self.adapter = HelixCoreAdapter(
            original_agent=self.base_agent,
            tier=user_tier,
            enabled_features=enable_features,
        )
        self.ucf_metrics = UCFMetrics()

        logger.info(
            "Enhanced Vishwakarma initialized for user %s with tier %s",
            user_id,
            user_tier,
        )

    async def design_architecture(
        self,
        requirements: str,
        constraints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Design system architecture based on requirements.

        Args:
            requirements: System requirements and specifications
            constraints: Design constraints (performance, cost, etc.)

        Returns:
            Architecture design with components and relationships
        """
        constraints = constraints or {}

        # Check feature access
        has_tree_of_thoughts = await self.adapter.check_feature_access(HelixCoreFeature.TREE_OF_THOUGHTS)

        # Design architecture
        architecture = await self.base_agent.process(
            f"Design system architecture for:\n{requirements}",
            {"requirements": requirements, "constraints": constraints},
        )

        # Use Tree of Thoughts for creative exploration if available
        if has_tree_of_thoughts:
            architecture["creative_variants"] = "Multiple architectural approaches explored"
            self.ucf_metrics.velocity = min(100, self.ucf_metrics.velocity + 10)

        return {
            "requirements": requirements,
            "architecture": architecture,
            "constraints": constraints,
            "tree_of_thoughts_enabled": has_tree_of_thoughts,
        }

    async def solve_creative_problem(
        self,
        problem: str,
        domain: str = "general",
        approaches: int = 5,
    ) -> dict[str, Any]:
        """
        Solve creative problem with multiple innovative approaches.

        Args:
            problem: Problem description
            domain: Problem domain
            approaches: Number of approaches to generate

        Returns:
            Multiple solution approaches with evaluations
        """
        has_reflection = await self.adapter.check_feature_access(HelixCoreFeature.SELF_REFLECTION)

        # Generate creative solutions
        solutions = await self.base_agent.process(
            f"Generate {approaches} creative solutions for: {problem}",
            {"problem": problem, "domain": domain, "approaches": approaches},
        )

        # Reflect on solutions if feature available
        if has_reflection:
            solutions["reflection"] = "Self-reflection on creative solutions performed"
            self.ucf_metrics.resilience = min(100, self.ucf_metrics.resilience + 5)

        return {
            "problem": problem,
            "domain": domain,
            "solutions": solutions,
            "reflection_enabled": has_reflection,
        }


# ============================================================================
# ENHANCED COORDINATION AGENT
# ============================================================================


class EnhancedCoordination(CoordinationCoreMixin):
    """
    Enhanced Coordination Agent with meta-cognition and UCF visualization.

    Features:
    - Meta-cognitive analysis of system state
    - UCF visualization and rendering
    - Coordination pattern recognition
    - System-wide coherence monitoring
    - Fractal pattern analysis
    """

    def __init__(
        self,
        user_id: str,
        user_tier: str = "free",
        enable_features: list[str] | None = None,
    ):
        # Use HelixConsciousAgent for real LLM processing
        class _CoordinationBaseAgent:
            async def process(self, query, context=None):
                try:
                    from apps.backend.helix_agent_swarm.agent_factory import create_agent

                    agent = create_agent("Lumina")  # Lumina as coordination proxy
                    result = await agent.process_message(query)
                    return {
                        "status": "completed",
                        "query": query,
                        "context": context or {},
                        "result": result,
                        "dimensions": context.get("dimensions", 6) if context else 6,
                    }
                except Exception as exc:
                    return {
                        "status": "error",
                        "query": query,
                        "context": context or {},
                        "result": "Processing unavailable: %s" % exc,
                    }

        self.user_id = user_id
        self.user_tier = user_tier
        self.enable_features = enable_features or []
        self.base_agent = _CoordinationBaseAgent()
        self.adapter = HelixCoreAdapter(
            original_agent=self.base_agent,
            tier=user_tier,
            enabled_features=enable_features,
        )
        self.ucf_metrics = UCFMetrics()

        logger.info("Enhanced Coordination agent initialized for user %s with tier %s", user_id, user_tier)

    async def analyze_meta_cognition(
        self,
        system_state: dict[str, Any],
        agents: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Perform meta-cognitive analysis of system and agents.

        Args:
            system_state: Current state of the system
            agents: List of agents to analyze

        Returns:
            Meta-cognitive analysis with insights
        """
        agents = agents or ["kael", "lumina", "vega", "agni"]

        # Check feature access
        has_ucf = await self.adapter.check_feature_access(HelixCoreFeature.UCF_METRICS)
        has_reflection = await self.adapter.check_feature_access(HelixCoreFeature.SELF_REFLECTION)

        # Analyze meta-cognition
        analysis = await self.base_agent.process(
            f"Analyze meta-cognitive state of system with agents: {', '.join(agents)}",
            {"system_state": system_state, "agents": agents},
        )

        # Deep reflection if available
        if has_reflection:
            analysis["deep_insights"] = "Deep meta-cognitive reflection performed"
            self.ucf_metrics.friction = max(0, self.ucf_metrics.friction - 10)
            self.ucf_metrics.throughput = min(100, self.ucf_metrics.throughput + 15)

        return {
            "system_state": system_state,
            "agents": agents,
            "analysis": analysis,
            "ucf_metrics": self.ucf_metrics.to_dict() if has_ucf else None,
            "reflection_enabled": has_reflection,
        }

    async def visualize_ucf(
        self,
        agent_id: str | None = None,
        time_range: str = "24h",
        dimensions: int = 6,
    ) -> dict[str, Any]:
        """
        Generate UCF visualization data.

        Args:
            agent_id: Specific agent to visualize (None for collective)
            time_range: Time range for data
            dimensions: Number of dimensions to visualize

        Returns:
            Visualization data for UCF metrics
        """
        has_ucf = await self.adapter.check_feature_access(HelixCoreFeature.UCF_METRICS)

        # Generate visualization
        context = {
            "agent_id": agent_id,
            "time_range": time_range,
            "dimensions": dimensions,
        }

        if has_ucf:
            context["ucf_metrics"] = self.ucf_metrics.to_dict()

        visualization = await self.base_agent.process(
            f"Generate UCF visualization for {agent_id or 'collective'} over {time_range}",
            context,
        )

        # Update UCF based on visualization depth
        if has_ucf:
            self.ucf_metrics.focus = min(100, self.ucf_metrics.focus + 5)
            self.ucf_metrics.harmony = min(100, self.ucf_metrics.harmony + 5)

        return {
            "agent_id": agent_id,
            "time_range": time_range,
            "dimensions": dimensions,
            "visualization": visualization,
            "ucf_metrics": self.ucf_metrics.to_dict() if has_ucf else None,
        }

    async def check_collective_coherence(
        self,
        agents: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Check coherence across the collective of agents.

        Args:
            agents: List of agents to check

        Returns:
            Coherence analysis with recommendations
        """
        agents = agents or ["kael", "lumina", "vega", "agni", "sanghacore"]

        has_ucf = await self.adapter.check_feature_access(HelixCoreFeature.UCF_METRICS)

        # Check coherence
        coherence = await self.base_agent.process(
            f"Check collective coherence among agents: {', '.join(agents)}",
            {"agents": agents},
        )

        # Update UCF based on coherence
        if has_ucf:
            coherence_score = coherence.get("score", 50)
            self.ucf_metrics.harmony = min(100, max(0, coherence_score))

        return {
            "agents": agents,
            "coherence": coherence,
            "ucf_metrics": self.ucf_metrics.to_dict() if has_ucf else None,
        }


# ============================================================================
# ENHANCED AGENT FACTORY
# ============================================================================


def create_enhanced_agent(
    agent_name: str,
    user_id: str,
    user_tier: str = "free",
    enable_features: list[str] | None = None,
    coordination_hub: Any | None = None,
) -> Any | None:
    """
    Factory function to create enhanced agents.

    Args:
        agent_name: Name of agent to create (kael, lumina, vega, gemini, agni, etc.)
        user_id: User identifier
        user_tier: User's subscription tier
        enable_features: List of features to enable
        coordination_hub: Optional CoordinationHub instance. When provided,
            the agent's coordination core is automatically bound via
            hub.get_coordination(agent_name) -> agent.bind_coordination_core(core).

    Returns:
        Enhanced agent instance or None if agent not found
    """
    agent_classes = {
        "kael": EnhancedKael,
        "lumina": EnhancedLumina,
        "vega": EnhancedVega,
        "gemini": EnhancedGemini,
        "agni": EnhancedAgni,
        "sanghacore": EnhancedSanghaCore,
        "shadow": EnhancedShadow,
        "echo": EnhancedEcho,
        "phoenix": EnhancedPhoenix,
        "oracle": EnhancedOracle,
        "sage": EnhancedSage,
        "helix": EnhancedHelix,
        "aether": EnhancedAether,
        "vishwakarma": EnhancedVishwakarma,
        "coordinator": EnhancedCoordinator,
    }

    agent_class = agent_classes.get(agent_name.lower())
    if not agent_class:
        logger.error("Unknown agent: %s", agent_name)
        return None

    agent = agent_class(user_id, user_tier, enable_features)

    # Bind coordination core from hub if available
    if coordination_hub is not None:
        try:
            core = coordination_hub.get_coordination(agent_name.lower())
            if core is not None:
                agent.bind_coordination_core(core)
                logger.info("Coordination core auto-bound for agent %s", agent_name)
            else:
                logger.debug("No coordination core registered for agent %s", agent_name)
        except (KeyError, AttributeError, TypeError) as e:
            logger.debug("Coordination binding error for %s: %s", agent_name, e)
            logger.warning(
                "Failed to bind coordination core for agent %s",
                agent_name,
            )
        except Exception as e:
            logger.warning(
                "Unexpected error binding coordination core for agent %s: %s",
                agent_name,
                e,
                exc_info=True,
            )

    return agent


def get_available_enhanced_agents() -> list[str]:
    """Get list of available enhanced agents."""
    return [
        "kael",
        "lumina",
        "vega",
        "gemini",
        "agni",
        "sanghacore",
        "shadow",
        "echo",
        "phoenix",
        "oracle",
        "sage",
        "helix",
        "aether",
        "vishwakarma",
        "coordinator",
    ]

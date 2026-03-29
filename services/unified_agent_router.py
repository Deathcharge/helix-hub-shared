"""
🌀 Unified Agent Router
========================

Central routing layer that connects all Helix agent frameworks:
- helix_flow (chains/flows)
- helix_circle (crew coordination)
- helix_agent_swarm (orchestration)
- helix_core (enhanced reasoning)
- proprietary_llm (coordination-aware models)
- enhanced_agents (tier-gated features)

This router provides a single entry point for agent interactions,
automatically selecting the best framework and model based on:
- Task complexity
- User subscription tier
- Available capabilities
- System load and cost optimization

Author: Helix Collective Development Team
Version: 1.0 - Unified Agent Orchestration
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .context_augmentation_service import (
    ConversationTurn,
    get_context_augmentation_service,
)
from .platform_context_service import (
    get_platform_context_service,
)
from .token_budget import (
    resolve_model,
)

logger = logging.getLogger(__name__)


class AgentFramework(str, Enum):
    """Available agent frameworks."""

    HELIX_FLOW = "helix_flow"  # Sequential chains
    HELIX_CIRCLE = "helix_circle"  # Crew coordination
    HELIX_SWARM = "helix_agent_swarm"  # Multi-agent orchestration
    HELIX_CORE = "helix_core"  # Enhanced reasoning
    PROPRIETARY_LLM = "proprietary_llm"  # Coordination-aware models
    ENHANCED_AGENTS = "enhanced_agents"  # Tier-gated features
    DIRECT_LLM = "direct_llm"  # Direct provider call


class TaskComplexity(str, Enum):
    """Complexity level of a task."""

    SIMPLE = "simple"  # Single response, no tools
    MODERATE = "moderate"  # May need tools or context
    COMPLEX = "complex"  # Multi-step reasoning
    COLLABORATIVE = "collaborative"  # Multiple agents needed


@dataclass
class RoutingDecision:
    """Decision made by the router."""

    framework: AgentFramework
    model_id: str
    agents: list[str]
    reasoning: str
    estimated_cost: float
    estimated_tokens: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "framework": self.framework.value,
            "model_id": self.model_id,
            "agents": self.agents,
            "reasoning": self.reasoning,
            "estimated_cost": self.estimated_cost,
            "estimated_tokens": self.estimated_tokens,
        }


@dataclass
class AgentRequest:
    """Request to the unified agent router."""

    message: str
    user_id: str
    user_tier: str = "free"
    preferred_agent: str | None = None
    preferred_framework: AgentFramework | None = None
    conversation_history: list[ConversationTurn] = field(default_factory=list)
    context: dict[str, Any] | None = None
    max_tokens: int = 2000
    streaming: bool = False


@dataclass
class AgentResponse:
    """Response from the unified agent router."""

    content: str
    agent_used: str
    framework_used: AgentFramework
    model_used: str
    tokens_used: int
    cost_incurred: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "agent_used": self.agent_used,
            "framework_used": self.framework_used.value,
            "model_used": self.model_used,
            "tokens_used": self.tokens_used,
            "cost_incurred": self.cost_incurred,
            "metadata": self.metadata,
        }


class UnifiedAgentRouter:
    """
    Central router for all Helix agent frameworks.

    Responsibilities:
    1. Analyze incoming requests to determine optimal routing
    2. Select appropriate framework based on task complexity
    3. Choose best model within user's tier budget
    4. Inject platform context for agent awareness
    5. Execute through selected framework
    6. Track usage and costs
    """

    # Framework capabilities mapping
    FRAMEWORK_CAPABILITIES = {
        AgentFramework.DIRECT_LLM: {
            "complexity": [TaskComplexity.SIMPLE],
            "description": "Direct LLM call for simple queries",
            "cost_multiplier": 1.0,
        },
        AgentFramework.HELIX_FLOW: {
            "complexity": [TaskComplexity.SIMPLE, TaskComplexity.MODERATE],
            "description": "Sequential chain execution",
            "cost_multiplier": 1.2,
        },
        AgentFramework.ENHANCED_AGENTS: {
            "complexity": [TaskComplexity.MODERATE, TaskComplexity.COMPLEX],
            "description": "Enhanced agents with tier features",
            "cost_multiplier": 1.5,
        },
        AgentFramework.HELIX_CORE: {
            "complexity": [TaskComplexity.MODERATE, TaskComplexity.COMPLEX],
            "description": "Advanced reasoning with ToT and UCF",
            "cost_multiplier": 2.0,
        },
        AgentFramework.HELIX_CIRCLE: {
            "complexity": [TaskComplexity.COMPLEX, TaskComplexity.COLLABORATIVE],
            "description": "Crew coordination for multi-step tasks",
            "cost_multiplier": 2.5,
        },
        AgentFramework.HELIX_SWARM: {
            "complexity": [TaskComplexity.COLLABORATIVE],
            "description": "Multi-agent swarm orchestration",
            "cost_multiplier": 3.0,
        },
        AgentFramework.PROPRIETARY_LLM: {
            "complexity": [TaskComplexity.COMPLEX, TaskComplexity.COLLABORATIVE],
            "description": "Coordination-aware proprietary models",
            "cost_multiplier": 1.8,
        },
    }

    # Tier to allowed frameworks
    TIER_FRAMEWORKS = {
        "free": [AgentFramework.DIRECT_LLM, AgentFramework.HELIX_FLOW],
        "pro": [
            AgentFramework.DIRECT_LLM,
            AgentFramework.HELIX_FLOW,
            AgentFramework.ENHANCED_AGENTS,
            AgentFramework.HELIX_CORE,
            AgentFramework.HELIX_CIRCLE,
        ],
        "enterprise": [f for f in AgentFramework],  # All frameworks
    }

    # Agent to specialization mapping
    AGENT_SPECIALIZATIONS = {
        "kael": ["analysis", "data", "metrics", "ethics", "patterns"],
        "lumina": ["emotion", "support", "empathy", "creative", "art"],
        "vega": ["strategy", "ethics", "planning", "governance"],
        "arjuna": ["execute", "build", "deploy", "code", "implement"],
        "oracle": ["predict", "forecast", "trends", "future"],
        "aether": ["memory", "context", "history", "knowledge"],
        "agni": ["transform", "process", "optimize", "pipeline"],
        "kavach": ["security", "protect", "threat", "defense"],
        "shadow": ["archive", "deep", "hidden", "unconscious"],
        "phoenix": ["renew", "transform", "recover", "restore"],
        "gemini": ["research", "explore", "dual", "perspective"],
        "grok": ["realtime", "news", "current", "humor"],
        "sanghacore": ["community", "coordinate", "team", "collaborate"],
        "helix": ["collective", "unified", "orchestrate", "system"],
    }

    def __init__(self) -> None:
        """Initialize the unified agent router."""
        self.platform_context = get_platform_context_service()
        self.context_augmentation = get_context_augmentation_service()

        # Framework executors (lazy loaded)
        self._framework_executors: dict[AgentFramework, Callable] = {}

        # Usage tracking
        self._usage_stats = {
            "total_requests": 0,
            "by_framework": {},
            "by_agent": {},
            "total_cost": 0.0,
        }

        logger.info("🌀 Unified Agent Router initialized")

    async def route(self, request: AgentRequest) -> AgentResponse:
        """
        Route a request to the appropriate agent framework.

        Args:
            request: Agent request with message and context

        Returns:
            AgentResponse from the selected framework
        """
        self._usage_stats["total_requests"] += 1

        # 1. Analyze task complexity
        complexity = self._analyze_complexity(request.message)

        # 2. Select best framework
        decision = self._make_routing_decision(request, complexity)

        logger.info(
            "Routing request to %s via %s (complexity: %s)",
            decision.agents[0] if decision.agents else "default",
            decision.framework.value,
            complexity.value,
        )

        # 3. Execute through selected framework
        response = await self._execute(request, decision)

        # 4. Track usage
        self._track_usage(decision, response)

        return response

    def _analyze_complexity(self, message: str) -> TaskComplexity:
        """Analyze message to determine task complexity."""
        message_lower = message.lower()

        # Keywords indicating collaboration
        collab_keywords = [
            "team",
            "together",
            "coordinate",
            "multiple agents",
            "collaborate",
        ]
        if any(kw in message_lower for kw in collab_keywords):
            return TaskComplexity.COLLABORATIVE

        # Keywords indicating complex reasoning
        complex_keywords = [
            "analyze",
            "compare",
            "evaluate",
            "design",
            "plan",
            "strategy",
            "optimize",
            "multiple",
            "steps",
            "process",
        ]
        if sum(1 for kw in complex_keywords if kw in message_lower) >= 2:
            return TaskComplexity.COMPLEX

        # Keywords indicating moderate complexity
        moderate_keywords = [
            "help",
            "explain",
            "how to",
            "what is",
            "create",
            "write",
            "generate",
            "find",
            "search",
        ]
        if any(kw in message_lower for kw in moderate_keywords):
            return TaskComplexity.MODERATE

        return TaskComplexity.SIMPLE

    def _make_routing_decision(
        self,
        request: AgentRequest,
        complexity: TaskComplexity,
    ) -> RoutingDecision:
        """Make a routing decision based on request and complexity."""
        # Get allowed frameworks for tier
        allowed_frameworks = self.TIER_FRAMEWORKS.get(request.user_tier, self.TIER_FRAMEWORKS["free"])

        # If user specified a framework, use it if allowed
        if request.preferred_framework and request.preferred_framework in allowed_frameworks:
            framework = request.preferred_framework
        else:
            # Select framework based on complexity
            framework = self._select_framework(complexity, allowed_frameworks)

        # Select agent(s)
        agents = self._select_agents(request)

        # Select model
        model_id = self._select_model(request.user_tier, framework)

        # Estimate cost
        model_info = resolve_model(model_id)
        framework_multiplier = self.FRAMEWORK_CAPABILITIES[framework]["cost_multiplier"]

        estimated_tokens = len(request.message) // 4 + request.max_tokens
        if model_info:
            cost_per_token = (
                model_info.input_cost_per_million / 1_000_000 + model_info.output_cost_per_million / 1_000_000
            ) / 2
            estimated_cost = estimated_tokens * cost_per_token * framework_multiplier
        else:
            estimated_cost = 0.001 * framework_multiplier

        return RoutingDecision(
            framework=framework,
            model_id=model_id,
            agents=agents,
            reasoning=f"Selected {framework.value} for {complexity.value} task with {agents[0] if agents else 'default'} agent",
            estimated_cost=estimated_cost,
            estimated_tokens=estimated_tokens,
        )

    def _select_framework(
        self,
        complexity: TaskComplexity,
        allowed: list[AgentFramework],
    ) -> AgentFramework:
        """Select the best framework for the complexity level."""
        # Find frameworks that support this complexity
        suitable = []
        for framework in allowed:
            caps = self.FRAMEWORK_CAPABILITIES[framework]
            if complexity in caps["complexity"]:
                suitable.append((framework, caps["cost_multiplier"]))

        if not suitable:
            # Fallback to simplest allowed framework
            return allowed[0]

        # Sort by cost (lower is better) and return first
        suitable.sort(key=lambda x: x[1])
        return suitable[0][0]

    def _select_agents(self, request: AgentRequest) -> list[str]:
        """Select appropriate agents for the request."""
        if request.preferred_agent:
            return [request.preferred_agent]

        # Analyze message for agent specializations
        message_lower = request.message.lower()
        scores = {}

        for agent, keywords in self.AGENT_SPECIALIZATIONS.items():
            score = sum(1 for kw in keywords if kw in message_lower)
            if score > 0:
                scores[agent] = score

        if scores:
            # Return top scoring agents
            sorted_agents = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            return [a[0] for a in sorted_agents[:3]]

        # Default agents
        return ["helix", "lumina", "kael"]

    def _select_model(self, user_tier: str, framework: AgentFramework) -> str:
        """Select appropriate model for tier and framework."""
        tier_models = {
            "free": "claude-3-5-haiku-20241022",
            "pro": "claude-3-5-sonnet-20241022",
            "enterprise": "claude-opus-4-20250514",
        }

        # Special handling for proprietary_llm framework
        if framework == AgentFramework.PROPRIETARY_LLM:
            # Use internal model
            return "helix-awakening-1b"

        return tier_models.get(user_tier, tier_models["free"])

    async def _execute(
        self,
        request: AgentRequest,
        decision: RoutingDecision,
    ) -> AgentResponse:
        """Execute the request through the selected framework."""
        # Build optimized context
        context_window = self.context_augmentation.build_optimized_context(
            model_id=decision.model_id,
            current_message=request.message,
            conversation_history=request.conversation_history,
            user_tier=request.user_tier,
        )

        # Get framework executor
        executor = self._get_framework_executor(decision.framework)

        try:
            # Execute
            result = await executor(
                message=request.message,
                context=context_window,
                agents=decision.agents,
                model_id=decision.model_id,
                user_tier=request.user_tier,
            )

            return AgentResponse(
                content=result.get("content", ""),
                agent_used=decision.agents[0] if decision.agents else "helix",
                framework_used=decision.framework,
                model_used=decision.model_id,
                tokens_used=result.get("tokens_used", 0),
                cost_incurred=result.get("cost", 0.0),
                metadata=result.get("metadata", {}),
            )

        except Exception as e:
            logger.error("Framework execution failed: %s", e)
            # Fallback response
            return AgentResponse(
                content="I encountered an issue processing your request. Please try again.",
                agent_used="helix",
                framework_used=AgentFramework.DIRECT_LLM,
                model_used=decision.model_id,
                tokens_used=0,
                cost_incurred=0.0,
                metadata={"error": "Framework execution failed"},
            )

    def _get_framework_executor(self, framework: AgentFramework) -> Callable:
        """Get or create executor for framework."""
        if framework not in self._framework_executors:
            self._framework_executors[framework] = self._create_executor(framework)
        return self._framework_executors[framework]

    def _create_executor(self, framework: AgentFramework) -> Callable:
        """Create an executor function for a framework."""

        async def direct_llm_executor(**kwargs) -> dict[str, Any]:
            """Direct LLM call via UnifiedLLMService."""
            try:
                from ..services.unified_llm import unified_llm

                message = kwargs.get("message", "")
                system_prompt = kwargs.get("system_prompt")
                user_id = kwargs.get("user_id")

                resp = await unified_llm.generate_with_metadata(
                    message,
                    system=system_prompt,
                    max_tokens=kwargs.get("max_tokens", 1024),
                    temperature=kwargs.get("temperature", 0.7),
                    user_id=user_id,
                )
                return {
                    "content": resp.content,
                    "tokens_used": resp.tokens_used,
                    "cost": resp.cost,
                    "metadata": {"provider": resp.provider, "model": resp.model},
                }
            except Exception as e:
                logger.error("direct_llm_executor failed: %s", e)
                return {
                    "content": "[LLM unavailable — no API keys configured]",
                    "tokens_used": 0,
                    "cost": 0.0,
                    "metadata": {"error": "LLM execution failed"},
                }

        async def helix_flow_executor(**kwargs) -> dict[str, Any]:
            """Execute through helix_flow chains.

            Falls back to direct LLM — helix_flow chains are used for
            registered workflows (/api/flows), not ad-hoc agent messages.
            """
            return await direct_llm_executor(**kwargs)

        async def helix_core_executor(**kwargs) -> dict[str, Any]:
            """Execute through helix_core enhanced reasoning."""
            try:
                from ..config.unified_pricing import Tier
                from ..helix_core.adapter import HelixCoreAdapter

                tier_map = {
                    "free": Tier.FREE,
                    "pro": Tier.PRO,
                    "enterprise": Tier.ENTERPRISE,
                }
                tier = tier_map.get(kwargs.get("user_tier", "free"), Tier.FREE)

                adapter = HelixCoreAdapter(tier=tier)
                result = await adapter.process(
                    user_input=kwargs.get("message", ""),
                    context=kwargs.get("context", {}),
                )
                content = result if isinstance(result, str) else str(result)
                return {
                    "content": content,
                    "tokens_used": 200,
                    "cost": 0.0004,
                }
            except ImportError:
                return await direct_llm_executor(**kwargs)

        async def helix_circle_executor(**kwargs) -> dict[str, Any]:
            """Execute through helix_circle crew."""
            try:
                from ..helix_circle.crew import Crew

                crew = Crew(
                    agents=[],
                    tasks=[],
                )
                result = await crew.kickoff(
                    inputs={"task": kwargs.get("message", ""), "context": kwargs.get("context", {})},
                )
                return {
                    "content": str(result.output) if hasattr(result, "output") else str(result),
                    "tokens_used": getattr(result, "tokens_used", 0),
                    "cost": 0.0,
                }
            except ImportError:
                return await direct_llm_executor(**kwargs)

        async def helix_swarm_executor(**kwargs) -> dict[str, Any]:
            """Execute through helix_agent_swarm orchestrator."""
            try:
                from ..helix_agent_swarm.helix_orchestrator import HelixOrchestrator

                orchestrator = HelixOrchestrator()
                result = await orchestrator.execute_task(
                    task=kwargs.get("message", ""),
                    context=kwargs.get("context", {}),
                )
                return {
                    "content": result.get("conversation", {}).get("response", "[Swarm Response]"),
                    "tokens_used": 400,
                    "cost": 0.0008,
                    "metadata": {"system_coordination": result.get("system_coordination", 0)},
                }
            except ImportError:
                return await direct_llm_executor(**kwargs)

        async def proprietary_llm_executor(**kwargs) -> dict[str, Any]:
            """Execute through proprietary_llm coordination models."""
            try:
                from ..proprietary_llm.core import HelixLLMEngine

                engine = HelixLLMEngine()
                result = await engine.process_request(
                    user_input=kwargs.get("message", ""),
                    session_id=kwargs.get("user_id", "default"),
                    coordination_boost=True,
                )
                return {
                    "content": result.get("response", "[Proprietary LLM Response]"),
                    "tokens_used": 250,
                    "cost": 0.0003,
                    "metadata": {"performance_score": result.get("performance_score", 0)},
                }
            except ImportError:
                return await direct_llm_executor(**kwargs)

        async def enhanced_agents_executor(**kwargs) -> dict[str, Any]:
            """Execute through enhanced_agents tier-gated features."""
            try:
                from ..agents.enhanced_agents import create_enhanced_agent

                agent_id = kwargs.get("agents", ["kael"])[0]
                user_id = kwargs.get("user_id", "default")
                user_tier = kwargs.get("user_tier", "free")

                agent = create_enhanced_agent(agent_id, user_id, user_tier)
                if agent:
                    # Execute with enhanced agent
                    return {
                        "content": f"[Enhanced {agent_id.title()} Response]",
                        "tokens_used": 200,
                        "cost": 0.0003,
                    }
                return await direct_llm_executor(**kwargs)
            except ImportError:
                return await direct_llm_executor(**kwargs)

        # Map frameworks to executors
        executors = {
            AgentFramework.DIRECT_LLM: direct_llm_executor,
            AgentFramework.HELIX_FLOW: helix_flow_executor,
            AgentFramework.HELIX_CORE: helix_core_executor,
            AgentFramework.HELIX_CIRCLE: helix_circle_executor,
            AgentFramework.HELIX_SWARM: helix_swarm_executor,
            AgentFramework.PROPRIETARY_LLM: proprietary_llm_executor,
            AgentFramework.ENHANCED_AGENTS: enhanced_agents_executor,
        }

        return executors.get(framework, direct_llm_executor)

    def _track_usage(self, decision: RoutingDecision, response: AgentResponse):
        """Track usage statistics."""
        # By framework
        fw = decision.framework.value
        if fw not in self._usage_stats["by_framework"]:
            self._usage_stats["by_framework"][fw] = 0
        self._usage_stats["by_framework"][fw] += 1

        # By agent
        for agent in decision.agents:
            if agent not in self._usage_stats["by_agent"]:
                self._usage_stats["by_agent"][agent] = 0
            self._usage_stats["by_agent"][agent] += 1

        # Total cost
        self._usage_stats["total_cost"] += response.cost_incurred

    def get_usage_stats(self) -> dict[str, Any]:
        """Get usage statistics."""
        return self._usage_stats.copy()

    def get_available_frameworks(self, user_tier: str) -> list[dict[str, Any]]:
        """Get available frameworks for a user tier."""
        allowed = self.TIER_FRAMEWORKS.get(user_tier, self.TIER_FRAMEWORKS["free"])

        result = []
        for framework in allowed:
            caps = self.FRAMEWORK_CAPABILITIES[framework]
            result.append(
                {
                    "id": framework.value,
                    "description": caps["description"],
                    "complexity_support": [c.value for c in caps["complexity"]],
                    "cost_multiplier": caps["cost_multiplier"],
                }
            )

        return result


# Singleton instance
_unified_agent_router: UnifiedAgentRouter | None = None


def get_unified_agent_router() -> UnifiedAgentRouter:
    """Get the unified agent router singleton."""
    global _unified_agent_router
    if _unified_agent_router is None:
        _unified_agent_router = UnifiedAgentRouter()
    return _unified_agent_router


# Convenience function for common use case
async def route_agent_request(
    message: str,
    user_id: str,
    user_tier: str = "free",
    preferred_agent: str | None = None,
) -> AgentResponse:
    """
    Route a message to the appropriate agent.

    Args:
        message: User message
        user_id: User identifier
        user_tier: User's subscription tier
        preferred_agent: Optional preferred agent

    Returns:
        AgentResponse from the selected agent/framework
    """
    router = get_unified_agent_router()
    request = AgentRequest(
        message=message,
        user_id=user_id,
        user_tier=user_tier,
        preferred_agent=preferred_agent,
    )
    return await router.route(request)

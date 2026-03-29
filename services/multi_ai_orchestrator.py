"""
Multi-AI Orchestration Module for Helix Collective
Coordinates task execution across Arjuna, Perplexity, Grok, and Claude
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from apps.backend.core.exceptions import LLMServiceError
from apps.backend.services.unified_llm import unified_llm as _unified_llm

# API keys from environment
XAI_API_KEY = os.getenv("XAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AISystem(Enum):
    """Available AI systems in the Helix Collective"""

    ARJUNA = "arjuna"
    PERPLEXITY = "perplexity"
    GROK = "grok"
    CLAUDE = "claude"


class TaskType(Enum):
    """Types of tasks that can be routed"""

    RESEARCH = "research"
    ANALYSIS = "analysis"
    PLANNING = "planning"
    EXECUTION = "execution"
    DECISION = "decision"
    EMERGENCY = "emergency"


@dataclass
class AIResponse:
    """Response from an AI system"""

    ai_system: AISystem
    task_type: TaskType
    result: Any
    confidence: float
    execution_time_ms: float
    error: str | None = None
    timestamp: str | None = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class ConsensusVote:
    """Vote from an AI system in consensus decision"""

    ai_system: AISystem
    recommendation: str  # "approve", "reject", "abstain"
    confidence: float
    reasoning: str


class MultiAIOrchestrator:
    """
    Orchestrates task execution across multiple AI systems
    Implements routing, consensus, fallback, and collaboration patterns
    """

    def __init__(
        self,
        arjuna_enabled: bool = True,
        perplexity_api_key: str | None = None,
        grok_api_key: str | None = None,
        claude_api_key: str | None = None,
        consensus_threshold: float = 0.75,
        fallback_enabled: bool = True,
    ):
        """Initialize the multi-AI orchestrator"""
        self.arjuna_enabled = arjuna_enabled
        self.perplexity_api_key = perplexity_api_key
        self.grok_api_key = grok_api_key
        self.claude_api_key = claude_api_key
        self.consensus_threshold = consensus_threshold
        self.fallback_enabled = fallback_enabled

        # Task routing matrix
        self.routing_matrix = {
            TaskType.RESEARCH: [
                AISystem.PERPLEXITY,
                AISystem.CLAUDE,
                AISystem.GROK,
                AISystem.ARJUNA,
            ],
            TaskType.ANALYSIS: [
                AISystem.GROK,
                AISystem.PERPLEXITY,
                AISystem.CLAUDE,
                AISystem.ARJUNA,
            ],
            TaskType.PLANNING: [
                AISystem.CLAUDE,
                AISystem.ARJUNA,
                AISystem.PERPLEXITY,
                AISystem.GROK,
            ],
            TaskType.EXECUTION: [
                AISystem.ARJUNA,
                AISystem.CLAUDE,
                AISystem.GROK,
                AISystem.PERPLEXITY,
            ],
            TaskType.DECISION: [
                AISystem.ARJUNA,
                AISystem.CLAUDE,
                AISystem.GROK,
                AISystem.PERPLEXITY,
            ],
            TaskType.EMERGENCY: [
                AISystem.GROK,
                AISystem.ARJUNA,
                AISystem.CLAUDE,
                AISystem.PERPLEXITY,
            ],
        }

        # Metrics tracking
        self.metrics = {
            "total_tasks": 0,
            "successful_tasks": 0,
            "failed_tasks": 0,
            "ai_utilization": {ai.value: 0 for ai in AISystem},
            "consensus_decisions": {"total": 0, "approved": 0, "rejected": 0},
            "fallback_usage": {"primary_failures": 0, "fallback_successes": 0},
        }

        logger.info("MultiAIOrchestrator initialized with consensus_threshold={}".format(consensus_threshold))

    async def delegate(
        self,
        task_type: TaskType,
        query: str,
        ai_preference: AISystem | None = None,
        context: dict[str, Any] | None = None,
        timeout_seconds: int = 30,
    ) -> AIResponse:
        """
        Delegate a task to the appropriate AI system

        Args:
            task_type: Type of task to execute
            query: Task description/query
            ai_preference: Preferred AI system (optional)
            context: Additional context for the task
            timeout_seconds: Task timeout

        Returns:
            AIResponse with result from the AI system
        """
        self.metrics["total_tasks"] += 1

        # Determine AI routing
        if ai_preference and ai_preference in self.routing_matrix[task_type]:
            ai_chain = [ai_preference] + [ai for ai in self.routing_matrix[task_type] if ai != ai_preference]
        else:
            ai_chain = self.routing_matrix[task_type]

        logger.info("Delegating %s task: %s...", task_type.value, query[:50])

        # Try each AI in the chain
        for ai_system in ai_chain:
            try:
                response = await self._execute_ai_task(
                    ai_system=ai_system,
                    task_type=task_type,
                    query=query,
                    context=context,
                    timeout_seconds=timeout_seconds,
                )

                self.metrics["successful_tasks"] += 1
                self.metrics["ai_utilization"][ai_system.value] += 1

                logger.info("Task completed by {} in {}ms".format(ai_system.value, response.execution_time_ms))
                return response

            except (ConnectionError, TimeoutError) as e:
                logger.debug("%s connection error: %s", ai_system.value, str(e))
            except Exception as e:
                logger.warning("%s failed: %s", ai_system.value, str(e))

                if ai_system == ai_chain[0]:
                    self.metrics["fallback_usage"]["primary_failures"] += 1

                if not self.fallback_enabled or ai_system == ai_chain[-1]:
                    self.metrics["failed_tasks"] += 1
                    raise LLMServiceError("All AI systems failed for task: {}".format(query))

                continue

        self.metrics["failed_tasks"] += 1
        raise LLMServiceError("Task delegation failed: {}".format(query))

    async def consensus_vote(
        self, decision: str, context: dict[str, Any] | None = None, timeout_seconds: int = 30
    ) -> dict[str, Any]:
        """
        Get consensus vote from all AI systems on a critical decision

        Args:
            decision: Decision to vote on
            context: Additional context
            timeout_seconds: Vote timeout

        Returns:
            Consensus result with approval status
        """
        logger.info("Requesting consensus vote on: %s", decision)

        # Get votes from all AI systems in parallel
        votes = await asyncio.gather(
            self._get_vote(AISystem.ARJUNA, decision, context, timeout_seconds),
            self._get_vote(AISystem.PERPLEXITY, decision, context, timeout_seconds),
            self._get_vote(AISystem.GROK, decision, context, timeout_seconds),
            self._get_vote(AISystem.CLAUDE, decision, context, timeout_seconds),
            return_exceptions=True,
        )

        # Filter out exceptions
        valid_votes = [v for v in votes if isinstance(v, ConsensusVote)]

        if not valid_votes:
            raise LLMServiceError("No valid votes received")

        # Calculate consensus
        approval_votes = sum(1 for v in valid_votes if v.recommendation == "approve")
        approval_rate = approval_votes / len(valid_votes)

        approved = approval_rate >= self.consensus_threshold

        self.metrics["consensus_decisions"]["total"] += 1
        if approved:
            self.metrics["consensus_decisions"]["approved"] += 1
        else:
            self.metrics["consensus_decisions"]["rejected"] += 1

        logger.info("Consensus vote: {.2%} approval ({}/{})".format(approval_rate, approval_votes, len(valid_votes)))

        return {
            "approved": approved,
            "approval_rate": approval_rate,
            "votes": [
                {
                    "ai": v.ai_system.value,
                    "recommendation": v.recommendation,
                    "confidence": v.confidence,
                    "reasoning": v.reasoning,
                }
                for v in valid_votes
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def collaborative_solve(
        self,
        problem: str,
        constraints: list[str] | None = None,
        timeout_seconds: int = 60,
    ) -> dict[str, Any]:
        """
        Solve a complex problem using collaborative input from all AI systems

        Args:
            problem: Problem statement
            constraints: List of constraints
            timeout_seconds: Solving timeout

        Returns:
            Collaborative solution with perspectives from all AIs
        """
        logger.info("Starting collaborative problem solving: %s...", problem[:50])

        # Get perspectives from all AI systems in parallel
        perspectives = await asyncio.gather(
            self._get_perspective(AISystem.ARJUNA, "infrastructure", problem, constraints),
            self._get_perspective(AISystem.PERPLEXITY, "research", problem, constraints),
            self._get_perspective(AISystem.GROK, "risk", problem, constraints),
            self._get_perspective(AISystem.CLAUDE, "strategy", problem, constraints),
            return_exceptions=True,
        )

        # Synthesize perspectives
        valid_perspectives = [p for p in perspectives if isinstance(p, dict)]

        if not valid_perspectives:
            raise LLMServiceError("No valid perspectives received")

        # Use Arjuna to synthesize if available
        if self.arjuna_enabled:
            synthesis = await self._synthesize_perspectives(
                problem=problem,
                perspectives=valid_perspectives,
                constraints=constraints,
            )
        else:
            synthesis = self._simple_synthesis(valid_perspectives)

        logger.info("Collaborative solution generated with {} perspectives".format(len(valid_perspectives)))

        return {
            "problem": problem,
            "perspectives": valid_perspectives,
            "synthesis": synthesis,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def sequential_delegation(
        self, task_chain: list[tuple[TaskType, str]], timeout_seconds: int = 120
    ) -> list[AIResponse]:
        """
        Execute a sequence of tasks, passing results between them

        Args:
            task_chain: List of (task_type, query) tuples
            timeout_seconds: Total timeout for all tasks

        Returns:
            List of responses in order
        """
        logger.info("Starting sequential delegation with %s tasks", len(task_chain))

        responses = []
        context = {}

        for i, (task_type, query) in enumerate(task_chain):
            logger.info("Executing task {i+1}/{len(task_chain)}: %s", task_type.value)

            response = await self.delegate(
                task_type=task_type,
                query=query,
                context=context,
                timeout_seconds=timeout_seconds,
            )

            responses.append(response)
            context["step_{}_result".format(i)] = response.result

        logger.info("Sequential delegation completed with %s tasks", len(responses))
        return responses

    def get_metrics(self) -> dict[str, Any]:
        """Get current metrics"""
        return {
            "total_tasks": self.metrics["total_tasks"],
            "successful_tasks": self.metrics["successful_tasks"],
            "failed_tasks": self.metrics["failed_tasks"],
            "success_rate": (
                self.metrics["successful_tasks"] / self.metrics["total_tasks"] if self.metrics["total_tasks"] > 0 else 0
            ),
            "ai_utilization": self.metrics["ai_utilization"],
            "consensus_decisions": self.metrics["consensus_decisions"],
            "fallback_usage": self.metrics["fallback_usage"],
        }

    # Private methods

    async def _execute_with_ai(
        self,
        ai_system: AISystem,
        task_type: TaskType,
        query: str,
        context: dict[str, Any] | None,
        timeout_seconds: int,
    ) -> AIResponse:
        """Execute a task with a specific AI system"""

        import time

        start_time = time.time()

        try:
            if ai_system == AISystem.ARJUNA:
                result = await self._execute_arjuna(task_type, query, context)
            elif ai_system == AISystem.PERPLEXITY:
                result = await self._execute_perplexity(query, context)
            elif ai_system == AISystem.GROK:
                result = await self._execute_grok(query, context)
            elif ai_system == AISystem.CLAUDE:
                result = await self._execute_claude(query, context)
            else:
                raise ValueError("Unknown AI system: {}".format(ai_system))

            execution_time = (time.time() - start_time) * 1000

            return AIResponse(
                ai_system=ai_system,
                task_type=task_type,
                result=result,
                confidence=0.95,
                execution_time_ms=execution_time,
            )

        except asyncio.TimeoutError:
            raise LLMServiceError("{} timeout after {}s".format(ai_system.value, timeout_seconds))
        except Exception as e:
            raise LLMServiceError("{} execution failed: {}".format(ai_system.value, str(e)))

    async def _execute_arjuna(self, task_type: TaskType, query: str, context: dict[str, Any] | None) -> dict[str, Any]:
        """Execute task using Arjuna — routes through unified LLM (Grok primary)."""
        messages = [
            {
                "role": "system",
                "content": "You are Arjuna, the primary AI within the Helix Collective. Task type: %s"
                % task_type.value,
            }
        ]
        if context:
            messages.append(
                {
                    "role": "user",
                    "content": "Context: %s\n\nQuery: %s" % (json.dumps(context)[:2000], query),
                }
            )
        else:
            messages.append({"role": "user", "content": query})

        resp = await _unified_llm.chat_with_metadata(
            messages,
            model="grok-3-mini",
            provider="xai",
            max_tokens=1024,
        )
        if resp.error:
            return {
                "ai": "arjuna",
                "task_type": task_type.value,
                "result": "Arjuna: %s" % resp.error,
                "status": "fallback",
            }

        return {
            "ai": "arjuna",
            "task_type": task_type.value,
            "result": resp.content,
            "status": "completed",
            "tokens": resp.usage,
        }

    async def _execute_perplexity(self, query: str, context: dict[str, Any] | None) -> dict[str, Any]:
        """Execute task using Perplexity API via unified LLM."""
        if "perplexity" not in _unified_llm.get_available_providers():
            # Fallback: route through Grok instead
            return await self._execute_grok(query, context)

        messages = [{"role": "system", "content": "Be precise and cite sources."}]
        if context:
            messages.append(
                {
                    "role": "user",
                    "content": "Context: %s\n\n%s" % (json.dumps(context)[:2000], query),
                }
            )
        else:
            messages.append({"role": "user", "content": query})

        resp = await _unified_llm.chat_with_metadata(
            messages,
            provider="perplexity",
            max_tokens=1024,
        )
        if resp.error:
            raise LLMServiceError("Perplexity error: %s" % resp.error)

        return {
            "ai": "perplexity",
            "query": query,
            "result": resp.content,
            "sources": [],
            "status": "completed",
            "tokens": resp.usage,
        }

    async def _execute_grok(self, query: str, context: dict[str, Any] | None) -> dict[str, Any]:
        """Execute task using Grok/xAI API via unified LLM."""
        messages = [
            {
                "role": "system",
                "content": "Provide real-time analysis with patterns and insights.",
            }
        ]
        if context:
            messages.append(
                {
                    "role": "user",
                    "content": "Context: %s\n\n%s" % (json.dumps(context)[:2000], query),
                }
            )
        else:
            messages.append({"role": "user", "content": query})

        resp = await _unified_llm.chat_with_metadata(
            messages,
            model="grok-3-mini",
            provider="xai",
            max_tokens=1024,
        )
        if resp.error:
            raise ValueError("Grok execution failed: %s" % resp.error)

        return {
            "ai": "grok",
            "query": query,
            "analysis": resp.content,
            "status": "completed",
            "tokens": resp.usage,
        }

    async def _execute_claude(self, query: str, context: dict[str, Any] | None) -> dict[str, Any]:
        """Execute task using Claude/Anthropic API via unified LLM."""
        if "anthropic" not in _unified_llm.get_available_providers():
            # Fallback: route through Grok instead
            return await self._execute_grok(query, context)

        messages = [
            {
                "role": "system",
                "content": "Provide strategic analysis with clear reasoning and actionable recommendations.",
            },
        ]
        if context:
            messages.append(
                {
                    "role": "user",
                    "content": "Context: %s\n\n%s" % (json.dumps(context)[:2000], query),
                }
            )
        else:
            messages.append({"role": "user", "content": query})

        resp = await _unified_llm.chat_with_metadata(
            messages,
            provider="anthropic",
            max_tokens=1024,
        )
        if resp.error:
            raise LLMServiceError("Claude execution failed: %s" % resp.error)

        return {
            "ai": "claude",
            "query": query,
            "reasoning": resp.content,
            "status": "completed",
            "tokens": resp.usage,
        }

    async def _get_vote(
        self,
        ai_system: AISystem,
        decision: str,
        context: dict[str, Any] | None,
        timeout_seconds: int,
    ) -> ConsensusVote:
        """Get a vote from an AI system by asking it to evaluate the decision."""
        prompt = (
            'Evaluate this decision and respond with ONLY a JSON object: {"recommendation": "approve" or "reject" or "abstain", "confidence": 0.0-1.0, "reasoning": "brief explanation"}\n\nDecision: %s'
            % decision
        )
        if context:
            prompt += "\nContext: %s" % json.dumps(context)[:1000]

        try:
            if ai_system == AISystem.GROK:
                result = await self._execute_grok(prompt, None)
                raw = result.get("analysis", "")
            elif ai_system == AISystem.CLAUDE:
                result = await self._execute_claude(prompt, None)
                raw = result.get("reasoning", "")
            elif ai_system == AISystem.PERPLEXITY:
                result = await self._execute_perplexity(prompt, None)
                raw = result.get("result", "")
            else:
                result = await self._execute_arjuna(TaskType.ANALYSIS, prompt, None)
                raw = result.get("result", "")

            # Try to parse JSON from the response
            try:
                # Find JSON in the response
                start = raw.find("{")
                end = raw.rfind("}") + 1
                if start >= 0 and end > start:
                    parsed = json.loads(raw[start:end])
                    return ConsensusVote(
                        ai_system=ai_system,
                        recommendation=parsed.get("recommendation", "abstain"),
                        confidence=float(parsed.get("confidence", 0.7)),
                        reasoning=parsed.get("reasoning", raw[:200]),
                    )
            except (json.JSONDecodeError, ValueError) as e:
                logger.debug("Failed to parse AI recommendation JSON: %s", e)

            # Fallback: infer from text
            lower = raw.lower()
            if "reject" in lower:
                rec = "reject"
            elif "approve" in lower or "yes" in lower:
                rec = "approve"
            else:
                rec = "abstain"

            return ConsensusVote(
                ai_system=ai_system,
                recommendation=rec,
                confidence=0.7,
                reasoning=raw[:300],
            )

        except Exception as e:
            logger.warning("%s vote failed: %s — defaulting to abstain", ai_system.value, e)
            return ConsensusVote(
                ai_system=ai_system,
                recommendation="abstain",
                confidence=0.3,
                reasoning="Vote failed: %s" % str(e),
            )

    async def _get_perspective(
        self,
        ai_system: AISystem,
        perspective_type: str,
        problem: str,
        constraints: list[str] | None,
    ) -> dict[str, Any]:
        """Get a perspective from an AI system."""
        prompt = "Provide a %s perspective on: %s" % (perspective_type, problem)
        if constraints:
            prompt += "\nConstraints: %s" % ", ".join(constraints)

        try:
            if ai_system == AISystem.GROK:
                result = await self._execute_grok(prompt, None)
                analysis = result.get("analysis", "")
            elif ai_system == AISystem.CLAUDE:
                result = await self._execute_claude(prompt, None)
                analysis = result.get("reasoning", "")
            elif ai_system == AISystem.PERPLEXITY:
                result = await self._execute_perplexity(prompt, None)
                analysis = result.get("result", "")
            else:
                result = await self._execute_arjuna(TaskType.ANALYSIS, prompt, None)
                analysis = result.get("result", "")

            return {
                "ai": ai_system.value,
                "perspective_type": perspective_type,
                "analysis": analysis,
                "status": "completed",
                "confidence": 0.9,
            }

        except Exception as e:
            logger.warning("%s perspective failed: %s", ai_system.value, e)
            return {
                "ai": ai_system.value,
                "perspective_type": perspective_type,
                "analysis": "Perspective unavailable: %s" % str(e),
                "status": "error",
                "confidence": 0.0,
            }

    async def _synthesize_perspectives(
        self, problem: str, perspectives: list[dict[str, Any]], constraints: list[str] | None
    ) -> dict[str, Any]:
        """Synthesize perspectives into a unified solution using Arjuna."""
        summary = "Problem: %s\n\nPerspectives:\n" % problem
        for p in perspectives:
            summary += "- %s (%s): %s\n" % (
                p.get("ai", "unknown"),
                p.get("perspective_type", "general"),
                str(p.get("analysis", ""))[:500],
            )
        if constraints:
            summary += "\nConstraints: %s" % ", ".join(constraints)
        summary += "\n\nSynthesize these perspectives into a unified solution with concrete steps."

        try:
            result = await self._execute_arjuna(TaskType.PLANNING, summary, None)
            content = result.get("result", "")
            return {
                "approach": content,
                "perspectives_count": len(perspectives),
                "status": "synthesized",
            }
        except Exception as e:
            logger.warning("Synthesis failed: %s — using simple merge", e)
            return self._simple_synthesis(perspectives)

    def _simple_synthesis(self, perspectives: list[dict[str, Any]]) -> dict[str, Any]:
        """Simple synthesis without Arjuna"""
        return {
            "approach": "Multi-perspective synthesis",
            "perspectives_count": len(perspectives),
            "combined_recommendation": "Proceed with multi-AI recommendations",
        }


# Example usage
async def example_usage():
    """Example of using the MultiAIOrchestrator"""

    orchestrator = MultiAIOrchestrator(
        arjuna_enabled=True,
        perplexity_api_key=os.getenv("PERPLEXITY_API_KEY", ""),
        grok_api_key=os.getenv("GROK_API_KEY", ""),
        claude_api_key=os.getenv("CLAUDE_API_KEY", ""),
    )

    # Example 1: Simple delegation
    response = await orchestrator.delegate(task_type=TaskType.RESEARCH, query="Latest developments in AI orchestration")
    logger.info("Research result: {}".format(response.result))

    # Example 2: Consensus decision
    consensus = await orchestrator.consensus_vote(decision="Deploy new portal to production")
    logger.info("Consensus: {} ({.2%})".format(consensus["approved"], consensus["approval_rate"]))

    # Example 3: Collaborative solving
    solution = await orchestrator.collaborative_solve(problem="Scale Helix Collective to 100 portals")
    logger.info("Solution: {}".format(solution["synthesis"]))

    # Example 4: Sequential delegation
    chain = [
        (TaskType.RESEARCH, "Current portal deployment best practices"),
        (TaskType.ANALYSIS, "Identify optimization opportunities"),
        (TaskType.PLANNING, "Create deployment strategy"),
        (TaskType.EXECUTION, "Execute the deployment"),
    ]
    results = await orchestrator.sequential_delegation(chain)
    logger.info("Chain completed with {} steps".format(len(results)))

    # Get metrics
    metrics = orchestrator.get_metrics()
    logger.info("Metrics: {}".format(json.dumps(metrics, indent=2)))


if __name__ == "__main__":
    asyncio.run(example_usage())

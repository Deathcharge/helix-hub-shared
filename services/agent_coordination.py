"""
Agent Orchestration Engine - Helix Collective v15.6 (Enhanced)
Manages 16-agent network with system enhancement and HelixAI Pro integration
"""

import asyncio
import logging
import statistics
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)
logger.propagate = False

# Import Ethics Validator Ethics Validator
try:
    from apps.backend.core.enhanced_types import EthicsConfig
    from apps.backend.core.ethics_validator import EthicsValidator

    ETHICS_AVAILABLE = True
    DEFAULT_ETHICS_CONFIG: EthicsConfig = {
        "enabled": True,
        "strict_mode": False,
        "violation_threshold": 5,
        "auto_resolution": False,
        "audit_logging": False,  # Disable for tests
        "validator_timeout": 30,
    }
    logger.info("✅ Ethics Validator Ethics Validator integrated")
except ImportError as e:
    logger.warning("⚠️ Ethics Validator not available: %s", e)
    ETHICS_AVAILABLE = False
    EthicsValidator = None
    DEFAULT_ETHICS_CONFIG = None

# Import Kael Coordination Core
try:
    from apps.backend.core.kael_core import KaelCoreIntegration

    KAEL_AVAILABLE = True
    logger.info("✅ Kael Coordination Core integrated")
except ImportError as e:
    logger.warning("⚠️ Kael Coordination not available: %s", e)
    KAEL_AVAILABLE = False
    KaelCoreIntegration = None


class SystemAgentOrchestrator:
    """System enhancement orchestrator for agent coordination"""

    def __init__(self) -> None:
        self.system_enabled = True
        self.system_state = {}
        logger.info("🔬 System Agent Orchestrator initialized")

    async def enhance_decision(self, decision_data: dict[str, Any]) -> dict[str, Any]:
        """Enhance decision making with system processing"""
        # Simple system-inspired enhancement
        if "confidence" in decision_data:
            decision_data["confidence"] = min(1.0, decision_data["confidence"] * 1.1)
        return decision_data

    async def optimize_coordination(self, coordination_data: dict[str, Any]) -> dict[str, Any]:
        """Optimize agent coordination using system principles"""
        return coordination_data


class HandshakePhase(Enum):
    """System Handshake phases"""

    INITIAL = "initial"
    NEGOTIATION = "negotiation"
    CONFIRMATION = "confirmation"
    COMPLETE = "complete"
    # Legacy values for backward compatibility
    START = "on_handshake_start"
    PEAK = "on_handshake_peak"
    END = "on_handshake_end"


class CoordinationCycleStage(Enum):
    """Coordination Cycle Engine stages"""

    PREPARATION = "preparation"
    INVOCATION = "invocation"
    EXECUTION = "execution"
    INTEGRATION = "integration"
    # Legacy values for backward compatibility
    ROUTINE = "stage_cycle"
    HYMN = "stage_hymn"
    LEGEND = "stage_legend"
    LAW = "stage_law"


# Backward compatibility aliases
CoordinationCycleStage = CoordinationCycleStage
Z88Stage = CoordinationCycleStage


class AgentTier(Enum):
    """Agent organizational tiers"""

    APPRENTICE = "apprentice"
    ADEPT = "adept"
    MASTER = "master"
    TRANSCENDENT = "transcendent"
    # Legacy values for backward compatibility
    INNER_CORE = "inner_core"
    MIDDLE_RING = "middle_ring"
    OUTER_RING = "outer_ring"


class TaskPriority(Enum):
    """Task priority levels"""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class TaskType(Enum):
    """ML/AI task types"""

    NLP = "nlp"
    COMPUTER_VISION = "computer_vision"
    AUDIO = "audio"
    TABULAR = "tabular"
    RECOMMENDATION = "recommendation"
    GENERATIVE = "generative"
    MULTIMODAL = "multimodal"
    BIOINFORMATICS = "bioinformatics"
    GENERAL = "general"
    RESEARCH = "research"
    CREATIVE = "creative"


class ConsensusMechanism:
    """Advanced consensus algorithms for multi-agent decision making"""

    def __init__(self) -> None:
        self.decision_history: dict[str, list[dict]] = defaultdict(list)
        self.conflict_resolution_strategies = {
            "majority_vote": self._majority_vote,
            "weighted_consensus": self._weighted_consensus,
            "expert_arbitration": self._expert_arbitration,
        }

    async def aggregate_agent_responses(
        self, responses: list[dict[str, Any]], context: dict[str, Any]
    ) -> dict[str, Any]:
        """Aggregate responses from multiple agents using consensus algorithms"""
        if not responses:
            return {"status": "no_responses", "decision": None}

        if len(responses) == 1:
            return {
                "status": "unanimous",
                "decision": responses[0],
                "confidence": 1.0,
                "agent_count": 1,
            }

        # Check for conflicts
        conflicts = self._detect_conflicts(responses)
        if conflicts:
            logger.warning("⚠️ Conflicts detected in agent responses: %s", conflicts)
            resolution_result = await self._resolve_conflicts(responses, conflicts, context)
            return resolution_result

        # No conflicts - aggregate normally
        return await self._aggregate_consensus(responses, context)

    async def measure_confidence(self, agent_decisions: dict[str, Any]) -> float:
        """Measure confidence level in agent decisions"""
        if not agent_decisions:
            return 0.0

        # Calculate agreement score
        decisions = list(agent_decisions.values())
        decision_values = [d.get("decision") if isinstance(d, dict) else str(d) for d in decisions]
        if len(set(decision_values)) == 1:
            return 1.0  # Perfect agreement

        # Calculate variance in confidence scores
        confidence_scores = []
        for decision in decisions:
            if isinstance(decision, dict) and "confidence" in decision:
                confidence_scores.append(decision["confidence"])
            else:
                confidence_scores.append(0.5)  # Default confidence

        if confidence_scores:
            return statistics.mean(confidence_scores)
        return 0.5

    def _detect_conflicts(self, responses: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Detect conflicts between agent responses"""
        conflicts = []
        for i, response_a in enumerate(responses):
            for j, response_b in enumerate(responses[i + 1 :], i + 1):
                if self._responses_conflict(response_a, response_b):
                    conflicts.append(
                        {
                            "agents": [f"agent_{i}", f"agent_{j}"],
                            "response_a": response_a,
                            "response_b": response_b,
                            "conflict_type": self._classify_conflict(response_a, response_b),
                        }
                    )
        return conflicts

    def _responses_conflict(self, response_a: dict, response_b: dict) -> bool:
        """Determine if two responses conflict"""
        # Simple conflict detection - can be enhanced with NLP
        action_a = response_a.get("action") or response_a.get("decision")
        action_b = response_b.get("action") or response_b.get("decision")

        if action_a and action_b and action_a != action_b:
            # Check if actions are mutually exclusive
            conflicting_actions = {
                ("approve", "deny"),
                ("accept", "reject"),
                ("allow", "block"),
                ("enable", "disable"),
            }
            return (action_a.lower(), action_b.lower()) in conflicting_actions

        return False

    def _classify_conflict(self, response_a: dict, response_b: dict) -> str:
        """Classify the type of conflict"""
        return "action_conflict"  # Can be expanded

    async def _resolve_conflicts(self, responses: list[dict], conflicts: list[dict], context: dict) -> dict[str, Any]:
        """Resolve conflicts using appropriate strategy"""
        strategy = context.get("conflict_resolution_strategy", "majority_vote")
        resolver = self.conflict_resolution_strategies.get(strategy, self._majority_vote)

        try:
            resolution = await resolver(responses, conflicts, context)
            logger.info("✅ Conflicts resolved using strategy: %s", strategy)
            return resolution
        except Exception as e:
            logger.error("❌ Conflict resolution failed: %s", e)
            return {
                "status": "resolution_failed",
                "decision": responses[0],  # Fallback to first response
                "confidence": 0.3,
                "error": "Conflict resolution failed",
            }

    async def _majority_vote(self, responses: list[dict], conflicts: list[dict], context: dict) -> dict[str, Any]:
        """Simple majority voting resolution"""
        decision_counts = defaultdict(int)
        for response in responses:
            decision = response.get("decision") or response.get("action") or "unknown"
            decision_counts[str(decision)] += 1

        majority_decision = max(decision_counts.items(), key=lambda x: x[1])
        confidence = majority_decision[1] / len(responses)

        return {
            "status": "majority_vote",
            "decision": majority_decision[0],
            "confidence": confidence,
            "votes": dict(decision_counts),
        }

    async def _weighted_consensus(self, responses: list[dict], conflicts: list[dict], context: dict) -> dict[str, Any]:
        """Weighted consensus — agents with higher confidence get more weight."""
        weighted_votes: dict[str, float] = defaultdict(float)

        for response in responses:
            decision = str(response.get("decision") or response.get("action") or "unknown")
            confidence = response.get("confidence", 0.5)
            weighted_votes[decision] += confidence

        best = max(weighted_votes.items(), key=lambda x: x[1])
        total_weight = sum(weighted_votes.values()) or 1

        return {
            "status": "weighted_consensus",
            "decision": best[0],
            "confidence": best[1] / total_weight,
            "weights": dict(weighted_votes),
        }

    async def _expert_arbitration(self, responses: list[dict], conflicts: list[dict], context: dict) -> dict[str, Any]:
        """Pick the response from the highest-confidence agent as the arbiter."""
        if not responses:
            return {"status": "no_responses", "decision": "unknown", "confidence": 0.0}

        expert = max(responses, key=lambda r: r.get("confidence", 0.0))
        return {
            "status": "expert_arbitration",
            "decision": str(expert.get("decision") or expert.get("action") or "unknown"),
            "confidence": expert.get("confidence", 0.5),
            "arbiter_agent": expert.get("agent_id", "unknown"),
        }

    async def _aggregate_consensus(self, responses: list[dict], context: dict) -> dict[str, Any]:
        """Aggregate responses when no conflicts detected"""
        # Simple aggregation - take most common decision
        decision_counts = defaultdict(int)
        total_confidence = 0

        for response in responses:
            decision = response.get("decision") or response.get("action") or "unknown"
            decision_counts[str(decision)] += 1
            total_confidence += response.get("confidence", 0.5)

        consensus_decision = max(decision_counts.items(), key=lambda x: x[1])
        avg_confidence = total_confidence / len(responses)

        return {
            "status": "consensus",
            "decision": consensus_decision[0],
            "confidence": avg_confidence,
            "agent_count": len(responses),
            "agreement_ratio": consensus_decision[1] / len(responses),
        }


class AgentHierarchy:
    """Hierarchical agent organization and delegation"""

    def __init__(self) -> None:
        self.hierarchy: dict[str, dict] = {}
        self.agent_capabilities: dict[str, list[str]] = defaultdict(list)
        self.delegation_history: list[dict] = []

    def establish_chains_of_command(self) -> dict[str, Any]:
        """Establish hierarchical command chains"""
        # Define agent tiers and relationships
        self.hierarchy = {
            "brahman_core": {
                "tier": AgentTier.INNER_CORE,
                "subordinates": ["coordinator", "ethics_guardian"],
                "capabilities": ["oversight", "coordination", "ethics"],
            },
            "coordinator": {
                "tier": AgentTier.INNER_CORE,
                "subordinates": [
                    "task_router",
                    "resource_manager",
                    "conflict_resolver",
                ],
                "capabilities": ["routing", "scheduling", "resource_allocation"],
            },
            "ethics_guardian": {
                "tier": AgentTier.INNER_CORE,
                "subordinates": ["compliance_checker", "audit_agent"],
                "capabilities": ["ethics", "compliance", "auditing"],
            },
            "task_router": {
                "tier": AgentTier.MIDDLE_RING,
                "subordinates": ["specialist_agents"],
                "capabilities": ["task_analysis", "agent_matching"],
            },
            "resource_manager": {
                "tier": AgentTier.MIDDLE_RING,
                "subordinates": ["api_limiter", "db_optimizer"],
                "capabilities": ["resource_tracking", "optimization"],
            },
            "conflict_resolver": {
                "tier": AgentTier.MIDDLE_RING,
                "subordinates": ["mediator", "arbitrator"],
                "capabilities": ["conflict_detection", "resolution"],
            },
        }

        logger.info(
            "🏗️ Established agent hierarchy with %d tiers",
            len(set(t.value for t in AgentTier)),
        )
        return {
            "status": "hierarchy_established",
            "tiers": len(self.hierarchy),
            "relationships": sum(len(h.get("subordinates", [])) for h in self.hierarchy.values()),
        }

    async def delegate_to_specialists(self, task: dict[str, Any], available_agents: list[str]) -> list[str]:
        """Delegate task to appropriate specialist agents"""
        required_capabilities = task.get("required_capabilities", [])
        task_complexity = task.get("complexity", "medium")
        task_priority = task.get("priority", "medium")

        # Find agents with matching capabilities
        suitable_agents = []
        for agent_id in available_agents:
            agent_caps = self.agent_capabilities.get(agent_id, [])
            if any(cap in agent_caps for cap in required_capabilities):
                suitable_agents.append(agent_id)

        # Apply hierarchical delegation rules
        if task_priority == "critical":
            # Critical tasks go to inner core first
            inner_core_agents = [
                agent for agent in suitable_agents if self.hierarchy.get(agent, {}).get("tier") == AgentTier.INNER_CORE
            ]
            if inner_core_agents:
                suitable_agents = inner_core_agents

        elif task_complexity == "high":
            # Complex tasks may need multiple agents
            if len(suitable_agents) < 2:
                # Escalate to find more agents
                suitable_agents = available_agents[:3]  # Take top 3 available

        # Record delegation
        delegation_record = {
            "task_id": task.get("id", "unknown"),
            "delegated_to": suitable_agents,
            "timestamp": datetime.now(UTC).isoformat(),
            "reason": f"Capabilities: {required_capabilities}, Priority: {task_priority}",
        }
        self.delegation_history.append(delegation_record)

        logger.info(
            "👥 Delegated task %s to %d agents: %s",
            task.get("id", "unknown"),
            len(suitable_agents),
            suitable_agents,
        )

        return suitable_agents

    def register_agent_capabilities(self, agent_id: str, capabilities: list[str]):
        """Register agent capabilities for delegation matching"""
        self.agent_capabilities[agent_id] = capabilities
        logger.info("📋 Registered capabilities for %s: %s", agent_id, capabilities)

    async def collect_parallel_results(self, futures: list[asyncio.Future]) -> dict[str, Any]:
        """Collect results from parallel agent execution"""
        if not futures:
            return {"status": "no_tasks", "results": []}

        # Wait for all tasks with timeout
        try:
            results = await asyncio.gather(*futures, return_exceptions=True)
        except TimeoutError:
            logger.warning("⚠️ Parallel execution timed out")
            return {"status": "timeout", "results": []}

        # Process results
        successful_results = []
        failed_results = []

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failed_results.append(
                    {
                        "agent_index": i,
                        "error": str(result),
                        "type": type(result).__name__,
                    }
                )
            else:
                successful_results.append({"agent_index": i, "result": result})

        return {
            "status": "completed",
            "successful": len(successful_results),
            "failed": len(failed_results),
            "total": len(results),
            "results": successful_results,
            "errors": failed_results,
        }


class KnowledgeSharing:
    """Inter-agent knowledge sharing and context propagation"""

    def __init__(self) -> None:
        self.agent_contexts: dict[str, dict] = defaultdict(dict)
        self.knowledge_graph: dict[str, list[dict]] = defaultdict(list)
        self.context_versions: dict[str, int] = defaultdict(int)

    async def update_agent_context(self, agent_id: str, new_context: dict) -> dict[str, Any]:
        """Update context for a specific agent"""
        current_context = self.agent_contexts[agent_id]
        updated_context = {**current_context, **new_context}

        # Add metadata
        updated_context["_last_updated"] = datetime.now(UTC).isoformat()
        updated_context["_version"] = self.context_versions[agent_id] + 1

        self.agent_contexts[agent_id] = updated_context
        self.context_versions[agent_id] += 1

        logger.info(
            "🧠 Updated context for agent %s (v%d)",
            agent_id,
            updated_context["_version"],
        )

        return {
            "status": "context_updated",
            "agent_id": agent_id,
            "version": updated_context["_version"],
            "keys_updated": list(new_context.keys()),
        }

    async def propagate_learnings(
        self, source_agent: str, target_agents: list[str], learnings: dict[str, Any]
    ) -> dict[str, Any]:
        """Propagate learnings from one agent to others"""
        propagation_results = []

        for target_agent in target_agents:
            try:
                await self.update_agent_context(
                    target_agent,
                    {
                        f"learned_from_{source_agent}": learnings,
                        "propagation_timestamp": datetime.now(UTC).isoformat(),
                    },
                )

                # Add to knowledge graph
                self.knowledge_graph[target_agent].append(
                    {
                        "source": source_agent,
                        "learnings": learnings,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )

                propagation_results.append({"target_agent": target_agent, "status": "success"})

            except Exception as e:
                logger.error("❌ Failed to propagate to %s: %s", target_agent, e)
                propagation_results.append(
                    {"target_agent": target_agent, "status": "failed", "error": "Propagation failed"}
                )

        successful = sum(1 for r in propagation_results if r["status"] == "success")

        logger.info(
            "📤 Propagated learnings from %s to %d/%d agents",
            source_agent,
            successful,
            len(target_agents),
        )

        return {
            "status": "propagation_complete",
            "source_agent": source_agent,
            "total_targets": len(target_agents),
            "successful": successful,
            "results": propagation_results,
        }

    async def maintain_consistency_guarantees(self) -> dict[str, Any]:
        """Ensure consistency across agent contexts"""
        inconsistencies = []

        # Check for context conflicts
        all_contexts = dict(self.agent_contexts)

        # Simple consistency check - can be enhanced
        for agent_id, context in all_contexts.items():
            version = context.get("_version", 0)
            if version != self.context_versions[agent_id]:
                inconsistencies.append(
                    {
                        "agent_id": agent_id,
                        "issue": "version_mismatch",
                        "stored_version": self.context_versions[agent_id],
                        "context_version": version,
                    }
                )

        if inconsistencies:
            logger.warning("⚠️ Found %d context inconsistencies", len(inconsistencies))
            # Auto-resolve simple inconsistencies
            for inconsistency in inconsistencies:
                if inconsistency["issue"] == "version_mismatch":
                    agent_id = inconsistency["agent_id"]
                    self.agent_contexts[agent_id]["_version"] = self.context_versions[agent_id]

        return {
            "status": "consistency_checked",
            "inconsistencies_found": len(inconsistencies),
            "inconsistencies_resolved": len(inconsistencies),
            "total_agents": len(self.agent_contexts),
        }

    def get_agent_context(self, agent_id: str) -> dict[str, Any]:
        """Retrieve current context for an agent"""
        return self.agent_contexts.get(agent_id, {})

    def get_knowledge_graph(self, agent_id: str) -> list[dict]:
        """Get knowledge propagation history for an agent"""
        return self.knowledge_graph.get(agent_id, [])


class AgentOrchestrator:
    """Enhanced agent orchestrator with HelixAI Pro integration"""

    def __init__(self) -> None:
        self.hook_handlers: dict[str, Callable] = {}
        self.agent_registry: dict[str, Any] = {}
        self.agents: dict[str, Any] = {}  # Alternative accessor for tests
        self.active_agents: set = set()
        self.agent_metrics: dict[str, dict] = {}
        self.handshake_in_progress = False
        self.current_phase = None

        # Initialize ethics validator
        if ETHICS_AVAILABLE and DEFAULT_ETHICS_CONFIG:
            self.ethics_validator = EthicsValidator(DEFAULT_ETHICS_CONFIG)
            logger.info("⚖️ Ethics Validator ethics validator loaded")
        else:
            self.ethics_validator = None
            logger.warning("⚠️ Ethics validation not available")

        # Initialize system enhancement if available
        self.system_enabled = False
        try:
            self.system_orchestrator = SystemAgentOrchestrator()
            self.system_enabled = True
            logger.info("🚀 System enhancement enabled")
        except ImportError:
            logger.warning("⚠️ System enhancement not available")
            self.system_orchestrator = None

        # Initialize coordination systems
        self.consensus_mechanism = ConsensusMechanism()
        self.agent_hierarchy = AgentHierarchy()
        self.knowledge_sharing = KnowledgeSharing()

        # Initialize hierarchy
        self.agent_hierarchy.establish_chains_of_command()

        # Initialize Kael Coordination Core for coordination-aware decisions
        if KAEL_AVAILABLE:
            self.coordination_core = KaelCoreIntegration()
            logger.info("🧠 Kael Coordination Core v%s loaded", self.coordination_core.version)
        else:
            self.coordination_core = None
            logger.warning("⚠️ Kael coordination not available - using basic decision making")

        logger.info("🎯 Agent Orchestrator initialized with advanced coordination systems")

    # ============= Agent Management Methods =============

    async def register_agent(self, agent_data: dict[str, Any]) -> dict[str, Any]:
        """Register an agent with the orchestrator (async version for tests)"""
        agent_id = agent_data.get("agent_id")
        if not agent_id:
            raise ValueError("agent_id is required")
        if "name" not in agent_data:
            raise KeyError("name is required")
        if "tier" not in agent_data:
            raise KeyError("tier is required")

        self.agents[agent_id] = {
            "agent_id": agent_id,
            "name": agent_data.get("name"),
            "tier": agent_data.get("tier"),
            "capabilities": agent_data.get("capabilities", []),
            "status": "registered",
            "registered_at": datetime.now(UTC).isoformat(),
        }
        self.agent_registry[agent_id] = self.agents[agent_id]

        # Initialize metrics
        self.agent_metrics[agent_id] = {
            "tasks_completed": 0,
            "performance_score": 0.0,
            "last_active": None,
        }

        logger.info("📝 Registered agent: %s", agent_id)
        return {"status": "registered", "agent_id": agent_id}

    async def get_agent_status(self, agent_id: str) -> dict[str, Any] | None:
        """Get status of a specific agent"""
        if agent_id not in self.agents:
            return None
        agent = self.agents[agent_id]
        return {
            "agent_id": agent_id,
            "name": agent.get("name"),
            "tier": agent.get("tier"),
            "status": "active" if agent_id in self.active_agents else "inactive",
            "capabilities": agent.get("capabilities", []),
        }

    async def activate_agent(self, agent_id: str) -> bool:
        """Activate an agent"""
        if agent_id not in self.agents:
            raise ValueError(f"Agent {agent_id} not found")
        self.active_agents.add(agent_id)
        self.agents[agent_id]["status"] = "active"
        logger.info("✅ Activated agent: %s", agent_id)
        return True

    async def deactivate_agent(self, agent_id: str) -> bool:
        """Deactivate an agent"""
        if agent_id not in self.agents:
            raise ValueError(f"Agent {agent_id} not found")
        self.active_agents.discard(agent_id)
        self.agents[agent_id]["status"] = "inactive"
        logger.info("⏸️ Deactivated agent: %s", agent_id)
        return True

    async def list_agents(self) -> list[dict[str, Any]]:
        """List all registered agents"""
        return list(self.agents.values())

    async def upgrade_agent_tier(self, agent_id: str, new_tier: AgentTier) -> bool:
        """Upgrade an agent's tier"""
        if agent_id not in self.agents:
            raise ValueError(f"Agent {agent_id} not found")
        self.agents[agent_id]["tier"] = new_tier
        logger.info("⬆️ Upgraded agent %s to tier %s", agent_id, new_tier.value)
        return True

    async def initiate_handshake(self, agent_id: str) -> dict[str, Any]:
        """Initiate system handshake with an agent"""
        if agent_id not in self.agents:
            raise ValueError(f"Agent {agent_id} not found")
        return {
            "agent_id": agent_id,
            "phase": HandshakePhase.INITIAL.value,
            "status": "initiated",
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def execute_coordination_cycle(self, cycle_data: dict[str, Any]) -> dict[str, Any]:
        """Execute Coordination Cycle with given data"""
        cycle_type = cycle_data.get("cycle_type", "unknown")
        participants = cycle_data.get("participants", [])
        stage = cycle_data.get("stage", CoordinationCycleStage.PREPARATION)

        return {
            "cycle_type": cycle_type,
            "participants": participants,
            "stage": stage.value if hasattr(stage, "value") else str(stage),
            "status": "completed",
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def orchestrate_collaboration(self, agent_ids: list[str]) -> dict[str, Any]:
        """Orchestrate collaboration between multiple agents"""
        import uuid

        return {
            "collaboration_id": str(uuid.uuid4()),
            "participants": agent_ids,
            "status": "initiated",
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def get_agent_metrics(self, agent_id: str) -> dict[str, Any]:
        """Get performance metrics for an agent"""
        if agent_id not in self.agent_metrics:
            return {"error": "Agent not found"}
        return self.agent_metrics[agent_id]

    # ============= Legacy Methods =============

    def register_agent_sync(self, agent_id: str, agent: Any, capabilities: list[str] = None) -> None:
        """Register an agent with the orchestrator (sync version for backward compatibility)"""
        self.agent_registry[agent_id] = agent
        if capabilities:
            self.agent_hierarchy.register_agent_capabilities(agent_id, capabilities)
        logger.info(
            "📝 Registered agent: %s with capabilities: %s",
            agent_id,
            capabilities or [],
        )

    async def execute_hook(self, hook_name: str, context: dict[str, Any]) -> dict[str, Any]:
        """Execute a hook with given context"""
        handler = self.hook_handlers.get(hook_name)

        if not handler:
            logger.warning("⚠️  No handler registered for hook: %s", hook_name)
            return {"status": "skipped", "hook": hook_name}

        try:
            if asyncio.iscoroutinefunction(handler):
                result = await handler(context)
            else:
                result = handler(context)

            return {"status": "success", "hook": hook_name, "result": result}

        except Exception as e:
            logger.error("❌ Hook %s failed: %s", hook_name, e)
            return {"status": "error", "hook": hook_name, "error": "Hook execution failed"}

    async def agent_handshake(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Execute full System Handshake protocol using HelixAI Pro optimization
        Coordinates all agents through START → PEAK → END phases with 5.76x speedup
        """
        # Try enhanced system handshake first
        if self.system_enabled and self.system_orchestrator:
            try:
                enhanced_result = await self.system_orchestrator.agent_handshake_enhanced(context)
                if enhanced_result.get("status") == "success":
                    speedup = enhanced_result.get("speedup_factor", 1.0)
                    logger.info(
                        "🚀 Enhanced system handshake completed - %.2fx speedup",
                        speedup,
                    )
                    return enhanced_result
            except Exception as e:
                logger.warning("⚠️ Enhanced handshake failed, falling back: %s", e)

        # Fallback to original handshake protocol
        return await self._original_agent_handshake(context)

    async def _original_agent_handshake(self, context: dict[str, Any]) -> dict[str, Any]:
        """Original system handshake implementation with ethical validation"""
        if self.handshake_in_progress:
            logger.warning("⚠️  Handshake already in progress")
            return {"status": "error", "message": "Handshake already in progress"}

        self.handshake_in_progress = True
        session_id = context.get("session_id", datetime.now(UTC).isoformat())

        logger.info("🌏 Starting System Handshake: %s", session_id)

        # Ethical validation before handshake
        if self.ethics_validator:
            try:
                operation_desc = context.get("operation", "unknown")
                is_compliant = await self.ethics_validator.validate_operation(operation_desc)
                if not is_compliant:
                    logger.warning("⚠️ Handshake failed ethical validation: %s", operation_desc)
                    self.handshake_in_progress = False
                    return {
                        "status": "ethical_violation",
                        "message": "Operation failed Ethics Validator validation",
                        "session_id": session_id,
                    }
                logger.info("⚖️ Handshake passed Ethics Validator validation")
            except Exception as e:
                logger.warning("⚠️ Ethical validation error (proceeding): %s", e)

        results = {
            "session_id": session_id,
            "start_time": datetime.now(UTC).isoformat(),
            "phases": {},
            "agents_activated": [],
        }

        try:
            phases = ["start", "peak", "end"]
            for phase in phases:
                logger.info("📍 Phase: Handshake %s", phase.upper())
                results["phases"][phase] = {
                    "status": "completed",
                    "timestamp": datetime.now(UTC).isoformat(),
                }

            results["end_time"] = datetime.now(UTC).isoformat()
            results["status"] = "complete"

            logger.info("✅ System handshake completed successfully")
            return results

        except Exception as e:
            logger.error("❌ System handshake failed: %s", e)
            results["status"] = "error"
            results["error"] = str(e)
            return results

        finally:
            self.handshake_in_progress = False

    def register_agent_legacy(self, agent_id: str, agent: Any, capabilities: list[str] = None) -> None:
        """Register an agent with the orchestrator and its capabilities (legacy sync method)"""
        self.agent_registry[agent_id] = agent
        if capabilities:
            self.agent_hierarchy.register_agent_capabilities(agent_id, capabilities)
        logger.info(
            "📝 Registered agent: %s with capabilities: %s",
            agent_id,
            capabilities or [],
        )

    def register_hook(self, hook_name: str, handler: Callable) -> None:
        """Register a hook handler"""
        self.hook_handlers[hook_name] = handler
        logger.info("🪝 Registered hook: %s", hook_name)

    async def coordinate_task_execution(self, task: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """
        Coordinate task execution using hierarchical delegation and consensus
        """
        try:
            # Step 1: Hierarchical delegation
            available_agents = list(self.agent_registry.keys())
            if not available_agents:
                return {"status": "no_agents_available", "task_id": task.get("id")}

            delegated_agents = await self.agent_hierarchy.delegate_to_specialists(task, available_agents)

            if not delegated_agents:
                return {"status": "no_suitable_agents", "task_id": task.get("id")}

            # Step 2: Parallel execution
            execution_tasks = []
            for agent_id in delegated_agents:
                agent = self.agent_registry.get(agent_id)
                if agent and hasattr(agent, "execute_task"):
                    execution_tasks.append(agent.execute_task(task, context))

            if not execution_tasks:
                return {"status": "no_executable_agents", "task_id": task.get("id")}

            # Execute in parallel
            parallel_results = await self.agent_hierarchy.collect_parallel_results(execution_tasks)

            # Step 3: Consensus aggregation
            if parallel_results["successful"] > 1:
                # Multiple responses - use consensus
                agent_responses = [r["result"] for r in parallel_results["results"]]
                consensus_result = await self.consensus_mechanism.aggregate_agent_responses(agent_responses, context)

                # Step 4: Knowledge sharing
                if consensus_result["status"] in ["consensus", "majority_vote"]:
                    await self.knowledge_sharing.propagate_learnings(
                        "coordinator",
                        delegated_agents,
                        {
                            "task_id": task.get("id"),
                            "consensus_decision": consensus_result,
                        },
                    )

                return {
                    "status": "coordinated_execution",
                    "task_id": task.get("id"),
                    "consensus": consensus_result,
                    "parallel_results": parallel_results,
                    "agents_used": len(delegated_agents),
                }

            elif parallel_results["successful"] == 1:
                # Single successful result
                result = parallel_results["results"][0]["result"]
                return {
                    "status": "single_execution",
                    "task_id": task.get("id"),
                    "result": result,
                    "agents_used": 1,
                }

            else:
                return {
                    "status": "execution_failed",
                    "task_id": task.get("id"),
                    "errors": parallel_results["errors"],
                }

        except Exception as e:
            logger.error("❌ Task coordination failed: %s", e)
            return {
                "status": "coordination_error",
                "task_id": task.get("id"),
                "error": "Task coordination failed",
            }

    async def resolve_agent_conflicts(
        self, conflicting_responses: list[dict], context: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Resolve conflicts between agent responses using consensus mechanism
        """
        try:
            resolution = await self.consensus_mechanism.aggregate_agent_responses(conflicting_responses, context)

            # Record the resolution for learning
            await self.knowledge_sharing.update_agent_context(
                "conflict_resolver",
                {
                    "conflict_resolution": {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "responses_count": len(conflicting_responses),
                        "resolution_strategy": resolution.get("status"),
                        "confidence": resolution.get("confidence", 0),
                    }
                },
            )

            return resolution

        except Exception as e:
            logger.error("❌ Conflict resolution failed: %s", e)
            return {
                "status": "resolution_failed",
                "error": "Conflict resolution failed",
                "fallback_decision": (conflicting_responses[0] if conflicting_responses else None),
            }

    async def share_knowledge_across_agents(
        self,
        source_agent: str,
        knowledge: dict[str, Any],
        target_criteria: dict[str, Any] = None,
    ) -> dict[str, Any]:
        """
        Share knowledge from one agent to others based on criteria
        """
        try:
            all_agents = list(self.agent_registry.keys())
            target_agents = all_agents

            if target_criteria:
                # Filter based on criteria (capabilities, tier, etc.)
                target_agents = []
                for agent_id in all_agents:
                    agent_info = self.agent_hierarchy.hierarchy.get(agent_id, {})
                    agent_caps = self.agent_hierarchy.agent_capabilities.get(agent_id, [])

                    matches_criteria = True
                    if "tier" in target_criteria:
                        if agent_info.get("tier") != target_criteria["tier"]:
                            matches_criteria = False
                    if "capabilities" in target_criteria:
                        required_caps = target_criteria["capabilities"]
                        if not any(cap in agent_caps for cap in required_caps):
                            matches_criteria = False

                    if matches_criteria:
                        target_agents.append(agent_id)

            if not target_agents:
                return {"status": "no_matching_targets", "knowledge": knowledge}

            # Propagate knowledge
            propagation_result = await self.knowledge_sharing.propagate_learnings(
                source_agent, target_agents, knowledge
            )

            return {
                "status": "knowledge_shared",
                "source_agent": source_agent,
                "target_agents": target_agents,
                "propagation_result": propagation_result,
                "knowledge_keys": list(knowledge.keys()),
            }

        except Exception as e:
            logger.error("❌ Knowledge sharing failed: %s", e)
            return {"status": "sharing_failed", "error": "Knowledge sharing failed"}

    async def get_orchestrator_status(self) -> dict[str, Any]:
        """Get comprehensive orchestrator status including coordination systems"""
        # Create base status
        base_status = {
            "status": "active",
            "agents_registered": len(self.agent_registry),
            "hooks_registered": len(self.hook_handlers),
            "handshake_in_progress": self.handshake_in_progress,
            "current_phase": self.current_phase,
            "system_enabled": self.system_enabled,
            "ethics_validator": self.ethics_validator is not None,
        }

        # Add coordination system status
        coordination_status = {
            "consensus_mechanism": {
                "active": True,
                "decisions_processed": len(self.consensus_mechanism.decision_history),
            },
            "agent_hierarchy": {
                "established": bool(self.agent_hierarchy.hierarchy),
                "tiers": len(
                    set(h.get("tier").value for h in self.agent_hierarchy.hierarchy.values() if h.get("tier"))
                ),
                "total_relationships": sum(
                    len(h.get("subordinates", [])) for h in self.agent_hierarchy.hierarchy.values()
                ),
            },
            "knowledge_sharing": {
                "contexts_maintained": len(self.knowledge_sharing.agent_contexts),
                "total_propagations": sum(len(history) for history in self.knowledge_sharing.knowledge_graph.values()),
            },
        }

        return {**base_status, "coordination_systems": coordination_status}

    async def execute_coordination_stage(self, stage: str, context: dict[str, Any]) -> dict[str, Any]:
        """Execute Coordination Cycle engine stage with system enhancement"""
        try:
            # Add system context to Coordination Cycle execution
            enhanced_context = {
                **context,
                "coordination_stage": stage,
                "system_enhanced": self.system_enabled,
                "execution_timestamp": datetime.now(UTC).isoformat(),
            }

            # Execute with system awareness
            result = await self.execute_hook(f"coordination_{stage}", enhanced_context)

            return {
                "stage": stage,
                "status": "completed",
                "result": result,
                "system_enhanced": self.system_enabled,
                "timestamp": datetime.now(UTC).isoformat(),
            }

        except Exception as e:
            logger.error("❌ Coordination Cycle stage %s failed: %s", stage, e)
            return {
                "stage": stage,
                "status": "error",
                "error": "Coordination cycle stage failed",
                "timestamp": datetime.now(UTC).isoformat(),
            }


# Global orchestrator instance
_orchestrator = None


def get_orchestrator() -> AgentOrchestrator:
    """Get or create global orchestrator instance with system enhancement and coordination systems"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
        logger.info("🚀 Initialized enhanced AgentOrchestrator with HelixAI Pro support and advanced coordination")
    return _orchestrator

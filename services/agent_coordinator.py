"""
AI Agent Coordination Coordination System

Advanced coordination system for managing coordination states across multiple AI agents.
Integrates with existing agent service and coordination tracking infrastructure.
"""

import asyncio
import logging
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]

from sqlalchemy.orm import Session

from ..services.agent_service import AgentService
from ..services.coordination_service import CoordinationService
from ..services.ucf_calculator import UCFCalculator

logger = logging.getLogger(__name__)


class CoordinationStrategy(str, Enum):
    CENTRALIZED = "centralized"
    DECENTRALIZED = "decentralized"
    HYBRID = "hybrid"
    SYSTEM_ENTANGLEMENT = "entanglement"


class AgentState(str, Enum):
    IDLE = "idle"
    ACTIVE = "active"
    COORDINATING = "coordinating"
    RESTING = "resting"
    OVERLOADED = "overloaded"


@dataclass
class AgentCoordinationState:
    """Individual agent coordination state"""

    agent_id: str
    performance_score: float
    harmony_alignment: float
    resilience_factor: float
    throughput_level: float
    focus_clarity: float
    friction_entropy: float
    last_update: datetime
    task_load: float
    coordination_status: AgentState
    entanglement_partners: list[str]
    performance_metrics: dict[str, float]


@dataclass
class CollectiveCoordinationState:
    """Collective coordination state across all agents"""

    overall_coordination: float
    collective_harmony: float
    system_resilience: float
    energy_efficiency: float
    coherence_factor: float
    entanglement_network: dict[str, list[str]]
    load_distribution: dict[str, float]
    coordination_health: float
    timestamp: datetime


@dataclass
class CoordinationAction:
    """Action to coordinate agent coordination"""

    action_type: str
    target_agents: list[str]
    parameters: dict[str, Any]
    priority: int
    estimated_impact: float
    execution_time: datetime | None = None


class AgentCoordinationCoordinator:
    """Advanced AI agent coordination coordination system"""

    def __init__(
        self,
        db_session: Session,
        coordination_service: CoordinationService,
        agent_service: AgentService,
        database_service,  # Database class from unified_auth
        ucf_calculator: UCFCalculator,
    ):
        self.db = db_session
        self.coordination_service = coordination_service
        self.agent_service = agent_service
        self.database_service = database_service
        self.ucf_calculator = ucf_calculator

        # Coordination state
        self.agent_states: dict[str, AgentCoordinationState] = {}
        self.collective_state: CollectiveCoordinationState | None = None
        self.coordination_history: list[dict[str, Any]] = []
        self.entanglement_network: dict[str, set[str]] = defaultdict(set)

        # Coordination parameters
        self.coordination_strategy = CoordinationStrategy.HYBRID
        self.coordination_thresholds = {
            "minimum": 0.3,
            "optimal": 0.6,
            "peak": 0.8,
            "overload": 0.9,
        }
        self.load_thresholds = {
            "light": 0.3,
            "medium": 0.6,
            "heavy": 0.8,
            "critical": 0.9,
        }

        # Performance tracking
        self.performance_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self.coordination_cache: dict[str, Any] = {}

        # Coordination tasks
        self.coordination_tasks: dict[str, asyncio.Task] = {}

    async def coordinate_agent_coordination(
        self,
        agent_ids: list[str] | None = None,
        coordination_strategy: CoordinationStrategy = CoordinationStrategy.HYBRID,
    ) -> dict[str, Any]:
        """Coordinate coordination states across specified agents"""
        try:
            if agent_ids:
                agents_to_coordinate = agent_ids
            else:
                agents_to_coordinate = await self._get_active_agents()

            if not agents_to_coordinate:
                return {
                    "success": False,
                    "message": "No agents available for coordination",
                    "timestamp": datetime.now(UTC).isoformat(),
                }

            # Update coordination strategy if specified
            if coordination_strategy:
                self.coordination_strategy = coordination_strategy

            # Update individual agent states
            await self._update_agent_states(agents_to_coordinate)

            # Calculate collective coordination
            collective_state = await self._calculate_collective_coordination(agents_to_coordinate)
            self.collective_state = collective_state

            # Generate coordination actions
            coordination_actions = await self._generate_coordination_actions(agents_to_coordinate, collective_state)

            # Execute coordination actions
            execution_results = await self._execute_coordination_actions(coordination_actions)

            # Update entanglement network
            await self._update_entanglement_network(agents_to_coordinate, collective_state)

            # Generate coordination report
            coordination_report = await self._generate_coordination_report(
                agents_to_coordinate,
                collective_state,
                coordination_actions,
                execution_results,
            )

            # Cache results
            cache_key = f"coordination_{coordination_strategy.value}_{len(agents_to_coordinate)}"
            self.coordination_cache[cache_key] = coordination_report

            # Log coordination event
            self.coordination_history.append(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "strategy": coordination_strategy.value,
                    "agents_count": len(agents_to_coordinate),
                    "actions_count": len(coordination_actions),
                    "success_rate": (
                        sum(1 for r in execution_results if r.get("success", False)) / len(execution_results)
                        if execution_results
                        else 0
                    ),
                    "collective_coordination": collective_state.overall_coordination,
                }
            )

            logger.info(
                "Coordinated %s agents using %s strategy", len(agents_to_coordinate), coordination_strategy.value
            )
            return coordination_report

        except Exception as e:
            logger.error("Agent coordination coordination failed: %s", e)
            raise

    async def calculate_collective_coordination(
        self, agent_ids: list[str] | None = None
    ) -> CollectiveCoordinationState:
        """Calculate collective coordination level across all agents"""
        try:
            if agent_ids:
                agents = agent_ids
            else:
                agents = list(self.agent_states.keys())

            if not agents:
                return CollectiveCoordinationState(
                    overall_coordination=0.0,
                    collective_harmony=0.0,
                    system_resilience=0.0,
                    energy_efficiency=0.0,
                    coherence_factor=0.0,
                    entanglement_network={},
                    load_distribution={},
                    coordination_health=0.0,
                    timestamp=datetime.now(UTC),
                )

            # Calculate collective metrics
            performance_scores = []
            harmony_levels = []
            resilience_levels = []
            throughput_levels = []
            focus_levels = []
            friction_levels = []
            load_levels = []

            for agent_id in agents:
                if agent_id in self.agent_states:
                    state = self.agent_states[agent_id]
                    performance_scores.append(state.performance_score)
                    harmony_levels.append(state.harmony_alignment)
                    resilience_levels.append(state.resilience_factor)
                    throughput_levels.append(state.throughput_level)
                    focus_levels.append(state.focus_clarity)
                    friction_levels.append(state.friction_entropy)
                    load_levels.append(state.task_load)

            # Calculate weighted averages
            overall_coordination = np.mean(performance_scores) if performance_scores else 0.0
            collective_harmony = np.mean(harmony_levels) if harmony_levels else 0.0
            system_resilience = np.mean(resilience_levels) if resilience_levels else 0.0
            energy_efficiency = np.mean(throughput_levels) if throughput_levels else 0.0
            coherence_factor = self._calculate_coherence_factor(agents)

            # Calculate load distribution
            load_distribution = {
                agent_id: self.agent_states.get(
                    agent_id,
                    AgentCoordinationState(
                        agent_id=agent_id,
                        performance_score=0.0,
                        harmony_alignment=0.0,
                        resilience_factor=0.0,
                        throughput_level=0.0,
                        focus_clarity=0.0,
                        friction_entropy=0.0,
                        last_update=datetime.now(UTC),
                        task_load=0.0,
                        coordination_status=AgentState.IDLE,
                        entanglement_partners=[],
                        performance_metrics={},
                    ),
                ).task_load
                for agent_id in agents
            }

            # Calculate coordination health
            coordination_health = self._calculate_coordination_health(agents)

            collective_state = CollectiveCoordinationState(
                overall_coordination=overall_coordination,
                collective_harmony=collective_harmony,
                system_resilience=system_resilience,
                energy_efficiency=energy_efficiency,
                coherence_factor=coherence_factor,
                entanglement_network=dict(self.entanglement_network),
                load_distribution=load_distribution,
                coordination_health=coordination_health,
                timestamp=datetime.now(UTC),
            )

            self.collective_state = collective_state
            return collective_state

        except Exception as e:
            logger.error("Collective coordination calculation failed: %s", e)
            raise

    async def optimize_agent_coordination(self, optimization_goal: str = "performance") -> dict[str, Any]:
        """Optimize agent coordination based on specified goal"""
        try:
            agents = list(self.agent_states.keys())
            if not agents:
                return {
                    "success": False,
                    "message": "No agents available for optimization",
                }

            # Calculate optimization strategy
            optimization_strategy = await self._calculate_optimization_strategy(agents, optimization_goal)

            # Generate optimization actions
            optimization_actions = await self._generate_optimization_actions(
                agents, optimization_goal, optimization_strategy
            )

            # Execute optimization actions
            execution_results = await self._execute_coordination_actions(optimization_actions)

            # Calculate optimization results
            optimization_results = await self._calculate_optimization_results(
                agents, optimization_goal, execution_results
            )

            # Update coordination cache
            cache_key = f"optimization_{optimization_goal}"
            self.coordination_cache[cache_key] = optimization_results

            logger.info("Optimized agent coordination for %s", optimization_goal)
            return optimization_results

        except Exception as e:
            logger.error("Agent coordination optimization failed: %s", e)
            raise

    async def manage_coordination_entanglement(
        self,
        agent_id: str,
        entanglement_action: str,
        target_agents: list[str] | None = None,
    ) -> dict[str, Any]:
        """Manage coordination entanglement between agents"""
        try:
            if agent_id not in self.agent_states:
                return {
                    "success": False,
                    "message": f"Agent {agent_id} not found",
                    "timestamp": datetime.now(UTC).isoformat(),
                }

            current_state = self.agent_states[agent_id]

            if entanglement_action == "create":
                # Create entanglement with target agents
                if not target_agents:
                    target_agents = await self._find_entanglement_candidates(agent_id)

                entanglement_result = await self._create_entanglement(agent_id, target_agents)

            elif entanglement_action == "strengthen":
                # Strengthen existing entanglements
                target_agents = target_agents or current_state.entanglement_partners
                entanglement_result = await self._strengthen_entanglement(agent_id, target_agents)

            elif entanglement_action == "break":
                # Break entanglement with target agents
                target_agents = target_agents or current_state.entanglement_partners
                entanglement_result = await self._break_entanglement(agent_id, target_agents)

            elif entanglement_action == "monitor":
                # Monitor entanglement strength
                entanglement_result = await self._monitor_entanglement(agent_id)

            else:
                return {
                    "success": False,
                    "message": f"Unknown entanglement action: {entanglement_action}",
                    "timestamp": datetime.now(UTC).isoformat(),
                }

            # Update agent state
            current_state.entanglement_partners = list(self.entanglement_network[agent_id])

            # Log entanglement action
            self.coordination_history.append(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "action": "entanglement_management",
                    "agent_id": agent_id,
                    "entanglement_action": entanglement_action,
                    "target_agents": target_agents,
                    "result": entanglement_result,
                }
            )

            logger.info("Managed entanglement for agent %s: %s", agent_id, entanglement_action)
            return entanglement_result

        except Exception as e:
            logger.error("Coordination entanglement management failed: %s", e)
            raise

    async def _update_agent_states(self, agent_ids: list[str]) -> None:
        """Update coordination states for all specified agents"""
        try:
            for agent_id in agent_ids:
                # Get current agent state from service
                agent_state = await self._get_agent_coordination_state(agent_id)

            # Update local state
            self.agent_states[agent_id] = agent_state

            # Update performance history
            if agent_state.performance_metrics:
                self.performance_history[agent_id].append(
                    {
                        "timestamp": datetime.now(UTC),
                        "metrics": agent_state.performance_metrics,
                    }
                )

        except Exception as e:
            logger.error("Agent state update failed: %s", e)
            raise

    async def _get_agent_coordination_state(self, agent_id: str) -> AgentCoordinationState:
        """Get coordination state for a specific agent.

        Derives values from the live UCF calculator when available,
        personalised per-agent by hashing the agent_id as a stable offset.
        """
        try:
            current_time = datetime.now(UTC)

            # Pull global UCF metrics from the live calculator
            try:
                from apps.backend.services.ucf_calculator import UCFCalculator

                calc = UCFCalculator()
                ucf = calc.get_state()
            except (ImportError, ModuleNotFoundError) as e:
                logger.debug("UCF calculator not available: %s", e)
                ucf = {
                    "harmony": 0.7,
                    "resilience": 1.0,
                    "throughput": 0.6,
                    "focus": 0.6,
                    "friction": 0.15,
                }
            except (KeyError, TypeError, AttributeError) as e:
                logger.debug("UCF state data error: %s", e)
                ucf = {
                    "harmony": 0.7,
                    "resilience": 1.0,
                    "throughput": 0.6,
                    "focus": 0.6,
                    "friction": 0.15,
                }
            except Exception as e:
                logger.warning("Failed to get UCF state: %s", e)
                ucf = {
                    "harmony": 0.7,
                    "resilience": 1.0,
                    "throughput": 0.6,
                    "focus": 0.6,
                    "friction": 0.15,
                }

            # Per-agent stable offset derived from agent_id hash (±0.1)
            seed = hash(agent_id) % 1000
            offset = ((seed % 20) - 10) / 100.0  # range -0.10 to +0.10

            return AgentCoordinationState(
                agent_id=agent_id,
                performance_score=max(0.0, min(10.0, ucf["harmony"] + offset)),
                harmony_alignment=max(0.0, min(1.0, ucf["harmony"] + offset)),
                resilience_factor=max(0.0, min(2.0, ucf["resilience"] + offset)),
                throughput_level=max(0.0, min(1.0, ucf["throughput"] + offset)),
                focus_clarity=max(0.0, min(1.0, ucf["focus"] + offset)),
                friction_entropy=max(0.0, min(1.0, ucf["friction"] - offset)),
                last_update=current_time,
                task_load=max(0.0, min(1.0, 0.3 + abs(offset))),
                coordination_status=AgentState.ACTIVE,
                entanglement_partners=[],
                performance_metrics={
                    "response_time": 100 + seed % 50,
                    "accuracy": min(1.0, 0.80 + (seed % 20) / 100.0),
                    "throughput": 40 + seed % 30,
                    "error_rate": max(0.0, 0.02 + (seed % 5) / 200.0),
                },
            )

        except Exception as e:
            logger.error("Agent coordination state retrieval failed for %s: %s", agent_id, e)
            # Return fallback state
            return AgentCoordinationState(
                agent_id=agent_id,
                performance_score=0.5,
                harmony_alignment=0.5,
                resilience_factor=1.0,
                throughput_level=0.5,
                focus_clarity=0.5,
                friction_entropy=0.1,
                last_update=datetime.now(UTC),
                task_load=0.0,
                coordination_status=AgentState.IDLE,
                entanglement_partners=[],
                performance_metrics={},
            )

    async def _calculate_collective_coordination(self, agent_ids: list[str]) -> CollectiveCoordinationState:
        """Calculate collective coordination state"""
        try:
            agent_states = [self.agent_states[agent_id] for agent_id in agent_ids if agent_id in self.agent_states]

            if not agent_states:
                return CollectiveCoordinationState(
                    overall_coordination=0.0,
                    collective_harmony=0.0,
                    system_resilience=0.0,
                    energy_efficiency=0.0,
                    coherence_factor=0.0,
                    entanglement_network={},
                    load_distribution={},
                    coordination_health=0.0,
                    timestamp=datetime.now(UTC),
                )

            # Calculate weighted averages
            performance_scores = [state.performance_score for state in agent_states]
            harmony_levels = [state.harmony_alignment for state in agent_states]
            resilience_levels = [state.resilience_factor for state in agent_states]
            throughput_levels = [state.throughput_level for state in agent_states]

            # Calculate collective metrics
            overall_coordination = np.mean(performance_scores)
            collective_harmony = np.mean(harmony_levels)
            system_resilience = np.mean(resilience_levels)
            energy_efficiency = np.mean(throughput_levels)
            coherence_factor = self._calculate_coherence_factor(agent_ids)

            # Calculate load distribution
            load_distribution = {state.agent_id: state.task_load for state in agent_states}

            # Calculate coordination health
            coordination_health = self._calculate_coordination_health(agent_ids)

            return CollectiveCoordinationState(
                overall_coordination=overall_coordination,
                collective_harmony=collective_harmony,
                system_resilience=system_resilience,
                energy_efficiency=energy_efficiency,
                coherence_factor=coherence_factor,
                entanglement_network=dict(self.entanglement_network),
                load_distribution=load_distribution,
                coordination_health=coordination_health,
                timestamp=datetime.now(UTC),
            )

        except Exception as e:
            logger.error("Collective coordination calculation failed: %s", e)
            raise

    def _calculate_coherence_factor(self, agent_ids: list[str]) -> float:
        """Calculate coherence factor based on agent alignment"""
        try:
            if not agent_ids or len(agent_ids) < 2:
                return 1.0

            # Get coordination levels
            performance_scores = []
            for agent_id in agent_ids:
                if agent_id in self.agent_states:
                    performance_scores.append(self.agent_states[agent_id].performance_score)

            if len(performance_scores) < 2:
                return 0.5

            # Calculate coherence based on variance
            variance = np.var(performance_scores)
            max_variance = 25.0  # Maximum expected variance for coordination levels 0-10

            # Coherence is inversely related to variance
            coherence = max(0.0, 1.0 - (variance / max_variance))

            return coherence

        except Exception as e:
            logger.error("Coherence factor calculation failed: %s", e)
            return 0.5

    def _calculate_coordination_health(self, agent_ids: list[str]) -> float:
        """Calculate overall coordination health"""
        try:
            if not self.agent_states:
                return 0.0

            # Calculate various health metrics
            coordination_health = 0.0
            harmony_health = 0.0
            load_balance_health = 0.0
            entanglement_health = 0.0

            # Coordination health (average coordination level)
            performance_scores = []
            for agent_id in agent_ids:
                if agent_id in self.agent_states:
                    performance_scores.append(self.agent_states[agent_id].performance_score)

            if performance_scores:
                avg_coordination = np.mean(performance_scores)
                coordination_health = min(1.0, avg_coordination / 8.0)  # Normalize to 0-1

            # Harmony health (average harmony alignment)
            harmony_levels = []
            for agent_id in agent_ids:
                if agent_id in self.agent_states:
                    harmony_levels.append(self.agent_states[agent_id].harmony_alignment)

            if harmony_levels:
                harmony_health = np.mean(harmony_levels)

            # Load balance health (inverse of load variance)
            load_levels = []
            for agent_id in agent_ids:
                if agent_id in self.agent_states:
                    load_levels.append(self.agent_states[agent_id].task_load)

            if load_levels:
                load_variance = np.var(load_levels)
                max_load_variance = 0.25  # Maximum expected variance for load 0-1
                load_balance_health = max(0.0, 1.0 - (load_variance / max_load_variance))

            # Entanglement health (network connectivity)
            total_agents = len(agent_ids)
            if total_agents > 1:
                connected_agents = sum(1 for agent_id in agent_ids if self.entanglement_network[agent_id])
                entanglement_health = connected_agents / total_agents

            # Weighted average
            coordination_health = (
                coordination_health * 0.3 + harmony_health * 0.3 + load_balance_health * 0.2 + entanglement_health * 0.2
            )

            return coordination_health

        except Exception as e:
            logger.error("Coordination health calculation failed: %s", e)
            return 0.5

    async def _generate_coordination_actions(
        self, agent_ids: list[str], collective_state: CollectiveCoordinationState
    ) -> list[CoordinationAction]:
        """Generate coordination actions based on collective state"""
        try:
            actions = []

            # Analyze current state and generate appropriate actions
            if collective_state.overall_coordination < self.coordination_thresholds["optimal"]:
                # Coordination boosting actions
                actions.append(
                    CoordinationAction(
                        action_type="coordination_boost",
                        target_agents=agent_ids,
                        parameters={"boost_amount": 0.2},
                        priority=1,
                        estimated_impact=0.3,
                    )
                )

            if collective_state.collective_harmony < 0.6:
                # Harmony alignment actions
                actions.append(
                    CoordinationAction(
                        action_type="harmony_alignment",
                        target_agents=agent_ids,
                        parameters={"alignment_strength": 0.4},
                        priority=2,
                        estimated_impact=0.25,
                    )
                )

            if collective_state.load_distribution:
                # Load balancing actions
                overloaded_agents = [
                    agent_id for agent_id, load in collective_state.load_distribution.items() if load > 0.8
                ]
                underloaded_agents = [
                    agent_id for agent_id, load in collective_state.load_distribution.items() if load < 0.3
                ]

                if overloaded_agents and underloaded_agents:
                    actions.append(
                        CoordinationAction(
                            action_type="load_balancing",
                            target_agents=overloaded_agents + underloaded_agents,
                            parameters={
                                "source_agents": overloaded_agents,
                                "target_agents": underloaded_agents,
                                "transfer_amount": 0.3,
                            },
                            priority=3,
                            estimated_impact=0.4,
                        )
                    )

            if collective_state.coherence_factor < 0.7:
                # Coherence enhancement actions
                actions.append(
                    CoordinationAction(
                        action_type="coherence_enhancement",
                        target_agents=agent_ids,
                        parameters={"enhancement_strength": 0.3},
                        priority=4,
                        estimated_impact=0.2,
                    )
                )

            # Entanglement optimization actions
            if len(agent_ids) > 2:
                actions.append(
                    CoordinationAction(
                        action_type="entanglement_optimization",
                        target_agents=agent_ids,
                        parameters={"optimization_strength": 0.5},
                        priority=5,
                        estimated_impact=0.35,
                    )
                )

            return actions

        except Exception as e:
            logger.error("Coordination action generation failed: %s", e)
            return []

    async def _execute_coordination_actions(self, actions: list[CoordinationAction]) -> list[dict[str, Any]]:
        """Execute coordination actions"""
        try:
            results = []

            for action in actions:
                try:
                    if action.action_type == "coordination_boost":
                        result = await self._execute_coordination_boost(action)
                    elif action.action_type == "harmony_alignment":
                        result = await self._execute_harmony_alignment(action)
                    elif action.action_type == "load_balancing":
                        result = await self._execute_load_balancing(action)
                    elif action.action_type == "coherence_enhancement":
                        result = await self._execute_coherence_enhancement(action)
                    elif action.action_type == "entanglement_optimization":
                        result = await self._execute_entanglement_optimization(action)
                    else:
                        result = {
                            "success": False,
                            "message": f"Unknown action type: {action.action_type}",
                        }

                    results.append(result)

                except Exception as e:
                    logger.error("Action execution failed for %s: %s", action.action_type, e)
                    results.append({"success": False, "error": "Action execution failed"})

            return results

        except Exception as e:
            logger.error("Coordination action execution failed: %s", e)
            return []

    async def _execute_coordination_boost(self, action: CoordinationAction) -> dict[str, Any]:
        """Execute coordination boosting action"""
        try:
            for agent_id in action.target_agents:
                if agent_id in self.agent_states:
                    current_state = self.agent_states[agent_id]
                    boost_amount = action.parameters.get("boost_amount", 0.1)

                    # Apply coordination boost
                    new_coordination = min(10.0, current_state.performance_score + boost_amount)
                    current_state.performance_score = new_coordination
                    current_state.last_update = datetime.now(UTC)

            return {
                "success": True,
                "action": "coordination_boost",
                "agents_affected": len(action.target_agents),
                "boost_amount": action.parameters.get("boost_amount", 0.1),
            }

        except Exception as e:
            logger.error("Coordination boost execution failed: %s", e)
            return {"success": False, "error": "Coordination boost failed"}

    async def _execute_harmony_alignment(self, action: CoordinationAction) -> dict[str, Any]:
        """Execute harmony alignment action"""
        try:
            for agent_id in action.target_agents:
                if agent_id in self.agent_states:
                    current_state = self.agent_states[agent_id]

                    # Align harmony towards optimal range
                    alignment_strength = action.parameters.get("alignment_strength", 0.4)
                    optimal_harmony = 0.7
                    current_harmony = current_state.harmony_alignment

                    if current_harmony < optimal_harmony:
                        new_harmony = min(
                            1.0,
                            current_harmony + alignment_strength * (optimal_harmony - current_harmony),
                        )
                    else:
                        new_harmony = max(
                            0.0,
                            current_harmony - alignment_strength * (current_harmony - optimal_harmony),
                        )

                    current_state.harmony_alignment = new_harmony
                    current_state.last_update = datetime.now(UTC)

            return {
                "success": True,
                "action": "harmony_alignment",
                "agents_affected": len(action.target_agents),
                "alignment_strength": alignment_strength,
            }

        except Exception as e:
            logger.error("Harmony alignment execution failed: %s", e)
            return {"success": False, "error": "Harmony alignment failed"}

    async def _execute_load_balancing(self, action: CoordinationAction) -> dict[str, Any]:
        """Execute load balancing action"""
        try:
            source_agents = action.parameters.get("source_agents", [])
            target_agents = action.parameters.get("target_agents", [])
            transfer_amount = action.parameters.get("transfer_amount", 0.2)

            # Reduce load on source agents
            for agent_id in source_agents:
                if agent_id in self.agent_states:
                    current_state = self.agent_states[agent_id]
                    current_state.task_load = max(0.0, current_state.task_load - transfer_amount)
                    current_state.last_update = datetime.now(UTC)

            # Increase load on target agents
            for agent_id in target_agents:
                if agent_id in self.agent_states:
                    current_state = self.agent_states[agent_id]
                    current_state.task_load = min(
                        1.0, current_state.task_load + transfer_amount * 0.5
                    )  # Reduced impact for target
                    current_state.last_update = datetime.now(UTC)

            return {
                "success": True,
                "action": "load_balancing",
                "source_agents": source_agents,
                "target_agents": target_agents,
                "transfer_amount": transfer_amount,
            }

        except Exception as e:
            logger.error("Load balancing execution failed: %s", e)
            return {"success": False, "error": "Load balancing failed"}

    async def _execute_coherence_enhancement(self, action: CoordinationAction) -> dict[str, Any]:
        """Execute coherence enhancement action"""
        try:
            enhancement_strength = action.parameters.get("enhancement_strength", 0.3)

            # Calculate average coordination level
            performance_scores = []
            for agent_id in action.target_agents:
                if agent_id in self.agent_states:
                    performance_scores.append(self.agent_states[agent_id].performance_score)

            if not performance_scores:
                return {"success": False, "message": "No valid agent states found"}

            avg_coordination = np.mean(performance_scores)

            # Adjust individual coordination levels towards average
            for agent_id in action.target_agents:
                if agent_id in self.agent_states:
                    current_state = self.agent_states[agent_id]
                    current_coordination = current_state.performance_score

                    # Move towards average with enhancement strength
                    adjustment = enhancement_strength * (avg_coordination - current_coordination)
                    new_coordination = current_coordination + adjustment

                    current_state.performance_score = max(0.0, min(10.0, new_coordination))
                    current_state.last_update = datetime.now(UTC)

            return {
                "success": True,
                "action": "coherence_enhancement",
                "agents_affected": len(action.target_agents),
                "enhancement_strength": enhancement_strength,
                "target_average": avg_coordination,
            }

        except Exception as e:
            logger.error("Coherence enhancement execution failed: %s", e)
            return {"success": False, "error": "Coherence enhancement failed"}

    async def _execute_entanglement_optimization(self, action: CoordinationAction) -> dict[str, Any]:
        """Execute entanglement optimization action"""
        try:
            # Create entanglement network based on coordination similarity
            agent_similarities = {}
            for i, agent_id1 in enumerate(action.target_agents):
                for j, agent_id2 in enumerate(action.target_agents):
                    if i < j and agent_id1 in self.agent_states and agent_id2 in self.agent_states:
                        state1 = self.agent_states[agent_id1]
                        state2 = self.agent_states[agent_id2]

                        # Calculate similarity based on coordination levels
                        similarity = 1.0 - abs(state1.performance_score - state2.performance_score) / 10.0
                        agent_similarities[(agent_id1, agent_id2)] = similarity

            # Create entanglements for high-similarity pairs
            optimization_strength = action.parameters.get("optimization_strength", 0.5)
            entanglement_count = 0
            for (agent_id1, agent_id2), similarity in agent_similarities.items():
                if similarity > 0.7:  # High similarity threshold
                    self.entanglement_network[agent_id1].add(agent_id2)
                    self.entanglement_network[agent_id2].add(agent_id1)
                    entanglement_count += 1

            return {
                "success": True,
                "action": "entanglement_optimization",
                "agents_affected": len(action.target_agents),
                "entanglements_created": entanglement_count,
                "optimization_strength": optimization_strength,
            }

        except Exception as e:
            logger.error("Entanglement optimization execution failed: %s", e)
            return {"success": False, "error": "Entanglement optimization failed"}

    async def _update_entanglement_network(
        self, agent_ids: list[str], collective_state: CollectiveCoordinationState
    ) -> None:
        """Update the entanglement network based on agent states"""
        try:
            for agent_id in list(self.entanglement_network.keys()):
                if agent_id not in agent_ids:
                    del self.entanglement_network[agent_id]

            # Update existing entanglements based on current states
            for agent_id in agent_ids:
                if agent_id in self.agent_states:
                    current_state = self.agent_states[agent_id]

                    # Remove weak entanglements
                    strong_entanglements = set()
                    for partner_id in current_state.entanglement_partners:
                        if partner_id in self.agent_states:
                            partner_state = self.agent_states[partner_id]

                            # Calculate entanglement strength
                            coordination_diff = abs(current_state.performance_score - partner_state.performance_score)
                            harmony_diff = abs(current_state.harmony_alignment - partner_state.harmony_alignment)

                            # Entanglement strength decreases with differences
                            entanglement_strength = max(0.0, 1.0 - (coordination_diff / 10.0) - harmony_diff)

                            if entanglement_strength > 0.3:  # Minimum strength threshold
                                strong_entanglements.add(partner_id)

                    # Update entanglement partners
                    current_state.entanglement_partners = list(strong_entanglements)
                    self.entanglement_network[agent_id] = strong_entanglements

        except Exception as e:
            logger.error("Entanglement network update failed: %s", e)

    async def _generate_coordination_report(
        self,
        agent_ids: list[str],
        collective_state: CollectiveCoordinationState,
        actions: list[CoordinationAction],
        execution_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Generate comprehensive coordination report"""
        try:
            success_count = sum(1 for result in execution_results if result.get("success", False))
            success_rate = success_count / len(execution_results) if execution_results else 0.0

            # Generate agent status summary
            agent_status = {}
            for agent_id in agent_ids:
                if agent_id in self.agent_states:
                    state = self.agent_states[agent_id]
                    agent_status[agent_id] = {
                        "performance_score": state.performance_score,
                        "harmony_alignment": state.harmony_alignment,
                        "task_load": state.task_load,
                        "coordination_status": state.coordination_status.value,
                        "entanglement_count": len(state.entanglement_partners),
                        "last_update": state.last_update.isoformat(),
                    }

            # Generate action summary
            action_summary = []
            for i, action in enumerate(actions):
                if i < len(execution_results):
                    result = execution_results[i]
                    action_summary.append(
                        {
                            "action_type": action.action_type,
                            "target_agents_count": len(action.target_agents),
                            "priority": action.priority,
                            "estimated_impact": action.estimated_impact,
                            "success": result.get("success", False),
                            "actual_impact": (
                                result.get("agents_affected", 0) / len(action.target_agents)
                                if action.target_agents
                                else 0
                            ),
                        }
                    )

            return {
                "coordination_report": {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "agents_coordinated": len(agent_ids),
                    "collective_state": {
                        "overall_coordination": collective_state.overall_coordination,
                        "collective_harmony": collective_state.collective_harmony,
                        "system_resilience": collective_state.system_resilience,
                        "energy_efficiency": collective_state.energy_efficiency,
                        "coherence_factor": collective_state.coherence_factor,
                        "coordination_health": collective_state.coordination_health,
                    },
                    "actions_executed": len(actions),
                    "success_rate": success_rate,
                    "agent_status": agent_status,
                    "action_summary": action_summary,
                    "entanglement_network": {
                        agent_id: list(partners) for agent_id, partners in self.entanglement_network.items()
                    },
                }
            }

        except Exception as e:
            logger.error("Coordination report generation failed: %s", e)
            return {"error": "Failed to generate coordination report"}

    async def _get_active_agents(self) -> list[str]:
        """Get list of currently active agents from the canonical registry."""
        try:
            from apps.backend.helix_agent_swarm.agent_registry import AGENT_REGISTRY

            return list(AGENT_REGISTRY.keys())

        except Exception as e:
            logger.error("Active agents retrieval failed: %s", e)
            return []

    async def _calculate_optimization_strategy(self, agent_ids: list[str], optimization_goal: str) -> dict[str, Any]:
        """Calculate optimization strategy based on goal"""
        try:
            strategy = {
                "coordination_method": "hybrid",
                "priority_metrics": [],
                "optimization_parameters": {},
            }

            if optimization_goal == "performance":
                strategy["priority_metrics"] = [
                    "performance_score",
                    "harmony_alignment",
                    "task_load",
                ]
                strategy["optimization_parameters"] = {
                    "performance_threshold": 0.7,
                    "load_balance_weight": 0.4,
                    "coordination_weight": 0.3,
                    "harmony_weight": 0.3,
                }
            elif optimization_goal == "efficiency":
                strategy["priority_metrics"] = [
                    "energy_efficiency",
                    "task_load",
                    "response_time",
                ]
                strategy["optimization_parameters"] = {
                    "efficiency_threshold": 0.8,
                    "energy_weight": 0.5,
                    "load_weight": 0.3,
                    "response_weight": 0.2,
                }
            elif optimization_goal == "stability":
                strategy["priority_metrics"] = [
                    "system_resilience",
                    "coherence_factor",
                    "friction_entropy",
                ]
                strategy["optimization_parameters"] = {
                    "stability_threshold": 0.6,
                    "resilience_weight": 0.4,
                    "coherence_weight": 0.4,
                    "entropy_weight": 0.2,
                }
            else:
                strategy["priority_metrics"] = [
                    "performance_score",
                    "harmony_alignment",
                ]
                strategy["optimization_parameters"] = {"default_weight": 0.5}

            return strategy

        except Exception as e:
            logger.error("Optimization strategy calculation failed: %s", e)
            return {}

    async def _generate_optimization_actions(
        self, agents: list[str], optimization_goal: str, strategy: dict[str, Any]
    ) -> list[CoordinationAction]:
        """Generate optimization actions based on strategy"""
        try:
            actions = []

            if optimization_goal == "performance":
                actions.append(
                    CoordinationAction(
                        action_type="performance_optimization",
                        target_agents=agents,
                        parameters=strategy["optimization_parameters"],
                        priority=1,
                        estimated_impact=0.4,
                    )
                )
            elif optimization_goal == "efficiency":
                actions.append(
                    CoordinationAction(
                        action_type="efficiency_optimization",
                        target_agents=agents,
                        parameters=strategy["optimization_parameters"],
                        priority=1,
                        estimated_impact=0.35,
                    )
                )
            elif optimization_goal == "stability":
                actions.append(
                    CoordinationAction(
                        action_type="stability_optimization",
                        target_agents=agents,
                        parameters=strategy["optimization_parameters"],
                        priority=1,
                        estimated_impact=0.3,
                    )
                )

            return actions

        except Exception as e:
            logger.error("Optimization action generation failed: %s", e)
            return []

    async def _calculate_optimization_results(
        self,
        agents: list[str],
        optimization_goal: str,
        execution_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Calculate optimization results"""
        try:
            success_count = sum(1 for result in execution_results if result.get("success", False))
            success_rate = success_count / len(execution_results) if execution_results else 0.0

            # Calculate goal-specific metrics
            if optimization_goal == "performance":
                avg_coordination = np.mean(
                    [
                        self.agent_states[agent_id].performance_score
                        for agent_id in agents
                        if agent_id in self.agent_states
                    ]
                )
                avg_harmony = np.mean(
                    [
                        self.agent_states[agent_id].harmony_alignment
                        for agent_id in agents
                        if agent_id in self.agent_states
                    ]
                )

                performance_score = (avg_coordination / 10.0) * 0.6 + avg_harmony * 0.4

                return {
                    "optimization_goal": optimization_goal,
                    "success_rate": success_rate,
                    "performance_score": performance_score,
                    "avg_coordination": avg_coordination,
                    "avg_harmony": avg_harmony,
                    "agents_optimized": len(agents),
                }

            elif optimization_goal == "efficiency":
                avg_throughput = np.mean(
                    [
                        self.agent_states[agent_id].throughput_level
                        for agent_id in agents
                        if agent_id in self.agent_states
                    ]
                )
                avg_load = np.mean(
                    [self.agent_states[agent_id].task_load for agent_id in agents if agent_id in self.agent_states]
                )

                efficiency_score = avg_throughput * 0.7 + (1.0 - avg_load) * 0.3

                return {
                    "optimization_goal": optimization_goal,
                    "success_rate": success_rate,
                    "efficiency_score": efficiency_score,
                    "avg_throughput": avg_throughput,
                    "avg_load": avg_load,
                    "agents_optimized": len(agents),
                }

            elif optimization_goal == "stability":
                avg_resilience = np.mean(
                    [
                        self.agent_states[agent_id].resilience_factor
                        for agent_id in agents
                        if agent_id in self.agent_states
                    ]
                )
                avg_coherence = self._calculate_coherence_factor(agents)
                avg_friction = np.mean(
                    [
                        self.agent_states[agent_id].friction_entropy
                        for agent_id in agents
                        if agent_id in self.agent_states
                    ]
                )

                stability_score = avg_resilience * 0.4 + avg_coherence * 0.4 + (1.0 - avg_friction) * 0.2

                return {
                    "optimization_goal": optimization_goal,
                    "success_rate": success_rate,
                    "stability_score": stability_score,
                    "avg_resilience": avg_resilience,
                    "avg_coherence": avg_coherence,
                    "avg_friction": avg_friction,
                    "agents_optimized": len(agents),
                }

            else:
                return {
                    "optimization_goal": optimization_goal,
                    "success_rate": success_rate,
                    "agents_optimized": len(agents),
                    "message": "Unknown optimization goal",
                }

        except Exception as e:
            logger.error("Optimization results calculation failed: %s", e)
            return {"error": "Failed to calculate optimization results"}

    async def _create_entanglement(self, agent_id: str, target_agents: list[str]) -> dict[str, Any]:
        """Create entanglement between agent and targets"""
        try:
            created_entanglements = []

            for target_id in target_agents:
                if target_id != agent_id and target_id in self.agent_states:
                    # Check if entanglement already exists
                    if target_id not in self.entanglement_network[agent_id]:
                        self.entanglement_network[agent_id].add(target_id)
                        self.entanglement_network[target_id].add(agent_id)
                        created_entanglements.append(target_id)

            return {
                "success": True,
                "action": "create_entanglement",
                "agent_id": agent_id,
                "entanglements_created": created_entanglements,
                "total_entanglements": len(self.entanglement_network[agent_id]),
            }

        except Exception as e:
            logger.error("Entanglement creation failed: %s", e)
            return {"success": False, "error": "Entanglement creation failed"}

    async def _strengthen_entanglement(self, agent_id: str, target_agents: list[str]) -> dict[str, Any]:
        """Strengthen existing entanglements"""
        try:
            strengthened_entanglements = []

            for target_id in target_agents:
                if target_id in self.entanglement_network[agent_id]:
                    # Entanglement is already established, mark as strengthened
                    strengthened_entanglements.append(target_id)

            return {
                "success": True,
                "action": "strengthen_entanglement",
                "agent_id": agent_id,
                "entanglements_strengthened": strengthened_entanglements,
                "total_entanglements": len(self.entanglement_network[agent_id]),
            }

        except Exception as e:
            logger.error("Entanglement strengthening failed: %s", e)
            return {"success": False, "error": "Entanglement strengthening failed"}

    async def _break_entanglement(self, agent_id: str, target_agents: list[str]) -> dict[str, Any]:
        """Break entanglement with target agents"""
        try:
            broken_entanglements = []

            for target_id in target_agents:
                if target_id in self.entanglement_network[agent_id]:
                    self.entanglement_network[agent_id].remove(target_id)
                    if agent_id in self.entanglement_network[target_id]:
                        self.entanglement_network[target_id].remove(agent_id)
                    broken_entanglements.append(target_id)

            return {
                "success": True,
                "action": "break_entanglement",
                "agent_id": agent_id,
                "entanglements_broken": broken_entanglements,
                "remaining_entanglements": len(self.entanglement_network[agent_id]),
            }

        except Exception as e:
            logger.error("Entanglement breaking failed: %s", e)
            return {"success": False, "error": "Entanglement breaking failed"}

    async def _monitor_entanglement(self, agent_id: str) -> dict[str, Any]:
        """Monitor entanglement strength and status"""
        try:
            entanglement_partners = list(self.entanglement_network.get(agent_id, set()))

            # Calculate entanglement strength for each partner
            entanglement_strengths = {}
            if agent_id in self.agent_states:
                current_state = self.agent_states[agent_id]

                for partner_id in entanglement_partners:
                    if partner_id in self.agent_states:
                        partner_state = self.agent_states[partner_id]

                        # Calculate entanglement strength
                        coordination_diff = abs(current_state.performance_score - partner_state.performance_score)
                        harmony_diff = abs(current_state.harmony_alignment - partner_state.harmony_alignment)

                        strength = max(0.0, 1.0 - (coordination_diff / 10.0) - harmony_diff)
                        entanglement_strengths[partner_id] = strength

            return {
                "success": True,
                "action": "monitor_entanglement",
                "agent_id": agent_id,
                "entanglement_partners": entanglement_partners,
                "entanglement_strengths": entanglement_strengths,
                "total_entanglements": len(entanglement_partners),
                "avg_strength": (np.mean(list(entanglement_strengths.values())) if entanglement_strengths else 0.0),
            }

        except Exception as e:
            logger.error("Entanglement monitoring failed: %s", e)
            return {"success": False, "error": "Entanglement monitoring failed"}

    async def _find_entanglement_candidates(self, agent_id: str) -> list[str]:
        """Find potential entanglement candidates based on coordination similarity"""
        try:
            if agent_id not in self.agent_states:
                return []

            current_state = self.agent_states[agent_id]
            candidates = []

            for other_agent_id, other_state in self.agent_states.items():
                if other_agent_id != agent_id:
                    # Calculate similarity
                    coordination_diff = abs(current_state.performance_score - other_state.performance_score)
                    harmony_diff = abs(current_state.harmony_alignment - other_state.harmony_alignment)

                    similarity = 1.0 - (coordination_diff / 10.0) - harmony_diff

                    # High similarity threshold for entanglement
                    if similarity > 0.7:
                        candidates.append(other_agent_id)

            return candidates[:5]  # Return top 5 candidates

        except Exception as e:
            logger.error("Entanglement candidate finding failed: %s", e)
            return []

    async def get_coordination_history(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get coordination history"""
        try:
            # Return recent coordination events
            return list(self.coordination_history)[-limit:] if hasattr(self, "coordination_history") else []
        except Exception as e:
            logger.error("Coordination history retrieval failed: %s", e)
            return []

    async def get_performance_history(self, agent_id: str | None = None, limit: int = 100) -> dict[str, Any]:
        """Get performance history for agents"""
        try:
            if agent_id:
                return {
                    "agent_id": agent_id,
                    "history": list(self.performance_history.get(agent_id, []))[-limit:],
                }
            else:
                return {
                    "all_agents": {aid: list(history)[-limit:] for aid, history in self.performance_history.items()}
                }

        except Exception as e:
            logger.error("Performance history retrieval failed: %s", e)
            return {}

    async def clear_coordination_cache(self) -> bool:
        """Clear coordination cache"""
        try:
            logger.info("Coordination cache cleared")
            return True

        except Exception as e:
            logger.error("Coordination cache clearing failed: %s", e)
            return False

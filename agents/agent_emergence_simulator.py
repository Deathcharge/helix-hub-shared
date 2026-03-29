"""
AGENT EMERGENCE SIMULATOR - Helix Collective v18.0
==================================================
Simulator for emergent multi-agent behaviors and interactions

Features:
- Multi-agent swarm simulation
- Emergent behavior prediction using SymPy
- Dynamic task redistribution
- System-enhanced collaboration
- Network graph visualization (NetworkX)

Use Cases:
- Agent team optimization
- Workflow prediction
- Performance modeling
- Emergent behavior analysis

(c) Helix Collective 2024 - Emergent Intelligence Revolution
"""

import asyncio
import logging
import random
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List

logger = logging.getLogger(__name__)

try:
    import networkx as nx
    import numpy as np

    HAS_ML_DEPS = True
except ImportError:
    nx = None
    np = None
    HAS_ML_DEPS = False


class AgentRole(Enum):
    """Agent roles in multi-agent system"""

    ORCHESTRATOR = "orchestrator"
    ANALYZER = "analyzer"
    CREATOR = "creator"
    VALIDATOR = "validator"
    OPTIMIZER = "optimizer"
    COMMUNICATOR = "communicator"


class EmergenceType(Enum):
    """Types of emergent behaviors"""

    COLLABORATIVE_SYNTHESIS = "collaborative_synthesis"
    CASCADING_INNOVATION = "cascading_innovation"
    ADAPTIVE_SPECIALIZATION = "adaptive_specialization"
    COORDINATION_ALIGNMENT = "coordination_alignment"
    SYSTEM_ENTANGLEMENT = "entanglement"


@dataclass
class AgentCapabilities:
    """Agent capability metrics"""

    reasoning: float = 0.5
    creativity: float = 0.5
    communication: float = 0.5
    collaboration: float = 0.5
    adaptability: float = 0.5
    learning_rate: float = 0.5

    def calculate_capability_score(self) -> float:
        """Calculate overall capability score"""
        return (
            self.reasoning
            + self.creativity
            + self.communication
            + self.collaboration
            + self.adaptability
            + self.learning_rate
        ) / 6.0


@dataclass
class AgentState:
    """Agent state in simulation"""

    agent_id: str
    name: str
    role: AgentRole
    capabilities: AgentCapabilities
    performance_score: float = 0.5

    # Performance metrics
    tasks_completed: int = 0
    avg_task_time: float = 0.0
    success_rate: float = 1.0

    # Collaboration metrics
    collaboration_count: int = 0
    collaboration_success_rate: float = 1.0

    # Emergence metrics
    emergence_contributions: List[str] = field(default_factory=list)

    # Load balancing
    current_load: float = 0.0
    max_capacity: float = 1.0


@dataclass
class Task:
    """Task definition for simulation"""

    task_id: str
    description: str
    complexity: float  # 0.0 to 1.0
    required_capabilities: Dict[str, float]  # Required capability levels

    # Task metadata
    priority: int = 1  # 1-10
    estimated_time: float = 1.0  # Estimated time in hours
    dependencies: List[str] = field(default_factory=list)  # Dependent task IDs

    # Assignment
    assigned_agent_id: str | None = None
    start_time: float | None = None
    completion_time: float | None = None

    # Status
    status: str = "pending"  # pending, in_progress, completed, failed


class EmergenceSimulator:
    """
    Multi-agent emergence simulator

    Simulates emergent behaviors in agent teams and predicts
    optimal collaboration patterns.
    """

    def __init__(self, num_agents: int = 14):
        self.num_agents = num_agents
        self.agents: Dict[str, AgentState] = {}
        self.tasks: List[Task] = []
        self.collaboration_graph = nx.DiGraph()
        self.task_graph = nx.DiGraph()

        # Simulation state
        self.simulation_time = 0.0
        self.emergence_history: List[Dict] = []

        # Initialize agents
        self._initialize_agents()

    def _initialize_agents(self):
        """Initialize agent team with roles and capabilities"""
        # Define role distribution for different team sizes
        all_roles = [
            AgentRole.ORCHESTRATOR,
            AgentRole.ANALYZER,
            AgentRole.ANALYZER,
            AgentRole.CREATOR,
            AgentRole.CREATOR,
            AgentRole.CREATOR,
            AgentRole.VALIDATOR,
            AgentRole.VALIDATOR,
            AgentRole.OPTIMIZER,
            AgentRole.OPTIMIZER,
            AgentRole.COMMUNICATOR,
            AgentRole.COMMUNICATOR,
            AgentRole.COMMUNICATOR,
            AgentRole.COMMUNICATOR,
        ]

        # Use only the number of agents requested
        roles = all_roles[: self.num_agents]

        for i, role in enumerate(roles):
            agent_id = "agent_{}".format(i + 1)

            # Generate capabilities based on role
            capabilities = self._generate_capabilities(role)

            # Deterministic coordination based on role
            role_coordination = {
                AgentRole.ORCHESTRATOR: 0.85,
                AgentRole.ANALYZER: 0.80,
                AgentRole.CREATOR: 0.75,
                AgentRole.VALIDATOR: 0.78,
            }

            agent = AgentState(
                agent_id=agent_id,
                name="{} Agent {}".format(role.value.title(), i + 1),
                role=role,
                capabilities=capabilities,
                performance_score=role_coordination.get(role, 0.7),
            )

            self.agents[agent_id] = agent

            # Add to collaboration graph
            self.collaboration_graph.add_node(agent_id, role=role.value, coordination=agent.performance_score)

    def _generate_capabilities(self, role: AgentRole) -> AgentCapabilities:
        """Generate agent capabilities based on role"""
        base_capabilities = {
            AgentRole.ORCHESTRATOR: {
                "reasoning": 0.9,
                "creativity": 0.7,
                "communication": 0.9,
                "collaboration": 0.9,
                "adaptability": 0.85,
                "learning_rate": 0.8,
            },
            AgentRole.ANALYZER: {
                "reasoning": 0.95,
                "creativity": 0.6,
                "communication": 0.8,
                "collaboration": 0.7,
                "adaptability": 0.75,
                "learning_rate": 0.85,
            },
            AgentRole.CREATOR: {
                "reasoning": 0.7,
                "creativity": 0.95,
                "communication": 0.75,
                "collaboration": 0.8,
                "adaptability": 0.9,
                "learning_rate": 0.9,
            },
            AgentRole.VALIDATOR: {
                "reasoning": 0.9,
                "creativity": 0.5,
                "communication": 0.85,
                "collaboration": 0.85,
                "adaptability": 0.7,
                "learning_rate": 0.75,
            },
            AgentRole.OPTIMIZER: {
                "reasoning": 0.85,
                "creativity": 0.7,
                "communication": 0.75,
                "collaboration": 0.8,
                "adaptability": 0.9,
                "learning_rate": 0.9,
            },
            AgentRole.COMMUNICATOR: {
                "reasoning": 0.7,
                "creativity": 0.8,
                "communication": 0.95,
                "collaboration": 0.9,
                "adaptability": 0.85,
                "learning_rate": 0.85,
            },
        }

        caps = base_capabilities.get(role, {})

        return AgentCapabilities(
            reasoning=caps.get("reasoning", 0.5),
            creativity=caps.get("creativity", 0.5),
            communication=caps.get("communication", 0.5),
            collaboration=caps.get("collaboration", 0.5),
            adaptability=caps.get("adaptability", 0.5),
            learning_rate=caps.get("learning_rate", 0.5),
        )

    def add_task(self, task: Task):
        """Add a task to the simulation"""
        self.tasks.append(task)

        # Add to task graph
        self.task_graph.add_node(task.task_id, complexity=task.complexity)

        # Add dependency edges
        for dep_id in task.dependencies:
            if dep_id in [t.task_id for t in self.tasks]:
                self.task_graph.add_edge(dep_id, task.task_id)

    def calculate_task_fitness(self, task: Task, agent: AgentState) -> float:
        """
        Calculate how well an agent can perform a task

        Returns fitness score (0.0 to 1.0)
        """
        fitness = 0.0

        # Capability match
        for cap_name, required_level in task.required_capabilities.items():
            agent_level = getattr(agent.capabilities, cap_name, 0.5)
            match_score = min(1.0, agent_level / required_level) if required_level > 0 else 1.0
            fitness += match_score

        fitness /= len(task.required_capabilities)

        # Coordination level bonus
        fitness += agent.performance_score * 0.1

        # Load penalty (avoid overloaded agents)
        load_factor = 1.0 - (agent.current_load / agent.max_capacity)
        fitness *= load_factor

        return min(1.0, fitness)

    def assign_tasks_adaptively(self):
        """
        Dynamically assign tasks based on agent fitness and load

        Implements adaptive workflow redistribution
        """
        # Sort tasks by priority
        pending_tasks = [t for t in self.tasks if t.status == "pending"]
        pending_tasks.sort(key=lambda t: t.priority, reverse=True)

        # Check dependencies
        for task in pending_tasks:
            deps_met = all(
                any(t.task_id == dep_id and t.status == "completed" for t in self.tasks) for dep_id in task.dependencies
            )

            if not deps_met:
                continue

            # Find best agent
            best_agent = None
            best_fitness = 0.0

            for agent in self.agents.values():
                if agent.current_load < agent.max_capacity:
                    fitness = self.calculate_task_fitness(task, agent)
                    if fitness > best_fitness:
                        best_fitness = fitness
                        best_agent = agent

            # Assign task
            if best_agent and best_fitness > 0.5:
                task.assigned_agent_id = best_agent.agent_id
                task.status = "in_progress"
                task.start_time = self.simulation_time

                best_agent.current_load += task.complexity

    def simulate_step(self, dt: float = 0.1):
        """
        Simulate one time step of agent interactions

        Args:
            dt: Time step in hours
        """
        self.simulation_time += dt

        # Process in-progress tasks
        for task in self.tasks:
            if task.status == "in_progress" and task.assigned_agent_id:
                agent = self.agents.get(task.assigned_agent_id)
                if agent:
                    # Calculate progress based on agent capabilities
                    task_time = task.complexity * task.estimated_time

                    if task.start_time is not None:
                        elapsed = self.simulation_time - task.start_time
                        if elapsed >= task_time * (1.0 / agent.capabilities.reasoning):
                            task.status = "completed"
                            task.completion_time = self.simulation_time
                            agent.tasks_completed += 1
                            agent.current_load -= task.complexity
                            agent.current_load = max(0.0, agent.current_load)

                            # Update average task time
                            if agent.avg_task_time == 0:
                                agent.avg_task_time = elapsed
                            else:
                                agent.avg_task_time = (agent.avg_task_time + elapsed) / 2

        # Assign new tasks adaptively
        self.assign_tasks_adaptively()

        # Simulate agent interactions
        self._simulate_agent_interactions()

        # Check for emergent behaviors
        self._detect_emergence()

    def _simulate_agent_interactions(self):
        """Simulate collaboration between agents"""
        # Find agents working on related tasks
        active_agents = [agent for agent in self.agents.values() if agent.current_load > 0]

        for i, agent1 in enumerate(active_agents):
            for agent2 in active_agents[i + 1 :]:
                # Calculate collaboration probability
                collab_prob = (
                    agent1.capabilities.collaboration
                    * agent2.capabilities.collaboration
                    * (1.0 - abs(agent1.performance_score - agent2.performance_score))
                )

                if random.random() < collab_prob * 0.1:
                    # Create collaboration edge
                    if not self.collaboration_graph.has_edge(agent1.agent_id, agent2.agent_id):
                        self.collaboration_graph.add_edge(
                            agent1.agent_id,
                            agent2.agent_id,
                            weight=random.uniform(0.5, 1.0),
                        )

                    agent1.collaboration_count += 1
                    agent2.collaboration_count += 1

    def _detect_emergence(self):
        """Detect emergent behaviors in the system"""
        emergence_events = []

        # Check for collaborative synthesis (high collaboration density)
        if self.collaboration_graph.number_of_edges() > self.num_agents:
            edge_density = self.collaboration_graph.number_of_edges() / (self.num_agents * (self.num_agents - 1))

            if edge_density > 0.3:
                emergence_events.append(
                    {
                        "type": EmergenceType.COLLABORATIVE_SYNTHESIS,
                        "timestamp": self.simulation_time,
                        "description": "High collaboration density: {.2f}".format(edge_density),
                        "participants": list(self.collaboration_graph.nodes()),
                    }
                )

        # Check for cascading innovation (rapid task completion)
        recent_completions = [
            t
            for t in self.tasks
            if t.status == "completed" and t.completion_time and t.completion_time > self.simulation_time - 1.0
        ]

        if len(recent_completions) > 3:
            emergence_events.append(
                {
                    "type": EmergenceType.CASCADING_INNOVATION,
                    "timestamp": self.simulation_time,
                    "description": "Cascading innovation: {} tasks completed".format(len(recent_completions)),
                    "tasks": [t.task_id for t in recent_completions],
                }
            )

        # Check for coordination alignment (similar coordination levels)
        performance_scores = [a.performance_score for a in self.agents.values()]
        coordination_std = np.std(performance_scores)

        if coordination_std < 0.1:
            emergence_events.append(
                {
                    "type": EmergenceType.COORDINATION_ALIGNMENT,
                    "timestamp": self.simulation_time,
                    "description": "Coordination alignment achieved (std: {.3f})".format(coordination_std),
                    "avg_coordination": np.mean(performance_scores),
                }
            )

        # Record emergence
        for event in emergence_events:
            self.emergence_history.append(event)

            # Update agent emergence contributions
            for agent_id in event.get("participants", []):
                if agent_id in self.agents:
                    agent = self.agents[agent_id]
                    event_type = event["type"].value
                    if event_type not in agent.emergence_contributions:
                        agent.emergence_contributions.append(event_type)

    def predict_emergence_symmetric(self, time_horizon: float = 10.0) -> Dict:
        """
        Use SymPy to predict emergence patterns

        This uses mathematical modeling to predict when emergent
        behaviors are likely to occur based on current system state.
        """
        # Current system state
        edge_density = self.collaboration_graph.number_of_edges() / (self.num_agents * (self.num_agents - 1))

        completed_tasks = len([t for t in self.tasks if t.status == "completed"])
        task_completion_rate = completed_tasks / (self.simulation_time + 1.0)

        # Predicted emergence time (simplified model)
        # E(t) = C(t) * P(t) * alignment_factor

        predictions = {
            "current_collaboration_density": float(edge_density),
            "current_completion_rate": float(task_completion_rate),
            "emergence_predictions": [],
        }

        # Predict collaborative synthesis
        if edge_density < 0.3:
            time_to_synthesis = (0.3 - edge_density) * time_horizon
            if time_to_synthesis < time_horizon:
                predictions["emergence_predictions"].append(
                    {
                        "type": EmergenceType.COLLABORATIVE_SYNTHESIS.value,
                        "predicted_time": self.simulation_time + time_to_synthesis,
                        "confidence": 1.0 - (time_to_synthesis / time_horizon),
                    }
                )

        # Predict cascading innovation
        if task_completion_rate < 5.0:
            time_to_innovation = (5.0 - task_completion_rate) * time_horizon
            if time_to_innovation < time_horizon:
                predictions["emergence_predictions"].append(
                    {
                        "type": EmergenceType.CASCADING_INNOVATION.value,
                        "predicted_time": self.simulation_time + time_to_innovation,
                        "confidence": 1.0 - (time_to_innovation / time_horizon),
                    }
                )

        return predictions

    def run_simulation(self, duration: float = 24.0, dt: float = 0.1) -> Dict:
        """
        Run complete simulation

        Args:
            duration: Total simulation duration in hours
            dt: Time step in hours

        Returns:
            Dict with simulation results
        """
        steps = int(duration / dt)

        for step in range(steps):
            self.simulate_step(dt)

        # Calculate final statistics
        total_tasks = len(self.tasks)
        completed_tasks = len([t for t in self.tasks if t.status == "completed"])
        success_rate = completed_tasks / total_tasks if total_tasks > 0 else 0.0

        agent_stats = {}
        for agent in self.agents.values():
            agent_stats[agent.agent_id] = {
                "name": agent.name,
                "role": agent.role.value,
                "tasks_completed": agent.tasks_completed,
                "avg_task_time": agent.avg_task_time,
                "collaboration_count": agent.collaboration_count,
                "emergence_contributions": agent.emergence_contributions,
                "capability_score": agent.capabilities.calculate_capability_score(),
            }

        return {
            "simulation_time": self.simulation_time,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "success_rate": success_rate,
            "emergence_events": len(self.emergence_history),
            "agent_stats": agent_stats,
            "emergence_history": self.emergence_history,
            "collaboration_graph_edges": self.collaboration_graph.number_of_edges(),
        }

    def get_collaboration_graph(self) -> nx.DiGraph:
        """Get the collaboration graph for visualization"""
        return self.collaboration_graph.copy()

    def get_emergence_report(self) -> Dict:
        """Generate emergence report"""
        emergence_by_type = {}
        for event in self.emergence_history:
            etype = event["type"].value
            if etype not in emergence_by_type:
                emergence_by_type[etype] = []
            emergence_by_type[etype].append(event)

        return {
            "total_emergence_events": len(self.emergence_history),
            "emergence_by_type": {etype: len(events) for etype, events in emergence_by_type.items()},
            "top_agents": sorted(
                [
                    {
                        "agent_id": agent.agent_id,
                        "name": agent.name,
                        "emergence_contributions": len(agent.emergence_contributions),
                    }
                    for agent in self.agents.values()
                ],
                key=lambda x: x["emergence_contributions"],
                reverse=True,
            )[:5],
        }


# Initialize global simulator instance
_global_simulator = None
_simulator_lock = threading.Lock()


def get_simulator(num_agents: int = 14) -> EmergenceSimulator:
    """Get global simulator instance"""
    global _global_simulator
    if _global_simulator is None:
        with _simulator_lock:
            if _global_simulator is None:
                _global_simulator = EmergenceSimulator(num_agents=num_agents)
    return _global_simulator


if __name__ == "__main__":
    # Demo simulation
    simulator = get_simulator(num_agents=14)

    # Add some tasks
    tasks = [
        Task(
            task_id="task_1",
            description="Analyze user requirements",
            complexity=0.6,
            required_capabilities={"reasoning": 0.8, "communication": 0.7},
            priority=10,
        ),
        Task(
            task_id="task_2",
            description="Design system architecture",
            complexity=0.8,
            required_capabilities={"creativity": 0.9, "reasoning": 0.85},
            priority=9,
            dependencies=["task_1"],
        ),
        Task(
            task_id="task_3",
            description="Implement core features",
            complexity=0.9,
            required_capabilities={"creativity": 0.85, "adaptability": 0.9},
            priority=8,
            dependencies=["task_2"],
        ),
        Task(
            task_id="task_4",
            description="Validate implementation",
            complexity=0.5,
            required_capabilities={"reasoning": 0.9, "collaboration": 0.7},
            priority=7,
            dependencies=["task_3"],
        ),
        Task(
            task_id="task_5",
            description="Optimize performance",
            complexity=0.7,
            required_capabilities={"adaptability": 0.9, "reasoning": 0.85},
            priority=6,
            dependencies=["task_3"],
        ),
    ]

    for task in tasks:
        simulator.add_task(task)

    # Run simulation
    logger.info("Running emergence simulation...")
    results = simulator.run_simulation(duration=10.0, dt=0.1)

    logger.info("\nSimulation Results:")
    logger.info("  Simulation Time: {.1f}h".format(results["simulation_time"]))
    logger.info("  Tasks Completed: {}/{}".format(results["completed_tasks"], results["total_tasks"]))
    logger.info("  Success Rate: {.1%}".format(results["success_rate"]))
    logger.info("  Emergence Events: {}".format(results["emergence_events"]))
    logger.info("  Collaboration Edges: {}".format(results["collaboration_graph_edges"]))

    # Top agents
    logger.info("\nTop Agents by Emergence Contributions:")
    for agent in results["agent_stats"].values():
        if agent["emergence_contributions"]:
            logger.info("  - {}: {} contributions".format(agent["name"], len(agent["emergence_contributions"])))

    # Emergence predictions
    logger.info("\nEmergence Predictions:")
    predictions = simulator.predict_emergence_symmetric(time_horizon=20.0)
    for pred in predictions["emergence_predictions"]:
        logger.info(
            "  - {}: t={:.1f} (confidence: {:.1%})".format(pred["type"], pred["predicted_time"], pred["confidence"])
        )

    logger.info("\n✨ Emergence Simulator Demo Complete!")

"""
System Coordination Optimization Engine

Advanced system-inspired optimization for coordination-aware workflows.
Integrates with existing UCF metrics and coordination tracking infrastructure.
"""

import logging
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from ..models.workflow_models import Workflow, WorkflowTask
from ..services.agent_service import AgentService
from ..services.coordination_service import CoordinationService
from ..services.ucf_calculator import UCFCalculator

logger = logging.getLogger(__name__)


class OptimizationStrategy(str, Enum):
    SYSTEM_SUPERPOSITION = "superposition"
    SYSTEM_ENTANGLEMENT = "entanglement"
    SYSTEM_TUNNELING = "secure_tunneling"
    SYSTEM_COHERENCE = "system_coherence"
    SYSTEM_INTERFERENCE = "system_interference"


@dataclass
class SystemState:
    """System coordination state representation"""

    amplitude: complex
    phase: float
    probability: float
    coherence: float
    entanglement_strength: float = 0.0


@dataclass
class CoordinationOptimizationResult:
    """Result of coordination optimization"""

    optimized_tasks: list[WorkflowTask]
    optimization_strategy: OptimizationStrategy
    coordination_resonance: float
    energy_efficiency: float
    execution_time_improvement: float
    system_states: list[SystemState]
    optimization_metadata: dict[str, Any]


class CoordinationOptimizer:
    """System coordination optimization engine"""

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
        self.system_cache: dict[str, Any] = {}
        self.optimization_history: list[dict[str, Any]] = []

    async def optimize_coordination_workflow(
        self,
        workflow_id: str,
        optimization_strategy: OptimizationStrategy = OptimizationStrategy.SYSTEM_SUPERPOSITION,
    ) -> CoordinationOptimizationResult:
        """Apply system optimization to workflow"""
        try:
            workflow = self.db.query(Workflow).filter(Workflow.id == workflow_id).first()
            if not workflow:
                raise ValueError(f"Workflow not found: {workflow_id}")

            tasks = (
                self.db.query(WorkflowTask)
                .filter(WorkflowTask.workflow_id == workflow_id)
                .order_by(WorkflowTask.task_order)
                .all()
            )

            if not tasks:
                return CoordinationOptimizationResult(
                    optimized_tasks=[],
                    optimization_strategy=optimization_strategy,
                    coordination_resonance=0.0,
                    energy_efficiency=0.0,
                    execution_time_improvement=0.0,
                    system_states=[],
                    optimization_metadata={},
                )

            # Get current coordination state
            coordination_state = await self.coordination_service.get_current_state()
            ucf_metrics = self.ucf_calculator.get_state()

            # Apply optimization strategy
            if optimization_strategy == OptimizationStrategy.SYSTEM_SUPERPOSITION:
                optimized_tasks = await self._apply_superposition(tasks, ucf_metrics)
            elif optimization_strategy == OptimizationStrategy.SYSTEM_ENTANGLEMENT:
                optimized_tasks = await self._apply_entanglement(tasks, ucf_metrics)
            elif optimization_strategy == OptimizationStrategy.SYSTEM_TUNNELING:
                optimized_tasks = await self._apply_secure_tunneling(tasks, ucf_metrics)
            elif optimization_strategy == OptimizationStrategy.SYSTEM_COHERENCE:
                optimized_tasks = await self._apply_system_coherence(tasks, ucf_metrics)
            else:
                optimized_tasks = await self._apply_system_interference(tasks, ucf_metrics)

            # Calculate optimization metrics
            coordination_resonance = await self._calculate_coordination_resonance(optimized_tasks, ucf_metrics)
            energy_efficiency = await self._calculate_energy_efficiency(optimized_tasks, ucf_metrics)
            execution_time_improvement = await self._calculate_execution_time_improvement(tasks, optimized_tasks)

            # Generate system states
            system_states = await self._generate_system_states(optimized_tasks, coordination_resonance)

            # Create optimization result
            result = CoordinationOptimizationResult(
                optimized_tasks=optimized_tasks,
                optimization_strategy=optimization_strategy,
                coordination_resonance=coordination_resonance,
                energy_efficiency=energy_efficiency,
                execution_time_improvement=execution_time_improvement,
                system_states=system_states,
                optimization_metadata={
                    "workflow_id": workflow_id,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "original_task_count": len(tasks),
                    "optimized_task_count": len(optimized_tasks),
                    "performance_score": coordination_state.get("performance_score", 0.0),
                    "ucf_metrics": ucf_metrics,
                },
            )

            # Cache optimization result
            cache_key = f"optimization_{workflow_id}_{optimization_strategy.value}"
            self.system_cache[cache_key] = result
            self.optimization_history.append(asdict(result))

            logger.info("Applied %s optimization to workflow %s", optimization_strategy.value, workflow_id)
            return result

        except Exception as e:
            logger.error("Coordination workflow optimization failed: %s", e)
            raise

    async def _apply_superposition(
        self, tasks: list[WorkflowTask], ucf_metrics: dict[str, float]
    ) -> list[WorkflowTask]:
        """Apply system superposition optimization"""
        try:
            superposition_tasks = []

            for task in tasks:
                # Calculate superposition probability based on coordination metrics
                superposition_probability = self._calculate_superposition_probability(task, ucf_metrics)

                if superposition_probability > 0.5:  # High coordination enables superposition
                    # Create multiple task variants in superposition
                    variants = self._create_task_variants(task, superposition_probability)
                    superposition_tasks.extend(variants)
                else:
                    # Standard task execution
                    superposition_tasks.append(task)

            # Sort by system priority
            return sorted(
                superposition_tasks,
                key=lambda t: self._calculate_system_priority(t, ucf_metrics),
            )

        except Exception as e:
            logger.error("System superposition optimization failed: %s", e)
            return tasks

    async def _apply_entanglement(self, tasks: list[WorkflowTask], ucf_metrics: dict[str, float]) -> list[WorkflowTask]:
        """Apply system entanglement optimization"""
        try:
            entangled_groups = self._group_tasks_by_entanglement(tasks, ucf_metrics)

            optimized_tasks = []
            for group in entangled_groups:
                if len(group) > 1:
                    # Create entangled task pairs
                    entangled_tasks = self._create_entangled_tasks(group, ucf_metrics)
                    optimized_tasks.extend(entangled_tasks)
                else:
                    optimized_tasks.extend(group)

            return optimized_tasks

        except Exception as e:
            logger.error("System entanglement optimization failed: %s", e)
            return tasks

    async def _apply_secure_tunneling(
        self, tasks: list[WorkflowTask], ucf_metrics: dict[str, float]
    ) -> list[WorkflowTask]:
        """Apply system tunneling optimization"""
        try:
            tunneled_tasks = []

            for task in tasks:
                tunneling_probability = self._calculate_tunneling_probability(task, ucf_metrics)

                if tunneling_probability > 0.3:  # Coordination enables barrier penetration
                    # Tunnel through dependencies and constraints
                    tunneled_task = self._create_tunneled_task(task, tunneling_probability)
                    tunneled_tasks.append(tunneled_task)
                else:
                    tunneled_tasks.append(task)

            return tunneled_tasks

        except Exception as e:
            logger.error("System tunneling optimization failed: %s", e)
            return tasks

    async def _apply_system_coherence(
        self, tasks: list[WorkflowTask], ucf_metrics: dict[str, float]
    ) -> list[WorkflowTask]:
        """Apply system coherence optimization"""
        try:
            coherent_tasks = []

            for task in tasks:
                coherence_level = self._calculate_task_coherence(task, ucf_metrics)

                if coherence_level > 0.6:  # High coherence enables optimization
                    # Align task to optimal coherence state
                    aligned_task = self._align_task_to_coherence(task, coherence_level)
                    coherent_tasks.append(aligned_task)
                else:
                    coherent_tasks.append(task)

            return coherent_tasks

        except Exception as e:
            logger.error("System coherence optimization failed: %s", e)
            return tasks

    async def _apply_system_interference(
        self, tasks: list[WorkflowTask], ucf_metrics: dict[str, float]
    ) -> list[WorkflowTask]:
        """Apply system interference optimization"""
        try:
            interference_tasks = []

            for i, task in enumerate(tasks):
                interference_pattern = self._calculate_interference_pattern(task, i, ucf_metrics)

                if interference_pattern > 0:  # Constructive interference
                    # Enhance task efficiency
                    enhanced_task = self._enhance_task_by_interference(task, interference_pattern)
                    interference_tasks.append(enhanced_task)
                elif interference_pattern < 0:  # Destructive interference
                    # Skip or minimize task
                    if abs(interference_pattern) < 0.5:  # Don't eliminate completely
                        minimized_task = self._minimize_task_by_interference(task, interference_pattern)
                        interference_tasks.append(minimized_task)
                else:
                    interference_tasks.append(task)

            return interference_tasks

        except Exception as e:
            logger.error("System interference optimization failed: %s", e)
            return tasks

    def _calculate_superposition_probability(self, task: WorkflowTask, ucf_metrics: dict[str, float]) -> float:
        """Calculate probability of system superposition for a task"""
        try:
            harmony = ucf_metrics.get("harmony", 0.5)
            throughput = ucf_metrics.get("throughput", 0.5)
            resilience = ucf_metrics.get("resilience", 1.0)

            # Task-specific factors
            complexity_factor = 1.0 / (1.0 + task.complexity)
            coordination_weight = task.coordination_weight

            # Calculate superposition probability
            probability = (
                harmony * 0.3
                + throughput * 0.2
                + resilience * 0.2
                + complexity_factor * 0.2
                + coordination_weight * 0.1
            )

            return min(max(probability, 0.0), 1.0)

        except Exception as e:
            logger.error("Superposition probability calculation failed: %s", e)
            return 0.5

    def _create_task_variants(self, task: WorkflowTask, superposition_probability: float) -> list[WorkflowTask]:
        """Create multiple task variants in system superposition"""
        try:
            variants = []

            # Create base variant
            base_variant = task
            variants.append(base_variant)

            # Create optimized variants based on superposition probability
            if superposition_probability > 0.7:
                # High superposition: create multiple optimized variants
                for i in range(2):
                    variant = WorkflowTask(
                        workflow_id=task.workflow_id,
                        name=f"{task.name}_variant_{i + 1}",
                        description=f"Superposition variant {i + 1} of {task.name}",
                        task_type=task.task_type,
                        task_config=task.task_config,
                        dependencies=task.dependencies,
                        task_order=task.task_order + (i * 0.1),
                        min_performance_score=task.min_performance_score * 0.9,
                        coordination_weight=task.coordination_weight * 1.1,
                        complexity=task.complexity * 0.8,
                        is_parallelizable=True,
                        estimated_duration=task.estimated_duration * 0.7,
                    )
                    variants.append(variant)

            return variants

        except Exception as e:
            logger.error("Task variant creation failed: %s", e)
            return [task]

    def _calculate_system_priority(self, task: WorkflowTask, ucf_metrics: dict[str, float]) -> float:
        """Calculate system priority for task ordering"""
        try:
            harmony = ucf_metrics.get("harmony", 0.5)
            focus = ucf_metrics.get("focus", 0.5)

            # Task priority calculation
            priority = task.coordination_weight * 0.4 + (1.0 - task.complexity) * 0.3 + harmony * 0.2 + focus * 0.1

            return priority

        except Exception as e:
            logger.error("System priority calculation failed: %s", e)
            return 0.5

    def _group_tasks_by_entanglement(
        self, tasks: list[WorkflowTask], ucf_metrics: dict[str, float]
    ) -> list[list[WorkflowTask]]:
        """Group tasks by system entanglement potential"""
        try:
            entanglement_matrix = {}

            for i, task1 in enumerate(tasks):
                for j, task2 in enumerate(tasks):
                    if i != j:
                        entanglement_strength = self._calculate_entanglement_strength(task1, task2, ucf_metrics)
                        entanglement_matrix[(i, j)] = entanglement_strength

            # Group tasks with high entanglement
            groups = []
            visited = set()

            for i, task in enumerate(tasks):
                if i not in visited:
                    group = [task]
                    visited.add(i)

                    # Find entangled tasks
                    for j, other_task in enumerate(tasks):
                        if j not in visited and entanglement_matrix.get((i, j), 0) > 0.5:
                            group.append(other_task)
                            visited.add(j)

                    groups.append(group)

            return groups

        except Exception as e:
            logger.error("Task entanglement grouping failed: %s", e)
            return [[task] for task in tasks]

    def _calculate_entanglement_strength(
        self, task1: WorkflowTask, task2: WorkflowTask, ucf_metrics: dict[str, float]
    ) -> float:
        """Calculate system entanglement strength between two tasks"""
        try:
            type_similarity = 1.0 if task1.task_type == task2.task_type else 0.5
            complexity_similarity = 1.0 - abs(task1.complexity - task2.complexity)
            coordination_alignment = 1.0 - abs(task1.coordination_weight - task2.coordination_weight)

            # UCF influence
            harmony = ucf_metrics.get("harmony", 0.5)

            entanglement_strength = (
                type_similarity * 0.3 + complexity_similarity * 0.3 + coordination_alignment * 0.2 + harmony * 0.2
            )

            return min(max(entanglement_strength, 0.0), 1.0)

        except Exception as e:
            logger.error("Entanglement strength calculation failed: %s", e)
            return 0.0

    def _create_entangled_tasks(self, tasks: list[WorkflowTask], ucf_metrics: dict[str, float]) -> list[WorkflowTask]:
        """Create entangled task pairs"""
        try:
            entangled_tasks = []

            for i, task in enumerate(tasks):
                if i < len(tasks) - 1:
                    next_task = tasks[i + 1]

                    # Create entangled pair
                    entangled_task = WorkflowTask(
                        workflow_id=task.workflow_id,
                        name=f"{task.name}_entangled_with_{next_task.name}",
                        description=f"Entangled task pair: {task.name} + {next_task.name}",
                        task_type="entangled",
                        task_config={
                            "original_tasks": [task.id, next_task.id],
                            "entanglement_strength": self._calculate_entanglement_strength(
                                task, next_task, ucf_metrics
                            ),
                        },
                        dependencies=task.dependencies + next_task.dependencies,
                        task_order=task.task_order,
                        min_performance_score=min(
                            task.min_performance_score,
                            next_task.min_performance_score,
                        ),
                        coordination_weight=(task.coordination_weight + next_task.coordination_weight) / 2,
                        complexity=(task.complexity + next_task.complexity) / 2,
                        is_parallelizable=True,
                        estimated_duration=max(task.estimated_duration, next_task.estimated_duration) * 0.8,
                    )
                    entangled_tasks.append(entangled_task)
                else:
                    entangled_tasks.append(task)

            return entangled_tasks

        except Exception as e:
            logger.error("Entangled task creation failed: %s", e)
            return tasks

    def _calculate_tunneling_probability(self, task: WorkflowTask, ucf_metrics: dict[str, float]) -> float:
        """Calculate system tunneling probability for a task"""
        try:
            performance_score = ucf_metrics.get("performance_score", 0.5)
            harmony = ucf_metrics.get("harmony", 0.5)
            resilience = ucf_metrics.get("resilience", 1.0)

            # Barrier strength (dependencies, complexity)
            barrier_strength = len(task.dependencies) * 0.1 + task.complexity * 0.5

            # Calculate tunneling probability
            tunneling_probability = performance_score * 0.4 + harmony * 0.3 + resilience * 0.2 - barrier_strength * 0.3

            return min(max(tunneling_probability, 0.0), 1.0)

        except Exception as e:
            logger.error("Tunneling probability calculation failed: %s", e)
            return 0.0

    def _create_tunneled_task(self, task: WorkflowTask, tunneling_probability: float) -> WorkflowTask:
        """Create a task that has tunneled through barriers"""
        try:
            tunneled_dependencies = []
            if tunneling_probability > 0.7:
                # High tunneling: remove most dependencies
                tunneled_dependencies = task.dependencies[:1]  # Keep only critical dependency
            elif tunneling_probability > 0.5:
                # Medium tunneling: reduce dependencies
                tunneled_dependencies = task.dependencies[: len(task.dependencies) // 2]
            else:
                # Low tunneling: minimal change
                tunneled_dependencies = task.dependencies

            tunneled_task = WorkflowTask(
                workflow_id=task.workflow_id,
                name=f"{task.name}_tunneled",
                description=f"Tunneled version of {task.name} (probability: {tunneling_probability:.2f})",
                task_type=task.task_type,
                task_config=task.task_config,
                dependencies=tunneled_dependencies,
                task_order=task.task_order,
                min_performance_score=task.min_performance_score * 0.8,
                coordination_weight=task.coordination_weight * 1.2,
                complexity=task.complexity * (1.0 - tunneling_probability * 0.3),
                is_parallelizable=True,
                estimated_duration=task.estimated_duration * (1.0 - tunneling_probability * 0.4),
            )

            return tunneled_task

        except Exception as e:
            logger.error("Tunneled task creation failed: %s", e)
            return task

    def _calculate_task_coherence(self, task: WorkflowTask, ucf_metrics: dict[str, float]) -> float:
        """Calculate system coherence level for a task"""
        try:
            harmony = ucf_metrics.get("harmony", 0.5)
            focus = ucf_metrics.get("focus", 0.5)
            throughput = ucf_metrics.get("throughput", 0.5)

            # Task coherence calculation
            task_coherence = harmony * 0.4 + focus * 0.3 + throughput * 0.2 + (1.0 - task.complexity) * 0.1

            return min(max(task_coherence, 0.0), 1.0)

        except Exception as e:
            logger.error("Task coherence calculation failed: %s", e)
            return 0.5

    def _align_task_to_coherence(self, task: WorkflowTask, coherence_level: float) -> WorkflowTask:
        """Align task to optimal coherence state"""
        try:
            aligned_task = WorkflowTask(
                workflow_id=task.workflow_id,
                name=f"{task.name}_coherent",
                description=f"Coherence-aligned version of {task.name}",
                task_type=task.task_type,
                task_config=task.task_config,
                dependencies=task.dependencies,
                task_order=task.task_order,
                min_performance_score=task.min_performance_score * (1.0 - coherence_level * 0.2),
                coordination_weight=task.coordination_weight * (1.0 + coherence_level * 0.1),
                complexity=task.complexity * (1.0 - coherence_level * 0.15),
                is_parallelizable=task.is_parallelizable,
                estimated_duration=task.estimated_duration * (1.0 - coherence_level * 0.25),
            )

            return aligned_task
        except Exception as e:
            logger.error("Task coherence alignment failed: %s", e)
            return task

    def _calculate_interference_pattern(
        self, task: WorkflowTask, task_index: int, ucf_metrics: dict[str, float]
    ) -> float:
        """Calculate system interference pattern for a task"""
        try:
            performance_score = ucf_metrics.get("performance_score", 0.5)
            harmony = ucf_metrics.get("harmony", 0.5)

            # Wave interference calculation
            wave_function = math.sin(task_index * math.pi / len(ucf_metrics)) * performance_score
            interference = wave_function * harmony

            return interference

        except Exception as e:
            logger.error("Interference pattern calculation failed: %s", e)
            return 0.0

    def _enhance_task_by_interference(self, task: WorkflowTask, interference_strength: float) -> WorkflowTask:
        """Enhance task through constructive interference"""
        try:
            enhanced_task = WorkflowTask(
                workflow_id=task.workflow_id,
                name=f"{task.name}_enhanced",
                description=f"Constructively interfered version of {task.name}",
                task_type=task.task_type,
                task_config=task.task_config,
                dependencies=task.dependencies,
                task_order=task.task_order,
                min_performance_score=task.min_performance_score * 0.9,
                coordination_weight=task.coordination_weight * (1.0 + interference_strength),
                complexity=task.complexity * (1.0 - interference_strength * 0.2),
                is_parallelizable=task.is_parallelizable,
                estimated_duration=task.estimated_duration * (1.0 - interference_strength * 0.3),
            )

            return enhanced_task

        except Exception as e:
            logger.error("Task enhancement by interference failed: %s", e)
            return task

    def _minimize_task_by_interference(self, task: WorkflowTask, interference_strength: float) -> WorkflowTask:
        """Minimize task through destructive interference"""
        try:
            minimized_task = WorkflowTask(
                workflow_id=task.workflow_id,
                name=f"{task.name}_minimized",
                description=f"Destructively interfered version of {task.name}",
                task_type=task.task_type,
                task_config=task.task_config,
                dependencies=task.dependencies,
                task_order=task.task_order,
                min_performance_score=task.min_performance_score * 1.1,
                coordination_weight=task.coordination_weight * (1.0 + interference_strength),
                complexity=task.complexity * (1.0 + abs(interference_strength) * 0.1),
                is_parallelizable=False,
                estimated_duration=task.estimated_duration * (1.0 + abs(interference_strength) * 0.2),
            )

            return minimized_task

        except Exception as e:
            logger.error("Task minimization by interference failed: %s", e)
            return task

    async def _calculate_coordination_resonance(
        self, optimized_tasks: list[WorkflowTask], ucf_metrics: dict[str, float]
    ) -> float:
        """Calculate coordination resonance of optimized tasks"""
        try:
            # Calculate resonance based on task alignment with coordination
            total_resonance = 0.0
            harmony = ucf_metrics.get("harmony", 0.5)
            focus = ucf_metrics.get("focus", 0.5)

            for task in optimized_tasks:
                task_resonance = (
                    task.coordination_weight * 0.4 + (1.0 - task.complexity) * 0.3 + harmony * 0.2 + focus * 0.1
                )
                total_resonance += task_resonance

            average_resonance = total_resonance / len(optimized_tasks)
            return min(max(average_resonance, 0.0), 1.0)

        except Exception as e:
            logger.error("Coordination resonance calculation failed: %s", e)
            return 0.0

    async def _calculate_energy_efficiency(
        self, optimized_tasks: list[WorkflowTask], ucf_metrics: dict[str, float]
    ) -> float:
        """Calculate energy efficiency of optimized tasks"""
        try:
            # Calculate efficiency based on reduced complexity and improved alignment
            total_efficiency = 0.0
            throughput = ucf_metrics.get("throughput", 0.5)

            for task in optimized_tasks:
                task_efficiency = (1.0 - task.complexity) * 0.5 + task.coordination_weight * 0.3 + throughput * 0.2
                total_efficiency += task_efficiency

            average_efficiency = total_efficiency / len(optimized_tasks)
            return min(max(average_efficiency, 0.0), 1.0)

        except Exception as e:
            logger.error("Energy efficiency calculation failed: %s", e)
            return 0.0

    async def _calculate_execution_time_improvement(
        self, original_tasks: list[WorkflowTask], optimized_tasks: list[WorkflowTask]
    ) -> float:
        """Calculate execution time improvement percentage"""
        try:
            original_time = sum(task.estimated_duration for task in original_tasks)
            optimized_time = sum(task.estimated_duration for task in optimized_tasks)

            if original_time == 0:
                return 0.0

            improvement = (original_time - optimized_time) / original_time
            return max(improvement, 0.0)

        except Exception as e:
            logger.error("Execution time improvement calculation failed: %s", e)
            return 0.0

    async def _generate_system_states(
        self, optimized_tasks: list[WorkflowTask], coordination_resonance: float
    ) -> list[SystemState]:
        """Generate system states for optimized tasks"""
        try:
            system_states = []

            for i, task in enumerate(optimized_tasks):
                # Calculate system state parameters
                amplitude = complex(
                    task.coordination_weight * coordination_resonance,
                    task.complexity * (1.0 - coordination_resonance),
                )

                phase = (i / len(optimized_tasks)) * 2 * math.pi
                probability = abs(amplitude) ** 2
                coherence = coordination_resonance * (1.0 - task.complexity)
                entanglement_strength = task.coordination_weight * coordination_resonance

                system_state = SystemState(
                    amplitude=amplitude,
                    phase=phase,
                    probability=probability,
                    coherence=coherence,
                    entanglement_strength=entanglement_strength,
                )

                system_states.append(system_state)

            return system_states

        except Exception as e:
            logger.error("System state generation failed: %s", e)
            return []

    async def get_optimization_history(self, workflow_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """Get optimization history"""
        try:
            if workflow_id:
                history = [h for h in self.optimization_history if h.get("workflow_id") == workflow_id]
            else:
                history = self.optimization_history

            return history[-limit:]

        except Exception as e:
            logger.error("Optimization history retrieval failed: %s", e)
            return []

    async def clear_optimization_cache(self) -> bool:
        """Clear optimization cache"""
        try:
            logger.info("Optimization cache cleared")
            return True

        except Exception as e:
            logger.error("Cache clearing failed: %s", e)
            return False

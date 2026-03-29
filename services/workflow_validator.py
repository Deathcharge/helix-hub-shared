"""
Workflow Validator for Helix Collective

Comprehensive validation and optimization system for coordination-aware workflows.
Ensures workflow integrity, coordination compatibility, and performance optimization.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from ..services.coordination_service import CoordinationService

logger = logging.getLogger(__name__)


class ValidationResult(str, Enum):
    VALID = "valid"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class ValidationIssue:
    """Represents a validation issue found in a workflow"""

    severity: ValidationResult
    code: str
    message: str
    field: str | None = None
    suggestion: str | None = None


@dataclass
class WorkflowValidationResult:
    """Complete validation result for a workflow"""

    is_valid: bool
    issues: list[ValidationIssue]
    warnings: list[ValidationIssue]
    errors: list[ValidationIssue]
    optimization_suggestions: list[str]
    coordination_compatibility: dict[str, Any]
    performance_score: float


class WorkflowValidator:
    """Comprehensive workflow validation and optimization system"""

    def __init__(self, db_session: Session, coordination_service: CoordinationService):
        self.db = db_session
        self.coordination_service = coordination_service
        self.validation_rules = self._load_validation_rules()

    def _load_validation_rules(self) -> dict[str, Any]:
        """Load validation rules and constraints"""
        return {
            "workflow_types": ["sequential", "parallel", "conditional", "event_driven"],
            "task_types": ["agent", "api", "database", "file", "notification"],
            "performance_scores": {"min": 0.0, "max": 10.0},
            "ucf_metrics": ["throughput", "harmony", "resilience", "friction"],
            "max_tasks_per_workflow": 100,
            "max_dependencies_per_task": 10,
            "max_execution_time_ms": 3600000,  # 1 hour
            "min_coordination_weight": 0.0,
            "max_coordination_weight": 10.0,
        }

    async def validate_workflow(
        self, workflow_definition: dict[str, Any], workflow_id: str | None = None
    ) -> WorkflowValidationResult:
        """Comprehensive workflow validation"""
        issues = []
        warnings = []
        errors = []
        optimization_suggestions = []

        # Basic structure validation
        basic_issues = self._validate_basic_structure(workflow_definition)
        issues.extend(basic_issues)

        # Coordination compatibility validation
        coordination_issues = await self._validate_coordination_compatibility(workflow_definition)
        issues.extend(coordination_issues)

        # Task validation
        task_issues, task_warnings = self._validate_tasks(workflow_definition)
        issues.extend(task_issues)
        warnings.extend(task_warnings)

        # Dependency validation
        dependency_issues, dependency_warnings = self._validate_dependencies(workflow_definition)
        issues.extend(dependency_issues)
        warnings.extend(dependency_warnings)

        # Performance optimization suggestions
        optimization_suggestions = self._analyze_performance_optimizations(workflow_definition)

        # Coordination compatibility analysis
        coordination_compatibility = await self._analyze_coordination_compatibility(workflow_definition)

        # Calculate performance score
        performance_score = self._calculate_performance_score(issues, warnings, optimization_suggestions)

        # Separate errors from warnings
        errors = [issue for issue in issues if issue.severity == ValidationResult.ERROR]
        warnings.extend([issue for issue in issues if issue.severity == ValidationResult.WARNING])

        is_valid = len(errors) == 0

        return WorkflowValidationResult(
            is_valid=is_valid,
            issues=issues,
            warnings=warnings,
            errors=errors,
            optimization_suggestions=optimization_suggestions,
            coordination_compatibility=coordination_compatibility,
            performance_score=performance_score,
        )

    def _validate_basic_structure(self, workflow_definition: dict[str, Any]) -> list[ValidationIssue]:
        """Validate basic workflow structure and required fields"""
        issues = []

        # Check required fields
        required_fields = ["name", "workflow_type", "tasks"]
        for field in required_fields:
            if field not in workflow_definition:
                issues.append(
                    ValidationIssue(
                        severity=ValidationResult.ERROR,
                        code="MISSING_REQUIRED_FIELD",
                        message=f"Missing required field: {field}",
                        field=field,
                    )
                )

        if not workflow_definition:
            issues.append(
                ValidationIssue(
                    severity=ValidationResult.ERROR,
                    code="EMPTY_DEFINITION",
                    message="Workflow definition cannot be empty",
                )
            )
            return issues

        # Validate workflow type
        workflow_type = workflow_definition.get("workflow_type")
        if workflow_type and workflow_type not in self.validation_rules["workflow_types"]:
            issues.append(
                ValidationIssue(
                    severity=ValidationResult.ERROR,
                    code="INVALID_WORKFLOW_TYPE",
                    message=f"Invalid workflow type: {workflow_type}",
                    field="workflow_type",
                    suggestion=f"Use one of: {', '.join(self.validation_rules['workflow_types'])}",
                )
            )

        # Validate name
        name = workflow_definition.get("name", "")
        if name and len(name) > 200:
            issues.append(
                ValidationIssue(
                    severity=ValidationResult.WARNING,
                    code="LONG_WORKFLOW_NAME",
                    message="Workflow name is very long (>200 characters)",
                    field="name",
                )
            )

        # Validate description
        description = workflow_definition.get("description", "")
        if description and len(description) > 1000:
            issues.append(
                ValidationIssue(
                    severity=ValidationResult.WARNING,
                    code="LONG_WORKFLOW_DESCRIPTION",
                    message="Workflow description is very long (>1000 characters)",
                    field="description",
                )
            )

        return issues

    def _validate_tasks(
        self, workflow_definition: dict[str, Any]
    ) -> tuple[list[ValidationIssue], list[ValidationIssue]]:
        """Validate individual tasks in the workflow"""
        issues = []
        warnings = []

        tasks = workflow_definition.get("tasks", [])

        if not tasks:
            issues.append(
                ValidationIssue(
                    severity=ValidationResult.ERROR,
                    code="NO_TASKS",
                    message="Workflow must contain at least one task",
                )
            )
            return issues, warnings

        if len(tasks) > self.validation_rules["max_tasks_per_workflow"]:
            issues.append(
                ValidationIssue(
                    severity=ValidationResult.ERROR,
                    code="TOO_MANY_TASKS",
                    message=f"Too many tasks: {len(tasks)} (max: {self.validation_rules['max_tasks_per_workflow']})",
                    field="tasks",
                )
            )

        task_names = set()
        task_ids = set()

        for i, task in enumerate(tasks):
            # Check task structure
            if not isinstance(task, dict):
                issues.append(
                    ValidationIssue(
                        severity=ValidationResult.ERROR,
                        code="INVALID_TASK_STRUCTURE",
                        message=f"Task {i} must be a dictionary",
                        field=f"tasks[{i}]",
                    )
                )
                continue

            # Check required task fields
            task_required_fields = ["name", "task_type", "task_order"]
            for field in task_required_fields:
                if field not in task:
                    issues.append(
                        ValidationIssue(
                            severity=ValidationResult.ERROR,
                            code="MISSING_TASK_FIELD",
                            message=f"Task {i} missing required field: {field}",
                            field=f"tasks[{i}].{field}",
                        )
                    )

            # Validate task type
            task_type = task.get("task_type")
            if task_type and task_type not in self.validation_rules["task_types"]:
                issues.append(
                    ValidationIssue(
                        severity=ValidationResult.ERROR,
                        code="INVALID_TASK_TYPE",
                        message=f"Task {i} has invalid type: {task_type}",
                        field=f"tasks[{i}].task_type",
                        suggestion=f"Use one of: {', '.join(self.validation_rules['task_types'])}",
                    )
                )

            # Validate task name uniqueness
            task_name = task.get("name", "")
            if task_name in task_names:
                warnings.append(
                    ValidationIssue(
                        severity=ValidationResult.WARNING,
                        code="DUPLICATE_TASK_NAME",
                        message=f"Task name '{task_name}' is not unique",
                        field=f"tasks[{i}].name",
                    )
                )
            task_names.add(task_name)

            # Validate task ID uniqueness
            task_id = task.get("id", f"task_{i}")
            if task_id in task_ids:
                warnings.append(
                    ValidationIssue(
                        severity=ValidationResult.WARNING,
                        code="DUPLICATE_TASK_ID",
                        message=f"Task ID '{task_id}' is not unique",
                        field=f"tasks[{i}].id",
                    )
                )
            task_ids.add(task_id)

            # Validate coordination requirements
            performance_score = task.get("min_performance_score", 0.0)
            if (
                performance_score < self.validation_rules["performance_scores"]["min"]
                or performance_score > self.validation_rules["performance_scores"]["max"]
            ):
                issues.append(
                    ValidationIssue(
                        severity=ValidationResult.ERROR,
                        code="INVALID_PERFORMANCE_SCORE",
                        message=f"Task {i} has invalid coordination level: {performance_score}",
                        field=f"tasks[{i}].min_performance_score",
                        suggestion=f"Use a value between {self.validation_rules['performance_scores']['min']} and {self.validation_rules['performance_scores']['max']}",
                    )
                )

            # Validate coordination weight
            coordination_weight = task.get("coordination_weight", 1.0)
            if (
                coordination_weight < self.validation_rules["min_coordination_weight"]
                or coordination_weight > self.validation_rules["max_coordination_weight"]
            ):
                issues.append(
                    ValidationIssue(
                        severity=ValidationResult.ERROR,
                        code="INVALID_COORDINATION_WEIGHT",
                        message=f"Task {i} has invalid coordination weight: {coordination_weight}",
                        field=f"tasks[{i}].coordination_weight",
                        suggestion=f"Use a value between {self.validation_rules['min_coordination_weight']} and {self.validation_rules['max_coordination_weight']}",
                    )
                )

            # Validate dependencies
            dependencies = task.get("dependencies", [])
            if len(dependencies) > self.validation_rules["max_dependencies_per_task"]:
                warnings.append(
                    ValidationIssue(
                        severity=ValidationResult.WARNING,
                        code="TOO_MANY_DEPENDENCIES",
                        message=f"Task {i} has too many dependencies: {len(dependencies)}",
                        field=f"tasks[{i}].dependencies",
                    )
                )

        return issues, warnings

    def _validate_dependencies(
        self, workflow_definition: dict[str, Any]
    ) -> tuple[list[ValidationIssue], list[ValidationIssue]]:
        """Validate task dependencies and execution order"""
        issues = []
        warnings = []

        tasks = workflow_definition.get("tasks", [])
        task_ids = {task.get("id", f"task_{i}") for i, task in enumerate(tasks)}

        # Check for circular dependencies
        if self._has_circular_dependencies(tasks):
            issues.append(
                ValidationIssue(
                    severity=ValidationResult.ERROR,
                    code="CIRCULAR_DEPENDENCIES",
                    message="Workflow contains circular dependencies",
                    suggestion="Review task dependencies to remove circular references",
                )
            )

        # Validate dependency references
        for i, task in enumerate(tasks):
            dependencies = task.get("dependencies", [])
            for dep_id in dependencies:
                if dep_id not in task_ids:
                    issues.append(
                        ValidationIssue(
                            severity=ValidationResult.ERROR,
                            code="INVALID_DEPENDENCY",
                            message=f"Task {i} references non-existent dependency: {dep_id}",
                            field=f"tasks[{i}].dependencies",
                        )
                    )

        # Check for unreachable tasks
        unreachable_tasks = self._find_unreachable_tasks(tasks)
        if unreachable_tasks:
            warnings.append(
                ValidationIssue(
                    severity=ValidationResult.WARNING,
                    code="UNREACHABLE_TASKS",
                    message=f"Tasks {unreachable_tasks} are not reachable in the execution flow",
                    suggestion="Review task dependencies to ensure all tasks can be executed",
                )
            )

        return issues, warnings

    def _has_circular_dependencies(self, tasks: list[dict[str, Any]]) -> bool:
        """Check for circular dependencies using DFS"""
        task_map = {task.get("id", f"task_{i}"): task for i, task in enumerate(tasks)}
        visited = set()
        rec_stack = set()

        def has_cycle(task_id: str) -> bool:
            visited.add(task_id)
            rec_stack.add(task_id)

            task = task_map.get(task_id, {})
            dependencies = task.get("dependencies", [])

            for dep_id in dependencies:
                if dep_id not in task_map:
                    continue

                if dep_id not in visited:
                    if has_cycle(dep_id):
                        return True
                elif dep_id in rec_stack:
                    return True

            rec_stack.remove(task_id)
            return False

        for task_id in task_map:
            if task_id not in visited:
                if has_cycle(task_id):
                    return True

        return False

    def _find_unreachable_tasks(self, tasks: list[dict[str, Any]]) -> list[str]:
        """Find tasks that cannot be reached in the execution flow"""
        if not tasks:
            return []

        task_map = {task.get("id", f"task_{i}"): task for i, task in enumerate(tasks)}
        reachable = set()

        # Start with tasks that have no dependencies
        queue = [task_id for task_id, task in task_map.items() if not task.get("dependencies", [])]
        reachable.update(queue)

        # BFS to find all reachable tasks
        while queue:
            current_task_id = queue.pop(0)

            # Find tasks that depend on current task
            for task_id, task in task_map.items():
                if task_id not in reachable and current_task_id in task.get("dependencies", []):
                    reachable.add(task_id)
                    queue.append(task_id)

        # Tasks that are not reachable
        return [task_id for task_id in task_map if task_id not in reachable]

    async def _validate_coordination_compatibility(self, workflow_definition: dict[str, Any]) -> list[ValidationIssue]:
        """Validate coordination requirements and compatibility"""
        issues = []

        # Get current coordination state
        try:
            coordination_state = await self.coordination_service.get_coordination_metrics()
            coordination_state = coordination_state.__dict__ if hasattr(coordination_state, "__dict__") else {}
            current_coordination = coordination_state.get("performance_score", 0.0)
            ucf_metrics = coordination_state.get("ucf_metrics", {})
        except Exception as e:
            logger.warning("Could not get current coordination state: %s", e)
            current_coordination = 0.5
            ucf_metrics = {}

        # Validate workflow-level coordination requirements
        min_coordination = workflow_definition.get("min_performance_score", 0.355)
        if min_coordination > current_coordination:
            issues.append(
                ValidationIssue(
                    severity=ValidationResult.WARNING,
                    code="COORDINATION_TOO_LOW",
                    message=f"Workflow requires coordination level {min_coordination}, current level is {current_coordination}",
                    suggestion="Consider raising coordination level or reducing workflow requirements",
                )
            )

        # Validate UCF requirements
        ucf_requirements = workflow_definition.get("ucf_requirements", {})
        for metric, required_value in ucf_requirements.items():
            if metric in self.validation_rules["ucf_metrics"]:
                current_value = ucf_metrics.get(metric, 0)
                if current_value < required_value:
                    issues.append(
                        ValidationIssue(
                            severity=ValidationResult.WARNING,
                            code="UCF_TOO_LOW",
                            message=f"UCF {metric} too low: {current_value}, required: {required_value}",
                            suggestion=f"Focus on improving {metric} to meet workflow requirements",
                        )
                    )

        # Validate task-level coordination requirements
        tasks = workflow_definition.get("tasks", [])
        for i, task in enumerate(tasks):
            task_coordination = task.get("min_performance_score", 0.355)
            if task_coordination > current_coordination:
                issues.append(
                    ValidationIssue(
                        severity=ValidationResult.WARNING,
                        code="TASK_COORDINATION_TOO_HIGH",
                        message=f"Task {i} requires coordination level {task_coordination}, current level is {current_coordination}",
                        field=f"tasks[{i}].min_performance_score",
                    )
                )

        return issues

    async def _analyze_coordination_compatibility(self, workflow_definition: dict[str, Any]) -> dict[str, Any]:
        """Analyze coordination compatibility and provide recommendations"""
        try:
            coordination_state = await self.coordination_service.get_coordination_metrics()
            coordination_state = coordination_state.__dict__ if hasattr(coordination_state, "__dict__") else {}
            current_coordination = coordination_state.get("performance_score", 0.0)
            ucf_metrics = coordination_state.get("ucf_metrics", {})
        except Exception as e:
            logger.warning("Could not get coordination state for analysis: %s", e)
            current_coordination = 0.5
            ucf_metrics = {}

        # Analyze workflow requirements
        min_coordination = workflow_definition.get("min_performance_score", 0.355)
        ucf_requirements = workflow_definition.get("ucf_requirements", {})

        # Calculate compatibility scores
        coordination_compatibility = (current_coordination / min_coordination) if min_coordination > 0 else 1.0

        ucf_compatibility = 1.0
        if ucf_requirements:
            compatibility_scores = []
            for metric, required_value in ucf_requirements.items():
                current_value = ucf_metrics.get(metric, 0)
                if required_value > 0:
                    score = current_value / required_value
                    compatibility_scores.append(score)

            if compatibility_scores:
                ucf_compatibility = sum(compatibility_scores) / len(compatibility_scores)

        # Overall compatibility
        overall_compatibility = (coordination_compatibility + ucf_compatibility) / 2

        return {
            "current_coordination": current_coordination,
            "required_coordination": min_coordination,
            "coordination_compatibility": coordination_compatibility,
            "ucf_compatibility": ucf_compatibility,
            "overall_compatibility": overall_compatibility,
            "recommendations": self._generate_compatibility_recommendations(
                current_coordination, min_coordination, ucf_metrics, ucf_requirements
            ),
        }

    def _generate_compatibility_recommendations(
        self,
        current_coordination: float,
        required_coordination: float,
        current_ucf: dict[str, float],
        required_ucf: dict[str, float],
    ) -> list[str]:
        """Generate recommendations for improving coordination compatibility"""
        recommendations = []

        # Coordination level recommendations
        if current_coordination < required_coordination:
            gap = required_coordination - current_coordination
            if gap > 2.0:
                recommendations.append("Consider significant coordination elevation before executing this workflow")
            elif gap > 1.0:
                recommendations.append("Focus on coordination elevation techniques")
            else:
                recommendations.append("Minor coordination elevation may be needed")

        # UCF recommendations
        for metric, required_value in required_ucf.items():
            current_value = current_ucf.get(metric, 0)
            if current_value < required_value:
                gap = required_value - current_value
                if gap > 30:
                    recommendations.append(f"Significant improvement needed in {metric}")
                elif gap > 15:
                    recommendations.append(f"Moderate improvement needed in {metric}")
                else:
                    recommendations.append(f"Minor improvement needed in {metric}")

        if not recommendations:
            recommendations.append("Workflow is fully compatible with current coordination state")

        return recommendations

    def _analyze_performance_optimizations(self, workflow_definition: dict[str, Any]) -> list[str]:
        """Analyze workflow for performance optimization opportunities"""
        suggestions = []

        tasks = workflow_definition.get("tasks", [])

        # Check for parallelization opportunities
        parallelizable_tasks = []
        for task in tasks:
            if not task.get("dependencies") and task.get("task_type") in [
                "notification",
                "logging",
            ]:
                parallelizable_tasks.append(task.get("name", "unnamed task"))

        if len(parallelizable_tasks) > 3:
            suggestions.append(f"Consider parallelizing tasks: {', '.join(parallelizable_tasks[:3])}")

        # Check for coordination optimization opportunities
        high_coordination_tasks = []
        for task in tasks:
            if task.get("min_performance_score", 0) > 0.8:
                high_coordination_tasks.append(task.get("name", "unnamed task"))

        if high_coordination_tasks:
            suggestions.append(f"Consider lowering coordination requirements for: {', '.join(high_coordination_tasks)}")

        # Check for dependency optimization
        total_dependencies = sum(len(task.get("dependencies", [])) for task in tasks)
        if total_dependencies > len(tasks) * 2:
            suggestions.append("Consider reducing task dependencies to improve execution speed")

        # Check for task ordering
        task_order = [task.get("task_order", 0) for task in tasks]
        if task_order != sorted(task_order):
            suggestions.append("Consider optimizing task execution order for better performance")

        return suggestions

    def _calculate_performance_score(
        self,
        issues: list[ValidationIssue],
        warnings: list[ValidationIssue],
        suggestions: list[str],
    ) -> float:
        """Calculate overall performance score (0-100)"""
        # Start with perfect score
        score = 100.0

        # Deduct points for errors
        error_count = len([i for i in issues if i.severity == ValidationResult.ERROR])
        score -= error_count * 20

        # Deduct points for warnings
        warning_count = len([i for i in issues if i.severity == ValidationResult.WARNING])
        score -= warning_count * 5

        # Add points for optimization suggestions (more suggestions = more optimization potential)
        score += len(suggestions) * 2

        # Ensure score stays within bounds
        return max(0.0, min(100.0, score))

    async def optimize_workflow(self, workflow_definition: dict[str, Any]) -> dict[str, Any]:
        """Apply automatic optimizations to workflow definition"""
        optimized_definition = workflow_definition.copy()

        # Optimize task ordering for parallel execution
        optimized_definition = self._optimize_task_ordering(optimized_definition)

        # Optimize coordination requirements
        optimized_definition = self._optimize_coordination_requirements(optimized_definition)

        # Optimize dependencies
        optimized_definition = self._optimize_dependencies(optimized_definition)

        return optimized_definition

    def _optimize_task_ordering(self, workflow_definition: dict[str, Any]) -> dict[str, Any]:
        """Optimize task ordering for better parallel execution"""
        tasks = workflow_definition.get("tasks", [])

        # Group tasks by dependency levels
        dependency_groups = self._group_tasks_by_dependencies(tasks)

        # Reorder tasks for optimal execution
        optimized_tasks = []
        for group in dependency_groups:
            # Sort tasks within group by coordination requirements
            sorted_group = sorted(group, key=lambda t: t.get("min_performance_score", 0.0))
            optimized_tasks.extend(sorted_group)

        workflow_definition["tasks"] = optimized_tasks
        return workflow_definition

    def _optimize_coordination_requirements(self, workflow_definition: dict[str, Any]) -> dict[str, Any]:
        """Optimize coordination requirements for better execution probability"""
        tasks = workflow_definition.get("tasks", [])

        for task in tasks:
            # Lower coordination requirements if they're too high
            current_level = task.get("min_performance_score", 0.355)
            if current_level > 0.9:
                task["min_performance_score"] = 0.8  # Reduce to more achievable level

            # Adjust coordination weight if too high
            current_weight = task.get("coordination_weight", 1.0)
            if current_weight > 5.0:
                task["coordination_weight"] = 3.0  # Reduce impact

        return workflow_definition

    def _optimize_dependencies(self, workflow_definition: dict[str, Any]) -> dict[str, Any]:
        """Optimize task dependencies for better performance"""
        tasks = workflow_definition.get("tasks", [])
        task_map = {task.get("id", f"task_{i}"): task for i, task in enumerate(tasks)}

        # Remove redundant dependencies
        for task in tasks:
            dependencies = task.get("dependencies", [])
            optimized_dependencies = []

            for dep_id in dependencies:
                if dep_id in task_map:
                    optimized_dependencies.append(dep_id)

            task["dependencies"] = optimized_dependencies

        return workflow_definition

    def _group_tasks_by_dependencies(self, tasks: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        """Group tasks by dependency levels for optimization"""
        if not tasks:
            return []

        dependency_levels = []
        processed_tasks = set()

        # Find tasks with no dependencies
        current_level = [task for task in tasks if not task.get("dependencies", [])]
        while current_level:
            dependency_levels.append(current_level)
            processed_tasks.update(task.get("id", f"task_{i}") for i, task in enumerate(current_level))

            # Find next level of tasks
            next_level = []
            for task in tasks:
                task_id = task.get("id", f"task_{tasks.index(task)}")
                if task_id not in processed_tasks:
                    # Check if all dependencies are in previous levels
                    dependencies = task.get("dependencies", [])
                    if all(dep_id in processed_tasks for dep_id in dependencies):
                        next_level.append(task)

            current_level = next_level

        return dependency_levels

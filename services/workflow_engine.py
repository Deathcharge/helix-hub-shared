"""
Workflow Engine for Helix Collective

Core execution engine for coordination-aware workflow automation.
Integrates with existing HelixAI Orchestrator Pro and coordination system.
"""

import asyncio
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from ..models.workflow_models import TaskExecution, Workflow, WorkflowExecution, WorkflowTask
from ..services.agent_service import AgentService
from ..services.coordination_service import CoordinationService
from ..services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class WorkflowContext:
    """Execution context for a workflow"""

    workflow_id: str
    execution_id: str
    input_data: dict[str, Any]
    performance_score: float
    ucf_metrics: dict[str, float]
    execution_context: dict[str, Any]
    agent_assignments: dict[str, str]  # task_id -> agent_name
    task_results: dict[str, Any]  # task_id -> result


class WorkflowEngine:
    """Coordination-aware workflow execution engine"""

    def __init__(
        self,
        db_session: Session,
        coordination_service: CoordinationService,
        agent_service: AgentService,
        database_service,  # Database class from unified_auth
        notification_service: NotificationService,
    ):
        self.db = db_session
        self.coordination_service = coordination_service
        self.agent_service = agent_service
        self.database_service = database_service
        self.notification_service = notification_service
        self.active_executions: dict[str, WorkflowExecution] = {}
        self.task_executors: dict[str, Callable] = self._initialize_task_executors()

    def _initialize_task_executors(self) -> dict[str, Callable]:
        """Initialize task execution handlers"""
        return {
            "agent": self._execute_agent_task,
            "api": self._execute_api_task,
            "database": self._execute_database_task,
            "file": self._execute_file_task,
            "notification": self._execute_notification_task,
        }

    async def create_workflow(
        self,
        name: str,
        description: str,
        workflow_type: str,
        definition: dict[str, Any],
        min_performance_score: float = 0.355,
        ucf_requirements: dict[str, float] | None = None,
        created_by: str | None = None,
    ) -> Workflow:
        """Create a new workflow"""
        try:
            workflow = Workflow(
                name=name,
                description=description,
                workflow_type=workflow_type,
                definition=definition,
                min_performance_score=min_performance_score,
                ucf_requirements=ucf_requirements or {},
                created_by=created_by,
            )

            self.db.add(workflow)
            self.db.commit()
            self.db.refresh(workflow)

            logger.info("Created workflow: %s (ID: %s)", workflow.name, workflow.id)
            return workflow

        except (ValueError, TypeError, KeyError) as e:
            self.db.rollback()
            logger.debug("Workflow creation validation error: %s", e)
            raise
        except Exception as e:
            self.db.rollback()
            logger.error("Error creating workflow: %s", e)
            raise

    async def execute_workflow(
        self,
        workflow_id: str,
        input_data: dict[str, Any] | None = None,
        user_id: str | None = None,
    ) -> str:
        """Execute a workflow with coordination-aware scheduling"""
        try:
            workflow = self.db.query(Workflow).filter(Workflow.id == workflow_id).first()
            if not workflow:
                raise ValueError(f"Workflow not found: {workflow_id}")

            if not workflow.is_active:
                raise ValueError(f"Workflow is not active: {workflow.name}")

            # Get current coordination state
            coordination_state = await self.coordination_service.get_current_state()
            current_coordination = coordination_state.get("performance_score", 0.0)
            ucf_metrics = coordination_state.get("ucf_metrics", {})

            # Validate coordination requirements
            if not workflow.can_execute(current_coordination, ucf_metrics):
                raise ValueError(f"Coordination requirements not met for workflow: {workflow.name}")

            # Create execution record
            execution_id = f"exec_{int(time.time())}_{str(uuid4())[:8]}"
            execution = WorkflowExecution(
                workflow_id=workflow_id,
                execution_id=execution_id,
                input_data=input_data or {},
                start_coordination=current_coordination,
                ucf_metrics=ucf_metrics,
                status=WorkflowStatus.RUNNING.value,
                execution_context={},
            )

            self.db.add(execution)
            self.db.commit()
            self.db.refresh(execution)

            # Store active execution
            self.active_executions[execution_id] = execution

            # Execute workflow
            await self._execute_workflow_tasks(execution, workflow, input_data or {})

            return execution_id

        except Exception as e:
            logger.error("Error executing workflow %s: %s", workflow_id, e)
            raise

    async def _execute_workflow_tasks(
        self,
        execution: WorkflowExecution,
        workflow: Workflow,
        input_data: dict[str, Any],
    ):
        """Execute workflow tasks with coordination-aware scheduling"""
        try:
            tasks = (
                self.db.query(WorkflowTask)
                .filter(WorkflowTask.workflow_id == workflow.id)
                .order_by(WorkflowTask.task_order)
                .all()
            )

            if not tasks:
                await self._complete_workflow(execution, input_data, {})
                return

            # Optimize task execution order using system optimization
            optimized_tasks = await self._optimize_task_order(tasks, execution.performance_score)

            # Create task executions
            task_executions = {}
            for task in optimized_tasks:
                task_execution = TaskExecution(
                    workflow_execution_id=execution.id,
                    task_id=task.id,
                    input_data=input_data,
                    status=TaskStatus.PENDING.value,
                )
                self.db.add(task_execution)
                task_executions[task.id] = task_execution

            self.db.commit()

            # Execute tasks based on workflow type
            if workflow.workflow_type == "sequential":
                await self._execute_sequential_tasks(execution, task_executions, optimized_tasks)
            elif workflow.workflow_type == "parallel":
                await self._execute_parallel_tasks(execution, task_executions, optimized_tasks)
            elif workflow.workflow_type == "conditional":
                await self._execute_conditional_tasks(execution, task_executions, optimized_tasks)
            else:
                await self._execute_sequential_tasks(execution, task_executions, optimized_tasks)

        except Exception as e:
            logger.error("Error in workflow task execution: %s", e)
            await self._fail_workflow(execution, str(e))

    async def _execute_sequential_tasks(
        self,
        execution: WorkflowExecution,
        task_executions: dict[str, TaskExecution],
        tasks: list[WorkflowTask],
    ):
        """Execute tasks sequentially with coordination monitoring"""
        task_results = {}

        for task in tasks:
            task_execution = task_executions[task.id]

            # Check coordination before each task
            coordination_state = await self.coordination_service.get_current_state()
            current_coordination = coordination_state.get("performance_score", 0.0)

            if current_coordination < task.min_performance_score:
                await self._fail_task(
                    task_execution,
                    f"Coordination level too low: {current_coordination}",
                )
                await self._fail_workflow(execution, f"Task {task.name} failed due to low coordination")
                return

            # Execute task
            result = await self._execute_single_task(task, task_execution, task_results)
            task_results[task.id] = result

            if task_execution.status == TaskStatus.FAILED.value:
                await self._fail_workflow(execution, f"Task {task.name} failed")
                return

        await self._complete_workflow(execution, execution.input_data, task_results)

    async def _execute_parallel_tasks(
        self,
        execution: WorkflowExecution,
        task_executions: dict[str, TaskExecution],
        tasks: list[WorkflowTask],
    ):
        """Execute tasks in parallel with coordination optimization"""
        # Group tasks by dependencies
        dependency_groups = self._group_tasks_by_dependencies(tasks)

        task_results = {}

        for group in dependency_groups:
            if not group:  # Skip empty groups
                continue

            # Execute group in parallel
            tasks_to_execute = [task for task in group if task.can_execute(execution.start_coordination)]

            if tasks_to_execute:
                # Execute in parallel
                task_coroutines = [
                    self._execute_single_task(task, task_executions[task.id], task_results) for task in tasks_to_execute
                ]

                results = await asyncio.gather(*task_coroutines, return_exceptions=True)

                # Process results
                for i, task in enumerate(tasks_to_execute):
                    if isinstance(results[i], Exception):
                        await self._fail_task(task_executions[task.id], str(results[i]))
                        await self._fail_workflow(execution, f"Task {task.name} failed")
                        return
                    else:
                        task_results[task.id] = results[i]

        await self._complete_workflow(execution, execution.input_data, task_results)

    async def _execute_conditional_tasks(
        self,
        execution: WorkflowExecution,
        task_executions: dict[str, TaskExecution],
        tasks: list[WorkflowTask],
    ):
        """Execute tasks conditionally based on coordination and previous results"""
        task_results = {}

        for task in tasks:
            task_execution = task_executions[task.id]

            # Check if task should be executed based on conditions
            should_execute = await self._check_task_conditions(task, task_results, execution)

            if should_execute:
                result = await self._execute_single_task(task, task_execution, task_results)
                task_results[task.id] = result

                if task_execution.status == TaskStatus.FAILED.value:
                    await self._fail_workflow(execution, f"Task {task.name} failed")
                    return
            else:
                await self._skip_task(task_execution, "Conditions not met")

        await self._complete_workflow(execution, execution.input_data, task_results)

    async def _execute_single_task(
        self,
        task: WorkflowTask,
        task_execution: TaskExecution,
        previous_results: dict[str, Any],
    ) -> Any:
        """Execute a single task with coordination tracking"""
        try:
            task_execution.status = TaskStatus.RUNNING.value
            task_execution.started_at = datetime.now(UTC)
            self.db.commit()

            # Get current coordination
            coordination_state = await self.coordination_service.get_current_state()
            task_execution.performance_score = coordination_state.get("performance_score", 0.0)

            # Prepare task input
            task_input = await self._prepare_task_input(task, task_execution.input_data, previous_results)

            # Execute task based on type
            executor = self.task_executors.get(task.task_type)
            if not executor:
                raise ValueError(f"Unknown task type: {task.task_type}")

            start_time = time.time()
            result = await executor(task, task_input)
            execution_time = (time.time() - start_time) * 1000  # Convert to milliseconds

            # Update task execution
            task_execution.status = TaskStatus.COMPLETED.value
            task_execution.completed_at = datetime.now(UTC)
            task_execution.execution_time = execution_time
            task_execution.output_data = result
            task_execution.coordination_impact = await self._calculate_coordination_impact(task, result)

            self.db.commit()

            logger.info("Task %s completed successfully in %.2fms", task.name, execution_time)
            return result

        except Exception as e:
            await self._fail_task(task_execution, str(e))
            raise

    async def _execute_agent_task(self, task: WorkflowTask, task_input: dict[str, Any]) -> Any:
        """Execute agent task using HelixAI Orchestrator Pro"""
        try:
            agent_name = task.assigned_agent or await self._select_best_agent(task)

            # Execute agent task
            result = await self.agent_service.execute_task(
                agent_name=agent_name,
                task_description=task.description,
                input_data=task_input,
                task_config=task.task_config,
            )

            return result

        except Exception as e:
            logger.error("Agent task execution failed: %s", e)
            raise

    async def _execute_api_task(self, task: WorkflowTask, task_input: dict[str, Any]) -> Any:
        """Execute API task using HTTP client"""
        try:
            api_config = task.task_config or {}
            url = api_config.get("url")
            method = api_config.get("method", "GET")
            headers = api_config.get("headers", {})
            timeout = api_config.get("timeout", 30)

            # Add coordination headers
            headers["X-Helix-Coordination"] = str(task.performance_score)
            headers["X-Helix-Timestamp"] = datetime.now(UTC).isoformat()

            # Execute API call
            result = await self._make_api_call(url, method, headers, task_input, timeout)

            return result

        except Exception as e:
            logger.error("API task execution failed: %s", e)
            raise

    async def _execute_database_task(self, task: WorkflowTask, task_input: dict[str, Any]) -> Any:
        """Execute database task"""
        try:
            db_config = task.task_config or {}
            operation = db_config.get("operation")
            query = db_config.get("query")
            parameters = db_config.get("parameters", {})

            # Execute database operation
            result = await self.database_service.execute_query(
                operation=operation,
                query=query,
                parameters={**parameters, **task_input},
            )

            return result

        except Exception as e:
            logger.error("Database task execution failed: %s", e)
            raise

    async def _execute_file_task(self, task: WorkflowTask, task_input: dict[str, Any]) -> Any:
        """Execute file operation task"""
        try:
            file_config = task.task_config or {}
            operation = file_config.get("operation")
            file_path = file_config.get("file_path")

            # Execute file operation
            if operation == "read":
                result = await self._read_file(file_path)
            elif operation == "write":
                content = task_input.get("content", "")
                result = await self._write_file(file_path, content)
            elif operation == "delete":
                result = await self._delete_file(file_path)
            else:
                raise ValueError(f"Unknown file operation: {operation}")

            return result

        except Exception as e:
            logger.error("File task execution failed: %s", e)
            raise

    async def _execute_notification_task(self, task: WorkflowTask, task_input: dict[str, Any]) -> Any:
        """Execute notification task"""
        try:
            notification_config = task.task_config or {}
            notification_type = notification_config.get("type")
            recipients = notification_config.get("recipients", [])

            # Send notification
            result = await self.notification_service.send_notification(
                notification_type=notification_type,
                recipients=recipients,
                message=task_input.get("message", ""),
                context=task_input,
            )

            return result

        except Exception as e:
            logger.error("Notification task execution failed: %s", e)
            raise

    async def _optimize_task_order(self, tasks: list[WorkflowTask], performance_score: float) -> list[WorkflowTask]:
        """Optimize task execution order using system optimization principles"""
        try:
            sorted_tasks = sorted(
                tasks,
                key=lambda t: (
                    len(t.dependencies),  # Fewer dependencies first
                    t.min_performance_score,  # Lower coordination requirements first
                    t.coordination_weight,  # Lower coordination impact first
                    t.task_order,  # Original order as tiebreaker
                ),
            )

            # Apply system superposition optimization
            optimized_tasks = await self._apply_system_optimization(sorted_tasks, performance_score)

            return optimized_tasks

        except Exception as e:
            logger.error("Task optimization failed: %s", e)
            return tasks

    async def _apply_system_optimization(
        self, tasks: list[WorkflowTask], performance_score: float
    ) -> list[WorkflowTask]:
        """Apply system-inspired optimization to task ordering"""
        # This is a simplified system optimization algorithm
        # In a real implementation, this would use system computing principles

        if performance_score >= 0.8:  # High coordination - more parallelization
            # Reorder to maximize parallel execution
            parallel_tasks = [t for t in tasks if t.is_parallelizable]
            sequential_tasks = [t for t in tasks if not t.is_parallelizable]
            return parallel_tasks + sequential_tasks

        elif performance_score >= 0.6:  # Medium coordination - balanced approach
            # Keep original order but optimize dependencies
            return sorted(tasks, key=lambda t: len(t.dependencies))

        else:  # Low coordination - conservative sequential execution
            return sorted(tasks, key=lambda t: t.task_order)

    async def _calculate_coordination_impact(self, task: WorkflowTask, result: Any) -> float:
        """Calculate the coordination impact of a task execution"""
        try:
            base_impact = task.coordination_weight * 0.1

            # Adjust based on result quality
            if isinstance(result, dict) and result.get("success", False):
                impact = base_impact * 1.2  # Positive impact
            else:
                impact = base_impact * -0.8  # Negative impact

            return impact

        except Exception as e:
            logger.error("Coordination impact calculation failed: %s", e)
            return 0.0

    async def _complete_workflow(
        self,
        execution: WorkflowExecution,
        input_data: dict[str, Any],
        task_results: dict[str, Any],
    ):
        """Complete workflow execution successfully"""
        try:
            final_coordination = await self._calculate_final_coordination(execution, task_results)

            # Update execution record
            execution.status = WorkflowStatus.COMPLETED.value
            execution.completed_at = datetime.now(UTC)
            execution.end_coordination = final_coordination
            execution.coordination_delta = final_coordination - execution.start_coordination
            execution.output_data = task_results
            execution.progress = 1.0

            # Calculate execution time
            if execution.started_at:
                execution.execution_time = (execution.completed_at - execution.started_at).total_seconds() * 1000

            self.db.commit()

            # Update workflow statistics
            await self._update_workflow_statistics(execution.workflow_id)

            # Send completion notification
            await self._send_workflow_completion_notification(execution, task_results)

            # Remove from active executions
            if execution.execution_id in self.active_executions:
                del self.active_executions[execution.execution_id]

            logger.info("Workflow %s completed successfully", execution.workflow_id)

        except Exception as e:
            logger.error("Workflow completion failed: %s", e)

    async def _fail_workflow(self, execution: WorkflowExecution, error_message: str):
        """Mark workflow as failed"""
        try:
            execution.error_message = error_message
            execution.completed_at = datetime.now(UTC)

            # Calculate execution time
            if execution.started_at:
                execution.execution_time = (execution.completed_at - execution.started_at).total_seconds() * 1000

            self.db.commit()

            # Update workflow statistics
            await self._update_workflow_statistics(execution.workflow_id)

            # Send failure notification
            await self._send_workflow_failure_notification(execution, error_message)

            # Remove from active executions
            if execution.execution_id in self.active_executions:
                del self.active_executions[execution.execution_id]

            logger.error("Workflow %s failed: %s", execution.workflow_id, error_message)

        except Exception as e:
            logger.error("Workflow failure handling failed: %s", e)

    async def _fail_task(self, task_execution: TaskExecution, error_message: str):
        """Mark task execution as failed"""
        try:
            task_execution.error_message = error_message
            task_execution.completed_at = datetime.now(UTC)

            # Calculate execution time
            if task_execution.started_at:
                task_execution.execution_time = (
                    task_execution.completed_at - task_execution.started_at
                ).total_seconds() * 1000

            self.db.commit()

            logger.error("Task %s failed: %s", task_execution.task_id, error_message)

        except Exception as e:
            logger.error("Task failure handling failed: %s", e)

    async def _skip_task(self, task_execution: TaskExecution, reason: str):
        """Mark task as skipped"""
        try:
            task_execution.error_message = f"Skipped: {reason}"
            task_execution.completed_at = datetime.now(UTC)

            self.db.commit()

            logger.info("Task %s skipped: %s", task_execution.task_id, reason)

        except Exception as e:
            logger.error("Task skip handling failed: %s", e)

    async def _calculate_final_coordination(self, execution: WorkflowExecution, task_results: dict[str, Any]) -> float:
        """Calculate final coordination level after workflow execution"""
        try:
            coordination_state = await self.coordination_service.get_current_state()
            current_coordination = coordination_state.get("performance_score", 0.0)

            # Calculate impact from task results
            total_impact = 0.0
            for task_id, result in task_results.items():
                task_execution = next(te for te in execution.task_executions if te.task_id == task_id)
                total_impact += task_execution.coordination_impact or 0.0

            # Apply impact to current coordination
            final_coordination = current_coordination + total_impact

            # Ensure coordination stays within bounds
            final_coordination = max(0.0, min(10.0, final_coordination))

            return final_coordination

        except Exception as e:
            logger.error("Final coordination calculation failed: %s", e)
            return execution.start_coordination

    async def _update_workflow_statistics(self, workflow_id: str):
        """Update workflow execution statistics"""
        try:
            workflow = self.db.query(Workflow).filter(Workflow.id == workflow_id).first()
            if not workflow:
                return

            # Get execution statistics
            executions = self.db.query(WorkflowExecution).filter(WorkflowExecution.workflow_id == workflow_id).all()

            if not executions:
                return

            # Calculate statistics
            total_executions = len(executions)
            completed_executions = len([e for e in executions if e.status == "completed"])

            success_rate = (completed_executions / total_executions) * 100 if total_executions > 0 else 0.0

            execution_times = [e.execution_time for e in executions if e.execution_time]
            avg_execution_time = sum(execution_times) / len(execution_times) if execution_times else 0.0

            # Update workflow
            workflow.execution_count = total_executions
            workflow.success_rate = success_rate
            workflow.avg_execution_time = avg_execution_time

            self.db.commit()

        except Exception as e:
            logger.error("Workflow statistics update failed: %s", e)

    async def _send_workflow_completion_notification(self, execution: WorkflowExecution, task_results: dict[str, Any]):
        """Send workflow completion notification"""
        try:
            # Send notification (implementation depends on your notification system)
            logger.info("Workflow completion notification sent for %s", execution.execution_id)

        except Exception as e:
            logger.error("Completion notification failed: %s", e)

    async def _send_workflow_failure_notification(self, execution: WorkflowExecution, error_message: str):
        """Send workflow failure notification"""
        try:
            # Send notification (implementation depends on your notification system)
            logger.info("Workflow failure notification sent for %s", execution.execution_id)

        except Exception as e:
            logger.error("Failure notification failed: %s", e)

    async def _select_best_agent(self, task: WorkflowTask) -> str:
        """Select the best agent for a task based on coordination and capabilities"""
        try:
            # For now, return a default agent
            return "Kael"  # Default agent

        except Exception as e:
            logger.error("Agent selection failed: %s", e)
            return "Kael"

    async def _prepare_task_input(
        self,
        task: WorkflowTask,
        base_input: dict[str, Any],
        previous_results: dict[str, Any],
    ) -> dict[str, Any]:
        """Prepare task input by combining base input with previous results"""
        try:
            task_input = base_input.copy()

            # Add previous task results if this task has dependencies
            if task.dependencies:
                for dep_task_id in task.dependencies:
                    if dep_task_id in previous_results:
                        task_input[f"dependency_{dep_task_id}"] = previous_results[dep_task_id]

            # Add task-specific configuration
            task_input.update(task.task_config.get("input_overrides", {}))

            return task_input

        except Exception as e:
            logger.error("Task input preparation failed: %s", e)
            return base_input

    def _group_tasks_by_dependencies(self, tasks: list[WorkflowTask]) -> list[list[WorkflowTask]]:
        """Group tasks by dependency levels for parallel execution"""
        try:
            dependency_levels = []
            processed_tasks = set()

            # Find tasks with no dependencies
            current_level = [task for task in tasks if not task.dependencies]
            while current_level:
                dependency_levels.append(current_level)
                processed_tasks.update(task.id for task in current_level)

                # Find next level of tasks
                next_level = []
                for task in tasks:
                    if task.id not in processed_tasks:
                        # Check if all dependencies are in previous levels
                        if all(dep_id in processed_tasks for dep_id in task.dependencies):
                            next_level.append(task)

                current_level = next_level

            return dependency_levels

        except Exception as e:
            logger.error("Task dependency grouping failed: %s", e)
            return [tasks]

    async def _check_task_conditions(
        self,
        task: WorkflowTask,
        previous_results: dict[str, Any],
        execution: WorkflowExecution,
    ) -> bool:
        """Check if task conditions are met for conditional workflows"""
        try:
            conditions = task.task_config.get("conditions", [])

            if not conditions:
                return True

            # Evaluate conditions
            for condition in conditions:
                condition_type = condition.get("type")
                condition_value = condition.get("value")

                if condition_type == "previous_task_result":
                    task_id = condition.get("task_id")
                    expected_result = condition.get("expected_result")

                    if task_id in previous_results:
                        actual_result = previous_results[task_id]
                        if actual_result != expected_result:
                            return False

                elif condition_type == "performance_score":
                    if execution.start_coordination < condition_value:
                        return False

                elif condition_type == "execution_context":
                    context_key = condition.get("key")
                    expected_value = condition.get("expected_value")

                    if context_key in execution.execution_context:
                        if execution.execution_context[context_key] != expected_value:
                            return False

            return True

        except Exception as e:
            logger.error("Task condition check failed: %s", e)
            return False

    async def _make_api_call(
        self,
        url: str,
        method: str,
        headers: dict[str, str],
        data: dict[str, Any],
        timeout: int,
    ) -> Any:
        """Make HTTP API call with coordination headers"""
        import httpx

        async with httpx.AsyncClient(timeout=timeout) as client:
            method_upper = method.upper()
            if method_upper == "GET":
                resp = await client.get(url, headers=headers, params=data)
            elif method_upper == "POST":
                resp = await client.post(url, headers=headers, json=data)
            elif method_upper == "PUT":
                resp = await client.put(url, headers=headers, json=data)
            elif method_upper == "PATCH":
                resp = await client.patch(url, headers=headers, json=data)
            elif method_upper == "DELETE":
                resp = await client.delete(url, headers=headers)
            else:
                resp = await client.request(method_upper, url, headers=headers, json=data)

            resp.raise_for_status()
            try:
                return resp.json()
            except (json.JSONDecodeError, ValueError) as e:
                logger.debug("Response is not valid JSON: %s", e)
                return {"success": True, "status_code": resp.status_code, "text": resp.text}
            except Exception as e:
                logger.warning("Unexpected error parsing response: %s", e)
                return {"success": True, "status_code": resp.status_code, "text": resp.text}

    async def _read_file(self, file_path: str) -> Any:
        """Read file content from web_os_storage sandbox"""
        import os

        import aiofiles

        base_dir = os.path.join(os.path.dirname(__file__), "..", "..", "web_os_storage")
        safe_path = os.path.normpath(os.path.join(base_dir, file_path))
        if not safe_path.startswith(os.path.normpath(base_dir)):
            return {"success": False, "error": "Path traversal denied"}
        if not os.path.isfile(safe_path):
            return {"success": False, "error": "File not found"}
        async with aiofiles.open(safe_path, encoding="utf-8") as f:
            content = await f.read()
        return {"success": True, "content": content, "file_path": file_path}

    async def _write_file(self, file_path: str, content: str) -> Any:
        """Write content to file in web_os_storage sandbox"""
        import os

        import aiofiles

        base_dir = os.path.join(os.path.dirname(__file__), "..", "..", "web_os_storage")
        safe_path = os.path.normpath(os.path.join(base_dir, file_path))
        if not safe_path.startswith(os.path.normpath(base_dir)):
            return {"success": False, "error": "Path traversal denied"}
        os.makedirs(os.path.dirname(safe_path), exist_ok=True)
        async with aiofiles.open(safe_path, "w", encoding="utf-8") as f:
            await f.write(content)
        return {"success": True, "file_path": file_path}

    async def _delete_file(self, file_path: str) -> Any:
        """Delete file from web_os_storage sandbox"""
        import os

        base_dir = os.path.join(os.path.dirname(__file__), "..", "..", "web_os_storage")
        safe_path = os.path.normpath(os.path.join(base_dir, file_path))
        if not safe_path.startswith(os.path.normpath(base_dir)):
            return {"success": False, "error": "Path traversal denied"}
        if not os.path.isfile(safe_path):
            return {"success": False, "error": "File not found"}
        os.remove(safe_path)
        return {"success": True, "file_path": file_path}

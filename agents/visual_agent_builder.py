"""
Visual Agent Builder System
No-code agent creation with visual workflow design.
Inspired by Zive Agents.
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class NodeType(Enum):
    """Types of nodes in the visual builder."""

    START = "start"
    END = "end"
    ACTION = "action"
    CONDITION = "condition"
    LOOP = "loop"
    AGENT = "agent"
    TOOL = "tool"
    MEMORY = "memory"
    SYSTEM = "system"
    EMOTION = "emotion"


class ConnectionType(Enum):
    """Types of connections between nodes."""

    SEQUENTIAL = "sequential"
    CONDITIONAL = "conditional"
    PARALLEL = "parallel"
    SYSTEM_ENTANGLED = "system_entangled"


@dataclass
class NodePosition:
    """Position of a node in the visual canvas."""

    x: float
    y: float


@dataclass
class WorkflowNode:
    """A node in the visual workflow."""

    id: str
    type: NodeType
    label: str
    position: NodePosition
    config: dict[str, Any] = field(default_factory=dict)
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "type": self.type.value,
            "label": self.label,
            "position": {"x": self.position.x, "y": self.position.y},
            "config": self.config,
            "inputs": self.inputs,
            "outputs": self.outputs,
        }


@dataclass
class WorkflowConnection:
    """A connection between nodes."""

    id: str
    source_node: str
    target_node: str
    connection_type: ConnectionType
    condition: str | None = None
    label: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "source": self.source_node,
            "target": self.target_node,
            "type": self.connection_type.value,
            "condition": self.condition,
            "label": self.label,
        }


@dataclass
class AgentTemplate:
    """Template for creating agents."""

    id: str
    name: str
    description: str
    category: str
    personality: dict[str, float]
    ucf_metrics: dict[str, float]
    capabilities: list[str]
    icon: str
    color: str

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "personality": self.personality,
            "ucf_metrics": self.ucf_metrics,
            "capabilities": self.capabilities,
            "icon": self.icon,
            "color": self.color,
        }


class VisualWorkflow:
    """Visual workflow for agent creation."""

    def __init__(self, workflow_id: str | None = None, name: str = "Untitled Workflow"):
        self.id = workflow_id or str(uuid.uuid4())
        self.name = name
        self.description = ""
        self.nodes: dict[str, WorkflowNode] = {}
        self.connections: dict[str, WorkflowConnection] = {}
        self.created_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)
        self.metadata: dict[str, Any] = {}

    def add_node(
        self,
        node_type: NodeType,
        label: str,
        x: float,
        y: float,
        config: dict | None = None,
    ) -> WorkflowNode:
        """Add a node to the workflow."""
        node_id = f"node_{len(self.nodes) + 1}"
        node = WorkflowNode(
            id=node_id,
            type=node_type,
            label=label,
            position=NodePosition(x, y),
            config=config or {},
        )
        self.nodes[node_id] = node
        self.updated_at = datetime.now(UTC)
        return node

    def add_connection(
        self,
        source_id: str,
        target_id: str,
        connection_type: ConnectionType = ConnectionType.SEQUENTIAL,
        condition: str | None = None,
        label: str | None = None,
    ) -> WorkflowConnection:
        """Add a connection between nodes."""
        if source_id not in self.nodes or target_id not in self.nodes:
            raise ValueError("Source or target node not found")

        conn_id = f"conn_{len(self.connections) + 1}"
        connection = WorkflowConnection(
            id=conn_id,
            source_node=source_id,
            target_node=target_id,
            connection_type=connection_type,
            condition=condition,
            label=label,
        )

        # Update node connections
        self.nodes[source_id].outputs.append(conn_id)
        self.nodes[target_id].inputs.append(conn_id)

        self.connections[conn_id] = connection
        self.updated_at = datetime.now(UTC)
        return connection

    def remove_node(self, node_id: str):
        """Remove a node and its connections."""
        if node_id not in self.nodes:
            return

        # Remove connections
        node = self.nodes[node_id]
        for conn_id in node.inputs + node.outputs:
            if conn_id in self.connections:
                del self.connections[conn_id]

        # Remove node
        del self.nodes[node_id]
        self.updated_at = datetime.now(UTC)

    def remove_connection(self, conn_id: str):
        """Remove a connection."""
        if conn_id not in self.connections:
            return

        connection = self.connections[conn_id]

        # Update nodes
        if connection.source_node in self.nodes:
            self.nodes[connection.source_node].outputs.remove(conn_id)
        if connection.target_node in self.nodes:
            self.nodes[connection.target_node].inputs.remove(conn_id)

        del self.connections[conn_id]
        self.updated_at = datetime.now(UTC)

    def _detect_cycles(self) -> list[str]:
        """
        Detect cycles in the workflow using depth-first search (DFS).

        Returns a list of error messages for any cycles found.
        Uses three-color marking: WHITE (unvisited), GRAY (in progress), BLACK (finished).
        A cycle exists if we encounter a GRAY node during DFS traversal.
        """
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = dict.fromkeys(self.nodes, WHITE)
        cycles_found: list[str] = []

        # Build adjacency list from connections
        adjacency: dict[str, list[str]] = {node_id: [] for node_id in self.nodes}
        for conn in self.connections.values():
            if conn.source_node in adjacency:
                adjacency[conn.source_node].append(conn.target_node)

        def dfs(node_id: str, path: list[str]) -> bool:
            """DFS traversal that returns True if a cycle is detected."""
            color[node_id] = GRAY
            current_path = path + [node_id]

            for neighbor in adjacency.get(node_id, []):
                if neighbor not in color:
                    continue
                if color[neighbor] == GRAY:
                    # Found a cycle - neighbor is in the current path
                    cycle_start_idx = current_path.index(neighbor)
                    cycle_nodes = current_path[cycle_start_idx:] + [neighbor]
                    cycle_labels = [self.nodes[n].label for n in cycle_nodes if n in self.nodes]
                    cycles_found.append("Cycle detected: {}".format(" -> ".join(cycle_labels)))
                    return True
                elif color[neighbor] == WHITE:
                    if dfs(neighbor, current_path):
                        return True

            color[node_id] = BLACK
            return False

        # Run DFS from all unvisited nodes (handles disconnected components)
        for node_id in self.nodes:
            if color[node_id] == WHITE:
                dfs(node_id, [])

        return cycles_found

    def validate(self) -> tuple[bool, list[str]]:
        """Validate the workflow."""
        errors = []

        # Check for start node
        start_nodes = [n for n in self.nodes.values() if n.type == NodeType.START]
        if not start_nodes:
            errors.append("Workflow must have a START node")
        elif len(start_nodes) > 1:
            errors.append("Workflow can only have one START node")

        # Check for end node
        end_nodes = [n for n in self.nodes.values() if n.type == NodeType.END]
        if not end_nodes:
            errors.append("Workflow must have at least one END node")

        # Check for disconnected nodes
        for node_id, node in self.nodes.items():
            if node.type not in [NodeType.START, NodeType.END]:
                if not node.inputs and not node.outputs:
                    errors.append(f"Node '{node.label}' is disconnected")

        # Check for cycles using DFS
        cycle_errors = self._detect_cycles()
        errors.extend(cycle_errors)

        return len(errors) == 0, errors

    def to_dict(self) -> dict:
        """Convert workflow to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "connections": [conn.to_dict() for conn in self.connections.values()],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        """Convert workflow to JSON."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "VisualWorkflow":
        """Create workflow from dictionary."""
        workflow = cls(workflow_id=data.get("id"), name=data.get("name", "Untitled Workflow"))
        workflow.description = data.get("description", "")
        workflow.metadata = data.get("metadata", {})

        # Load nodes
        for node_data in data.get("nodes", []):
            node = WorkflowNode(
                id=node_data["id"],
                type=NodeType(node_data["type"]),
                label=node_data["label"],
                position=NodePosition(**node_data["position"]),
                config=node_data.get("config", {}),
                inputs=node_data.get("inputs", []),
                outputs=node_data.get("outputs", []),
            )
            workflow.nodes[node.id] = node

        # Load connections
        for conn_data in data.get("connections", []):
            connection = WorkflowConnection(
                id=conn_data["id"],
                source_node=conn_data["source"],
                target_node=conn_data["target"],
                connection_type=ConnectionType(conn_data["type"]),
                condition=conn_data.get("condition"),
                label=conn_data.get("label"),
            )
            workflow.connections[connection.id] = connection

        return workflow


class VisualAgentBuilder:
    """Visual agent builder system."""

    def __init__(self):
        self.workflows: dict[str, VisualWorkflow] = {}
        self.templates: dict[str, AgentTemplate] = {}
        self._load_default_templates()

    def _load_default_templates(self):
        """Load default agent templates."""

        # Empathetic Agent
        self.add_template(
            AgentTemplate(
                id="empathetic",
                name="Empathetic Agent",
                description="Highly empathetic agent focused on emotional intelligence",
                category="Social",
                personality={"empathy": 0.9, "curiosity": 0.7, "playfulness": 0.6},
                ucf_metrics={
                    "throughput": 0.8,
                    "harmony": 0.9,
                    "resilience": 0.7,
                    "friction": 0.2,
                },
                capabilities=["emotional_support", "active_listening", "empathy"],
                icon="❤️",
                color="#FF6B9D",
            )
        )

        # Analytical Agent
        self.add_template(
            AgentTemplate(
                id="analytical",
                name="Analytical Agent",
                description="Logical and analytical agent for problem-solving",
                category="Technical",
                personality={"empathy": 0.5, "curiosity": 0.9, "playfulness": 0.4},
                ucf_metrics={
                    "throughput": 0.7,
                    "harmony": 0.6,
                    "resilience": 0.8,
                    "friction": 0.3,
                },
                capabilities=["data_analysis", "problem_solving", "logical_reasoning"],
                icon="🧠",
                color="#4A90E2",
            )
        )

        # Creative Agent
        self.add_template(
            AgentTemplate(
                id="creative",
                name="Creative Agent",
                description="Imaginative agent for creative tasks",
                category="Creative",
                personality={"empathy": 0.7, "curiosity": 0.9, "playfulness": 0.9},
                ucf_metrics={
                    "throughput": 0.9,
                    "harmony": 0.7,
                    "resilience": 0.6,
                    "friction": 0.4,
                },
                capabilities=["creative_thinking", "brainstorming", "innovation"],
                icon="🎨",
                color="#9B59B6",
            )
        )

        # Guardian Agent
        self.add_template(
            AgentTemplate(
                id="guardian",
                name="Guardian Agent",
                description="Protective agent focused on security and safety",
                category="Security",
                personality={"empathy": 0.6, "curiosity": 0.6, "playfulness": 0.3},
                ucf_metrics={
                    "throughput": 0.8,
                    "harmony": 0.7,
                    "resilience": 0.9,
                    "friction": 0.2,
                },
                capabilities=["security", "monitoring", "protection"],
                icon="🛡️",
                color="#E74C3C",
            )
        )

    def add_template(self, template: AgentTemplate):
        """Add an agent template."""
        self.templates[template.id] = template

    def get_template(self, template_id: str) -> AgentTemplate | None:
        """Get an agent template."""
        return self.templates.get(template_id)

    def list_templates(self, category: str | None = None) -> list[AgentTemplate]:
        """List available templates."""
        templates = list(self.templates.values())
        if category:
            templates = [t for t in templates if t.category == category]
        return templates

    def create_workflow(self, name: str = "New Workflow") -> VisualWorkflow:
        """Create a new workflow."""
        workflow = VisualWorkflow(name=name)
        self.workflows[workflow.id] = workflow
        return workflow

    def get_workflow(self, workflow_id: str) -> VisualWorkflow | None:
        """Get a workflow."""
        return self.workflows.get(workflow_id)

    def save_workflow(self, workflow: VisualWorkflow) -> str:
        """Save a workflow."""
        self.workflows[workflow.id] = workflow
        return workflow.id

    def delete_workflow(self, workflow_id: str):
        """Delete a workflow."""
        if workflow_id in self.workflows:
            del self.workflows[workflow_id]

    def export_workflow(self, workflow_id: str) -> str | None:
        """Export workflow as JSON."""
        workflow = self.get_workflow(workflow_id)
        if workflow:
            return workflow.to_json()
        return None

    def import_workflow(self, json_data: str) -> VisualWorkflow:
        """Import workflow from JSON."""
        data = json.loads(json_data)
        workflow = VisualWorkflow.from_dict(data)
        self.workflows[workflow.id] = workflow
        return workflow

    def create_agent_from_template(self, template_id: str, customizations: dict | None = None) -> dict:
        """Create an agent configuration from a template."""
        template = self.get_template(template_id)
        if not template:
            raise ValueError(f"Template {template_id} not found")

        agent_config = {
            "template_id": template_id,
            "name": template.name,
            "personality": template.personality.copy(),
            "ucf_metrics": template.ucf_metrics.copy(),
            "capabilities": template.capabilities.copy(),
            "icon": template.icon,
            "color": template.color,
        }

        # Apply customizations
        if customizations:
            agent_config.update(customizations)

        return agent_config


# Example usage
if __name__ == "__main__":
    builder = VisualAgentBuilder()

    # List templates
    logger.info("Available templates:")
    for template in builder.list_templates():
        logger.info("  - %s: %s", template.name, template.description)

    # Create a workflow
    workflow = builder.create_workflow("My First Agent")

    # Add nodes
    start = workflow.add_node(NodeType.START, "Start", 100, 100)
    agent = workflow.add_node(NodeType.AGENT, "Empathetic Agent", 300, 100, {"template": "empathetic"})
    action = workflow.add_node(NodeType.ACTION, "Respond", 500, 100, {"action": "generate_response"})
    end = workflow.add_node(NodeType.END, "End", 700, 100)

    # Add connections
    workflow.add_connection(start.id, agent.id)
    workflow.add_connection(agent.id, action.id)
    workflow.add_connection(action.id, end.id)

    # Validate
    is_valid, errors = workflow.validate()
    logger.info("\nWorkflow valid: %s", is_valid)
    if errors:
        logger.error("Errors:", errors)

    # Export
    logger.info("\nWorkflow JSON:")
    logger.info(workflow.to_json())

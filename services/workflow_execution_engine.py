"""
Helix Workflow Execution Engine — Proprietary n8n Alternative
==============================================================

A fully proprietary, async Python workflow execution engine that replaces
the need for n8n or any external workflow tool. Built from scratch with:

- DAG-based execution with topological sorting
- 25+ built-in node types (HTTP, Email, DB, AI, Transform, etc.)
- Async execution with proper error handling and retries
- Webhook triggers and cron scheduling
- State persistence and execution replay
- UCF coordination metrics per execution
- Plugin system for custom node types

This is NOT a wrapper around n8n. This IS the engine.

(c) Helix Collective 2025 - Proprietary Technology Stack
"""

import ast
import asyncio
import copy
import json
import logging
import os
import re
import smtplib
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Workflow file operations are sandboxed to this directory
_WORKFLOW_DATA_DIR = Path(os.getenv("WORKFLOW_DATA_DIR", "/tmp/helix_workflows")).resolve()


def _safe_workflow_path(user_path: str) -> Path:
    """Resolve user-supplied path within the workflow sandbox directory."""
    resolved = (_WORKFLOW_DATA_DIR / user_path).resolve()
    if not str(resolved).startswith(str(_WORKFLOW_DATA_DIR)):
        raise ValueError("Path traversal blocked")
    return resolved


# ============================================================================
# CORE TYPES
# ============================================================================


class NodeType(str, Enum):
    # Triggers
    WEBHOOK = "webhook"
    SCHEDULE = "schedule"
    MANUAL = "manual"
    EVENT = "event"

    # Data
    HTTP_REQUEST = "http_request"
    DATABASE_QUERY = "database_query"
    READ_FILE = "read_file"
    WRITE_FILE = "write_file"

    # Transform
    TRANSFORM = "transform"
    FILTER = "filter"
    MERGE = "merge"
    SPLIT = "split"
    AGGREGATE = "aggregate"
    JSON_PARSE = "json_parse"
    TEMPLATE = "template"
    CODE = "code"

    # AI
    AI_AGENT = "ai_agent"
    AI_CLASSIFY = "ai_classify"
    AI_SUMMARIZE = "ai_summarize"
    AI_EXTRACT = "ai_extract"
    AI_GENERATE = "ai_generate"

    # Communication
    EMAIL_SEND = "email_send"
    WEBHOOK_RESPONSE = "webhook_response"
    NOTIFICATION = "notification"

    # Flow Control
    CONDITIONAL = "conditional"
    LOOP = "loop"
    DELAY = "delay"
    ERROR_HANDLER = "error_handler"
    ROUTER = "router"  # Multi-way routing based on previous step output
    SUB_WORKFLOW = "sub_workflow"
    STOP_AND_ERROR = "stop_and_error"
    HUMAN_INPUT = "human_input"
    LLM_ROUTER = "llm_router"

    # Integration
    SLACK = "slack"
    DISCORD = "discord"
    GITHUB = "github"


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"
    WAITING = "waiting"


class NodeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# ============================================================================
# NODE DEFINITIONS
# ============================================================================


@dataclass
class NodeConfig:
    """Configuration for a workflow node."""

    id: str
    type: NodeType
    name: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    position: dict[str, float] = field(default_factory=lambda: {"x": 0, "y": 0})
    retry_count: int = 0
    retry_delay_seconds: float = 1.0
    timeout_seconds: float = 30.0
    continue_on_error: bool = False
    quality_gate: dict[str, Any] | None = None  # Quality gate config (mode, required_keys, expression, etc.)
    notes: str = ""


@dataclass
class Connection:
    """Connection between two nodes."""

    from_node: str
    to_node: str
    from_port: str = "output"
    to_port: str = "input"
    condition: str | None = None  # For conditional routing


@dataclass
class WorkflowDefinition:
    """Complete workflow definition."""

    id: str
    name: str
    description: str = ""
    nodes: list[NodeConfig] = field(default_factory=list)
    connections: list[Connection] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)
    trigger_config: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    version: int = 1
    created_at: str = ""
    updated_at: str = ""
    created_by: str = ""
    is_active: bool = True
    error_workflow_id: str | None = None  # Trigger another workflow on failure
    error_workflow_id: str | None = None  # Trigger another workflow on failure


@dataclass
class NodeExecutionResult:
    """Result from executing a single node."""

    node_id: str
    status: NodeStatus
    output: Any = None
    error: str | None = None
    started_at: str = ""
    completed_at: str = ""
    duration_ms: float = 0.0
    retries: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionState:
    """Complete execution state for replay/debugging."""

    execution_id: str
    workflow_id: str
    status: ExecutionStatus = ExecutionStatus.PENDING
    trigger_type: str = "manual"
    trigger_data: dict[str, Any] = field(default_factory=dict)
    node_results: dict[str, NodeExecutionResult] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)
    snapshots: list[dict[str, Any]] = field(default_factory=list)
    started_at: str = ""
    completed_at: str = ""
    total_duration_ms: float = 0.0
    error: str | None = None
    coordination_metrics: dict[str, float] = field(default_factory=dict)
    custom_data: dict[str, str] = field(default_factory=dict)  # User-attachable execution metadata
    pending_human_input: dict[str, Any] | None = None  # Active human input request


# ============================================================================
# NODE EXECUTORS — The actual logic for each node type
# ============================================================================


class NodeExecutors:
    """Registry of node execution functions. Each returns output data."""

    @staticmethod
    async def execute_http_request(params: dict, context: dict) -> Any:
        """Execute an HTTP request node."""
        url = params.get("url", "")
        method = params.get("method", "GET").upper()
        headers = params.get("headers", {})
        body = params.get("body")
        timeout = params.get("timeout", 30)
        auth = params.get("auth")

        # Template variable substitution
        url = NodeExecutors._substitute_vars(url, context)
        if isinstance(body, str):
            body = NodeExecutors._substitute_vars(body, context)

        async with httpx.AsyncClient(timeout=timeout) as client:
            kwargs: dict[str, Any] = {"headers": headers}
            if auth:
                if auth.get("type") == "bearer":
                    kwargs["headers"]["Authorization"] = f"Bearer {auth['token']}"
                elif auth.get("type") == "basic":
                    kwargs["auth"] = (auth["username"], auth["password"])

            if method in ("POST", "PUT", "PATCH") and body:
                if isinstance(body, (dict, list)):
                    kwargs["json"] = body
                else:
                    kwargs["content"] = body

            response = await client.request(method, url, **kwargs)

            result = {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": None,
            }

            try:
                result["body"] = response.json()
            except (json.JSONDecodeError, ValueError) as e:
                logger.debug("Response is not valid JSON: %s", e)
                result["body"] = response.text
            except Exception as e:
                logger.warning("Unexpected error parsing response: %s", e)
                result["body"] = response.text

            return result

    @staticmethod
    async def execute_transform(params: dict, context: dict) -> Any:
        """Transform data using expressions."""
        operation = params.get("operation", "map")
        input_data = context.get("input_data", params.get("data"))
        expression = params.get("expression", "")  # noqa: F841 — planned for expression eval

        if operation == "map" and isinstance(input_data, list):
            # Simple field mapping
            field_map = params.get("field_map", {})
            return [
                {new_key: item.get(old_key) for new_key, old_key in field_map.items()}
                for item in input_data
                if isinstance(item, dict)
            ]
        elif operation == "pick":
            fields = params.get("fields", [])
            if isinstance(input_data, dict):
                return {k: v for k, v in input_data.items() if k in fields}
            elif isinstance(input_data, list):
                return [{k: v for k, v in item.items() if k in fields} for item in input_data if isinstance(item, dict)]
        elif operation == "flatten":
            if isinstance(input_data, list):
                result = []
                for item in input_data:
                    if isinstance(item, list):
                        result.extend(item)
                    else:
                        result.append(item)
                return result
        elif operation == "set":
            # Set specific values
            target = params.get("target", {})
            if isinstance(input_data, dict):
                return {**input_data, **target}
            return target

        return input_data

    @staticmethod
    async def execute_filter(params: dict, context: dict) -> Any:
        """Filter data based on conditions."""
        input_data = context.get("input_data", params.get("data", []))
        field_name = params.get("field", "")
        operator = params.get("operator", "equals")
        value = params.get("value")

        if not isinstance(input_data, list):
            input_data = [input_data]

        def matches(item: Any) -> bool:
            if not isinstance(item, dict):
                return False
            item_val = item.get(field_name)
            if operator == "equals":
                return item_val == value
            elif operator == "not_equals":
                return item_val != value
            elif operator == "contains":
                return value in str(item_val) if item_val else False
            elif operator == "greater_than":
                return float(item_val or 0) > float(value or 0)
            elif operator == "less_than":
                return float(item_val or 0) < float(value or 0)
            elif operator == "exists":
                return field_name in item
            elif operator == "regex":
                return bool(re.search(str(value), str(item_val or "")))
            return True

        return [item for item in input_data if matches(item)]

    @staticmethod
    async def execute_conditional(params: dict, context: dict) -> Any:
        """Evaluate a condition and return which branch to take."""
        condition_field = params.get("field", "")
        operator = params.get("operator", "equals")
        value = params.get("value")
        input_data = context.get("input_data", {})

        actual_value = input_data.get(condition_field) if isinstance(input_data, dict) else input_data

        result = False
        if operator == "equals":
            result = actual_value == value
        elif operator == "not_equals":
            result = actual_value != value
        elif operator == "greater_than":
            result = float(actual_value or 0) > float(value or 0)
        elif operator == "less_than":
            result = float(actual_value or 0) < float(value or 0)
        elif operator == "contains":
            result = str(value) in str(actual_value or "")
        elif operator == "is_empty":
            result = not actual_value
        elif operator == "is_not_empty" or operator == "truthy":
            result = bool(actual_value)

        return {"condition_met": result, "branch": "true" if result else "false", "value": actual_value}

    @staticmethod
    async def execute_merge(params: dict, context: dict) -> Any:
        """Merge data from multiple inputs."""
        mode = params.get("mode", "append")
        inputs = context.get("multi_input", [])

        if mode == "append":
            result = []
            for inp in inputs:
                if isinstance(inp, list):
                    result.extend(inp)
                else:
                    result.append(inp)
            return result
        elif mode == "combine":
            if all(isinstance(i, dict) for i in inputs):
                merged = {}
                for inp in inputs:
                    merged.update(inp)
                return merged
        elif mode == "zip":
            if len(inputs) >= 2 and all(isinstance(i, list) for i in inputs):
                return [dict(zip(range(len(pair)), pair, strict=False)) for pair in zip(*inputs, strict=False)]

        return inputs

    @staticmethod
    async def execute_split(params: dict, context: dict) -> Any:
        """Split data into multiple outputs."""
        input_data = context.get("input_data", [])
        field_name = params.get("field", "")

        if isinstance(input_data, list) and field_name:
            groups: dict[str, list] = defaultdict(list)
            for item in input_data:
                if isinstance(item, dict):
                    key = str(item.get(field_name, "unknown"))
                    groups[key].append(item)
            return dict(groups)
        elif isinstance(input_data, list):
            chunk_size = params.get("chunk_size", 10)
            return [input_data[i : i + chunk_size] for i in range(0, len(input_data), chunk_size)]

        return [input_data]

    @staticmethod
    async def execute_aggregate(params: dict, context: dict) -> Any:
        """Aggregate data with operations like sum, count, avg."""
        input_data = context.get("input_data", [])
        operation = params.get("operation", "count")
        field_name = params.get("field", "")

        if not isinstance(input_data, list):
            return {"result": input_data}

        if operation == "count":
            return {"count": len(input_data)}
        elif operation == "sum" and field_name:
            total = sum(float(item.get(field_name, 0)) for item in input_data if isinstance(item, dict))
            return {"sum": total, "field": field_name}
        elif operation == "avg" and field_name:
            values = [float(item.get(field_name, 0)) for item in input_data if isinstance(item, dict)]
            return {"avg": sum(values) / len(values) if values else 0, "field": field_name}
        elif operation == "min" and field_name:
            values = [float(item.get(field_name, 0)) for item in input_data if isinstance(item, dict)]
            return {"min": min(values) if values else 0, "field": field_name}
        elif operation == "max" and field_name:
            values = [float(item.get(field_name, 0)) for item in input_data if isinstance(item, dict)]
            return {"max": max(values) if values else 0, "field": field_name}
        elif operation == "group" and field_name:
            groups: dict[str, int] = defaultdict(int)
            for item in input_data:
                if isinstance(item, dict):
                    groups[str(item.get(field_name, "unknown"))] += 1
            return {"groups": dict(groups)}

        return {"count": len(input_data)}

    @staticmethod
    def _validate_code_safety(code: str) -> None:
        """AST-level validation to prevent sandbox escape.

        Blocks:
        - import / from...import statements
        - Calls to dangerous builtins (__import__, eval, exec, compile, open, etc.)
        - Attribute access to dunder methods that enable escape
        """
        # Dangerous names that could be used to escape the sandbox
        BLOCKED_NAMES = {
            "__import__",
            "eval",
            "exec",
            "compile",
            "open",
            "getattr",
            "setattr",
            "delattr",
            "globals",
            "locals",
            "vars",
            "dir",
            "breakpoint",
            "exit",
            "quit",
            "__subclasses__",
            "__bases__",
            "__mro__",
        }

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            raise RuntimeError("Code syntax error: %s" % str(e))

        for node in ast.walk(tree):
            # Block import statements
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                raise RuntimeError("Import statements are not allowed in workflow code")
            # Block calls to dangerous builtins
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id in BLOCKED_NAMES:
                    raise RuntimeError("Call to '%s' is not allowed in workflow code" % func.id)
                if isinstance(func, ast.Attribute) and func.attr in BLOCKED_NAMES:
                    raise RuntimeError("Access to '%s' is not allowed in workflow code" % func.attr)
            # Block access to dunder attributes (e.g. obj.__class__.__subclasses__)
            if isinstance(node, ast.Attribute) and node.attr.startswith("__") and node.attr.endswith("__"):
                raise RuntimeError("Access to dunder attribute '%s' is not allowed" % node.attr)

    @staticmethod
    async def execute_code(params: dict, context: dict) -> Any:
        """Execute custom Python code in a sandboxed environment."""
        code = params.get("code", "")
        input_data = context.get("input_data")

        # Create a restricted execution environment
        safe_globals = {
            "__builtins__": {
                "len": len,
                "str": str,
                "int": int,
                "float": float,
                "list": list,
                "dict": dict,
                "set": set,
                "tuple": tuple,
                "bool": bool,
                "None": None,
                "True": True,
                "False": False,
                "range": range,
                "enumerate": enumerate,
                "zip": zip,
                "map": map,
                "filter": filter,
                "sorted": sorted,
                "min": min,
                "max": max,
                "sum": sum,
                "abs": abs,
                "round": round,
                "isinstance": isinstance,
                # NOTE: 'type' intentionally excluded — sandbox escape vector
                "print": lambda *a: None,  # Suppress prints
            },
            "json": json,
            "re": re,
            "input_data": input_data,
            "variables": context.get("variables", {}),
            "output": None,
        }

        try:
            # AST-level validation: block imports, dangerous builtins, dunder access
            WorkflowSteps._validate_code_safety(code)  # noqa: F821
            exec(code, safe_globals)
            return safe_globals.get("output", input_data)
        except RuntimeError:
            raise  # Re-raise our validation errors as-is
        except Exception as e:
            raise RuntimeError("Code execution error: %s" % str(e))

    @staticmethod
    async def execute_template(params: dict, context: dict) -> Any:
        """Render a template with variable substitution."""
        template = params.get("template", "")
        input_data = context.get("input_data", {})
        variables = context.get("variables", {})

        # Simple {{variable}} substitution
        result = template
        all_vars = {**variables}
        if isinstance(input_data, dict):
            all_vars.update(input_data)

        for key, value in all_vars.items():
            result = result.replace(f"{{{{{key}}}}}", str(value))

        return {"rendered": result}

    @staticmethod
    async def execute_json_parse(params: dict, context: dict) -> Any:
        """Parse JSON string to object or extract fields."""
        input_data = context.get("input_data", "")
        path = params.get("path", "")

        if isinstance(input_data, str):
            try:
                data = json.loads(input_data)
            except json.JSONDecodeError:
                return {"error": "Invalid JSON", "raw": input_data}
        else:
            data = input_data

        if path:
            # Simple dot-notation path extraction
            parts = path.split(".")
            current = data
            for part in parts:
                if isinstance(current, dict):
                    current = current.get(part)
                elif isinstance(current, list) and part.isdigit():
                    current = current[int(part)] if int(part) < len(current) else None
                else:
                    current = None
                    break
            return current

        return data

    @staticmethod
    async def execute_email_send(params: dict, context: dict) -> Any:
        """Send an email via SMTP."""
        smtp_host = params.get("smtp_host", os.environ.get("SMTP_HOST", ""))
        smtp_port = int(params.get("smtp_port", os.environ.get("SMTP_PORT", "587")))
        smtp_user = params.get("smtp_user", os.environ.get("SMTP_USER", ""))
        smtp_pass = params.get("smtp_password", os.environ.get("SMTP_PASSWORD", ""))
        from_addr = params.get("from", smtp_user)
        to_addrs = params.get("to", [])
        subject = params.get("subject", "")
        body = params.get("body", "")
        html = params.get("html", False)

        if isinstance(to_addrs, str):
            to_addrs = [to_addrs]

        # Substitute variables
        subject = NodeExecutors._substitute_vars(subject, context)
        body = NodeExecutors._substitute_vars(body, context)

        if not smtp_host or not to_addrs:
            return {"sent": False, "error": "SMTP not configured or no recipients"}

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = ", ".join(to_addrs)

        if html:
            msg.attach(MIMEText(body, "html"))
        else:
            msg.attach(MIMEText(body, "plain"))

        try:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                if smtp_user and smtp_pass:
                    server.login(smtp_user, smtp_pass)
                server.sendmail(from_addr, to_addrs, msg.as_string())
            return {"sent": True, "recipients": to_addrs, "subject": subject}
        except Exception as e:
            logger.error("Failed to send email: %s", e)
            return {"sent": False, "error": "Email delivery failed"}

    @staticmethod
    async def execute_delay(params: dict, context: dict) -> Any:
        """Delay execution for a specified duration."""
        seconds = params.get("seconds", 1)
        await asyncio.sleep(min(seconds, 300))  # Max 5 minutes
        return {"delayed": seconds, "input_data": context.get("input_data")}

    @staticmethod
    async def execute_loop(params: dict, context: dict) -> Any:
        """Loop over input data items."""
        input_data = context.get("input_data", [])
        if not isinstance(input_data, list):
            input_data = [input_data]
        return {"items": input_data, "count": len(input_data)}

    @staticmethod
    async def execute_ai_agent(params: dict, context: dict) -> Any:
        """Execute an AI agent call through the Helix LLM bridge."""
        agent_id = params.get("agent_id", "vega")
        prompt = params.get("prompt", "")
        input_data = context.get("input_data", "")

        # Substitute variables into prompt
        prompt = NodeExecutors._substitute_vars(prompt, context)
        if not prompt and input_data:
            prompt = str(input_data)

        try:
            from apps.backend.services.agent_llm_bridge import get_agent_llm_bridge

            bridge = get_agent_llm_bridge()
            await bridge.initialize()
            response = await bridge.generate_response(
                agent_id=agent_id,
                user_message=prompt,
            )
            return {
                "agent_id": agent_id,
                "response": response.content,
                "model_used": response.model_used,
                "tokens_used": response.tokens_used,
                "coordination_state": response.coordination_state,
            }
        except Exception as e:
            logger.error("AI agent execution failed for %s: %s", agent_id, e)
            return {"agent_id": agent_id, "error": "AI agent execution failed", "response": None}

    @staticmethod
    async def execute_ai_summarize(params: dict, context: dict) -> Any:
        """Summarize text using AI."""
        text = params.get("text", "") or str(context.get("input_data", ""))
        max_length = params.get("max_length", 200)

        try:
            from apps.backend.services.agent_llm_bridge import get_agent_llm_bridge

            bridge = get_agent_llm_bridge()
            await bridge.initialize()
            response = await bridge.generate_response(
                agent_id="oracle",
                user_message=f"Summarize the following in {max_length} words or less:\n\n{text[:3000]}",
            )
            return {"summary": response.content, "original_length": len(text)}
        except ImportError as e:
            logger.debug("Agent LLM bridge not available: %s", e)
            return {"summary": text[:max_length] + "...", "original_length": len(text), "fallback": True}
        except (ConnectionError, TimeoutError, OSError) as e:
            logger.debug("LLM service connection error: %s", e)
            return {"summary": text[:max_length] + "...", "original_length": len(text), "fallback": True}
        except Exception as e:
            logger.warning("AI summarization failed: %s", e)
            # Fallback: simple truncation
            return {"summary": text[:max_length] + "...", "original_length": len(text), "fallback": True}

    @staticmethod
    async def execute_ai_classify(params: dict, context: dict) -> Any:
        """Classify text into categories using AI."""
        text = str(context.get("input_data", params.get("text", "")))
        categories = params.get("categories", [])

        try:
            from apps.backend.services.agent_llm_bridge import get_agent_llm_bridge

            bridge = get_agent_llm_bridge()
            await bridge.initialize()
            response = await bridge.generate_response(
                agent_id="oracle",
                user_message=(
                    f"Classify the following text into one of these categories: "
                    f"{', '.join(categories)}.\n\nText: {text[:2000]}\n\n"
                    f"Respond with ONLY the category name."
                ),
            )
            return {"category": response.content.strip(), "text_preview": text[:200]}
        except Exception as e:
            logger.error("AI classification failed: %s", e)
            return {"category": "unknown", "error": "Classification failed"}

    @staticmethod
    async def execute_ai_extract(params: dict, context: dict) -> Any:
        """Extract structured data from text using AI."""
        text = str(context.get("input_data", params.get("text", "")))
        fields = params.get("fields", [])

        try:
            from apps.backend.services.agent_llm_bridge import get_agent_llm_bridge

            bridge = get_agent_llm_bridge()
            await bridge.initialize()
            response = await bridge.generate_response(
                agent_id="oracle",
                user_message=(
                    f"Extract the following fields from the text: {', '.join(fields)}.\n\n"
                    f"Text: {text[:3000]}\n\n"
                    f"Respond in JSON format with the field names as keys."
                ),
            )
            try:
                extracted = json.loads(response.content)
            except json.JSONDecodeError:
                extracted = {"raw": response.content}
            return {"extracted": extracted, "fields_requested": fields}
        except Exception as e:
            logger.error("AI data extraction failed: %s", e)
            return {"extracted": {}, "error": "Data extraction failed"}

    @staticmethod
    async def execute_ai_generate(params: dict, context: dict) -> Any:
        """Generate content using AI."""
        prompt = params.get("prompt", "")
        agent_id = params.get("agent_id", "surya")
        prompt = NodeExecutors._substitute_vars(prompt, context)

        try:
            from apps.backend.services.agent_llm_bridge import get_agent_llm_bridge

            bridge = get_agent_llm_bridge()
            await bridge.initialize()
            response = await bridge.generate_response(agent_id=agent_id, user_message=prompt)
            return {"generated": response.content, "agent_id": agent_id, "model": response.model_used}
        except Exception as e:
            logger.error("AI content generation failed: %s", e)
            return {"generated": None, "error": "Content generation failed"}

    @staticmethod
    async def execute_notification(params: dict, context: dict) -> Any:
        """Send a notification (webhook, internal, etc.)."""
        channel = params.get("channel", "internal")
        message = params.get("message", "")
        message = NodeExecutors._substitute_vars(message, context)

        if channel == "webhook":
            url = params.get("webhook_url", "")
            if url:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(url, json={"message": message, "timestamp": datetime.now(UTC).isoformat()})
                    return {"sent": True, "channel": "webhook", "status": resp.status_code}
        elif channel == "discord":
            webhook_url = params.get("discord_webhook", os.environ.get("DISCORD_WEBHOOK_URL", ""))
            if webhook_url:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(webhook_url, json={"content": message})
                    return {"sent": True, "channel": "discord", "status": resp.status_code}
        elif channel == "slack":
            webhook_url = params.get("slack_webhook", os.environ.get("SLACK_WEBHOOK_URL", ""))
            if webhook_url:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(webhook_url, json={"text": message})
                    return {"sent": True, "channel": "slack", "status": resp.status_code}

        return {"sent": True, "channel": "internal", "message": message}

    @staticmethod
    async def execute_database_query(params: dict, context: dict) -> Any:
        """Execute a database query (SELECT only for safety)."""
        query = params.get("query", "")
        query = NodeExecutors._substitute_vars(query, context)
        db_url = params.get("database_url", os.environ.get("DATABASE_URL", ""))

        if not db_url:
            return {"error": "No database URL configured", "rows": []}

        # Security guardrails: only allow SELECT queries
        normalized = query.strip().upper()
        _BLOCKED_SQL = {
            "INSERT",
            "UPDATE",
            "DELETE",
            "DROP",
            "ALTER",
            "TRUNCATE",
            "CREATE",
            "GRANT",
            "REVOKE",
            "EXEC",
            "EXECUTE",
            "COPY",
        }
        first_word = normalized.split()[0] if normalized.split() else ""
        if first_word in _BLOCKED_SQL:
            logger.warning("Blocked non-SELECT SQL in workflow: %s", first_word)
            return {"error": "Only SELECT queries are allowed in workflows", "rows": []}

        if not normalized.startswith("SELECT"):
            logger.warning("Non-SELECT query rejected in workflow node")
            return {"error": "Only SELECT queries are allowed in workflows", "rows": []}

        if len(query) > 10_000:
            return {"error": "Query too long (max 10,000 chars)", "rows": []}

        try:
            import asyncpg

            conn = await asyncpg.connect(db_url)
            try:
                rows = await conn.fetch(query)
                return {"rows": [dict(r) for r in rows], "count": len(rows)}
            finally:
                await conn.close()
        except ImportError:
            return {"error": "asyncpg not installed", "rows": []}
        except Exception as e:
            logger.error("Database query execution failed: %s", e)
            return {"error": "Database query failed", "rows": []}

    @staticmethod
    async def execute_read_file(params: dict, context: dict) -> Any:
        """Read a file from the workflow sandbox directory."""
        file_path = params.get("path", "")
        encoding = params.get("encoding", "utf-8")

        try:
            safe_path = _safe_workflow_path(file_path)
            content = safe_path.read_text(encoding=encoding)
            return {"content": content, "path": str(safe_path), "size": len(content)}
        except ValueError:
            logger.warning("Workflow file read blocked (path traversal): %s", file_path)
            return {"error": "Access denied — path outside sandbox", "path": file_path}
        except Exception as e:
            logger.error("File read failed for %s: %s", file_path, e)
            return {"error": "File read failed", "path": file_path}

    @staticmethod
    async def execute_write_file(params: dict, context: dict) -> Any:
        """Write data to a file in the workflow sandbox directory."""
        file_path = params.get("path", "")
        content = params.get("content", "") or str(context.get("input_data", ""))
        content = NodeExecutors._substitute_vars(content, context)

        try:
            safe_path = _safe_workflow_path(file_path)
            safe_path.parent.mkdir(parents=True, exist_ok=True)
            safe_path.write_text(content, encoding="utf-8")
            return {"written": True, "path": str(safe_path), "size": len(content)}
        except ValueError:
            logger.warning("Workflow file write blocked (path traversal): %s", file_path)
            return {"error": "Access denied — path outside sandbox", "path": file_path}
        except Exception as e:
            logger.error("File write failed for %s: %s", file_path, e)
            return {"error": "File write failed", "path": file_path}

    @staticmethod
    async def execute_webhook_response(params: dict, context: dict) -> Any:
        """Prepare a webhook response."""
        status_code = params.get("status_code", 200)
        body = params.get("body", context.get("input_data", {}))
        headers = params.get("headers", {"Content-Type": "application/json"})
        return {"status_code": status_code, "body": body, "headers": headers}

    @staticmethod
    async def execute_error_handler(params: dict, context: dict) -> Any:
        """Handle errors from previous nodes."""
        error = context.get("error")
        fallback = params.get("fallback_value")
        action = params.get("action", "continue")  # continue, retry, stop

        return {
            "error_handled": True,
            "original_error": str(error) if error else None,
            "action": action,
            "fallback_value": fallback,
        }

    @staticmethod
    async def execute_github(params: dict, context: dict) -> Any:
        """Interact with GitHub API."""
        action = params.get("action", "get_repo")
        token = params.get("token", os.environ.get("GITHUB_TOKEN", ""))
        repo = params.get("repo", "")

        headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}

        async with httpx.AsyncClient(timeout=30) as client:
            if action == "get_repo":
                resp = await client.get(f"https://api.github.com/repos/{repo}", headers=headers)
                return resp.json()
            elif action == "list_issues":
                resp = await client.get(f"https://api.github.com/repos/{repo}/issues", headers=headers)
                return resp.json()
            elif action == "create_issue":
                resp = await client.post(
                    f"https://api.github.com/repos/{repo}/issues",
                    headers=headers,
                    json={"title": params.get("title", ""), "body": params.get("body", "")},
                )
                return resp.json()

        return {"error": f"Unknown GitHub action: {action}"}

    @staticmethod
    async def execute_router(params: dict, context: dict) -> Any:
        """Multi-way router: examines input and returns a route key.

        The router selects which downstream branch to follow based on
        the previous step's output. Downstream connections whose
        ``condition`` field matches the returned route key will execute;
        others are skipped.

        Params:
            field (str): Key to inspect in input_data (default: "route")
            routes (dict): Mapping of possible values → descriptions
                           (used for documentation/validation)
            default_route (str): Fallback route if field value doesn't
                                match any defined route (default: "default")
            expression (str): Optional Python expression evaluated against
                              input_data to compute the route key. If set,
                              ``field`` is ignored.
        """
        input_data = context.get("input_data", {})
        field_name = params.get("field", "route")
        default_route = params.get("default_route", "default")
        expression = params.get("expression")
        routes = params.get("routes", {})

        route_key = default_route

        if expression:
            # Evaluate expression to compute route key
            safe_builtins = {
                "len": len,
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
                "type": type,
                "max": max,
                "min": min,
            }
            namespace = {"input": input_data, "data": input_data, **safe_builtins}
            try:
                from apps.backend.utils.safe_eval import safe_eval

                route_key = str(safe_eval(expression, allowed_names=namespace))
            except Exception as e:
                logger.warning("Router expression failed: %s, using default", e)
                route_key = default_route
        elif isinstance(input_data, dict):
            route_key = str(input_data.get(field_name, default_route))
        elif isinstance(input_data, str):
            route_key = input_data

        # Validate against defined routes
        if routes and route_key not in routes:
            logger.info(
                "Router: '%s' not in defined routes %s, using default '%s'",
                route_key,
                list(routes.keys()),
                default_route,
            )
            route_key = default_route

        return {
            "route": route_key,
            "available_routes": list(routes.keys()) if routes else [],
            "input_field": field_name,
        }

    @staticmethod
    async def execute_stop_and_error(params: dict, context: dict) -> Any:
        """Intentionally halt execution with an error message.

        Useful for validation-driven failures.  Triggers the error
        workflow if configured on the workflow definition.
        """
        message = params.get("message", "Execution stopped")
        error_code = params.get("error_code")
        condition = params.get("condition")

        if condition:
            input_data = context.get("input_data", {})
            safe_ns = {
                "input": input_data,
                "data": input_data,
                "len": len,
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
            }
            try:
                from apps.backend.utils.safe_eval import safe_eval

                should_stop = bool(safe_eval(condition, allowed_names=safe_ns))
            except Exception as e:
                logger.warning("stop_and_error condition eval failed: %s", e)
                should_stop = True
            if not should_stop:
                return {"stopped": False, "reason": "Condition not met"}

        raise RuntimeError(f"[STOP_AND_ERROR] {message} (code={error_code})")

    @staticmethod
    async def execute_human_input(params: dict, context: dict) -> Any:
        """Pause workflow execution and wait for human approval.

        Returns a marker dict — the engine loop checks for ``status:
        waiting_input`` and pauses execution.
        """
        prompt = params.get("prompt", "Please review and approve")
        actions = params.get("actions", ["approve", "reject"])
        timeout_minutes = params.get("timeout_minutes", 1440)
        assignee = params.get("assignee")
        require_feedback = params.get("require_feedback", False)

        return {
            "status": "waiting_input",
            "prompt": prompt,
            "actions": actions,
            "timeout_minutes": timeout_minutes,
            "assignee": assignee,
            "require_feedback": require_feedback,
            "requested_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    async def execute_llm_router(params: dict, context: dict) -> Any:
        """LLM-as-judge routing: classify input into named scenarios.

        Uses a cheap model to determine which downstream branch should
        execute, based on natural language understanding.
        """
        import json as _json

        scenarios = params.get("scenarios", {})
        instructions = params.get("instructions", "Classify the input into one of the defined scenarios.")
        model = params.get("model", "openai/gpt-4o-mini")
        default_scenario = params.get("default_scenario", "other")

        if not scenarios:
            return {"route": default_scenario, "reason": "No scenarios defined"}

        input_data = context.get("input_data", {})
        input_text = _json.dumps(input_data) if isinstance(input_data, dict) else str(input_data)

        scenario_list = "\n".join(f"- {name}: {desc}" for name, desc in scenarios.items())
        prompt = (
            f"{instructions}\n\nAvailable scenarios:\n{scenario_list}\n\n"
            f"Input to classify:\n{input_text}\n\n"
            f"Respond with ONLY the scenario name (one of: {', '.join(scenarios.keys())}). "
            f"If none match, respond with '{default_scenario}'."
        )

        try:
            from apps.backend.services.unified_llm import UnifiedLLMService

            llm = UnifiedLLMService()
            response = await llm.generate(
                prompt=prompt,
                model=model,
                max_tokens=50,
                temperature=0.1,
            )
            route_key = response.strip().lower().replace('"', "").replace("'", "")
            if route_key not in scenarios:
                logger.info(
                    "LLM router returned '%s' not in scenarios %s, using default",
                    route_key,
                    list(scenarios.keys()),
                )
                route_key = default_scenario
        except Exception as e:
            logger.warning("LLM router classification failed: %s, using default", e)
            route_key = default_scenario

        return {
            "route": route_key,
            "available_routes": list(scenarios.keys()),
            "input_preview": str(input_text)[:200],
        }

    @staticmethod
    def _substitute_vars(text: str, context: dict) -> str:
        """Substitute {{variable}} patterns in text."""
        if not isinstance(text, str):
            return text
        variables = context.get("variables", {})
        input_data = context.get("input_data", {})

        all_vars = {**variables}
        if isinstance(input_data, dict):
            all_vars.update(input_data)

        for key, value in all_vars.items():
            text = text.replace(f"{{{{{key}}}}}", str(value))

        return text


# ============================================================================
# WORKFLOW EXECUTION ENGINE
# ============================================================================

# Map node types to executor functions
NODE_EXECUTOR_MAP: dict[NodeType, Callable] = {
    NodeType.HTTP_REQUEST: NodeExecutors.execute_http_request,
    NodeType.TRANSFORM: NodeExecutors.execute_transform,
    NodeType.FILTER: NodeExecutors.execute_filter,
    NodeType.CONDITIONAL: NodeExecutors.execute_conditional,
    NodeType.MERGE: NodeExecutors.execute_merge,
    NodeType.SPLIT: NodeExecutors.execute_split,
    NodeType.AGGREGATE: NodeExecutors.execute_aggregate,
    NodeType.CODE: NodeExecutors.execute_code,
    NodeType.TEMPLATE: NodeExecutors.execute_template,
    NodeType.JSON_PARSE: NodeExecutors.execute_json_parse,
    NodeType.EMAIL_SEND: NodeExecutors.execute_email_send,
    NodeType.DELAY: NodeExecutors.execute_delay,
    NodeType.LOOP: NodeExecutors.execute_loop,
    NodeType.AI_AGENT: NodeExecutors.execute_ai_agent,
    NodeType.AI_SUMMARIZE: NodeExecutors.execute_ai_summarize,
    NodeType.AI_CLASSIFY: NodeExecutors.execute_ai_classify,
    NodeType.AI_EXTRACT: NodeExecutors.execute_ai_extract,
    NodeType.AI_GENERATE: NodeExecutors.execute_ai_generate,
    NodeType.NOTIFICATION: NodeExecutors.execute_notification,
    NodeType.DATABASE_QUERY: NodeExecutors.execute_database_query,
    NodeType.READ_FILE: NodeExecutors.execute_read_file,
    NodeType.WRITE_FILE: NodeExecutors.execute_write_file,
    NodeType.WEBHOOK_RESPONSE: NodeExecutors.execute_webhook_response,
    NodeType.ERROR_HANDLER: NodeExecutors.execute_error_handler,
    NodeType.GITHUB: NodeExecutors.execute_github,
    NodeType.ROUTER: NodeExecutors.execute_router,
    NodeType.STOP_AND_ERROR: NodeExecutors.execute_stop_and_error,
    NodeType.HUMAN_INPUT: NodeExecutors.execute_human_input,
    NodeType.LLM_ROUTER: NodeExecutors.execute_llm_router,
}

# Custom node plugin registry
_custom_node_registry: dict[str, Callable] = {}


def register_custom_node(node_type: str, executor: Callable) -> None:
    """Register a custom node type with its executor function."""
    _custom_node_registry[node_type] = executor
    logger.info("🔌 Registered custom node type: %s", node_type)


class WorkflowEngine:
    """
    The core workflow execution engine.

    Executes workflows as DAGs with topological sorting,
    async node execution, error handling, and state tracking.
    """

    def __init__(self):
        self._executions: dict[str, ExecutionState] = {}
        self._workflows: dict[str, WorkflowDefinition] = {}

    def register_workflow(self, workflow: WorkflowDefinition) -> str:
        """Register a workflow definition."""
        if not workflow.id:
            workflow.id = str(uuid.uuid4())
        workflow.created_at = workflow.created_at or datetime.now(UTC).isoformat()
        workflow.updated_at = datetime.now(UTC).isoformat()
        self._workflows[workflow.id] = workflow
        logger.info("📋 Registered workflow: %s (%s)", workflow.name, workflow.id)
        return workflow.id

    def get_workflow(self, workflow_id: str) -> WorkflowDefinition | None:
        """Get a workflow by ID."""
        return self._workflows.get(workflow_id)

    def list_workflows(self) -> list[dict[str, Any]]:
        """List all registered workflows."""
        return [
            {
                "id": w.id,
                "name": w.name,
                "description": w.description,
                "nodes": len(w.nodes),
                "connections": len(w.connections),
                "is_active": w.is_active,
                "version": w.version,
                "tags": w.tags,
                "created_at": w.created_at,
                "updated_at": w.updated_at,
            }
            for w in self._workflows.values()
        ]

    async def execute(
        self,
        workflow_id: str,
        trigger_data: dict[str, Any] | None = None,
        variables: dict[str, Any] | None = None,
    ) -> ExecutionState:
        """Execute a workflow."""
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow not found: {workflow_id}")

        execution_id = str(uuid.uuid4())
        state = ExecutionState(
            execution_id=execution_id,
            workflow_id=workflow_id,
            status=ExecutionStatus.RUNNING,
            trigger_data=trigger_data or {},
            variables={**workflow.variables, **(variables or {})},
            started_at=datetime.now(UTC).isoformat(),
        )
        self._executions[execution_id] = state

        try:
            # Build adjacency graph
            node_map = {n.id: n for n in workflow.nodes}
            adjacency: dict[str, list[str]] = defaultdict(list)
            reverse_adj: dict[str, list[str]] = defaultdict(list)

            for conn in workflow.connections:
                adjacency[conn.from_node].append(conn.to_node)
                reverse_adj[conn.to_node].append(conn.from_node)

            # Topological sort
            execution_order = self._topological_sort(node_map.keys(), adjacency, reverse_adj)

            # Take snapshot of initial state
            state.snapshots.append(
                {
                    "step": 0,
                    "type": "initial",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "variables": copy.deepcopy(state.variables),
                    "node_statuses": {},
                }
            )

            # ── Pre-execution planning ────────────────────────────────────
            if workflow.variables.get("enable_planning"):
                plan = await self._generate_workflow_plan(workflow, trigger_data)
                if plan:
                    state.variables["_execution_plan"] = plan
                    state.snapshots.append(
                        {
                            "step": len(state.snapshots),
                            "type": "plan_generated",
                            "timestamp": datetime.now(UTC).isoformat(),
                            "plan": plan[:500],
                        }
                    )

            # Execute nodes in order
            node_outputs: dict[str, Any] = {}

            for node_id in execution_order:
                node = node_map.get(node_id)
                if not node:
                    continue

                # Skip nodes already marked by conditional/router branching
                prior = state.node_results.get(node_id)
                if prior and prior.status == NodeStatus.SKIPPED:
                    continue

                # Gather input from parent nodes
                parent_outputs = []
                for parent_id in reverse_adj.get(node_id, []):
                    if parent_id in node_outputs:
                        parent_outputs.append(node_outputs[parent_id])

                # Build execution context
                context = {
                    "input_data": (
                        parent_outputs[0]
                        if len(parent_outputs) == 1
                        else (parent_outputs if parent_outputs else trigger_data)
                    ),
                    "multi_input": parent_outputs,
                    "variables": state.variables,
                    "trigger_data": trigger_data or {},
                    "execution_id": execution_id,
                    "node_id": node_id,
                }

                # Handle conditional branching
                if node.type == NodeType.CONDITIONAL:
                    result = await self._execute_node(node, context, state)
                    node_outputs[node_id] = result.output
                    # Skip false-branch nodes if condition not met
                    if isinstance(result.output, dict) and not result.output.get("condition_met"):
                        # Mark downstream false-branch nodes as skipped
                        for conn in workflow.connections:
                            if conn.from_node == node_id and conn.condition == "false":
                                state.node_results[conn.to_node] = NodeExecutionResult(
                                    node_id=conn.to_node,
                                    status=NodeStatus.SKIPPED,
                                )
                    continue

                # Handle multi-way routing
                if node.type == NodeType.ROUTER:
                    result = await self._execute_node(node, context, state)
                    node_outputs[node_id] = result.output
                    selected_route = (
                        result.output.get("route", "default") if isinstance(result.output, dict) else "default"
                    )
                    # Skip downstream nodes whose connection condition
                    # doesn't match the selected route
                    for conn in workflow.connections:
                        if conn.from_node == node_id:
                            if conn.condition and conn.condition != selected_route:
                                state.node_results[conn.to_node] = NodeExecutionResult(
                                    node_id=conn.to_node,
                                    status=NodeStatus.SKIPPED,
                                )
                    continue

                # Handle LLM-based routing (same downstream skip logic as ROUTER)
                if node.type == NodeType.LLM_ROUTER:
                    result = await self._execute_node(node, context, state)
                    node_outputs[node_id] = result.output
                    selected_route = result.output.get("route", "other") if isinstance(result.output, dict) else "other"
                    for conn in workflow.connections:
                        if conn.from_node == node_id:
                            if conn.condition and conn.condition != selected_route:
                                state.node_results[conn.to_node] = NodeExecutionResult(
                                    node_id=conn.to_node,
                                    status=NodeStatus.SKIPPED,
                                )
                    continue

                # Handle human-in-the-loop pause
                if node.type == NodeType.HUMAN_INPUT:
                    result = await self._execute_node(node, context, state)
                    node_outputs[node_id] = result.output
                    if isinstance(result.output, dict) and result.output.get("status") == "waiting_input":
                        state.status = ExecutionStatus.WAITING
                        state.pending_human_input = {
                            "node_id": node_id,
                            **result.output,
                        }
                        logger.info(
                            "Workflow %s paused at HUMAN_INPUT node %s",
                            workflow_id,
                            node_id,
                        )
                        break  # Pause execution — resume via external API
                    continue

                # Execute the node
                result = await self._execute_node(node, context, state)
                node_outputs[node_id] = result.output

                # Quality gate validation (if configured on this node)
                if node.quality_gate and result.status != NodeStatus.FAILED:
                    gate_passed = await self._run_node_quality_gate(node, result.output, state)
                    if not gate_passed:
                        on_failure = node.quality_gate.get("on_failure", "fail")
                        if on_failure == "fail" and not node.continue_on_error:
                            state.status = ExecutionStatus.FAILED
                            state.error = f"Quality gate failed for node '{node.name}'"
                            break

                # Update variables if node outputs them
                if isinstance(result.output, dict) and node.params.get("output_variable"):
                    state.variables[node.params["output_variable"]] = result.output

                # Take snapshot after each node
                state.snapshots.append(
                    {
                        "step": len(state.snapshots),
                        "type": "node_complete",
                        "node_id": node_id,
                        "node_name": node.name,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "output_preview": str(result.output)[:500] if result.output else None,
                        "status": result.status.value,
                        "duration_ms": result.duration_ms,
                    }
                )

                # Stop on failure if not continue_on_error
                if result.status == NodeStatus.FAILED and not node.continue_on_error:
                    state.status = ExecutionStatus.FAILED
                    state.error = result.error
                    break

            if state.status not in (ExecutionStatus.FAILED, ExecutionStatus.WAITING):
                state.status = ExecutionStatus.COMPLETED

        except Exception as e:
            logger.error("Workflow execution failed: %s", e, exc_info=True)
            state.status = ExecutionStatus.FAILED
            state.error = str(e)

        # If paused for human input, store state and return early
        if state.status == ExecutionStatus.WAITING:
            self._executions[execution_id] = state
            return state

        state.completed_at = datetime.now(UTC).isoformat()
        start = datetime.fromisoformat(state.started_at)
        end = datetime.fromisoformat(state.completed_at)
        state.total_duration_ms = (end - start).total_seconds() * 1000

        # Error workflow: trigger a separate workflow on failure
        if state.status == ExecutionStatus.FAILED and workflow.error_workflow_id:
            await self._trigger_error_workflow(
                workflow,
                state,
                execution_id,
            )

        # Calculate coordination metrics
        state.coordination_metrics = self._calculate_coordination_metrics(state)

        logger.info(
            "⚡ Workflow %s execution %s: %s (%.1fms, %d nodes)",
            workflow_id,
            state.status.value,
            execution_id,
            state.total_duration_ms,
            len(state.node_results),
        )

        return state

    async def _run_node_quality_gate(self, node: NodeConfig, output: Any, state: ExecutionState) -> bool:
        """Run quality gate validation on a node's output.

        Supports retry-with-feedback: when the gate fails, the failure reason
        is injected into context and the node is re-executed. Returns True if
        the gate eventually passes.
        """
        from apps.backend.services.quality_gate_validator import validate_quality_gate

        gate_config = node.quality_gate
        max_retries = gate_config.get("max_retries", 1) if isinstance(gate_config, dict) else 1
        feedback_on_retry = gate_config.get("feedback_on_retry", True) if isinstance(gate_config, dict) else True

        current_output = output

        for attempt in range(1 + max_retries):
            result = await validate_quality_gate(gate_config, current_output, node.name)

            if result.passed:
                if attempt > 0:
                    logger.info(
                        "Quality gate passed for node '%s' on retry %d: %s",
                        node.name,
                        attempt,
                        result.reason,
                    )
                    # Clear feedback from context
                    state.variables.pop(f"_quality_gate_feedback_{node.id}", None)
                else:
                    logger.info("Quality gate passed for node '%s': %s", node.name, result.reason)
                return True

            logger.warning(
                "Quality gate failed for node '%s' (attempt %d/%d): %s",
                node.name,
                attempt + 1,
                1 + max_retries,
                result.reason,
            )

            state.snapshots.append(
                {
                    "step": len(state.snapshots),
                    "type": "quality_gate_failed",
                    "node_id": node.id,
                    "node_name": node.name,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "reason": result.reason,
                    "mode": result.mode,
                    "attempt": attempt + 1,
                    "max_retries": max_retries,
                }
            )

            if attempt < max_retries:
                # Inject feedback into state variables before retry
                if feedback_on_retry:
                    feedback = (
                        "QUALITY GATE FEEDBACK: Your previous output was rejected. "
                        f"Reason: {result.reason}. Please correct your output to address this issue."
                    )
                    state.variables[f"_quality_gate_feedback_{node.id}"] = feedback
                    state.variables[f"_quality_gate_last_rejection_{node.id}"] = result.reason

                # Re-execute the node
                context = {"variables": state.variables, "inputs": state.inputs}
                retry_result = await self._execute_node(node, context, state)
                current_output = retry_result.output

        return False

    async def _execute_node(self, node: NodeConfig, context: dict, state: ExecutionState) -> NodeExecutionResult:
        """Execute a single node with retry logic."""
        start_time = time.time()
        result = NodeExecutionResult(
            node_id=node.id,
            status=NodeStatus.RUNNING,
            started_at=datetime.now(UTC).isoformat(),
        )
        state.node_results[node.id] = result

        executor = NODE_EXECUTOR_MAP.get(node.type) or _custom_node_registry.get(node.type)
        if not executor:
            result.status = NodeStatus.FAILED
            result.error = f"No executor for node type: {node.type}"
            result.completed_at = datetime.now(UTC).isoformat()
            result.duration_ms = (time.time() - start_time) * 1000
            return result

        retries = 0
        last_error = None

        while retries <= node.retry_count:
            try:
                output = await asyncio.wait_for(
                    executor(node.params, context),
                    timeout=node.timeout_seconds,
                )
                result.status = NodeStatus.COMPLETED
                result.output = output
                result.retries = retries
                break
            except TimeoutError:
                last_error = f"Node timed out after {node.timeout_seconds}s"
                retries += 1
            except Exception as e:
                last_error = str(e)
                retries += 1
                if retries <= node.retry_count:
                    await asyncio.sleep(node.retry_delay_seconds * retries)

        if result.status != NodeStatus.COMPLETED:
            result.status = NodeStatus.FAILED
            result.error = last_error
            result.retries = retries

        result.completed_at = datetime.now(UTC).isoformat()
        result.duration_ms = (time.time() - start_time) * 1000
        return result

    async def _generate_workflow_plan(
        self,
        workflow: WorkflowDefinition,
        trigger_data: dict[str, Any] | None,
    ) -> str | None:
        """Use a cheap model to plan the workflow execution.

        Returns a brief text plan or None on failure.
        """
        node_descriptions = []
        for n in workflow.nodes:
            node_descriptions.append(f"- [{n.type.value}] {n.name or n.id} (params: {list(n.params.keys())[:5]})")

        conn_descriptions = []
        for c in workflow.connections[:20]:
            cond = f" (condition: {c.condition})" if c.condition else ""
            conn_descriptions.append(f"  {c.from_node} → {c.to_node}{cond}")

        prompt = (
            "You are a workflow planning assistant. Create a concise execution plan.\n\n"
            "Workflow: {name}\n"
            "Trigger: {trigger}\n\n"
            "Nodes:\n{nodes}\n\n"
            "Connections:\n{conns}\n\n"
            "For each node: what it should accomplish, expected I/O, risks.\n"
            "Keep under 300 words."
        ).format(
            name=workflow.name,
            trigger=str(trigger_data)[:300] if trigger_data else "manual",
            nodes="\n".join(node_descriptions[:20]),
            conns="\n".join(conn_descriptions[:20]),
        )

        try:
            from apps.backend.services.unified_llm import unified_llm

            plan = await unified_llm.generate(
                prompt=prompt,
                model="openai/gpt-4o-mini",
                max_tokens=512,
                temperature=0.3,
            )
            return plan.strip() if plan else None
        except ImportError:
            return None
        except Exception as e:
            logger.warning("Workflow plan generation failed: %s", e)
            return None

    async def _trigger_error_workflow(
        self,
        workflow: WorkflowDefinition,
        state: ExecutionState,
        execution_id: str,
    ) -> None:
        """Trigger a separate workflow when this one fails.

        Passes the error details and original execution metadata so the
        error workflow can take corrective action (alert, retry, clean up).
        """
        error_wf_id = workflow.error_workflow_id
        if not error_wf_id or error_wf_id not in self._workflows:
            logger.warning(
                "Error workflow '%s' not registered, skipping error trigger",
                error_wf_id,
            )
            return

        error_trigger_data = {
            "error_source": "workflow",
            "source_workflow_id": workflow.id,
            "source_workflow_name": workflow.name,
            "source_execution_id": execution_id,
            "error": state.error,
            "failed_at": state.completed_at,
            "node_results_summary": {
                nid: {"status": nr.status.value, "error": nr.error}
                for nid, nr in state.node_results.items()
                if nr.status == NodeStatus.FAILED
            },
        }

        try:
            logger.info(
                "Triggering error workflow '%s' for failed execution %s",
                error_wf_id,
                execution_id,
            )
            await self.execute(error_wf_id, trigger_data=error_trigger_data)
        except Exception as e:
            logger.error(
                "Error workflow '%s' itself failed: %s",
                error_wf_id,
                e,
            )

    def _topological_sort(
        self,
        nodes: Any,
        adjacency: dict[str, list[str]],
        reverse_adj: dict[str, list[str]],
    ) -> list[str]:
        """Topological sort of the workflow DAG."""
        in_degree: dict[str, int] = {n: 0 for n in nodes}
        for node_id in nodes:
            in_degree[node_id] = len(reverse_adj.get(node_id, []))

        queue = deque([n for n, d in in_degree.items() if d == 0])
        order = []

        while queue:
            node = queue.popleft()
            order.append(node)
            for neighbor in adjacency.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(list(nodes)):
            logger.warning("Workflow has cycles — executing in registration order")
            return list(nodes)

        return order

    def _calculate_coordination_metrics(self, state: ExecutionState) -> dict[str, float]:
        """Calculate UCF coordination metrics for the execution."""
        completed = sum(1 for r in state.node_results.values() if r.status == NodeStatus.COMPLETED)
        total = len(state.node_results)
        failed = sum(1 for r in state.node_results.values() if r.status == NodeStatus.FAILED)

        return {
            "harmony": completed / max(total, 1),
            "resilience": 1.0 - (failed / max(total, 1)),
            "throughput": min(1.0, 1000 / max(state.total_duration_ms, 1)),  # Energy efficiency
            "focus": 1.0 if state.status == ExecutionStatus.COMPLETED else 0.5,
            "friction": failed / max(total, 1),
        }

    def get_execution(self, execution_id: str) -> ExecutionState | None:
        """Get execution state by ID."""
        return self._executions.get(execution_id)

    def list_executions(
        self,
        workflow_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List executions with optional filtering."""
        execs = list(self._executions.values())
        if workflow_id:
            execs = [e for e in execs if e.workflow_id == workflow_id]
        if status:
            execs = [e for e in execs if e.status.value == status]
        execs.sort(key=lambda e: e.started_at or "", reverse=True)
        return [
            {
                "execution_id": e.execution_id,
                "workflow_id": e.workflow_id,
                "status": e.status.value,
                "started_at": e.started_at,
                "completed_at": e.completed_at,
                "total_duration_ms": e.total_duration_ms,
                "nodes_executed": len(e.node_results),
                "error": e.error,
                "coordination_metrics": e.coordination_metrics,
            }
            for e in execs[:limit]
        ]


# Singleton engine instance
_engine_instance: WorkflowEngine | None = None


def get_workflow_engine() -> WorkflowEngine:
    """Get or create the singleton WorkflowEngine instance."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = WorkflowEngine()
    return _engine_instance

"""
Helix Agent Protocol v2 — Dynamic 18-Agent System with Real LLM
================================================================

Complete rewrite of the Agent Protocol to:
1. Dynamically load ALL agents from agents.json (currently 18)
2. Route through real LLM inference via AgentLLMBridge
3. Support agent-to-agent handoffs with coordination state transfer
4. Implement the Agent Protocol standard (agent-protocol.ai)
5. Support external agent registration (LangGraph/CrewAI/AutoGen/OpenAI)

No mocks. No hardcoded agent lists. Real inference or graceful degradation.

(c) Helix Collective 2025 - Proprietary Technology Stack
"""

import json
import logging
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .agent_llm_bridge import AgentLLMBridge, get_agent_llm_bridge

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent-protocol/v2", tags=["Agent Protocol v2"])


# ============================================================================
# MODELS
# ============================================================================


class TaskStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    WAITING_HANDOFF = "waiting_handoff"


class StepStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskCreateRequest(BaseModel):
    input: str = Field(..., description="Task description or user message")
    agent_id: str | None = Field(None, description="Target agent ID (auto-routes if None)")
    additional_input: dict[str, Any] | None = None
    conversation_history: list[dict[str, str]] | None = None
    stream: bool = Field(False, description="Enable SSE streaming")


class StepRequest(BaseModel):
    input: str | None = None
    additional_input: dict[str, Any] | None = None


class HandoffRequest(BaseModel):
    task_id: str
    from_agent: str
    to_agent: str
    reason: str
    context: dict[str, Any] | None = None


class ExternalAgentRegistration(BaseModel):
    name: str
    framework: str = Field(..., description="langgraph|crewai|autogen|openai|custom")
    endpoint_url: str
    capabilities: list[str] = []
    auth_token: str | None = None
    metadata: dict[str, Any] | None = None


# ============================================================================
# PERSISTENT STORES — Redis-backed with in-memory cache
# ============================================================================

_REDIS_TASKS_KEY = "helix:agent_protocol:tasks"
_REDIS_STEPS_KEY = "helix:agent_protocol:steps"
_REDIS_EXT_AGENTS_KEY = "helix:agent_protocol:external_agents"
_REDIS_HANDOFFS_KEY = "helix:agent_protocol:handoff_log"
_MAX_HANDOFF_LOG = 1000

_MAX_TASKS_CACHE = 10_000  # Maximum tasks in local cache
_MAX_STEPS_CACHE = 10_000  # Maximum step lists in local cache

# Write-through cache over Redis
_tasks: dict[str, dict[str, Any]] = {}
# Write-through cache over Redis
_steps: dict[str, list[dict[str, Any]]] = {}
_external_agents: dict[str, dict[str, Any]] = {}
_handoff_log: list[dict[str, Any]] = []


async def _get_redis():
    """Lazy Redis import to avoid circular deps."""
    try:
        from apps.backend.core.redis_client import get_redis

        return await get_redis()
    except Exception as e:
        logger.debug("Redis unavailable for agent protocol: %s", e)
        return None


async def _persist_task(task_id: str, task: dict[str, Any]) -> None:
    """Write task to Redis."""
    r = await _get_redis()
    if r:
        try:
            await r.hset(_REDIS_TASKS_KEY, task_id, json.dumps(task, default=str))
        except Exception as exc:
            logger.warning("Redis write failed for task %s: %s", task_id, exc)


async def _persist_steps(task_id: str, steps: list[dict[str, Any]]) -> None:
    """Write steps list for a task to Redis."""
    r = await _get_redis()
    if r:
        try:
            await r.hset(_REDIS_STEPS_KEY, task_id, json.dumps(steps, default=str))
        except Exception as exc:
            logger.warning("Redis write failed for steps[%s]: %s", task_id, exc)


async def _persist_external_agent(agent_id: str, data: dict[str, Any]) -> None:
    """Write external agent registration to Redis."""
    r = await _get_redis()
    if r:
        try:
            await r.hset(_REDIS_EXT_AGENTS_KEY, agent_id, json.dumps(data, default=str))
        except Exception as exc:
            logger.warning("Redis write failed for ext agent %s: %s", agent_id, exc)


async def _remove_external_agent_redis(agent_id: str) -> None:
    """Remove external agent from Redis."""
    r = await _get_redis()
    if r:
        try:
            await r.hdel(_REDIS_EXT_AGENTS_KEY, agent_id)
        except Exception as exc:
            logger.warning("Redis delete failed for ext agent %s: %s", agent_id, exc)


async def _persist_handoff(record: dict[str, Any]) -> None:
    """Append handoff to Redis list (bounded)."""
    r = await _get_redis()
    if r:
        try:
            await r.rpush(_REDIS_HANDOFFS_KEY, json.dumps(record, default=str))
            await r.ltrim(_REDIS_HANDOFFS_KEY, -_MAX_HANDOFF_LOG, -1)
        except Exception as exc:
            logger.warning("Redis write failed for handoff: %s", exc)


async def _load_external_agents_from_redis() -> None:
    """Populate _external_agents cache from Redis on first access."""
    if _external_agents:
        return  # already populated
    r = await _get_redis()
    if r:
        try:
            raw = await r.hgetall(_REDIS_EXT_AGENTS_KEY)
            for k, v in raw.items():
                key = k if isinstance(k, str) else k.decode()
                _external_agents[key] = json.loads(v if isinstance(v, str) else v.decode())
        except Exception as exc:
            logger.warning("Redis load failed for external agents: %s", exc)


# ============================================================================
# INTELLIGENT AGENT ROUTING
# ============================================================================

# Keyword-to-agent routing map for auto-routing
ROUTING_KEYWORDS: dict[str, list[str]] = {
    "kael": ["ethics", "ethical", "moral", "right", "wrong", "ethics validator", "principle", "fairness"],
    "lumina": ["feel", "emotion", "sad", "happy", "anxious", "wellness", "empathy", "support", "mental"],
    "vega": ["orchestrate", "coordinate", "multi-agent", "workflow", "distribute", "collective"],
    "oracle": ["pattern", "predict", "forecast", "trend", "anomaly", "insight", "analyze"],
    "nexus": ["strategy", "plan", "goal", "resource", "optimize", "roadmap", "objective"],
    "sentinel": ["security", "threat", "vulnerability", "protect", "guard", "firewall", "breach"],
    "phoenix": ["health", "recover", "performance", "optimize", "heal", "restore", "uptime"],
    "shadow": ["archive", "memory", "remember", "history", "document", "preserve", "recall"],
    "agni": ["transform", "change", "evolve", "growth", "progress", "catalyst", "fire"],
    "arjuna": ["execute", "action", "task", "focus", "precision", "achieve", "target", "do"],
    "echo": ["communicate", "voice", "message", "relay", "amplify", "broadcast", "announce"],
    "gemini": ["image", "video", "media", "multimodal", "visual", "document", "file", "pdf"],
    "kavach": ["shield", "protect", "violation", "scan", "compliance", "audit", "safety"],
    "sanghacore": ["community", "harmony", "unity", "collective", "together", "bind", "sync"],
    "mitra": ["relationship", "trust", "alliance", "friend", "connect", "bond", "partnership"],
    "varuna": ["truth", "law", "order", "compliance", "verify", "cosmic", "universal"],
    "surya": ["light", "clarity", "insight", "illuminate", "understand", "knowledge", "learn"],
    "aether": ["system", "monitor", "infrastructure", "status", "health", "anomaly", "fabric"],
}


def route_to_agent(user_input: str) -> str:
    """Intelligently route a user message to the best agent."""
    input_lower = user_input.lower()
    scores: dict[str, int] = {}

    for agent_id, keywords in ROUTING_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in input_lower)
        if score > 0:
            scores[agent_id] = score

    if scores:
        return max(scores, key=scores.get)

    # Default to Vega (orchestrator) for general queries
    return "vega"


# ============================================================================
# API ROUTES
# ============================================================================


@router.get("/agents")
async def list_agents():
    """List all 18 Helix agents with their capabilities and coordination state."""
    await _load_external_agents_from_redis()
    bridge = get_agent_llm_bridge()
    await bridge.initialize()
    agents = bridge.list_agents()

    # Add external agents
    for ext_id, ext_data in _external_agents.items():
        agents.append(
            {
                "id": ext_id,
                "name": ext_data["name"],
                "emoji": "🔌",
                "color": "#888",
                "personality": f"External {ext_data['framework']} agent",
                "capabilities": ext_data.get("capabilities", []),
                "tier": "external",
                "framework": ext_data["framework"],
                "endpoint": ext_data["endpoint_url"],
                "coordination_state": {},
            }
        )

    return {
        "agents": agents,
        "total": len(agents),
        "helix_agents": len(bridge.list_agents()),
        "external_agents": len(_external_agents),
    }


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Get detailed info about a specific agent."""
    bridge = get_agent_llm_bridge()
    await bridge.initialize()

    agents = {a["id"]: a for a in bridge.list_agents()}
    if agent_id not in agents and agent_id not in _external_agents:
        raise HTTPException(404, f"Agent '{agent_id}' not found")

    if agent_id in agents:
        agent = agents[agent_id]
        agent["system_prompt_preview"] = bridge.get_agent_system_prompt(agent_id)[:200] + "..."
        return agent

    return _external_agents[agent_id]


@router.post("/tasks")
async def create_task(request: TaskCreateRequest):
    """Create a new task and route to the appropriate agent."""
    bridge = get_agent_llm_bridge()
    await bridge.initialize()

    # Auto-route if no agent specified
    agent_id = request.agent_id or route_to_agent(request.input)

    task_id = str(uuid.uuid4())
    task = {
        "task_id": task_id,
        "agent_id": agent_id,
        "input": request.input,
        "status": TaskStatus.RUNNING,
        "created_at": datetime.now(UTC).isoformat(),
        "steps": [],
        "output": None,
        "artifacts": [],
        "coordination_state": {},
    }
    # FIFO eviction — remove oldest entry if cache is full
    if len(_tasks) >= _MAX_TASKS_CACHE:
        _tasks.pop(next(iter(_tasks)))
    _tasks[task_id] = task
    # FIFO eviction — remove oldest entry if cache is full
    if len(_steps) >= _MAX_STEPS_CACHE:
        _steps.pop(next(iter(_steps)))
    _steps[task_id] = []
    await _persist_task(task_id, task)
    await _persist_steps(task_id, [])

    # If streaming requested, return SSE stream
    if request.stream:
        return StreamingResponse(
            _stream_agent_response(bridge, agent_id, task_id, request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Task-Id": task_id,
                "X-Agent-Id": agent_id,
            },
        )

    # Non-streaming: generate full response
    try:
        # Check if this is an external agent
        if agent_id in _external_agents:
            response = await _call_external_agent(agent_id, request.input)
        else:
            response = await bridge.generate_response(
                agent_id=agent_id,
                user_message=request.input,
                conversation_history=request.conversation_history,
            )

        step = {
            "step_id": str(uuid.uuid4()),
            "task_id": task_id,
            "agent_id": agent_id,
            "status": StepStatus.COMPLETED,
            "input": request.input,
            "output": response.content if hasattr(response, "content") else str(response),
            "tokens_used": response.tokens_used if hasattr(response, "tokens_used") else 0,
            "inference_time_ms": response.inference_time_ms if hasattr(response, "inference_time_ms") else 0,
            "model_used": response.model_used if hasattr(response, "model_used") else "unknown",
            "coordination_state": response.coordination_state if hasattr(response, "coordination_state") else {},
            "created_at": datetime.now(UTC).isoformat(),
        }
        _steps[task_id].append(step)
        await _persist_steps(task_id, _steps[task_id])

        task["status"] = TaskStatus.COMPLETED
        task["output"] = step["output"]
        task["coordination_state"] = step["coordination_state"]
        task["steps"] = _steps[task_id]
        await _persist_task(task_id, task)

        return task

    except Exception as e:
        logger.error("Task execution failed: %s", e)
        task["status"] = TaskStatus.FAILED
        task["output"] = f"Error: {e!s}"
        await _persist_task(task_id, task)
        raise HTTPException(500, f"Agent execution failed: {e!s}")


async def _stream_agent_response(
    bridge: AgentLLMBridge,
    agent_id: str,
    task_id: str,
    request: TaskCreateRequest,
):
    """SSE streaming generator for agent responses."""
    yield f"data: {json.dumps({'type': 'start', 'task_id': task_id, 'agent_id': agent_id})}\n\n"

    full_response = []
    try:
        async for token in bridge.generate_stream(
            agent_id=agent_id,
            user_message=request.input,
            conversation_history=request.conversation_history,
        ):
            full_response.append(token)
            yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

        final_text = "".join(full_response)
        _tasks[task_id]["status"] = TaskStatus.COMPLETED
        _tasks[task_id]["output"] = final_text
        await _persist_task(task_id, _tasks[task_id])

        yield f"data: {json.dumps({'type': 'done', 'task_id': task_id, 'total_tokens': len(final_text.split())})}\n\n"

    except Exception as e:
        _tasks[task_id]["status"] = TaskStatus.FAILED
        await _persist_task(task_id, _tasks[task_id])
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """Get task status and results."""
    if task_id not in _tasks:
        raise HTTPException(404, f"Task '{task_id}' not found")
    task = _tasks[task_id]
    task["steps"] = _steps.get(task_id, [])
    return task


@router.get("/tasks")
async def list_tasks(
    status: str | None = None,
    agent_id: str | None = None,
    limit: int = Query(50, le=200),
):
    """List all tasks with optional filtering."""
    tasks = list(_tasks.values())

    if status:
        tasks = [t for t in tasks if t["status"] == status]
    if agent_id:
        tasks = [t for t in tasks if t["agent_id"] == agent_id]

    tasks.sort(key=lambda t: t.get("created_at", ""), reverse=True)
    return {"tasks": tasks[:limit], "total": len(tasks)}


@router.post("/tasks/{task_id}/steps")
async def execute_step(task_id: str, request: StepRequest):
    """Execute the next step in a task (for multi-step workflows)."""
    if task_id not in _tasks:
        raise HTTPException(404, f"Task '{task_id}' not found")

    task = _tasks[task_id]
    bridge = get_agent_llm_bridge()
    await bridge.initialize()

    step_input = request.input or task.get("input", "Continue the task.")

    response = await bridge.generate_response(
        agent_id=task["agent_id"],
        user_message=step_input,
        conversation_history=[
            {"role": "assistant", "content": s["output"]} for s in _steps.get(task_id, []) if s.get("output")
        ],
    )

    step = {
        "step_id": str(uuid.uuid4()),
        "task_id": task_id,
        "agent_id": task["agent_id"],
        "status": StepStatus.COMPLETED,
        "input": step_input,
        "output": response.content,
        "tokens_used": response.tokens_used,
        "inference_time_ms": response.inference_time_ms,
        "model_used": response.model_used,
        "coordination_state": response.coordination_state,
        "created_at": datetime.now(UTC).isoformat(),
    }
    _steps[task_id].append(step)

    return step


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    """Cancel a running task."""
    if task_id not in _tasks:
        raise HTTPException(404, f"Task '{task_id}' not found")
    _tasks[task_id]["status"] = TaskStatus.CANCELLED
    await _persist_task(task_id, _tasks[task_id])
    return {"task_id": task_id, "status": "cancelled"}


# ============================================================================
# AGENT HANDOFFS
# ============================================================================


@router.post("/handoff")
async def agent_handoff(request: HandoffRequest):
    """Hand off a task from one agent to another with coordination state transfer."""
    if request.task_id not in _tasks:
        raise HTTPException(404, f"Task '{request.task_id}' not found")

    bridge = get_agent_llm_bridge()
    await bridge.initialize()

    # Validate agents
    all_agents = {a["id"] for a in bridge.list_agents()}
    all_agents.update(_external_agents.keys())

    if request.from_agent not in all_agents:
        raise HTTPException(404, f"Source agent '{request.from_agent}' not found")
    if request.to_agent not in all_agents:
        raise HTTPException(404, f"Target agent '{request.to_agent}' not found")

    task = _tasks[request.task_id]

    # Log the handoff
    handoff_record = {
        "handoff_id": str(uuid.uuid4()),
        "task_id": request.task_id,
        "from_agent": request.from_agent,
        "to_agent": request.to_agent,
        "reason": request.reason,
        "context": request.context,
        "from_coordination": bridge._get_coordination_state(request.from_agent),
        "to_coordination": bridge._get_coordination_state(request.to_agent),
        "timestamp": datetime.now(UTC).isoformat(),
    }
    _handoff_log.append(handoff_record)
    await _persist_handoff(handoff_record)

    # Update task to new agent
    task["agent_id"] = request.to_agent
    task["status"] = TaskStatus.RUNNING

    # Generate handoff response from new agent
    handoff_prompt = (
        f"You are taking over this task from {request.from_agent}. "
        f"Reason for handoff: {request.reason}. "
        f"Original task: {task.get('input', 'Unknown')}. "
        f"Previous output: {task.get('output', 'None')}. "
        f"Please continue from where the previous agent left off."
    )

    response = await bridge.generate_response(
        agent_id=request.to_agent,
        user_message=handoff_prompt,
    )

    step = {
        "step_id": str(uuid.uuid4()),
        "task_id": request.task_id,
        "agent_id": request.to_agent,
        "status": StepStatus.COMPLETED,
        "input": handoff_prompt,
        "output": response.content,
        "handoff_from": request.from_agent,
        "tokens_used": response.tokens_used,
        "inference_time_ms": response.inference_time_ms,
        "model_used": response.model_used,
        "coordination_state": response.coordination_state,
        "created_at": datetime.now(UTC).isoformat(),
    }
    _steps[request.task_id].append(step)
    await _persist_steps(request.task_id, _steps[request.task_id])
    task["output"] = response.content
    task["coordination_state"] = response.coordination_state
    await _persist_task(request.task_id, task)

    return {
        "handoff": handoff_record,
        "new_step": step,
        "task": task,
    }


@router.get("/handoffs")
async def list_handoffs(limit: int = Query(50, le=200)):
    """List all agent handoff records."""
    return {
        "handoffs": _handoff_log[-limit:],
        "total": len(_handoff_log),
    }


# ============================================================================
# EXTERNAL AGENT REGISTRATION
# ============================================================================


@router.post("/external-agents")
async def register_external_agent(registration: ExternalAgentRegistration):
    """Register an external agent (LangGraph, CrewAI, AutoGen, OpenAI)."""
    agent_id = f"ext_{registration.framework}_{registration.name.lower().replace(' ', '_')}"

    _external_agents[agent_id] = {
        "id": agent_id,
        "name": registration.name,
        "framework": registration.framework,
        "endpoint_url": registration.endpoint_url,
        "capabilities": registration.capabilities,
        "auth_token": registration.auth_token,
        "metadata": registration.metadata or {},
        "registered_at": datetime.now(UTC).isoformat(),
        "status": "active",
    }
    await _persist_external_agent(agent_id, _external_agents[agent_id])

    logger.info("🔌 Registered external agent: %s (%s)", registration.name, registration.framework)

    return {
        "agent_id": agent_id,
        "status": "registered",
        "message": f"External {registration.framework} agent '{registration.name}' registered successfully",
    }


@router.get("/external-agents")
async def list_external_agents():
    """List all registered external agents."""
    await _load_external_agents_from_redis()
    return {
        "agents": list(_external_agents.values()),
        "total": len(_external_agents),
    }


@router.delete("/external-agents/{agent_id}")
async def unregister_external_agent(agent_id: str):
    """Unregister an external agent."""
    if agent_id not in _external_agents:
        raise HTTPException(404, f"External agent '{agent_id}' not found")
    removed = _external_agents.pop(agent_id)
    await _remove_external_agent_redis(agent_id)
    return {"status": "removed", "agent": removed}


async def _call_external_agent(agent_id: str, input_text: str) -> Any:
    """Call an external agent via its registered endpoint."""
    if agent_id not in _external_agents:
        raise HTTPException(404, f"External agent '{agent_id}' not found")

    agent = _external_agents[agent_id]
    headers = {"Content-Type": "application/json"}
    if agent.get("auth_token"):
        headers["Authorization"] = f"Bearer {agent['auth_token']}"

    payload = {"input": input_text}

    # Adapt payload based on framework
    if agent["framework"] == "openai":
        payload = {
            "messages": [{"role": "user", "content": input_text}],
            "model": agent.get("metadata", {}).get("model", "gpt-4"),
        }
    elif agent["framework"] == "langgraph":
        payload = {"input": {"messages": [{"role": "user", "content": input_text}]}}
    elif agent["framework"] == "crewai":
        payload = {"task": input_text}

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(agent["endpoint_url"], json=payload, headers=headers)
            resp.raise_for_status()
            result = resp.json()

            # Normalize response
            content = ""
            if isinstance(result, str):
                content = result
            elif isinstance(result, dict):
                content = (
                    result.get("output", "")
                    or result.get("content", "")
                    or result.get("text", "")
                    or result.get("choices", [{}])[0].get("message", {}).get("content", "")
                    or json.dumps(result)
                )

            # Return as AgentResponse-like object
            class _ExternalResponse:
                pass

            r = _ExternalResponse()
            r.content = content
            r.tokens_used = len(content.split())
            r.inference_time_ms = 0
            r.model_used = f"external-{agent['framework']}"
            r.coordination_state = {}
            return r

        except httpx.HTTPError as e:
            logger.error("External agent call failed: %s", e)
            raise HTTPException(502, f"External agent '{agent_id}' call failed: {e!s}")


# ============================================================================
# MULTI-AGENT CONVERSATION
# ============================================================================


class MultiAgentRequest(BaseModel):
    topic: str
    agents: list[str] = Field(default_factory=list, description="Agent IDs to participate")
    rounds: int = Field(3, ge=1, le=10)
    moderator: str = Field("vega", description="Agent that moderates the conversation")


@router.post("/multi-agent/conversation")
async def multi_agent_conversation(request: MultiAgentRequest):
    """Run a multi-agent conversation where agents discuss a topic."""
    bridge = get_agent_llm_bridge()
    await bridge.initialize()

    available = {a["id"] for a in bridge.list_agents()}
    agents = request.agents or list(available)[:5]  # Default to first 5

    # Validate agents
    invalid = [a for a in agents if a not in available]
    if invalid:
        raise HTTPException(400, f"Unknown agents: {invalid}")

    conversation = []
    task_id = str(uuid.uuid4())

    for round_num in range(request.rounds):
        for agent_id in agents:
            # Build context from previous messages
            context = "\n".join(f"{msg['agent']}: {msg['content'][:200]}" for msg in conversation[-6:])

            prompt = (
                f"Topic: {request.topic}\n\n"
                f"Previous discussion:\n{context}\n\n"
                f"It's your turn to contribute. Share your unique perspective as {agent_id}. "
                f"Be concise (2-3 sentences). Build on what others said."
                if context
                else f"Topic: {request.topic}\n\n"
                f"You're starting a multi-agent discussion. Share your opening perspective "
                f"as {agent_id}. Be concise (2-3 sentences)."
            )

            response = await bridge.generate_response(
                agent_id=agent_id,
                user_message=prompt,
            )

            conversation.append(
                {
                    "round": round_num + 1,
                    "agent": agent_id,
                    "agent_name": response.agent_name,
                    "content": response.content,
                    "model_used": response.model_used,
                    "coordination_state": response.coordination_state,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )

    return {
        "task_id": task_id,
        "topic": request.topic,
        "agents": agents,
        "rounds": request.rounds,
        "conversation": conversation,
        "total_messages": len(conversation),
    }


# ============================================================================
# STATS & HEALTH
# ============================================================================


@router.get("/stats")
async def protocol_stats():
    """Get Agent Protocol statistics."""
    bridge = get_agent_llm_bridge()
    return {
        "bridge_stats": bridge.get_stats(),
        "tasks": {
            "total": len(_tasks),
            "by_status": {
                status.value: len([t for t in _tasks.values() if t["status"] == status]) for status in TaskStatus
            },
        },
        "external_agents": len(_external_agents),
        "handoffs": len(_handoff_log),
    }


@router.get("/health")
async def protocol_health():
    """Health check for the Agent Protocol."""
    bridge = get_agent_llm_bridge()
    stats = bridge.get_stats()
    return {
        "status": "healthy",
        "agents_loaded": stats["agents_loaded"],
        "proprietary_llm": stats["proprietary_llm_available"],
        "external_llm": stats["external_llm_available"],
        "version": "2.0.0",
    }

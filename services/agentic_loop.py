"""
Agentic Tool-Calling Loop
==========================
Implements an agent-factory-inspired agentic loop where the LLM can
invoke tools autonomously across multiple rounds with streaming visibility.

Pattern (adapted from agent-factory/seed/lib/orchestrator.ts):
1. Build messages with tool definitions
2. Call LLM with tools parameter
3. If LLM returns tool_calls: execute each tool, append results, goto 2
4. If LLM returns text only: return as final response
5. If max_rounds reached: force final summary call without tools

SSE event types emitted during streaming:
  - round:       {round: N, max_rounds: N}
  - tool_call:   {round: N, tool: str, parameters: dict}
  - tool_result:  {round: N, tool: str, success: bool, output: str, execution_time_ms: float}
  - thinking:    {content: str}
  - token:       {content: str}
  - done:        {rounds: N, tools_used: [...], total_time_ms: float}
  - error:       {error: str}
"""

import json
import logging
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

MAX_TOOL_RESULT_CHARS = 3000

# Type for optional event callback (used by delegation tools to emit SSE events)
EventCallback = Callable[[dict[str, Any]], None] | None


@dataclass
class AgenticRound:
    """One round of the agentic loop."""

    round_number: int
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    thinking: str | None = None
    duration_ms: float = 0.0


@dataclass
class AgenticLoopResult:
    """Final result of the agentic loop."""

    response: str
    rounds: list[AgenticRound] = field(default_factory=list)
    total_rounds: int = 0
    tools_used: list[str] = field(default_factory=list)
    total_execution_time_ms: float = 0.0
    was_truncated: bool = False


class AgenticLoop:
    """
    Core agentic loop. Takes a user message + tool set, runs LLM with
    tool definitions, executes tool calls, and iterates until the LLM
    produces a final text response or max rounds are reached.
    """

    def __init__(
        self,
        tool_registry,
        llm_service,
        max_rounds: int = 5,
        tool_names: list[str] | None = None,
        max_tools_per_call: int = 20,
        execution_context: dict[str, Any] | None = None,
        quality_gate_config: dict[str, Any] | None = None,
        emit_plan_preview: bool = True,
    ):
        self.registry = tool_registry
        self.llm = llm_service
        self.max_rounds = max_rounds
        self.tool_names = tool_names
        self.max_tools_per_call = max_tools_per_call
        self.execution_context = execution_context or {}
        self.quality_gate_config = quality_gate_config
        self.emit_plan_preview = emit_plan_preview
        # Event queue for delegation sub-events (populated by tool callbacks)
        self._pending_events: list[dict[str, Any]] = []

    def _build_tool_definitions(self) -> list[dict[str, Any]]:
        """Build JSON Schema tool definitions for the LLM."""
        if self.tool_names:
            tools = []
            for name in self.tool_names:
                tool = self.registry.get(name)
                if tool and not tool.deprecated:
                    tools.append(tool.to_json_schema())
            return tools[: self.max_tools_per_call]
        else:
            all_tools = self.registry.list_tools()
            schemas = []
            for tool in all_tools:
                if not tool.deprecated:
                    schemas.append(tool.to_json_schema())
                if len(schemas) >= self.max_tools_per_call:
                    break
            return schemas

    def _filter_exhausted_tools(
        self,
        tool_defs: list[dict[str, Any]],
        usage_counts: dict[str, int],
    ) -> list[dict[str, Any]]:
        """Remove tools that have hit their max_usage_count from the definitions."""
        if not usage_counts:
            return tool_defs

        filtered = []
        for td in tool_defs:
            tool_name = td.get("name", "")
            tool_obj = self.registry.get(tool_name)
            max_count = getattr(tool_obj, "max_usage_count", None) if tool_obj else None
            if max_count is not None and usage_counts.get(tool_name, 0) >= max_count:
                logger.debug("Tool '%s' exhausted (%d/%d uses)", tool_name, usage_counts[tool_name], max_count)
                continue
            filtered.append(td)
        return filtered

    async def _execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a single tool and return the result dict.

        For delegation tools (delegate_work, ask_agent), emits delegation_started
        and delegation_complete events to self._pending_events so the streaming
        generator can yield them to the client.
        """
        is_delegation = tool_name in ("delegate_work", "ask_agent")
        target_agent = arguments.get("agent", "") if is_delegation else None

        if is_delegation and target_agent:
            self._pending_events.append(
                {
                    "type": "delegation_started",
                    "data": {
                        "tool": tool_name,
                        "target_agent": target_agent,
                        "task_preview": (arguments.get("task") or arguments.get("question", ""))[:200],
                    },
                }
            )

        start = time.monotonic()
        try:
            result = await self.registry.execute(tool_name, arguments, self.execution_context or None)
            duration = (time.monotonic() - start) * 1000

            output = str(result.output) if result.output is not None else ""
            if len(output) > MAX_TOOL_RESULT_CHARS:
                output = output[:MAX_TOOL_RESULT_CHARS] + "\n\n... [truncated]"

            # Emit delegation_complete for delegation tools
            if is_delegation and target_agent:
                delegate_name = target_agent
                if result.metadata and result.metadata.get("delegate_name"):
                    delegate_name = result.metadata["delegate_name"]
                self._pending_events.append(
                    {
                        "type": "delegation_complete",
                        "data": {
                            "tool": tool_name,
                            "target_agent": delegate_name,
                            "success": result.success,
                            "execution_time_ms": round(duration, 1),
                        },
                    }
                )

            return {
                "tool_name": tool_name,
                "success": result.success,
                "output": output,
                "error": result.error,
                "execution_time_ms": duration,
                "metadata": getattr(result, "metadata", None),
            }
        except Exception as e:
            duration = (time.monotonic() - start) * 1000
            logger.warning("Tool execution failed for '%s': %s", tool_name, e)

            if is_delegation and target_agent:
                self._pending_events.append(
                    {
                        "type": "delegation_complete",
                        "data": {
                            "tool": tool_name,
                            "target_agent": target_agent,
                            "success": False,
                            "error": str(e),
                            "execution_time_ms": round(duration, 1),
                        },
                    }
                )

            return {
                "tool_name": tool_name,
                "success": False,
                "output": "",
                "error": str(e),
                "execution_time_ms": duration,
            }

    async def _run_quality_gate(self, output: str, round_num: int) -> dict[str, Any] | None:
        """Run quality gate validation if configured. Returns gate result or None."""
        if not self.quality_gate_config:
            return None
        try:
            from apps.backend.services.quality_gate_validator import validate_quality_gate

            result = await validate_quality_gate(self.quality_gate_config, output, f"round_{round_num}")
            return {
                "passed": result.passed,
                "reason": result.reason,
                "mode": result.mode,
            }
        except ImportError:
            logger.debug("Quality gate validator not available")
            return None
        except Exception as e:
            logger.warning("Quality gate validation failed: %s", e)
            return None

    async def run(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        user_id: str | None = None,
    ) -> AgenticLoopResult:
        """Run the agentic loop (non-streaming). Returns final result."""
        tool_defs = self._build_tool_definitions()
        all_messages = list(messages)
        rounds = []
        all_tools_used = set()
        tool_usage_counts: dict[str, int] = {}
        total_start = time.monotonic()

        for round_num in range(self.max_rounds):
            round_start = time.monotonic()

            # Remove tools that have hit their max_usage_count
            active_tool_defs = self._filter_exhausted_tools(tool_defs, tool_usage_counts)

            resp = await self.llm.chat_with_tools(
                all_messages,
                tools=active_tool_defs if active_tool_defs else None,
                model=model,
                user_id=user_id,
            )

            if resp.error:
                return AgenticLoopResult(
                    response=f"Error: {resp.error}",
                    rounds=rounds,
                    total_rounds=len(rounds),
                    tools_used=list(all_tools_used),
                    total_execution_time_ms=(time.monotonic() - total_start) * 1000,
                    was_truncated=False,
                )

            # No tool calls - LLM produced final text
            if not resp.tool_calls:
                return AgenticLoopResult(
                    response=resp.content,
                    rounds=rounds,
                    total_rounds=len(rounds),
                    tools_used=list(all_tools_used),
                    total_execution_time_ms=(time.monotonic() - total_start) * 1000,
                    was_truncated=False,
                )

            # Execute tool calls
            round_data = AgenticRound(round_number=round_num)
            if resp.content:
                round_data.thinking = resp.content

            # Add assistant message with tool calls to history
            all_messages.append(
                {
                    "role": "assistant",
                    "content": resp.content or "",
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"])},
                        }
                        for tc in resp.tool_calls
                    ],
                }
            )

            result_as_answer_output = None

            for tc in resp.tool_calls:
                tool_name = tc["name"]
                all_tools_used.add(tool_name)
                tool_usage_counts[tool_name] = tool_usage_counts.get(tool_name, 0) + 1

                result = await self._execute_tool(tool_name, tc["arguments"])
                round_data.tool_calls.append({"tool": tool_name, "parameters": tc["arguments"]})
                round_data.tool_results.append(result)

                # Add tool result to message history
                all_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result["output"] if result["success"] else f"Error: {result['error']}",
                    }
                )

                # Check result_as_answer: if tool has this flag and succeeded, use output directly
                if result["success"]:
                    tool_obj = self.registry.get(tool_name)
                    if tool_obj and getattr(tool_obj, "result_as_answer", False):
                        result_as_answer_output = result["output"]

            round_data.duration_ms = (time.monotonic() - round_start) * 1000
            rounds.append(round_data)

            # If a result_as_answer tool fired, return immediately
            if result_as_answer_output is not None:
                return AgenticLoopResult(
                    response=result_as_answer_output,
                    rounds=rounds,
                    total_rounds=len(rounds),
                    tools_used=list(all_tools_used),
                    total_execution_time_ms=(time.monotonic() - total_start) * 1000,
                    was_truncated=False,
                )

        # Max rounds exhausted - force a final text response without tools
        try:
            final_resp = await self.llm.chat_with_tools(
                all_messages,
                tools=None,
                model=model,
                user_id=user_id,
            )
            final_text = final_resp.content or ""
        except Exception as e:
            logger.warning("Final summary call failed: %s", e)
            final_text = "[Agent reached maximum tool-calling rounds. Partial results above may be useful.]"

        return AgenticLoopResult(
            response=final_text,
            rounds=rounds,
            total_rounds=len(rounds),
            tools_used=list(all_tools_used),
            total_execution_time_ms=(time.monotonic() - total_start) * 1000,
            was_truncated=True,
        )

    async def _generate_plan(self, messages: list[dict[str, str]], tool_defs: list[dict[str, Any]]) -> list[str] | None:
        """Generate a numbered execution plan before the agentic loop starts.

        Makes a lightweight one-shot LLM call asking the agent to outline
        what it intends to do. Returns a list of step strings or None on failure.
        Only called when there are tools available (no plan needed for pure text).
        """
        if not tool_defs:
            return None

        tool_names = [t.get("name", "") for t in tool_defs[:10]]
        tool_list = ", ".join(tool_names)

        planning_messages = [
            {
                "role": "system",
                "content": (
                    "You are a planning assistant. Given the user's request and available tools, "
                    "output a concise numbered plan (3-7 steps) as a JSON array of strings. "
                    f"Available tools: {tool_list}. "
                    'Return ONLY a JSON array like: ["Step 1: ...", "Step 2: ..."] - no prose, no markdown.'
                ),
            },
            *messages[-2:],  # Only the most recent context
        ]

        try:
            raw = await self.llm.chat(planning_messages, max_tokens=250)
            raw = raw.strip()
            # Strip markdown fences
            if raw.startswith("```"):
                parts = raw.split("```")
                raw = parts[1] if len(parts) > 1 else raw
                if raw.startswith("json"):
                    raw = raw[4:]
            steps: list[str] = json.loads(raw)
            if isinstance(steps, list) and steps:
                return [str(s) for s in steps[:7]]
        except Exception as exc:
            logger.debug("Plan preview generation failed (non-critical): %s", exc)
        return None

    async def run_streaming(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        user_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Run the agentic loop with streaming events.
        Yields event dicts suitable for SSE.
        """
        tool_defs = self._build_tool_definitions()
        all_messages = list(messages)
        all_tools_used = set()
        tool_usage_counts: dict[str, int] = {}
        total_start = time.monotonic()

        # Pre-execution plan preview (Replit Agent pattern)
        if self.emit_plan_preview and tool_defs:
            try:
                steps = await self._generate_plan(all_messages, tool_defs)
                if steps:
                    yield {"type": "plan_preview", "data": {"steps": steps}}
            except Exception as _plan_err:
                logger.debug("Plan preview skipped: %s", _plan_err)

        for round_num in range(self.max_rounds):
            yield {"type": "round", "data": {"round": round_num + 1, "max_rounds": self.max_rounds}}

            # Remove exhausted tools
            active_tool_defs = self._filter_exhausted_tools(tool_defs, tool_usage_counts)

            resp = await self.llm.chat_with_tools(
                all_messages,
                tools=active_tool_defs if active_tool_defs else None,
                model=model,
                user_id=user_id,
            )

            if resp.error:
                yield {"type": "error", "data": {"error": resp.error}}
                return

            # No tool calls - stream final text
            if not resp.tool_calls:
                content = resp.content or ""
                # Emit token-by-token for UI streaming feel
                words = content.split(" ")
                for i, word in enumerate(words):
                    token = word if i == 0 else " " + word
                    yield {"type": "token", "data": {"content": token}}

                yield {
                    "type": "done",
                    "data": {
                        "rounds": round_num,
                        "tools_used": list(all_tools_used),
                        "total_time_ms": round((time.monotonic() - total_start) * 1000, 1),
                    },
                }
                return

            # Emit thinking if present
            if resp.content:
                yield {"type": "thinking", "data": {"content": resp.content}}

            # Add assistant message to history
            all_messages.append(
                {
                    "role": "assistant",
                    "content": resp.content or "",
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"])},
                        }
                        for tc in resp.tool_calls
                    ],
                }
            )

            # Execute and yield tool calls
            result_as_answer_output = None

            for tc in resp.tool_calls:
                tool_name = tc["name"]
                all_tools_used.add(tool_name)
                tool_usage_counts[tool_name] = tool_usage_counts.get(tool_name, 0) + 1

                yield {
                    "type": "tool_call",
                    "data": {
                        "round": round_num + 1,
                        "tool": tool_name,
                        "parameters": tc["arguments"],
                    },
                }

                result = await self._execute_tool(tool_name, tc["arguments"])

                # Flush any delegation events emitted by _execute_tool
                for pending in self._pending_events:
                    yield pending
                self._pending_events.clear()

                yield {
                    "type": "tool_result",
                    "data": {
                        "round": round_num + 1,
                        "tool": tool_name,
                        "success": result["success"],
                        "output": result["output"][:500],  # Truncate for SSE
                        "execution_time_ms": round(result["execution_time_ms"], 1),
                    },
                }

                # Add tool result to history
                all_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result["output"] if result["success"] else f"Error: {result['error']}",
                    }
                )

                # Check result_as_answer
                if result["success"]:
                    tool_obj = self.registry.get(tool_name)
                    if tool_obj and getattr(tool_obj, "result_as_answer", False):
                        result_as_answer_output = result["output"]

            # If result_as_answer tool fired, emit as final and stop
            if result_as_answer_output is not None:
                words = result_as_answer_output.split(" ")
                for i, word in enumerate(words):
                    token = word if i == 0 else " " + word
                    yield {"type": "token", "data": {"content": token}}

                yield {
                    "type": "done",
                    "data": {
                        "rounds": round_num + 1,
                        "tools_used": list(all_tools_used),
                        "total_time_ms": round((time.monotonic() - total_start) * 1000, 1),
                        "result_as_answer": True,
                    },
                }
                return

            # Quality gate: validate output between rounds
            last_tool_output = all_messages[-1].get("content", "") if all_messages else ""
            gate_result = await self._run_quality_gate(last_tool_output, round_num + 1)
            if gate_result is not None:
                yield {
                    "type": "quality_gate",
                    "data": {
                        "round": round_num + 1,
                        "passed": gate_result["passed"],
                        "reason": gate_result.get("reason", ""),
                        "mode": gate_result.get("mode", ""),
                    },
                }

        # Max rounds - force final text
        try:
            final_resp = await self.llm.chat_with_tools(
                all_messages,
                tools=None,
                model=model,
                user_id=user_id,
            )
            content = final_resp.content or "[Reached maximum tool rounds]"
            words = content.split(" ")
            for i, word in enumerate(words):
                token = word if i == 0 else " " + word
                yield {"type": "token", "data": {"content": token}}
        except Exception as e:
            logger.warning("Final streaming summary failed: %s", e)
            yield {"type": "token", "data": {"content": "[Reached maximum tool-calling rounds]"}}

        yield {
            "type": "done",
            "data": {
                "rounds": self.max_rounds,
                "tools_used": list(all_tools_used),
                "total_time_ms": round((time.monotonic() - total_start) * 1000, 1),
                "was_truncated": True,
            },
        }

"""
Quality Gate Validator
=====================

Validates action/node output between pipeline steps.
Supports three modes:
- schema: checks required keys exist in output
- expression: evaluates a Python expression against output
- llm: sends output to an LLM for quality assessment
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class QualityGateResult:
    """Result of a quality gate validation."""

    __slots__ = ("mode", "passed", "reason")

    def __init__(self, passed: bool, reason: str = "", mode: str = ""):
        self.passed = passed
        self.reason = reason
        self.mode = mode


async def validate_quality_gate(
    gate_config: Any,
    output: Any,
    action_name: str = "unknown",
) -> QualityGateResult:
    """Validate an action's output against its quality gate configuration.

    Args:
        gate_config: A QualityGateConfig (or dict with the same keys).
        output: The action's output to validate.
        action_name: Name of the action (for logging).

    Returns:
        QualityGateResult with passed=True/False and a reason string.
    """
    if gate_config is None:
        return QualityGateResult(passed=True, reason="No quality gate configured")

    # Support both pydantic model and raw dict
    mode = getattr(gate_config, "mode", None) or (
        gate_config.get("mode") if isinstance(gate_config, dict) else "schema"
    )

    try:
        if mode == "schema":
            return _validate_schema(gate_config, output)
        elif mode == "expression":
            return _validate_expression(gate_config, output)
        elif mode == "llm":
            return await _validate_llm(gate_config, output, action_name)
        else:
            logger.warning("Unknown quality gate mode '%s' for action '%s'", mode, action_name)
            return QualityGateResult(passed=True, reason=f"Unknown mode '{mode}', skipping", mode=mode)
    except Exception as e:
        logger.warning("Quality gate evaluation failed for '%s': %s", action_name, e)
        return QualityGateResult(passed=False, reason=f"Validation error: {e}", mode=mode)


def _validate_schema(gate_config: Any, output: Any) -> QualityGateResult:
    """Schema mode: check that required keys exist in the output dict."""
    required_keys = getattr(gate_config, "required_keys", None) or (
        gate_config.get("required_keys") if isinstance(gate_config, dict) else None
    )

    if not required_keys:
        return QualityGateResult(passed=True, reason="No required_keys specified", mode="schema")

    if not isinstance(output, dict):
        return QualityGateResult(
            passed=False,
            reason=f"Output is {type(output).__name__}, expected dict with keys: {required_keys}",
            mode="schema",
        )

    missing = [k for k in required_keys if k not in output]
    if missing:
        return QualityGateResult(
            passed=False,
            reason=f"Missing required keys: {missing}",
            mode="schema",
        )

    # Check for null/empty values in required keys
    empty = [k for k in required_keys if output.get(k) is None or output.get(k) == ""]
    if empty:
        return QualityGateResult(
            passed=False,
            reason=f"Required keys have empty values: {empty}",
            mode="schema",
        )

    return QualityGateResult(passed=True, reason="All required keys present", mode="schema")


def _validate_expression(gate_config: Any, output: Any) -> QualityGateResult:
    """Expression mode: evaluate a safe expression against the output."""
    expression = getattr(gate_config, "expression", None) or (
        gate_config.get("expression") if isinstance(gate_config, dict) else None
    )

    if not expression:
        return QualityGateResult(passed=True, reason="No expression specified", mode="expression")

    # Restricted evaluation namespace — no builtins except safe ones
    safe_builtins = {"len": len, "str": str, "int": int, "float": float, "bool": bool, "type": type}
    namespace: dict[str, Any] = {"output": output, **safe_builtins}

    try:
        from apps.backend.utils.safe_eval import safe_eval

        result = safe_eval(expression, allowed_names=namespace)
    except Exception as e:
        return QualityGateResult(
            passed=False,
            reason=f"Expression '{expression}' raised: {e}",
            mode="expression",
        )

    if bool(result):
        return QualityGateResult(passed=True, reason=f"Expression passed: {expression}", mode="expression")
    else:
        return QualityGateResult(
            passed=False,
            reason=f"Expression failed: {expression} → {result}",
            mode="expression",
        )


async def _validate_llm(gate_config: Any, output: Any, action_name: str) -> QualityGateResult:
    """LLM mode: use an LLM to assess the output quality."""
    llm_prompt = getattr(gate_config, "llm_prompt", None) or (
        gate_config.get("llm_prompt") if isinstance(gate_config, dict) else None
    )

    if not llm_prompt:
        return QualityGateResult(passed=True, reason="No llm_prompt specified", mode="llm")

    try:
        from apps.backend.services.unified_llm import get_unified_llm

        llm = get_unified_llm()

        # Truncate output for LLM context
        output_str = str(output)
        if len(output_str) > 2000:
            output_str = output_str[:2000] + "... (truncated)"

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a quality gate validator. Evaluate the action output against the criteria. "
                    "Respond with exactly 'PASS' or 'FAIL' on the first line, followed by a brief reason."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Action: {action_name}\n"
                    f"Quality criteria: {llm_prompt}\n\n"
                    f"Output to validate:\n{output_str}"
                ),
            },
        ]

        response = await llm.chat(messages)
        reply = response.content.strip() if response.content else ""
        first_line = reply.split("\n")[0].strip().upper()

        passed = first_line.startswith("PASS")
        reason = reply[len(first_line) :].strip() if len(reply) > len(first_line) else first_line

        return QualityGateResult(passed=passed, reason=reason or first_line, mode="llm")

    except ImportError:
        logger.warning("UnifiedLLM not available for quality gate LLM validation")
        return QualityGateResult(passed=True, reason="LLM unavailable, skipping", mode="llm")
    except Exception as e:
        logger.warning("LLM quality gate failed for '%s': %s", action_name, e)
        return QualityGateResult(passed=False, reason=f"LLM validation error: {e}", mode="llm")

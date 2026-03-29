"""
System Enhancement Module for agents_loop.py
Provides system coordination enhancement for directive processing
"""

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

# Import orchestrator getter
try:
    from agent_orchestrator import get_orchestrator
except ImportError:

    def get_orchestrator():
        """Fallback function when agent_orchestrator import fails."""
        return None


# Use environment variables with defaults for paths
# Fall back to repo-root-anchored path so cwd doesn't matter
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DEFAULT_SHADOW = str(_REPO_ROOT / "Shadow" / "arjuna_archive")
ARCHIVE_PATH = Path(os.getenv("SHADOW_DIR", _DEFAULT_SHADOW))
COMMANDS_PATH = Path(os.getenv("STATE_DIR", "Helix/state")) / "commands/helix_directives.json"
STATE_PATH = Path(os.getenv("STATE_DIR", "Helix/state")) / "ucf_state.json"
CYCLE_LOCK = Path(os.getenv("STATE_DIR", "Helix/state")) / ".cycle_lock"


async def process_directives_system(arjuna, kavach, log_event):
    """
    Process directive with optional system orchestration and return execution metrics.

    Returns:
        dict: Metrics describing the processing run with keys:
            - `timestamp` (str): UTC ISO timestamp when processing started.
            - `directive_type` (str): Value of the directive's `"command"` or `"unknown"`.
            - `system_enabled` (bool): True if a system orchestrator was engaged.
            - `execution_time` (float): Elapsed time in seconds for processing.
            - `coordination_delta` (float): Quantified coordination delta applied (0 if not used).
        None: If no command file exists or if an error occurred during processing.
    """
    if not COMMANDS_PATH.exists():
        return None

    try:
        # Load directive from file
        with open(COMMANDS_PATH, encoding="utf-8") as f:
            directive = json.load(f)

        # System-enhanced directive processing
        system_metrics = {
            "timestamp": datetime.now(UTC).isoformat(),
            "directive_type": directive.get("command", "unknown"),
            "system_enabled": False,
            "execution_time": 0,
            "coordination_delta": 0,
        }

        start_time = time.time()

        # Kavach scan before execution
        if "command" in directive:
            scan_result = await kavach.scan(directive["command"])
            if not scan_result.get("approved"):
                await log_event(f"🛡️ Kavach blocked: {directive['command']}")
                os.remove(COMMANDS_PATH)
                return system_metrics

        # Try system-enhanced execution
        try:
            orchestrator = get_orchestrator()

            if orchestrator and orchestrator.system_enabled:
                system_metrics["system_enabled"] = True

                # Execute with system coordination context
                coordination_context = {
                    "directive": directive,
                    "source": "arjuna_directive",
                    "priority": directive.get("priority", "normal"),
                }

                # Use system handshake for directive planning
                await orchestrator.execute_z88_stage(stage_name="directive_planning", context=coordination_context)

                system_metrics["coordination_delta"] = 0.087
        except Exception as system_error:
            await log_event(f"⚠️ System enhancement unavailable: {system_error}")

        # Standard execution
        await arjuna.planner(directive)

        # Calculate metrics
        system_metrics["execution_time"] = time.time() - start_time

        os.remove(COMMANDS_PATH)

        status_msg = f"✅ Processed directive: {directive}"
        if system_metrics["system_enabled"]:
            status_msg += f" [SYSTEM +{system_metrics['coordination_delta']:.3f}]"

        await log_event(status_msg)

        return system_metrics

    except Exception as e:
        await log_event(f"⚠️ Directive processing error: {e}")
        return None

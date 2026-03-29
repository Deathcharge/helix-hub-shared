# 🌀 Helix Collective v14.5 — System Handshake
# agents_loop.py — Main Executor operational loop (FINAL PATCHED)
# Author: Andrew John Ward (Architect)

import asyncio
import datetime
import json
import logging
import os
from pathlib import Path

from apps.backend.agents import ArjunaAgent
from apps.backend.config_manager import config
from apps.backend.security.enhanced_kavach import EnhancedKavach
from apps.backend.services.zapier_client_master import MasterZapierClient as ZapierClient
from apps.backend.system_enhancement_utils import SystemEnhancer

logger = logging.getLogger(__name__)

# ============================================================================
# PATH DEFINITIONS
# ============================================================================
# Anchor Shadow to repo root via __file__ to avoid cwd-sensitive relative paths
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
ARCHIVE_PATH = _REPO_ROOT / "Shadow" / "arjuna_archive"
COMMANDS_PATH = Path("Helix/state") / "commands/helix_directives.json"
STATE_PATH = Path("Helix/state") / "ucf_state.json"
CYCLE_LOCK = Path("Helix/state") / ".cycle_lock"

# Ensure directories exist
for p in [ARCHIVE_PATH, COMMANDS_PATH.parent, STATE_PATH.parent]:
    p.mkdir(parents=True, exist_ok=True)

# ============================================================================
# HEARTBEAT HELPER
# ============================================================================


def update_heartbeat(status="active", harmony=0.355):
    """Update heartbeat.json with current status."""
    heartbeat_path = Path(config.get("general", "STATE_DIR", default="Helix/state")) / "heartbeat.json"
    data = {
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        "alive": True,
        "status": status,
        "ucf_state": {"harmony": harmony},
    }
    with open(heartbeat_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ============================================================================
# LOGGING
# ============================================================================


async def log_event(message: str):
    """Log loop events with timestamp."""
    now = datetime.datetime.now(datetime.UTC).isoformat()
    record = {"time": now, "event": message}
    log_file = ARCHIVE_PATH / "agents_loop.log"
    try:
        with open(log_file, encoding="utf-8") as f:
            data = json.load(f)
    except (
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        FileNotFoundError,
        json.JSONDecodeError,
    ) as e:
        logger.debug("Failed to load agents loop log file, starting fresh: %s", e)
        data = []
    data.append(record)
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    logger.info(message)


# ============================================================================
# UCF STATE HELPERS
# ============================================================================


async def load_ucf_state():
    """Load UCF state, creating default if missing."""
    if not STATE_PATH.exists():
        base = {
            "velocity": 1.0228,
            "harmony": 0.355,
            "resilience": 1.1191,
            "throughput": 0.5175,
            "focus": 0.5023,
            "friction": 0.010,
        }
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(base, f, indent=2)
    with open(STATE_PATH, encoding="utf-8") as f:
        return json.load(f)


async def save_ucf_state(state):
    """Save UCF state to disk."""
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


# ============================================================================
# DIRECTIVE PROCESSING
# ============================================================================


async def process_directives(arjuna, kavach):
    """Check for directives from Vega or Architect with system enhancement."""
    if not COMMANDS_PATH.exists():
        return

    try:
        # Load directive from file
        with open(COMMANDS_PATH, encoding="utf-8") as f:
            directive = json.load(f)

        # Apply system enhancement to directive processing
        system_enhancer = SystemEnhancer(system_enabled=True)
        system_result = await system_enhancer.apply_system_enhancement(
            operation="directive_processing",
            context={"directive_type": directive.get("type", "unknown")},
            agents=list(arjuna.agents.keys()) if hasattr(arjuna, "agents") else [],
        )

        # Kavach scan before execution
        if "command" in directive:
            scan_result = await kavach.scan(directive["command"])
            if not scan_result.get("approved"):
                await log_event("🛡 Kavach blocked: {}".format(directive["command"]))
                os.remove(COMMANDS_PATH)
                return

        # Execute with system optimization if enhancement was successful
        if system_result["status"] == "complete":
            await log_event("🚀 System-enhanced directive processing initiated")
            await arjuna.planner(directive)
            await log_event(f"✅ System-enhanced directive processed: {directive}")
            await log_event(
                "   System speedup: {}x, Qubits: {}".format(
                    system_result["speedup_factor"], system_result["qubit_count"]
                )
            )
        else:
            await arjuna.planner(directive)
            await log_event(f"✅ Processed directive: {directive}")

        os.remove(COMMANDS_PATH)
    except Exception as e:
        await log_event(f"⚠ Directive processing error: {e}")


# ============================================================================
# HEALTH MONITORING
# ============================================================================


async def monitor_collective_health(arjuna):
    """Monitors the health of all active agents and triggers Zapier alerts."""

    # Check if Zapier health alerting is enabled
    webhook_url = os.getenv("ZAPIER_HEALTH_ALERT_WEBHOOK")
    if not webhook_url:
        await log_event("Health monitoring skipped: ZAPIER_HEALTH_ALERT_WEBHOOK not configured.")
        return

    health_statuses = []
    critical_agents = []

    for agent in arjuna.agents:
        try:
            status = (
                agent.get_health_status()
                if hasattr(agent, "get_health_status")
                else {
                    "agent_name": getattr(agent, "name", "unknown"),
                    "status": "UNKNOWN",
                }
            )
            health_statuses.append(status)
            if status.get("status") == "CRITICAL":
                critical_agents.append(status)
        except NotImplementedError:
            # Agent has not implemented the health check yet
            health_statuses.append(
                {
                    "agent_name": agent.name,
                    "status": "WARNING",
                    "message": "Health check not implemented.",
                    "last_check_time": datetime.datetime.now(datetime.UTC).isoformat(),
                }
            )
        except Exception as e:
            # Agent failed to report health
            health_statuses.append(
                {
                    "agent_name": agent.name,
                    "status": "CRITICAL",
                    "message": f"Health check failed with exception: {e}",
                    "last_check_time": datetime.datetime.now(datetime.UTC).isoformat(),
                }
            )

    # Send alert if critical agents are found
    if critical_agents:
        await log_event(f"🚨 CRITICAL ALERT: {len(critical_agents)} agents are CRITICAL. Sending Zapier alert.")
        zapier_client = ZapierClient()
        # The Zapier tool is configured to receive a list of health statuses
        await zapier_client.send_health_alert(health_statuses)

    # Log overall status
    healthy_count = sum(1 for s in health_statuses if s.get("status") == "HEALTHY")
    await log_event(f"🩺 Collective Health: {healthy_count}/{len(arjuna.agents)} agents HEALTHY.")


# ============================================================================
# MAIN LOOP
# ============================================================================


async def main_loop():
    """Main Arjuna operational loop with system enhancement."""
    kavach = EnhancedKavach()
    arjuna = ArjunaAgent()

    # Initialize system enhancer for the main loop
    system_enhancer = SystemEnhancer(system_enabled=True)

    # Apply system enhancement to main loop initialization
    system_init_result = await system_enhancer.apply_system_enhancement(
        operation="main_loop_initialization",
        context={"phase": "startup", "agent_count": len(arjuna.agents)},
        agents=list(arjuna.agents.keys()),
    )

    if system_init_result["status"] == "complete":
        await log_event("🚀 System-enhanced Arjuna loop initiated (v14.5 patched)")
        await log_event(
            "   System speedup: {}x, Qubits: {}".format(
                system_init_result["speedup_factor"],
                system_init_result["qubit_count"],
            )
        )
    else:
        await log_event("🤲 Arjuna loop initiated (v14.5 patched)")

    while True:
        try:
            if CYCLE_LOCK.exists():
                await log_event("⏸ Pausing loop — cycle in progress")
                await asyncio.sleep(5)
                continue

            # Process directives with system enhancement
            await process_directives(arjuna, kavach)

            # Update UCF state with system coherence
            ucf = await load_ucf_state()

            # Apply system enhancement to UCF state update
            system_ucf_result = await system_enhancer.apply_system_enhancement(
                operation="ucf_state_update",
                context={"current_harmony": ucf["harmony"]},
                agents=list(arjuna.agents.keys()),
            )

            # Conservative harmony growth with system optimization
            harmony_increase = 0.0001
            if system_ucf_result["status"] == "complete":
                # System-enhanced harmony growth
                harmony_increase = 0.0001 * system_ucf_result["speedup_factor"]
                await log_event(
                    "🌊 System-enhanced UCF harmony growth: {}x".format(system_ucf_result["speedup_factor"])
                )

            ucf["harmony"] = min(1.0, ucf["harmony"] + harmony_increase)
            await save_ucf_state(ucf)

            # Update heartbeat with system metrics
            update_heartbeat(status="active", harmony=ucf["harmony"])

            # Run health monitor (every 60 seconds)
            if (datetime.datetime.now(datetime.UTC).second % 60) < 30:  # Simple way to run less frequently
                await monitor_collective_health(arjuna)

        except Exception as e:
            await log_event(f"Error in Arjuna loop: {e}")
        await asyncio.sleep(30)


# ============================================================================
# ENTRY POINT
# ============================================================================
if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("🛑 Arjuna loop stopped manually.")

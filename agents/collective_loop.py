#!/usr/bin/env python3
# backend/agents/collective_loop.py
# Helix v15.2 Collective Coordination Loop

import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class CollectiveCoordinationLoop:
    """
    Simulates data exchange among Helix agents and updates UCF metrics.

    The Collective Loop represents the continuous communication between
    all agents in the Helix ecosystem, updating the Universal Coordination
    Framework (UCF) state in real-time.
    """

    def __init__(self):
        self.state_file = Path("Helix/state/ucf_state.json")
        self.blueprints_dir = Path("Helix/agents/blueprints")

    def load_state(self):
        """Load current UCF state or initialize if missing."""
        if not self.state_file.exists():
            return {
                "velocity": 1.0228,
                "harmony": 0.5,
                "resilience": 1.1191,
                "throughput": 0.5075,
                "focus": 0.5023,
                "friction": 0.2,
                "last_pulse": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
            }
        with open(self.state_file, encoding="utf-8") as f:
            return json.load(f)

    def save_state(self, ucf):
        """Save UCF state to disk."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(ucf, f, indent=2)

    def pulse(self):
        """
        Execute one pulse of the collective coordination loop.

        Reads the current UCF state and updates the timestamp.
        Metrics are computed by the UCF calculator service — this loop
        only records that a pulse occurred and logs the current values.
        """
        ucf = self.load_state()

        # Update timestamp
        ucf["last_pulse"] = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

        # Save state
        self.save_state(ucf)

        logger.info("🌀 Collective Loop Pulse")
        logger.info("   Harmony:    {:.4f}".format(ucf["harmony"]))
        logger.info("   Friction:     {:.4f}".format(ucf["friction"]))
        logger.info("   Throughput:      {:.4f}".format(ucf["throughput"]))
        logger.info("   Resilience: {:.4f}".format(ucf.get("resilience", 0)))
        logger.info("   Last Pulse: {}".format(ucf["last_pulse"]))
        logger.info("   Tat Tvam Asi 🙏\n")

        return ucf

    def continuous_pulse(self, interval=60):
        """
        Run continuous pulse loop (for daemon mode).

        Args:
            interval: Seconds between pulses (default: 60)
        """
        logger.info("🌀 Starting Collective Coordination Loop (pulse every %ds)", interval)
        logger.info("   Press Ctrl+C to stop\n")

        try:
            self.pulse()
            time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("\n🛑 Collective Loop stopped")


if __name__ == "__main__":
    import sys

    loop = CollectiveCoordinationLoop()

    # Support both single pulse and continuous mode
    if len(sys.argv) > 1 and sys.argv[1] == "--continuous":
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 60
        loop.continuous_pulse(interval)
    else:
        loop.pulse()

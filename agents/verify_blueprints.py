#!/usr/bin/env python3
# backend/agents/verify_blueprints.py
# Helix v15.2 Blueprint Verification & Combination Tool

import glob
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from apps.backend.logging.helix_logger import get_logger

logger = get_logger(__name__)


ROOT = Path("Helix/agents/blueprints")
STATE = Path("Helix/state")


def checksum(data: dict) -> str:
    """Generate SHA256 checksum of blueprint data."""
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:12]


def verify():
    """Verify all agent blueprints and create combined file."""
    logger.info("🌀 Helix v15.2 Blueprint Verification")
    logger.info("=" * 50)

    # Load manifest
    manifest_path = STATE / "blueprints_manifest.json"
    if not manifest_path.exists():
        logger.error("❌ blueprints_manifest.json not found!")
        sys.exit(1)

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    expected = set(manifest["agents"])

    # Find all blueprint files (excluding combined file)
    found_files = {Path(f).name for f in glob.glob(str(ROOT / "*.json")) if "all" not in f and "combined" not in f}

    # Check for missing files
    missing = expected - found_files
    extra = found_files - expected

    if missing:
        logger.error("❌ Missing blueprint files: {}".format(", ".join(missing)))
        sys.exit(1)

    if extra:
        logger.warning("⚠️  Extra files (not in manifest): {}".format(", ".join(extra)))

    # Verify each blueprint has required fields
    all_ok = True
    agent_data = {}

    for filename in found_files:
        filepath = ROOT / filename
        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)

            # Check required fields
            required = ["agent", "version", "role", "ethics_compliance", "status"]
            missing_fields = [f for f in required if f not in data]

            if missing_fields:
                logger.warning("⚠️  %s: missing fields %s", filename, missing_fields)
                all_ok = False

            # Verify ethics compliance
            if "ethics_compliance" not in data:
                logger.warning("⚠️  %s: no ethics_compliance key", filename)
                all_ok = False
            elif "Ethics Validator" not in data["ethics_compliance"]:
                logger.warning("⚠️  %s: ethics_compliance doesn't reference Ethics Validator", filename)
                all_ok = False

            # Store for combined file (use agent name as key)
            agent_name = data.get("agent", Path(filename).stem)
            agent_data[agent_name] = data

            logger.info("✅ {}: {} v{}".format(filename, data.get("agent", "Unknown"), data.get("version", "?")))

        except json.JSONDecodeError as e:
            logger.error("❌ %s: Invalid JSON - %s", filename, e)
            all_ok = False
        except Exception as e:
            logger.error("❌ %s: Error - %s", filename, e)
            all_ok = False

    if not all_ok:
        logger.warning("\n⚠️  Some blueprints have issues - review above")
        sys.exit(1)

    # Create combined blueprints file
    combined = {
        "version": manifest.get("version", "15.2"),
        "ethics": {
            "framework": manifest.get("ethics", "Ethics Validator v13.4"),
            "pillars": [
                "Non-Maleficence",
                "Autonomy",
                "Reciprocal Freedom",
                "Perfect State",
            ],
            "verification": "pass",
        },
        "agents": agent_data,
        "checksum": checksum(agent_data),
        "generated_on": datetime.now(UTC).isoformat() + "Z",
        "manifest": manifest,
    }

    # Write combined file
    combined_path = ROOT / "blueprints_all.json"
    with open(combined_path, "w", encoding="utf-8") as out:
        json.dump(combined, out, indent=2)

    logger.info("=" * 50)
    logger.info("✅ All %d agent blueprints verified!", len(agent_data))
    logger.info("✅ Combined file created: %s", combined_path)
    logger.info("📋 Checksum: {}".format(combined["checksum"]))
    logger.info("🔐 Ethics: {}".format(combined["ethics"]["framework"]))
    logger.info("\n🌀 Helix v15.2 Blueprint Archive Ready!")
    logger.info("   Tat Tvam Asi 🙏")


if __name__ == "__main__":
    verify()

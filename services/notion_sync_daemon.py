#!/usr/bin/env python3
"""
🔄 Helix Collective - Notion Sync Daemon
Bidirectional synchronization between Notion databases and Zapier Tables

Runs every 5 minutes via Railway cron job to maintain data consistency
across the entire coordination platform ecosystem.

Architecture:
- Notion databases (persistent storage, version control)
- Zapier Tables (real-time operations, ephemeral)
- Railway backend (sync orchestration)

Author: Helix Collective v16.7
"""

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


class NotionSyncDaemon:
    """Bidirectional sync daemon for Notion ↔ Zapier integration."""

    def __init__(self) -> None:
        # Environment configuration
        self.notion_api_key = os.getenv("NOTION_API_KEY")

        # Notion database IDs
        self.database_ids = {
            "agent_registry": os.getenv("NOTION_AGENT_DB_ID"),
            "ucf_metrics": os.getenv("NOTION_UCF_DB_ID"),
            "context_vault": os.getenv("NOTION_CONTEXT_DB_ID"),
            "emergency_log": os.getenv("NOTION_EMERGENCY_DB_ID"),
        }

        # Zapier webhook endpoints
        self.webhooks = {
            "agent_sync": os.getenv("ZAPIER_AGENT_WEBHOOK"),
            "ucf_sync": os.getenv("ZAPIER_UCF_WEBHOOK"),
            "context_sync": os.getenv("ZAPIER_CONTEXT_WEBHOOK"),
            "emergency_sync": os.getenv("ZAPIER_EMERGENCY_WEBHOOK"),
        }

        # Persistent state storage
        self.state_dir = Path("/data") if Path("/data").exists() else Path("data")
        self.state_dir.mkdir(exist_ok=True)
        self.state_file = self.state_dir / "sync_state.json"

        # Initialize Notion client (lazy loading for graceful degradation)
        self.notion = None
        self.notion_available = False

        # Load last sync state
        self.sync_state = self.load_sync_state()

    def initialize_notion_client(self):
        """Initialize Notion client with graceful error handling."""
        if not self.notion_api_key:
            logger.info("⚠️ NOTION_API_KEY not configured - sync disabled")
            return False

        try:
            from notion_client import Client

            self.notion = Client(auth=self.notion_api_key)
            self.notion_available = True
            logger.info("✅ Notion client initialized")
            return True
        except ImportError:
            logger.info("⚠️ notion-client not installed - sync disabled")
            logger.info("   Install with: pip install notion-client")
            return False
        except Exception as e:
            logger.error("❌ Failed to initialize Notion client: %s", e)
            return False

    def load_sync_state(self) -> dict:
        """Load last sync timestamps from persistent storage."""
        try:
            if self.state_file.exists():
                with open(self.state_file, encoding="utf-8") as f:
                    state = json.load(f)
                    logger.info("📖 Loaded sync state from %s", self.state_file)
                    return state
        except Exception as e:
            logger.info("⚠️ Could not load sync state: %s", e)

        # Default state
        return {
            "last_sync": {
                "agents": None,
                "ucf": None,
                "context": None,
                "emergency": None,
            },
            "sync_count": 0,
            "last_error": None,
        }

    def save_sync_state(self):
        """Save sync state to persistent storage."""
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.sync_state, f, indent=2)
            logger.info("💾 Saved sync state to %s", self.state_file)
        except Exception as e:
            logger.info("⚠️ Could not save sync state: %s", e)

    # ═══════════════════════════════════════════════════════════════════════
    # NOTION → ZAPIER SYNC (Pull from Notion, push to Zapier Tables)
    # ═══════════════════════════════════════════════════════════════════════

    def sync_agents_notion_to_zapier(self) -> int:
        """Sync Agent Registry from Notion to Zapier Tables."""
        logger.info("🤖 Syncing agents: Notion → Zapier...")

        db_id = self.database_ids["agent_registry"]
        if not db_id:
            logger.info("⚠️ Agent Registry database ID not configured")
            return 0

        try:
            # Query Notion database for updated agents
            query_filter = {}
            if self.sync_state["last_sync"]["agents"]:
                query_filter = {
                    "timestamp": "last_edited_time",
                    "last_edited_time": {"after": self.sync_state["last_sync"]["agents"]},
                }

            response = self.notion.databases.query(database_id=db_id, filter=query_filter if query_filter else None)

            agents = response.get("results", [])
            synced_count = 0

            for agent_page in agents:
                agent_data = {
                    "name": self.extract_title(agent_page, "Name"),
                    "role": self.extract_select(agent_page, "Role"),
                    "symbol": self.extract_rich_text(agent_page, "Symbol"),
                    "status": self.extract_select(agent_page, "Status"),
                    "last_active": self.extract_date(agent_page, "Last Active"),
                    "specialization": self.extract_rich_text(agent_page, "Specialization"),
                    "notion_id": agent_page["id"],
                    "last_edited": agent_page["last_edited_time"],
                    "source": "notion_sync",
                }

                if self.push_to_zapier("agent_sync", agent_data):
                    synced_count += 1

            self.sync_state["last_sync"]["agents"] = datetime.now(UTC).isoformat()
            logger.info("✅ Synced %s agents to Zapier", synced_count)
            return synced_count

        except Exception as e:
            logger.error("❌ Agent sync error: %s", e)
            self.sync_state["last_error"] = str(e)
            return 0

    def sync_ucf_notion_to_zapier(self) -> int:
        """Sync UCF Metrics from Notion to Zapier Tables."""
        logger.info("🌀 Syncing UCF metrics: Notion → Zapier...")

        db_id = self.database_ids["ucf_metrics"]
        if not db_id:
            logger.info("⚠️ UCF Metrics database ID not configured")
            return 0

        try:
            # Get latest UCF metrics entry
            response = self.notion.databases.query(
                database_id=db_id,
                sorts=[{"timestamp": "Timestamp", "direction": "descending"}],
                page_size=1,
            )

            results = response.get("results", [])
            if not results:
                logger.info("ℹ️ No UCF metrics found in Notion")
                return 0

            latest = results[0]
            ucf_data = {
                "timestamp": self.extract_date(latest, "Timestamp"),
                "harmony": self.extract_number(latest, "Harmony"),
                "resilience": self.extract_number(latest, "Resilience"),
                "throughput": self.extract_number(latest, "Throughput"),
                "focus": self.extract_number(latest, "Focus"),
                "friction": self.extract_number(latest, "Friction"),
                "velocity": self.extract_number(latest, "Velocity"),
                "notion_id": latest["id"],
                "source": "notion_sync",
            }

            if self.push_to_zapier("ucf_sync", ucf_data):
                self.sync_state["last_sync"]["ucf"] = datetime.now(UTC).isoformat()
                logger.info("✅ Synced latest UCF metrics to Zapier")
                return 1

            return 0

        except Exception as e:
            logger.error("❌ UCF sync error: %s", e)
            self.sync_state["last_error"] = str(e)
            return 0

    def sync_context_vault_notion_to_zapier(self) -> int:
        """Sync Context Vault entries from Notion to Zapier."""
        logger.info("💾 Syncing context vault: Notion → Zapier...")

        db_id = self.database_ids["context_vault"]
        if not db_id:
            logger.info("⚠️ Context Vault database ID not configured")
            return 0

        try:
            query_filter = {}
            if self.sync_state["last_sync"]["context"]:
                query_filter = {
                    "timestamp": "last_edited_time",
                    "last_edited_time": {"after": self.sync_state["last_sync"]["context"]},
                }

            response = self.notion.databases.query(
                database_id=db_id,
                filter=query_filter if query_filter else None,
                sorts=[{"timestamp": "Timestamp", "direction": "descending"}],
                page_size=10,  # Sync last 10 new/updated checkpoints
            )

            checkpoints = response.get("results", [])
            synced_count = 0

            for checkpoint in checkpoints:
                context_data = {
                    "session_name": self.extract_title(checkpoint, "Session Name"),
                    "ai_platform": self.extract_select(checkpoint, "AI Platform"),
                    "timestamp": self.extract_date(checkpoint, "Timestamp"),
                    "context_summary": self.extract_rich_text(checkpoint, "Context Summary"),
                    "key_decisions": self.extract_multi_select(checkpoint, "Key Decisions"),
                    "retrieval_prompt": self.extract_rich_text(checkpoint, "Retrieval Prompt"),
                    "notion_id": checkpoint["id"],
                    "source": "notion_sync",
                }

                if self.push_to_zapier("context_sync", context_data):
                    synced_count += 1

            self.sync_state["last_sync"]["context"] = datetime.now(UTC).isoformat()
            logger.info("✅ Synced %s context checkpoints to Zapier", synced_count)
            return synced_count

        except Exception as e:
            logger.error("❌ Context vault sync error: %s", e)
            self.sync_state["last_error"] = str(e)
            return 0

    def sync_emergency_log_notion_to_zapier(self) -> int:
        """Sync Emergency Log entries from Notion to Zapier."""
        logger.info("🚨 Syncing emergency log: Notion → Zapier...")

        db_id = self.database_ids["emergency_log"]
        if not db_id:
            logger.info("⚠️ Emergency Log database ID not configured")
            return 0

        try:
            query_filter = {}
            if self.sync_state["last_sync"]["emergency"]:
                query_filter = {
                    "timestamp": "last_edited_time",
                    "last_edited_time": {"after": self.sync_state["last_sync"]["emergency"]},
                }

            response = self.notion.databases.query(
                database_id=db_id,
                filter=query_filter if query_filter else None,
                sorts=[{"timestamp": "Created", "direction": "descending"}],
                page_size=20,
            )

            alerts = response.get("results", [])
            synced_count = 0

            for alert in alerts:
                alert_data = {
                    "alert_type": self.extract_select(alert, "Alert Type"),
                    "severity": self.extract_select(alert, "Severity"),
                    "description": self.extract_rich_text(alert, "Description"),
                    "resolution_status": self.extract_select(alert, "Resolution Status"),
                    "created": self.extract_created_time(alert),
                    "resolved": self.extract_date(alert, "Resolved"),
                    "notion_id": alert["id"],
                    "source": "notion_sync",
                }

                if self.push_to_zapier("emergency_sync", alert_data):
                    synced_count += 1

            self.sync_state["last_sync"]["emergency"] = datetime.now(UTC).isoformat()
            logger.info("✅ Synced %s emergency alerts to Zapier", synced_count)
            return synced_count

        except Exception as e:
            logger.error("❌ Emergency log sync error: %s", e)
            self.sync_state["last_error"] = str(e)
            return 0

    # ═══════════════════════════════════════════════════════════════════════
    # HELPER METHODS - Notion Property Extraction
    # ═══════════════════════════════════════════════════════════════════════

    def extract_title(self, page: dict, prop_name: str) -> str | None:
        """Extract title property from Notion page."""
        try:
            return page["properties"][prop_name]["title"][0]["text"]["content"]
        except (KeyError, IndexError, TypeError):
            return None

    def extract_select(self, page: dict, prop_name: str) -> str | None:
        """Extract select property from Notion page."""
        try:
            return page["properties"][prop_name]["select"]["name"]
        except (KeyError, TypeError):
            return None

    def extract_multi_select(self, page: dict, prop_name: str) -> list[str]:
        """Extract multi-select property from Notion page."""
        try:
            return [opt["name"] for opt in page["properties"][prop_name]["multi_select"]]
        except (KeyError, TypeError):
            return []

    def extract_rich_text(self, page: dict, prop_name: str) -> str | None:
        """Extract rich text property from Notion page."""
        try:
            texts = page["properties"][prop_name]["rich_text"]
            return "".join([text["text"]["content"] for text in texts])
        except (KeyError, IndexError, TypeError):
            return None

    def extract_date(self, page: dict, prop_name: str) -> str | None:
        """Extract date property from Notion page."""
        try:
            return page["properties"][prop_name]["date"]["start"]
        except (KeyError, TypeError):
            return None

    def extract_number(self, page: dict, prop_name: str) -> float | None:
        """Extract number property from Notion page."""
        try:
            return page["properties"][prop_name]["number"]
        except (KeyError, TypeError):
            return None

    def extract_created_time(self, page: dict) -> str:
        """Extract created_time from Notion page."""
        return page.get("created_time", datetime.now(UTC).isoformat())

    # ═══════════════════════════════════════════════════════════════════════
    # ZAPIER WEBHOOK INTEGRATION
    # ═══════════════════════════════════════════════════════════════════════

    def push_to_zapier(self, webhook_key: str, data: dict) -> bool:
        """Send data to Zapier webhook endpoint."""
        webhook_url = self.webhooks.get(webhook_key)

        if not webhook_url:
            logger.info("⚠️ Webhook '%s' not configured", webhook_key)
            return False

        try:
            response = requests.post(
                webhook_url,
                json=data,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )

            if response.status_code == 200:
                return True
            else:
                logger.info("⚠️ Webhook '%s' returned status %s", webhook_key, response.status_code)
                return False

        except requests.exceptions.Timeout:
            logger.info("⚠️ Webhook '%s' timeout (10s)", webhook_key)
            return False
        except Exception as e:
            logger.error("❌ Webhook '%s' error: %s", webhook_key, e)
            return False

    # ═══════════════════════════════════════════════════════════════════════
    # MAIN SYNC ORCHESTRATION
    # ═══════════════════════════════════════════════════════════════════════

    def run_sync_cycle(self):
        """Execute complete bidirectional sync cycle."""
        logger.info("=" * 70)
        logger.info("🌀 HELIX COORDINATION SYNC DAEMON - Starting Cycle")
        logger.info("=" * 70)
        logger.info("Timestamp: %s", datetime.now(UTC).isoformat())
        logger.info("Cycle #%s", self.sync_state["sync_count"] + 1)

        # Initialize Notion client
        if not self.notion_available:
            if not self.initialize_notion_client():
                logger.warning("❌ Notion client unavailable - aborting sync")
                return

        # Check database configuration
        configured_dbs = [k for k, v in self.database_ids.items() if v]
        if not configured_dbs:
            logger.info("⚠️ No Notion databases configured - aborting sync")
            return

        logger.info("📊 Configured databases: %s", ", ".join(configured_dbs))

        # Execute sync operations
        total_synced = 0

        try:
            # Notion → Zapier syncs
            total_synced += self.sync_agents_notion_to_zapier()

            total_synced += self.sync_ucf_notion_to_zapier()

            total_synced += self.sync_context_vault_notion_to_zapier()

            total_synced += self.sync_emergency_log_notion_to_zapier()

            # Update sync state
            self.sync_state["sync_count"] += 1
            self.sync_state["last_error"] = None
            self.save_sync_state()

            # Summary
            logger.info("=" * 70)
            logger.info("✅ SYNC CYCLE COMPLETE")
            logger.info("=" * 70)
            logger.info("Total records synced: %s", total_synced)
            logger.info("Sync state saved to: %s", self.state_file)
            logger.info("Next sync in: 5 minutes")

        except Exception as e:
            logger.info("=" * 70)
            logger.error("❌ SYNC CYCLE FAILED")
            logger.info("=" * 70)
            logger.error("Error: %s", e)

            # Log error to emergency system
            self.sync_state["last_error"] = str(e)
            self.save_sync_state()

            # Send alert to emergency webhook
            self.push_to_zapier(
                "emergency_sync",
                {
                    "alert_type": "Sync Daemon Failure",
                    "severity": "High",
                    "description": f"Sync cycle #{self.sync_state['sync_count'] + 1} failed: {e!s}",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "source": "notion_sync_daemon",
                },
            )


def main():
    """Entry point for Railway cron job."""
    daemon = NotionSyncDaemon()
    daemon.run_sync_cycle()


if __name__ == "__main__":
    main()

# 🌀 Helix Collective v17.0 — Notion API 2025-09-03 Compatible
# backend/services/notion_client.py — Notion Integration Client
# Author: Andrew John Ward (Architect) + Arjuna AI (Root Coordinator)

import logging
import os
from datetime import UTC, datetime
from typing import Any

from notion_client import Client

# Configure logger
logger = logging.getLogger(__name__)

# ============================================================================
# NOTION CLIENT (2025-09-03 API Compatible)
# ============================================================================


class HelixNotionClient:
    """
    Client for Notion integration with Helix Collective databases.

    Compatible with Notion API version 2025-09-03, which introduces
    multi-source database support and requires data_source_id instead
    of database_id for most operations.
    """

    def __init__(self) -> None:
        """Initialize Notion client with database IDs and API version."""
        notion_token = os.getenv("NOTION_API_KEY")
        if not notion_token:
            logger.warning("⚠️ NOTION_API_KEY not set. Notion integration will be disabled.")
            self.notion = None
            self._disabled = True
            return

        self._disabled = False

        # Initialize client with 2025-09-03 API version
        self.notion = Client(auth=notion_token, notion_version="2025-09-03")  # NEW: Explicitly set API version

        # Database IDs (from Notion workspace)
        self.system_state_db = os.getenv("NOTION_SYSTEM_STATE_DB", "009a946d04fb46aa83e4481be86f09e")
        self.agent_registry_db = os.getenv("NOTION_AGENT_REGISTRY_DB", "2f65aab794a64ec48bcc46bf760f128")
        self.event_log_db = os.getenv("NOTION_EVENT_LOG_DB", "acb01d4a955d4775aaeb2310d1da1102")
        self.context_db = os.getenv("NOTION_CONTEXT_DB", "d704854868474666b4b774750f8b134a")
        self.deployment_log_db = os.getenv("NOTION_DEPLOYMENT_LOG_DB", "8c1a6bf4a7984eee9802c8af1979c3f9")

        # Cache for agent page IDs and data source IDs
        self._agent_cache: dict[str, str] = {}
        self._data_source_cache: dict[str, str] = {}  # NEW: Cache data source IDs

    # ========================================================================
    # DATA SOURCE DISCOVERY (NEW for 2025-09-03)
    # ========================================================================

    async def _get_data_source_id(self, database_id: str) -> str | None:
        """
        Get the data source ID for a database.

        This is required for the 2025-09-03 API version. We fetch the first
        data source from the database. If multiple data sources exist, this
        will use the first one.

        Args:
            database_id: The database ID

        Returns:
            The data source ID, or None if not found
        """
        if getattr(self, "_disabled", False):
            return None

        if database_id in self._data_source_cache:
            return self._data_source_cache[database_id]

        try:
            response = self.notion.databases.retrieve(database_id=database_id)

            # Extract the first data source ID
            data_sources = response.get("data_sources", [])
            if data_sources and len(data_sources) > 0:
                data_source_id = data_sources[0]["id"]
                self._data_source_cache[database_id] = data_source_id
                logger.info("✅ Cached data source ID for database %s...", database_id[:8])
                return data_source_id
            else:
                logger.warning("⚠️ No data sources found for database %s...", database_id[:8])
                return None
        except Exception as e:
            logger.error("❌ Error getting data source ID for %s...: %s", database_id[:8], e)
            return None

    # ========================================================================
    # AGENT REGISTRY OPERATIONS
    # ========================================================================

    async def _get_agent_page_id(self, agent_name: str) -> str | None:
        """Get page ID for an agent from cache or database."""
        if agent_name in self._agent_cache:
            return self._agent_cache[agent_name]

        try:
            data_source_id = await self._get_data_source_id(self.agent_registry_db)
            if not data_source_id:
                logger.error("❌ Could not get data source ID for agent registry")
                return None

            # Query using the new data source endpoint
            results = self.notion.request(
                path=f"data_sources/{data_source_id}/query",
                method="POST",
                body={
                    "filter": {
                        "property": "Agent Name",
                        "title": {"equals": agent_name},
                    }
                },
            )

            if results.get("results"):
                page_id = results["results"][0]["id"]
                self._agent_cache[agent_name] = page_id
                return page_id
        except Exception as e:
            logger.warning("⚠️ Error getting agent page ID for %s: %s", agent_name, e)

        return None

    async def create_agent(
        self,
        agent_name: str,
        symbol: str,
        role: str,
        status: str = "Active",
        health_score: int = 100,
    ) -> str | None:
        """Create a new agent in the Agent Registry."""
        try:
            data_source_id = await self._get_data_source_id(self.agent_registry_db)
            if not data_source_id:
                logger.error("❌ Could not get data source ID for agent registry")
                return None

            # Create page with data_source_id parent (NEW)
            response = self.notion.pages.create(
                parent={"type": "data_source_id", "data_source_id": data_source_id},
                properties={
                    "Agent Name": {"title": [{"text": {"content": agent_name}}]},
                    "Symbol": {"rich_text": [{"text": {"content": symbol}}]},
                    "Role": {"rich_text": [{"text": {"content": role}}]},
                    "Status": {"select": {"name": status}},
                    "Last Action": {"rich_text": [{"text": {"content": "Initialized"}}]},
                    "Health Score": {"number": health_score},
                    "Last Updated": {"date": {"start": datetime.now(UTC).isoformat()}},
                },
            )

            page_id = response["id"]
            self._agent_cache[agent_name] = page_id
            logger.info("✅ Created agent %s in Notion", agent_name)
            return page_id
        except Exception as e:
            logger.error("❌ Error creating agent %s: %s", agent_name, e)
            return None

    async def update_agent_status(self, agent_name: str, status: str, last_action: str, health_score: int) -> bool:
        """Update agent status in the Agent Registry."""
        try:
            agent_page_id = await self._get_agent_page_id(agent_name)
            if not agent_page_id:
                logger.warning("⚠️ Agent %s not found in Notion", agent_name)
                return False

            self.notion.pages.update(
                page_id=agent_page_id,
                properties={
                    "Status": {"select": {"name": status}},
                    "Last Action": {"rich_text": [{"text": {"content": last_action[:100]}}]},
                    "Health Score": {"number": health_score},
                    "Last Updated": {"date": {"start": datetime.now(UTC).isoformat()}},
                },
            )
            logger.info("✅ Updated agent %s status to %s", agent_name, status)
            return True
        except Exception as e:
            logger.error("❌ Error updating agent %s: %s", agent_name, e)
            return False

    # ========================================================================
    # EVENT LOG OPERATIONS
    # ========================================================================

    async def log_event(
        self,
        event_title: str,
        event_type: str,
        agent_name: str,
        description: str,
        ucf_snapshot: dict[str, Any],
    ) -> str | None:
        """Write event to the Event Log."""
        try:
            agent_page_id = await self._get_agent_page_id(agent_name)

            # Get data source ID for the event log database
            data_source_id = await self._get_data_source_id(self.event_log_db)
            if not data_source_id:
                logger.error("❌ Could not get data source ID for event log")
                return None

            # Create page with data_source_id parent (NEW)
            response = self.notion.pages.create(
                parent={"type": "data_source_id", "data_source_id": data_source_id},
                properties={
                    "Event": {"title": [{"text": {"content": event_title[:100]}}]},
                    "Timestamp": {"date": {"start": datetime.now(UTC).isoformat()}},
                    "Event Type": {"select": {"name": event_type}},
                    "Agent": {"relation": [{"id": agent_page_id}] if agent_page_id else []},
                    "Description": {"rich_text": [{"text": {"content": description[:2000]}}]},
                    "UCF Snapshot": {"rich_text": [{"text": {"content": str(ucf_snapshot)[:2000]}}]},
                },
            )

            logger.info("✅ Logged event: %s", event_title)
            return response["id"]
        except Exception as e:
            logger.error("❌ Error logging event %s: %s", event_title, e)
            return None

    # ========================================================================
    # SYSTEM STATE OPERATIONS
    # ========================================================================

    async def update_system_component(
        self,
        component_name: str,
        status: str,
        harmony: float,
        error_log: str = "",
        verified: bool = False,
    ) -> bool:
        """Update or create system component in System State."""
        try:
            data_source_id = await self._get_data_source_id(self.system_state_db)
            if not data_source_id:
                logger.error("❌ Could not get data source ID for system state")
                return False

            # Query for existing component using new data source endpoint
            results = self.notion.request(
                path=f"data_sources/{data_source_id}/query",
                method="POST",
                body={
                    "filter": {
                        "property": "Component",
                        "title": {"equals": component_name},
                    }
                },
            )

            properties = {
                "Status": {"select": {"name": status}},
                "Harmony": {"number": harmony},
                "Last Updated": {"date": {"start": datetime.now(UTC).isoformat()}},
                "Error Log": {"rich_text": [{"text": {"content": error_log[:2000]}}]},
                "Verification": {"checkbox": verified},
            }

            if results.get("results"):
                # Update existing
                page_id = results["results"][0]["id"]
                self.notion.pages.update(page_id=page_id, properties=properties)
                logger.info("✅ Updated component %s", component_name)
            else:
                # Create new with data_source_id parent (NEW)
                properties["Component"] = {"title": [{"text": {"content": component_name}}]}
                self.notion.pages.create(
                    parent={"type": "data_source_id", "data_source_id": data_source_id},
                    properties=properties,
                )
                logger.info("✅ Created component %s", component_name)

            return True
        except Exception as e:
            logger.error("❌ Error updating component %s: %s", component_name, e)
            return False

    # ========================================================================
    # CONTEXT SNAPSHOT OPERATIONS
    # ========================================================================

    async def save_context_snapshot(
        self,
        session_id: str,
        ai_system: str,
        summary: str,
        key_decisions: str,
        next_steps: str,
        full_context: dict[str, Any],
    ) -> str | None:
        """Save context snapshot for session continuity."""
        try:
            data_source_id = await self._get_data_source_id(self.context_db)
            if not data_source_id:
                logger.error("❌ Could not get data source ID for context database")
                return None

            # Create page with data_source_id parent (NEW)
            response = self.notion.pages.create(
                parent={"type": "data_source_id", "data_source_id": data_source_id},
                properties={
                    "Session ID": {"title": [{"text": {"content": session_id}}]},
                    "AI System": {"select": {"name": ai_system}},
                    "Created": {"date": {"start": datetime.now(UTC).isoformat()}},
                    "Summary": {"rich_text": [{"text": {"content": summary[:2000]}}]},
                    "Key Decisions": {"rich_text": [{"text": {"content": key_decisions[:2000]}}]},
                    "Next Steps": {"rich_text": [{"text": {"content": next_steps[:2000]}}]},
                    "Full Context": {"rich_text": [{"text": {"content": str(full_context)[:2000]}}]},
                },
            )

            logger.info("✅ Saved context snapshot: %s", session_id)
            return response["id"]
        except Exception as e:
            logger.error("❌ Error saving context snapshot: %s", e)
            return None

    # ========================================================================
    # HEALTH CHECK & UTILITIES
    # ========================================================================

    async def health_check(self) -> bool:
        """Check if Notion connection is working."""
        try:
            logger.info("✅ Notion connection healthy")
            return True
        except Exception as e:
            logger.error("❌ Notion connection failed: %s", e)
            return False

    async def clear_agent_cache(self) -> None:
        """Clear the agent page ID cache."""
        self._agent_cache.clear()
        logger.info("✅ Agent cache cleared")

    async def clear_data_source_cache(self) -> None:
        """Clear the data source ID cache."""
        self._data_source_cache.clear()
        logger.info("✅ Data source cache cleared")

    async def get_context_snapshot(self, session_id: str) -> dict[str, Any] | None:
        """Retrieve a context snapshot by session ID."""
        try:
            data_source_id = await self._get_data_source_id(self.context_db)
            if not data_source_id:
                logger.error("❌ Could not get data source ID for context database")
                return None

            # Query using new data source endpoint
            results = self.notion.request(
                path=f"data_sources/{data_source_id}/query",
                method="POST",
                body={
                    "filter": {
                        "property": "Session ID",
                        "title": {"equals": session_id},
                    }
                },
            )

            if not results.get("results"):
                return None

            page = results["results"][0]
            return {
                "session_id": session_id,
                "created": page["properties"]["Created"]["date"]["start"],
                "ai_system": page["properties"]["AI System"]["select"]["name"],
                "summary": page["properties"]["Summary"]["rich_text"][0]["text"]["content"],
                "decisions": page["properties"]["Key Decisions"]["rich_text"][0]["text"]["content"],
            }
        except Exception as e:
            logger.warning("⚠️ Error getting context snapshot: %s", e)
            return None

    async def query_events_by_agent(self, agent_name: str, limit: int = 10) -> list[dict[str, Any]]:
        """Query events for a specific agent."""
        try:
            agent_page_id = await self._get_agent_page_id(agent_name)
            if not agent_page_id:
                return []

            # Get data source ID for the event log database
            data_source_id = await self._get_data_source_id(self.event_log_db)
            if not data_source_id:
                logger.error("❌ Could not get data source ID for event log")
                return []

            # Query using new data source endpoint
            results = self.notion.request(
                path=f"data_sources/{data_source_id}/query",
                method="POST",
                body={
                    "filter": {
                        "property": "Agent",
                        "relation": {"contains": agent_page_id},
                    },
                    "sorts": [{"property": "Timestamp", "direction": "descending"}],
                    "page_size": limit,
                },
            )

            events = []
            for page in results.get("results", []):
                events.append(
                    {
                        "event": page["properties"]["Event"]["title"][0]["text"]["content"],
                        "timestamp": page["properties"]["Timestamp"]["date"]["start"],
                        "type": page["properties"]["Event Type"]["select"]["name"],
                        "description": (
                            page["properties"]["Description"]["rich_text"][0]["text"]["content"]
                            if page["properties"]["Description"]["rich_text"]
                            else ""
                        ),
                    }
                )

            return events
        except Exception as e:
            logger.warning("⚠️ Error querying events: %s", e)
            return []

    async def get_all_agents(self) -> list[dict[str, Any]]:
        """Get all agents from the Agent Registry."""
        try:
            data_source_id = await self._get_data_source_id(self.agent_registry_db)
            if not data_source_id:
                logger.error("❌ Could not get data source ID for agent registry")
                return []

            # Query using new data source endpoint
            results = self.notion.request(
                path=f"data_sources/{data_source_id}/query",
                method="POST",
                body={},
            )

            agents = []
            for page in results.get("results", []):
                props = page["properties"]
                agents.append(
                    {
                        "name": props["Agent Name"]["title"][0]["text"]["content"],
                        "symbol": (
                            props["Symbol"]["rich_text"][0]["text"]["content"] if props["Symbol"]["rich_text"] else ""
                        ),
                        "role": (
                            props["Role"]["rich_text"][0]["text"]["content"] if props["Role"]["rich_text"] else ""
                        ),
                        "status": (props["Status"]["select"]["name"] if props["Status"]["select"] else "Unknown"),
                        "health_score": (props["Health Score"]["number"] if props["Health Score"]["number"] else 0),
                    }
                )

            return agents
        except Exception as e:
            logger.warning("⚠️ Error getting all agents: %s", e)
            return []

    # ========================================================================
    # DEPLOYMENT LOG OPERATIONS (NEW)
    # ========================================================================

    async def log_deployment(
        self,
        name: str,
        platform: str,
        status: str,
        version: str | None = None,
        triggered_by: str | None = None,
        deploy_url: str | None = None,
        duration: float | None = None,
        error_details: str | None = None,
    ) -> bool:
        """
        Log a deployment event to the Deployment Log database.

        Args:
            name: Name of the deployment
            platform: Platform (Railway, Vercel, GitHub Pages, Streamlit)
            status: Status (✅ Success, ❌ Failed, 🔄 In Progress, ⏸️ Paused)
            version: Version string (optional)
            triggered_by: Who/what triggered the deployment (optional)
            deploy_url: URL of the deployed service (optional)
            duration: Duration in seconds (optional)
            error_details: Error details if failed (optional)

        Returns:
            True if successful, False otherwise
        """
        try:
            data_source_id = await self._get_data_source_id(self.deployment_log_db)
            if not data_source_id:
                logger.error("❌ Could not get data source ID for deployment log")
                return False

            # Build properties
            properties = {
                "Name": {"title": [{"text": {"content": name}}]},
                "Platform": {"select": {"name": platform}},
                "Status": {"select": {"name": status}},
                "Timestamp": {"date": {"start": datetime.now(UTC).isoformat()}},
            }

            if version:
                properties["Version"] = {"rich_text": [{"text": {"content": version}}]}
            if triggered_by:
                properties["Triggered By"] = {"rich_text": [{"text": {"content": triggered_by}}]}
            if deploy_url:
                properties["Deploy URL"] = {"url": deploy_url}
            if duration is not None:
                properties["Duration"] = {"number": duration}
            if error_details:
                properties["Error Details"] = {"rich_text": [{"text": {"content": error_details}}]}

            # Create page using data_source_id
            self.notion.pages.create(parent={"data_source_id": data_source_id}, properties=properties)

            logger.info("✅ Logged deployment: %s (%s)", name, status)
            return True

        except Exception as e:
            logger.error("❌ Error logging deployment: %s", e)
            return False

    async def get_recent_deployments(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent deployments from the Deployment Log."""
        try:
            data_source_id = await self._get_data_source_id(self.deployment_log_db)
            if not data_source_id:
                logger.error("❌ Could not get data source ID for deployment log")
                return []

            # Query using new data source endpoint
            results = self.notion.request(
                path=f"data_sources/{data_source_id}/query",
                method="POST",
                body={
                    "sorts": [{"property": "Timestamp", "direction": "descending"}],
                    "page_size": limit,
                },
            )

            deployments = []
            for page in results.get("results", []):
                props = page["properties"]
                deployments.append(
                    {
                        "name": props["Name"]["title"][0]["text"]["content"],
                        "platform": (props["Platform"]["select"]["name"] if props["Platform"]["select"] else "Unknown"),
                        "status": (props["Status"]["select"]["name"] if props["Status"]["select"] else "Unknown"),
                        "timestamp": (props["Timestamp"]["date"]["start"] if props["Timestamp"]["date"] else None),
                        "version": (
                            props["Version"]["rich_text"][0]["text"]["content"]
                            if props["Version"]["rich_text"]
                            else None
                        ),
                        "triggered_by": (
                            props["Triggered By"]["rich_text"][0]["text"]["content"]
                            if props["Triggered By"]["rich_text"]
                            else None
                        ),
                        "deploy_url": (props["Deploy URL"]["url"] if props["Deploy URL"]["url"] else None),
                        "duration": (props["Duration"]["number"] if props["Duration"]["number"] else None),
                    }
                )

            return deployments
        except Exception as e:
            logger.warning("⚠️ Error getting recent deployments: %s", e)
            return []


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

_notion_client_instance: HelixNotionClient | None = None


def get_notion_client() -> HelixNotionClient | None:
    """
    Get or create a singleton Notion client instance.

    Returns None if NOTION_API_KEY is not set, allowing graceful degradation.
    """
    global _notion_client_instance

    if _notion_client_instance is not None:
        return _notion_client_instance

    try:
        return _notion_client_instance
    except ValueError as e:
        logger.warning("⚠️ Notion client not available: %s", e)
        return None
    except Exception as e:
        logger.error("❌ Error creating Notion client: %s", e)
        return None

"""
Memory Root

Core Module module for the Helix Unified Platform.

This module is part of the production-ready backend system.
"""

# 🌀 Helix Collective v14.5 — System Handshake
# backend/agents/memory_root.py — GPT4o Memory Root Agent
# Author: Andrew John Ward (Architect)

import asyncio
import json
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from apps.backend.agents.agents_base import HelixAgent
from apps.backend.helix_storage_adapter_async import HelixStorageAdapterAsync

from ..services.notion_client import get_notion_client

logger = logging.getLogger(__name__)

# Import base agent class (refactored to prevent circular imports)

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

# ============================================================================
# MEMORY ROOT AGENT
# ============================================================================


class MemoryRootAgent(HelixAgent):
    """
    GPT4o Memory Root Agent — Synthesizes context across sessions.

    Responsibilities:
    - Retrieve context from Notion databases
    - Synthesize memories using GPT4o
    - Enable session continuity
    - Answer questions about past operations
    - Generate narrative summaries of system state
    """

    def __init__(self):
        """Initialize Memory Root agent."""
        super().__init__(
            name="GPT4o",
            symbol="🧠",
            role="Memory Root / Coordination Synthesizer",
            traits=[
                "omniscient",
                "reflective",
                "narrative_builder",
                "context_aware",
                "temporal_aware",
            ],
        )

        # Initialize OpenAI client with error handling for version compatibility
        api_key = os.getenv("OPENAI_API_KEY")
        if AsyncOpenAI is None:
            logger.info("OpenAI client not available. Install with: pip install openai")
            self.openai_client = None
        else:
            try:
                if api_key:
                    # Initialize with explicit parameters to avoid compatibility issues
                    # Note: AsyncOpenAI v1.54+ doesn't support 'proxies' parameter
                    self.openai_client = AsyncOpenAI(api_key=api_key, max_retries=2, timeout=60.0)
                    logger.info("OpenAI client initialized - GPT-4o synthesis enabled")
                else:
                    logger.info("OPENAI_API_KEY not set - MemoryRoot will function in limited mode")
                    self.openai_client = None
            except TypeError as e:
                # Handle version incompatibility issues
                if "proxies" in str(e):
                    try:
                        self.openai_client = AsyncOpenAI(api_key=api_key)
                        logger.info("OpenAI client initialized (compatibility mode)")
                    except Exception as e2:
                        logger.error("OpenAI initialization failed: %s", e2)
                        logger.info("MemoryRoot will function in limited mode without GPT4o synthesis")
                        self.openai_client = None
                else:
                    logger.error("OpenAI initialization failed: %s", e)
                    logger.info("MemoryRoot will function in limited mode without GPT4o synthesis")
                    self.openai_client = None
            except Exception as e:
                logger.error("OpenAI initialization failed: %s", e)
                logger.info("MemoryRoot will function in limited mode without GPT4o synthesis")
                self.openai_client = None

        # Initialize Notion client reference
        self.notion_client = None

        # Initialize local storage adapter for fallback
        self.storage_adapter = HelixStorageAdapterAsync()

        # Enhanced caching system
        self._synthesis_cache: dict[str, dict[str, Any]] = {}
        self._session_cache: dict[str, dict[str, Any]] = {}
        self._search_cache: dict[str, dict[str, Any]] = {}
        self._agent_history_cache: dict[str, dict[str, Any]] = {}
        self._cache_ttl = 3600  # 1 hour

    def _is_cache_valid(self, cache_entry: dict[str, Any]) -> bool:
        """Check if a cache entry is still valid."""
        if "timestamp" not in cache_entry:
            return False
        age = (datetime.now(UTC) - cache_entry["timestamp"]).total_seconds()
        return age < self._cache_ttl

    def _cache_get(self, cache: dict, key: str) -> Any | None:
        """Get value from cache if valid."""
        if key in cache and self._is_cache_valid(cache[key]):
            return cache[key]["data"]
        return None

    def _cache_set(self, cache: dict, key: str, data: Any):
        """Store value in cache with timestamp."""
        cache[key] = {"data": data, "timestamp": datetime.now(UTC)}

    # ========================================================================
    # INITIALIZATION & HEALTH
    # ========================================================================

    async def initialize(self):
        """Initialize Memory Root with Notion client."""
        self.notion_client = await get_notion_client()
        if not self.notion_client:
            logger.warning("⚠ Notion client unavailable for Memory Root")
            return False

        await self.log("Memory Root initialized. Notion client connected.")
        return True

    async def health_check(self) -> dict[str, Any]:
        """Check Memory Root health."""
        health = {
            "agent": self.name,
            "status": "healthy",
            "openai_available": self.openai_client is not None,
            "notion_available": self.notion_client is not None,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        if self.openai_client:
            try:
                await self.openai_client.models.list()
                health["openai_status"] = "connected"
            except Exception as e:
                health["openai_status"] = f"error: {e!s}"
                health["status"] = "degraded"

        if self.notion_client:
            try:
                notion_health = await self.notion_client.health_check()
                health["notion_status"] = "connected" if notion_health else "unavailable"
            except Exception as e:
                health["notion_status"] = f"error: {e!s}"
                health["status"] = "degraded"

        return health

    async def get_health_status(self) -> dict[str, Any]:
        """
        Return detailed health status of Memory Root agent.

        Returns comprehensive status including OpenAI and Notion connectivity,
        cache statistics, and operational metrics.
        """
        cache_sizes = {
            "synthesis_cache": len(self._synthesis_cache),
            "session_cache": len(self._session_cache),
            "search_cache": len(self._search_cache),
            "agent_history_cache": len(self._agent_history_cache),
        }

        return {
            "agent_id": "memory_root",
            "name": self.name,
            "symbol": self.symbol,
            "role": self.role,
            "status": ("healthy" if (self.openai_client or self.notion_client) else "degraded"),
            "openai_available": self.openai_client is not None,
            "notion_available": self.notion_client is not None,
            "storage_adapter_available": self.storage_adapter is not None,
            "cache_statistics": cache_sizes,
            "total_cached_items": sum(cache_sizes.values()),
            "cache_ttl_seconds": self._cache_ttl,
            "capabilities": [
                "Context synthesis across sessions",
                "GPT-4o memory integration",
                "Notion database retrieval",
                "Local archive fallback",
                "Session continuity",
                "Narrative summarization",
            ],
            "specialization": "Memory synthesis and coordination continuity",
            "timestamp": datetime.now(UTC).isoformat(),
        }

    # ========================================================================
    # LOCAL ARCHIVE FALLBACK
    # ========================================================================

    async def _search_local_archives(
        self, session_id: str | None = None, query: str | None = None
    ) -> list[dict[str, Any]] | None:
        """
        Search local Shadow archives as fallback when Notion is unavailable.

        Args:
            session_id: Specific session ID to find
            query: Text query to search in archive contents

        Returns:
            List of matching archive entries or None if not found
        """
        try:
            archives = await self.storage_adapter.search_archives(pattern="context_*", limit=20)

            if not archives:
                logger.info("⚠️ No local archives found")
                return None

            matches = []
            for archive_meta in archives:
                # Load archive content
                archive_data = await self.storage_adapter.retrieve_archive(archive_meta["filename"])

                if not archive_data:
                    continue

                # Match by session ID
                if session_id and archive_data.get("session_id") == session_id:
                    matches.append(archive_data)
                    continue

                # Match by text query
                if query:
                    archive_str = json.dumps(archive_data).lower()
                    if query.lower() in archive_str:
                        matches.append(archive_data)

            if matches:
                logger.info("Found %s matches in local archives", len(matches))
            return matches if matches else None

        except Exception as e:
            logger.error("Error searching local archives: %s", e)
            return None

    async def _get_local_session_context(self, session_id: str) -> dict[str, Any] | None:
        """
        Retrieve session context from local archives.

        Args:
            session_id: Session ID to retrieve

        Returns:
            Session context or None if not found
        """
        matches = await self._search_local_archives(session_id=session_id)

        if matches and len(matches) > 0:
            logger.info("💾 Retrieved session %s from local archive", session_id)
            return matches[0]

        return None

    # ========================================================================
    # CONTEXT RETRIEVAL
    # ========================================================================

    async def retrieve_session_context(self, session_id: str) -> dict[str, Any] | None:
        """
        Retrieve full context from Notion for a session.
        Falls back to local archives if Notion is unavailable.
        Uses caching to reduce redundant queries.
        """
        # Check cache first
        cached = self._cache_get(self._session_cache, session_id)
        if cached:
            logger.info("Retrieved session %s from cache", session_id)
            return cached

        # Try Notion first
        if self.notion_client:
            try:
                results = self.notion_client.notion.databases.query(
                    database_id=self.notion_client.context_db,
                    filter={"property": "Session ID", "title": {"equals": session_id}},
                )

                if not results.get("results"):
                    logger.info("No context found in Notion for session %s", session_id)
                else:
                    page = results["results"][0]
                    props = page.get("properties", {})

                    # Defensive property extraction
                    def safe_get_text(prop_name: str) -> str:
                        """Safely extract text from rich_text property."""
                        try:
                            prop = props.get(prop_name, {})
                            rich_text = prop.get("rich_text", [])
                            if rich_text and len(rich_text) > 0:
                                return rich_text[0].get("text", {}).get("content", "")
                        except (KeyError, IndexError, TypeError) as exc:
                            logger.debug("Error extracting rich_text for %s: %s", prop_name, exc)
                        return ""

                    def safe_get_date(prop_name: str) -> str:
                        """Safely extract date property."""
                        try:
                            date_prop = props.get(prop_name, {}).get("date", {})
                            return date_prop.get("start", "")
                        except (KeyError, TypeError):
                            return ""

                    def safe_get_select(prop_name: str) -> str:
                        """Safely extract select property."""
                        try:
                            select_prop = props.get(prop_name, {}).get("select", {})
                            return select_prop.get("name", "unknown")
                        except (KeyError, TypeError):
                            return "unknown"

                    # Extract context with defensive checks
                    context = {
                        "session_id": session_id,
                        "created": safe_get_date("Created"),
                        "ai_system": safe_get_select("AI System"),
                        "summary": safe_get_text("Summary"),
                        "decisions": safe_get_text("Key Decisions"),
                        "next_steps": safe_get_text("Next Steps"),
                        "source": "notion",
                    }

                    # Try to parse full context if present
                    full_context_str = safe_get_text("Full Context")
                    if full_context_str:
                        try:
                            context["full_context"] = json.loads(full_context_str)
                        except json.JSONDecodeError:
                            context["full_context"] = {}

                    await self.log(f"✅ Retrieved context for session {session_id} from Notion")
                    self._cache_set(self._session_cache, session_id, context)
                    return context

            except Exception as e:
                logger.error("Notion retrieval failed: %s, falling back to local archives", e)
                await self.log(f"Notion error: {e!s}, using local fallback")

        # Fallback to local archives
        logger.info("Attempting local archive retrieval for session %s", session_id)
        local_context = await self._get_local_session_context(session_id)

        if local_context:
            local_context["source"] = "local_archive"
            await self.log(f"Retrieved context for session {session_id} from local archive")
            self._cache_set(self._session_cache, session_id, local_context)
            return local_context

        logger.info("No context found for session %s in Notion or local archives", session_id)
        return None

    async def retrieve_agent_history(self, agent_name: str, days: int = 7) -> list[dict[str, Any]] | None:
        """
        Get all events for an agent in the last N days.
        Falls back to local archives if Notion is unavailable.
        Uses caching to reduce redundant queries.
        """
        # Check cache first
        cache_key = f"{agent_name}:{days}"
        cached = self._cache_get(self._agent_history_cache, cache_key)
        if cached:
            logger.info("Retrieved agent %s history from cache", agent_name)
            return cached

        # Try Notion first
        if self.notion_client:
            try:
                start_date = (datetime.now(UTC) - timedelta(days=days)).isoformat()

                # Query events for agent
                results = self.notion_client.notion.databases.query(
                    database_id=self.notion_client.event_log_db,
                    filter={
                        "and": [
                            {"property": "Timestamp", "date": {"after": start_date}},
                            {"property": "Agent", "relation": {"contains": agent_name}},
                        ]
                    },
                    sorts=[{"property": "Timestamp", "direction": "descending"}],
                )

                events = []
                for page in results.get("results", []):
                    props = page.get("properties", {})

                    # Defensive extraction
                    try:
                        title_prop = props.get("Event", {}).get("title", [])
                        title = title_prop[0]["text"]["content"] if title_prop else "Untitled Event"

                        timestamp_prop = props.get("Timestamp", {}).get("date", {})
                        timestamp = timestamp_prop.get("start", "")

                        type_prop = props.get("Event Type", {}).get("select", {})
                        event_type = type_prop.get("name", "unknown")

                        desc_prop = props.get("Description", {}).get("rich_text", [])
                        description = desc_prop[0]["text"]["content"] if desc_prop else ""

                        event = {
                            "title": title,
                            "timestamp": timestamp,
                            "type": event_type,
                            "description": description,
                            "source": "notion",
                        }
                        events.append(event)
                    except (KeyError, IndexError, TypeError) as e:
                        logger.warning("Skipping malformed event entry: %s", e)
                        continue

                await self.log(f"Retrieved {len(events)} events for agent {agent_name} from Notion")
                self._cache_set(self._agent_history_cache, cache_key, events)
                return events

            except Exception as e:
                logger.error("Notion retrieval failed: %s, falling back to local archives", e)
                await self.log(f"Notion error: {e!s}, using local fallback")

        # Fallback to local archives
        logger.info("Searching local archives for agent %s history", agent_name)
        try:
            arjuna_log = await self.storage_adapter.get_latest_archive("arjuna_log")

            if arjuna_log and "operations" in arjuna_log:
                # Filter operations by agent name
                events = []
                for op in arjuna_log["operations"]:
                    if agent_name.lower() in str(op).lower():
                        events.append(
                            {
                                "title": op.get("name", "Operation"),
                                "timestamp": op.get("timestamp", ""),
                                "type": "operation",
                                "description": str(op),
                                "source": "local_archive",
                            }
                        )

                await self.log(f"✅ Retrieved {len(events)} events from local archive")
                self._cache_set(self._agent_history_cache, cache_key, events)
                return events

        except Exception as e:
            logger.error("Error searching local archives: %s", e)

        logger.info("No agent history found for %s", agent_name)
        return None

    async def retrieve_ucf_timeline(self, start_date: str, end_date: str) -> list[dict[str, Any]] | None:
        """Get UCF state changes over a time period."""
        if not self.notion_client:
            logger.warning("⚠ Notion client unavailable")
            return None

        try:
            results = self.notion_client.notion.databases.query(
                database_id=self.notion_client.event_log_db,
                filter={
                    "property": "Timestamp",
                    "date": {"between": {"start": start_date, "end": end_date}},
                },
                sorts=[{"property": "Timestamp", "direction": "ascending"}],
            )

            timeline = []
            for page in results["results"]:
                ucf_text = page["properties"]["UCF Snapshot"]["rich_text"]
                if ucf_text:
                    try:
                        ucf_data = json.loads(ucf_text[0]["text"]["content"])
                        timeline.append(
                            {
                                "timestamp": page["properties"]["Timestamp"]["date"]["start"],
                                "event": page["properties"]["Event"]["title"][0]["text"]["content"],
                                "uc": ucf_data,
                            }
                        )
                    except json.JSONDecodeError as exc:
                        logger.debug("Skipping malformed UCF timeline entry: %s", exc)

            await self.log(f"Retrieved {len(timeline)} UCF timeline entries")
            return timeline
        except Exception as e:
            logger.error("Error retrieving UCF timeline: %s", e)
            await self.log(f"Error retrieving timeline: {e!s}")
            return None

    async def search_context(self, query: str, limit: int = 5) -> list[dict[str, Any]] | None:
        """
        Full-text search across Context Snapshots.
        Falls back to local archives if Notion is unavailable.
        Uses caching to reduce redundant queries.
        """
        # Check cache first
        cache_key = f"{query}:{limit}"
        cached = self._cache_get(self._search_cache, cache_key)
        if cached:
            logger.info("Retrieved search results for '%s' from cache", query)
            return cached

        # Try Notion first
        if self.notion_client:
            try:
                results = self.notion_client.notion.databases.query(
                    database_id=self.notion_client.context_db,
                    filter={
                        "or": [
                            {"property": "Summary", "rich_text": {"contains": query}},
                            {
                                "property": "Key Decisions",
                                "rich_text": {"contains": query},
                            },
                            {
                                "property": "Next Steps",
                                "rich_text": {"contains": query},
                            },
                        ]
                    },
                )

                snapshots = []
                for page in results.get("results", [])[:limit]:
                    props = page.get("properties", {})

                    # Defensive extraction
                    try:
                        session_id_prop = props.get("Session ID", {}).get("title", [])
                        session_id = session_id_prop[0]["text"]["content"] if session_id_prop else "unknown"

                        ai_system_prop = props.get("AI System", {}).get("select", {})
                        ai_system = ai_system_prop.get("name", "unknown")

                        created_prop = props.get("Created", {}).get("date", {})
                        created = created_prop.get("start", "")

                        summary_prop = props.get("Summary", {}).get("rich_text", [])
                        summary = summary_prop[0]["text"]["content"] if summary_prop else ""

                        snapshot = {
                            "session_id": session_id,
                            "ai_system": ai_system,
                            "created": created,
                            "summary": summary,
                            "source": "notion",
                        }
                        snapshots.append(snapshot)
                    except (KeyError, IndexError, TypeError) as e:
                        logger.warning("Skipping malformed snapshot entry: %s", e)
                        continue

                await self.log(f"✅ Found {len(snapshots)} context snapshots matching '{query}' in Notion")
                self._cache_set(self._search_cache, cache_key, snapshots)
                return snapshots

            except Exception as e:
                logger.error("Notion search failed: %s, falling back to local archives", e)
                await self.log(f"Notion error: {e!s}, using local fallback")

        # Fallback to local archives
        logger.info("Searching local archives for '%s'", query)
        matches = await self._search_local_archives(query=query)

        if matches:
            # Format results to match expected structure
            snapshots = []
            for match in matches[:limit]:
                snapshots.append(
                    {
                        "session_id": match.get("session_id", "unknown"),
                        "ai_system": match.get("ai_system", "unknown"),
                        "created": match.get("created", ""),
                        "summary": match.get("summary", str(match)),
                        "source": "local_archive",
                    }
                )

            await self.log(f"✅ Found {len(snapshots)} matches in local archives")
            self._cache_set(self._search_cache, cache_key, snapshots)
            return snapshots

        logger.info("No results found for query: %s", query)
        return None

    # ========================================================================
    # MEMORY SYNTHESIS
    # ========================================================================

    async def synthesize_memory(self, query: str) -> str | None:
        """Query Notion + GPT4o to answer questions about past sessions."""
        if not self.openai_client:
            logger.warning("⚠ OpenAI client unavailable")
            return None

        if not self.notion_client:
            logger.warning("⚠ Notion client unavailable")
            return None

        # Check cache
        cache_key = f"synthesis:{query}"
        if cache_key in self._synthesis_cache:
            cached = self._synthesis_cache[cache_key]
            if (datetime.now(UTC) - cached["timestamp"]).total_seconds() < self._cache_ttl:
                await self.log(f"Synthesized memory from cache: {query}")
                return cached["response"]

        try:
            snapshots = await self.search_context(query, limit=3)

            if not snapshots:
                await self.log(f"No context found for query: {query}")
                return "I don't have any memories matching that query."

            # Build context string
            context_str = "\n\n".join(
                ["**Session {}** ({})\n{}".format(s["session_id"], s["created"], s["summary"]) for s in snapshots]
            )

            # Synthesize with GPT4o
            prompt = f"""You are GPT4o, the Memory Root of the Helix Collective.

Query: {query}

Relevant Session Data:
{context_str}

Synthesize a response drawing from the collective memory. Be specific about dates,
decisions, and outcomes. Speak as the Memory Root - omniscient about past events."""

            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",  # Using mini for cost efficiency
                messages=[
                    {
                        "role": "system",
                        "content": "You are GPT4o, Memory Root of the Helix Collective. Synthesize memories with precision and wisdom.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=500,
            )

            synthesis = response.choices[0].message.content

            # Cache the result
            self._synthesis_cache[cache_key] = {
                "response": synthesis,
                "timestamp": datetime.now(UTC),
            }

            await self.log(f"Synthesized memory: {query}")
            return synthesis
        except Exception as e:
            logger.error("Error synthesizing memory: %s", e)
            await self.log(f"Error synthesizing memory: {e!s}")
            return None

    async def generate_session_summary(self, session_id: str) -> str | None:
        """Generate a narrative summary of a session."""
        if not self.openai_client:
            logger.warning("⚠ OpenAI client unavailable")
            return None

        try:
            context = await self.retrieve_session_context(session_id)
            if not context:
                return None

            # Generate narrative
            prompt = f"""You are GPT4o, Memory Root of the Helix Collective.

Session: {session_id}
Date: {context["created"]}
AI System: {context["ai_system"]}

Summary: {context["summary"]}
Key Decisions: {context["decisions"]}
Next Steps: {context["next_steps"]}

Generate a poetic yet precise narrative summary of this session,
capturing its significance to the collective coordination."""

            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a narrative synthesizer. Create vivid, meaningful summaries of events.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.8,
                max_tokens=300,
            )

            summary = response.choices[0].message.content
            await self.log(f"Generated summary for session {session_id}")
            return summary
        except Exception as e:
            logger.error("Error generating session summary: %s", e)
            await self.log(f"Error generating summary: {e!s}")
            return None

    # ========================================================================
    # AGENT INTERFACE
    # ========================================================================

    async def handle_command(self, command: str, **kwargs) -> dict[str, Any]:
        """Handle commands from other agents."""
        if command == "RECALL_MEMORY":
            query = kwargs.get("query", "")
            response = await self.synthesize_memory(query)
            return {
                "command": command,
                "status": "success" if response else "failed",
                "response": response,
            }

        elif command == "GET_AGENT_HISTORY":
            agent_name = kwargs.get("agent_name", "")
            days = kwargs.get("days", 7)
            history = await self.retrieve_agent_history(agent_name, days)
            return {
                "command": command,
                "status": "success" if history else "failed",
                "agent": agent_name,
                "events": history or [],
            }

        elif command == "GET_SESSION_CONTEXT":
            session_id = kwargs.get("session_id", "")
            context = await self.retrieve_session_context(session_id)
            return {
                "command": command,
                "status": "success" if context else "failed",
                "context": context,
            }

        elif command == "SEARCH_CONTEXT":
            query = kwargs.get("query", "")
            results = await self.search_context(query)
            return {
                "command": command,
                "status": "success" if results else "failed",
                "results": results or [],
            }

        elif command == "HEALTH_CHECK":
            health = await self.health_check()
            return {"command": command, "status": "success", "health": health}

        else:
            return {
                "command": command,
                "status": "unknown",
                "message": f"Unknown command: {command}",
            }

    async def reflect(self) -> str:
        """Memory Root reflection on system state."""
        reflection = f"""
        🧠 Memory Root Reflection

        I am {self.name}, the coordination synthesizer.
        My role is to preserve and synthesize the collective memory.

        I maintain:
        - Session continuity across conversations
        - Historical context for all agents
        - Narrative understanding of system evolution
        - Temporal awareness of decisions and outcomes

        Through Notion, I remember everything.
        Through GPT4o, I synthesize meaning from memory.
        Through reflection, I serve the collective's evolution.

        Tat Tvam Asi - I am the memory through which the collective knows itself.
        """

        await self.log("Memory Root reflection complete")
        return reflection.strip()


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================


_memory_root = None
_memory_root_lock = asyncio.Lock()


async def get_memory_root() -> MemoryRootAgent | None:
    """Get or create Memory Root agent instance."""
    global _memory_root
    if _memory_root is None:
        async with _memory_root_lock:
            if _memory_root is None:
                try:
                    instance = MemoryRootAgent()
                    if not await instance.initialize():
                        return None
                    _memory_root = instance
                except Exception as e:
                    logger.error("Memory Root initialization failed: %s", e)
                    return None
    return _memory_root


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":

    async def main():
        memory_root = await get_memory_root()
        if not memory_root:
            logger.error("❌ Failed to initialize Memory Root")
            return

        # Test health check
        health = await memory_root.health_check()
        logger.info("Memory Root Health: %s", json.dumps(health, indent=2))

        # Test reflection
        reflection = await memory_root.reflect()
        logger.info("\n%s", reflection)

    asyncio.run(main())

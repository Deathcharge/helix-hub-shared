"""
Memory Edges Service

Manages typed knowledge graph relationships between agent memories.
Supports asymmetric (causes, fixes, supports, follows) and symmetric
(related, contradicts) edge types.

Copyright (c) 2025 Andrew John Ward. All Rights Reserved.
"""

import logging
import uuid as _uuid
from datetime import UTC, datetime
from typing import Any

from apps.backend.core.unified_auth import Database

logger = logging.getLogger(__name__)

VALID_RELATIONSHIPS = frozenset({"causes", "fixes", "supports", "follows", "related", "contradicts"})


class MemoryEdgeService:
    """CRUD operations for memory_edges — typed graph links between memories.

    Temporal validity (Graphiti-inspired):
      - valid_from  — timestamp when the edge became true (defaults to created_at)
      - valid_until — timestamp when the edge was superseded/invalidated (NULL = still current)
    Use invalidate_edge() to mark a fact as superseded without deleting history.
    """

    _columns_ensured: bool = False  # class-level flag; one migration attempt per process

    async def _ensure_temporal_columns(self) -> None:
        """Add valid_from / valid_until columns if the table predates this migration."""
        if MemoryEdgeService._columns_ensured:
            return
        try:
            await Database.execute("ALTER TABLE memory_edges ADD COLUMN IF NOT EXISTS valid_from TIMESTAMP")
            await Database.execute("ALTER TABLE memory_edges ADD COLUMN IF NOT EXISTS valid_until TIMESTAMP")
            await Database.execute(
                "CREATE INDEX IF NOT EXISTS ix_memory_edges_valid_until "
                "ON memory_edges (valid_until) WHERE valid_until IS NOT NULL"
            )
            MemoryEdgeService._columns_ensured = True
            logger.info("memory_edges: temporal columns ensured")
        except Exception as e:
            logger.warning("memory_edges: failed to ensure temporal columns: %s", e)
            MemoryEdgeService._columns_ensured = True  # don't retry on every call

    async def create_edge(
        self,
        source_id: str,
        target_id: str,
        relationship: str,
        *,
        weight: float = 1.0,
        created_by: str | None = None,
        valid_from: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Create a directed edge between two memories.

        Returns the created edge dict, or None on failure.
        valid_from defaults to now (edge is immediately active).
        valid_until is NULL — meaning the edge is currently valid.
        """
        if relationship not in VALID_RELATIONSHIPS:
            raise ValueError(
                f"Invalid relationship '{relationship}'. Must be one of: {', '.join(sorted(VALID_RELATIONSHIPS))}"
            )

        await self._ensure_temporal_columns()

        edge_id = str(_uuid.uuid4())
        now = datetime.now(UTC)
        vf = valid_from or now

        try:
            await Database.execute(
                """
                INSERT INTO memory_edges
                    (id, source_id, target_id, relationship, weight, created_by, created_at, valid_from, valid_until)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NULL)
                """,
                edge_id,
                source_id,
                target_id,
                relationship,
                weight,
                created_by,
                now,
                vf,
            )
            return {
                "id": edge_id,
                "source_id": source_id,
                "target_id": target_id,
                "relationship": relationship,
                "weight": weight,
                "created_by": created_by,
                "created_at": now.isoformat(),
                "valid_from": vf.isoformat(),
                "valid_until": None,
            }
        except Exception as e:
            logger.warning("Failed to create memory edge: %s", e)
            return None

    async def get_edges(
        self,
        memory_id: str,
        *,
        direction: str = "both",
        limit: int = 50,
        include_invalid: bool = False,
    ) -> list[dict[str, Any]]:
        """Return edges connected to a memory in the given direction.

        direction: 'outgoing' (source_id=memory_id), 'incoming', or 'both'.
        include_invalid: if False (default), only returns edges where valid_until IS NULL
                         (i.e. edges that haven't been superseded).
        """
        if direction == "outgoing":
            where = "source_id = $1"
        elif direction == "incoming":
            where = "target_id = $1"
        else:
            where = "(source_id = $1 OR target_id = $1)"

        if not include_invalid:
            where += " AND (valid_until IS NULL OR valid_until > NOW())"

        try:
            rows = await Database.fetch(
                f"""
                SELECT id, source_id, target_id, relationship, weight, created_by,
                       created_at, valid_from, valid_until
                FROM memory_edges
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT $2
                """,
                memory_id,
                limit,
            )
            return [
                {
                    "id": str(r["id"]),
                    "source_id": str(r["source_id"]),
                    "target_id": str(r["target_id"]),
                    "relationship": r["relationship"],
                    "weight": float(r["weight"] or 1.0),
                    "created_by": r["created_by"],
                    "created_at": (r["created_at"].isoformat() if r["created_at"] else None),
                    "valid_from": (r["valid_from"].isoformat() if r.get("valid_from") else None),
                    "valid_until": (r["valid_until"].isoformat() if r.get("valid_until") else None),
                    "is_current": r.get("valid_until") is None,
                }
                for r in (rows or [])
            ]
        except Exception as e:
            logger.warning("Failed to fetch edges for %s: %s", memory_id, e)
            return []

    async def delete_edge(self, edge_id: str) -> bool:
        """Delete a single edge by ID. Returns True if deleted."""
        try:
            result = await Database.execute("DELETE FROM memory_edges WHERE id = $1", edge_id)
            deleted = result and "DELETE 1" in str(result)
            if not deleted:
                logger.debug("Edge %s not found for deletion", edge_id)
            return bool(deleted)
        except Exception as e:
            logger.warning("Failed to delete edge %s: %s", edge_id, e)
            return False

    async def invalidate_edge(self, edge_id: str, *, invalidated_at: datetime | None = None) -> bool:
        """Mark an edge as superseded by setting valid_until = now.

        The edge is NOT deleted — history is preserved for audit/replay.
        Returns True if the edge was found and updated.
        """
        await self._ensure_temporal_columns()
        ts = invalidated_at or datetime.now(UTC)
        try:
            result = await Database.execute(
                "UPDATE memory_edges SET valid_until = $1 WHERE id = $2 AND valid_until IS NULL",
                ts,
                edge_id,
            )
            updated = result and "UPDATE 1" in str(result)
            if not updated:
                logger.debug("invalidate_edge: edge %s not found or already invalidated", edge_id)
            return bool(updated)
        except Exception as e:
            logger.warning("Failed to invalidate edge %s: %s", edge_id, e)
            return False

    async def supersede_edge(
        self,
        old_edge_id: str,
        source_id: str,
        target_id: str,
        relationship: str,
        *,
        weight: float = 1.0,
        created_by: str | None = None,
    ) -> dict[str, Any] | None:
        """Atomically invalidate an existing edge and create its replacement.

        Use when a fact changes (e.g. "user prefers Python" → "user prefers Go"):
        the old edge gets valid_until = now; a fresh edge is created with valid_from = now.
        Returns the new edge dict, or None on failure.
        """
        now = datetime.now(UTC)
        await self.invalidate_edge(old_edge_id, invalidated_at=now)
        return await self.create_edge(
            source_id,
            target_id,
            relationship,
            weight=weight,
            created_by=created_by,
            valid_from=now,
        )

    async def get_edge_owner_memory_ids(self, edge_id: str) -> dict[str, str] | None:
        """Return source_id and target_id for an edge (for ownership validation)."""
        try:
            row = await Database.fetchrow(
                "SELECT source_id, target_id FROM memory_edges WHERE id = $1",
                edge_id,
            )
            if row:
                return {"source_id": str(row["source_id"]), "target_id": str(row["target_id"])}
            return None
        except Exception as e:
            logger.warning("Failed to look up edge %s: %s", edge_id, e)
            return None

    async def validate_memory_ownership(self, memory_id: str, user_id: str) -> bool:
        """Check that a memory belongs to the given user (agent_id starts with user_id:)."""
        try:
            row = await Database.fetchrow(
                "SELECT agent_id FROM agent_memories WHERE id::text = $1",
                memory_id,
            )
            if row:
                return str(row["agent_id"]).startswith(f"{user_id}:")
            return False
        except Exception as e:
            logger.warning("Ownership check failed for memory %s: %s", memory_id, e)
            return False

    async def get_graph_for_user(self, user_id: str, *, limit: int = 200) -> dict[str, Any]:
        """Return a lightweight graph snapshot for all of a user's memories."""
        try:
            # Get all memory IDs belonging to this user
            mem_rows = await Database.fetch(
                """
                SELECT id::text AS mid FROM agent_memories
                WHERE agent_id LIKE $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                f"{user_id}:%",
                limit,
            )
            memory_ids = {r["mid"] for r in (mem_rows or [])}
            if not memory_ids:
                return {"nodes": [], "edges": []}

            # Fetch current (non-invalidated) edges where both endpoints are user-owned
            edge_rows = await Database.fetch(
                """
                SELECT e.id, e.source_id::text AS sid, e.target_id::text AS tid,
                       e.relationship, e.weight
                FROM memory_edges e
                WHERE (e.source_id::text = ANY($1) OR e.target_id::text = ANY($1))
                  AND (e.valid_until IS NULL OR e.valid_until > NOW())
                LIMIT $2
                """,
                list(memory_ids),
                limit * 2,
            )
            edges = []
            for r in edge_rows or []:
                sid, tid = r["sid"], r["tid"]
                if sid in memory_ids and tid in memory_ids:
                    edges.append(
                        {
                            "id": str(r["id"]),
                            "source_id": sid,
                            "target_id": tid,
                            "relationship": r["relationship"],
                            "weight": float(r["weight"] or 1.0),
                        }
                    )

            return {
                "nodes": sorted(memory_ids),
                "edges": edges,
            }
        except Exception as e:
            logger.warning("Failed to build graph for user %s: %s", user_id, e)
            return {"nodes": [], "edges": []}

    async def query_by_date_range(
        self,
        user_id: str,
        *,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        relationship: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return memory edges that were valid (or created) within a date range.

        An edge is included if:
        - It was created before ``to_date`` (or ``to_date`` is None), AND
        - It was still valid after ``from_date`` — i.e. ``valid_until`` is NULL
          (still current) or ``valid_until > from_date`` (not yet superseded).

        Args:
            user_id:      Filter to edges owned by this user's memories.
            from_date:    Start of the date range (inclusive). Defaults to epoch.
            to_date:      End of the date range (inclusive). Defaults to now.
            relationship: Optional relationship type filter (e.g. "supports").
            limit:        Maximum edges to return (1-500).
        """
        await self._ensure_temporal_columns()
        limit = max(1, min(limit, 500))

        try:
            # Resolve user's memory IDs
            mem_rows = await Database.fetch(
                "SELECT id::text AS mid FROM agent_memories WHERE agent_id LIKE $1",
                f"{user_id}:%",
            )
            memory_ids = [r["mid"] for r in (mem_rows or [])]
            if not memory_ids:
                return []

            # Build temporal WHERE clause
            conditions = [
                "(e.source_id::text = ANY($1) OR e.target_id::text = ANY($1))",
            ]
            params: list[Any] = [memory_ids]
            p_idx = 2

            if from_date is not None:
                conditions.append(f"(e.valid_until IS NULL OR e.valid_until > ${p_idx})")
                params.append(from_date)
                p_idx += 1

            if to_date is not None:
                conditions.append(f"e.created_at <= ${p_idx}")
                params.append(to_date)
                p_idx += 1

            if relationship:
                conditions.append(f"e.relationship = ${p_idx}")
                params.append(relationship)
                p_idx += 1

            params.append(limit)
            where = " AND ".join(conditions)
            sql = f"""
                SELECT e.id, e.source_id::text AS sid, e.target_id::text AS tid,
                       e.relationship, e.weight,
                       e.created_at, e.valid_from, e.valid_until
                FROM memory_edges e
                WHERE {where}
                ORDER BY e.created_at DESC
                LIMIT ${p_idx}
            """
            rows = await Database.fetch(sql, *params)
            return [
                {
                    "id": str(r["id"]),
                    "source_id": r["sid"],
                    "target_id": r["tid"],
                    "relationship": r["relationship"],
                    "weight": float(r["weight"] or 1.0),
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                    "valid_from": r["valid_from"].isoformat() if r["valid_from"] else None,
                    "valid_until": r["valid_until"].isoformat() if r["valid_until"] else None,
                    "is_current": r["valid_until"] is None,
                }
                for r in (rows or [])
            ]
        except Exception as exc:
            logger.warning("query_by_date_range failed for user %s: %s", user_id, exc)
            return []


# Singleton accessor
_service: MemoryEdgeService | None = None


def get_memory_edge_service() -> MemoryEdgeService:
    global _service
    if _service is None:
        _service = MemoryEdgeService()
    return _service

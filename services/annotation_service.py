"""
Annotation Override Service
===========================

Admin-curated Q&A pairs that auto-override AI responses when a user query
matches by embedding similarity.  Inspired by Dify's annotation system.

Flow:
  1. Admin creates annotation (question + answer) → stored in PostgreSQL +
     indexed in VectorStore with doc_id ``anno:{id}``
  2. Before every LLM call: ``check_annotation_match(query)`` embeds the
     query and searches the annotation namespace
  3. If top result score >= annotation's ``score_threshold`` → return the
     pinned answer directly, skip LLM
  4. Hit counter incremented on each match

DB operations use raw SQL via ``Database.execute()`` (asyncpg), matching
the pattern established in ``custom_agent_service.py``.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# VectorStore namespace prefix for annotation embeddings
_ANNO_DOC_PREFIX = "anno:"


async def _get_db():
    """Import and return the async Database class."""
    from apps.backend.saas_auth import Database

    return Database


class AnnotationService:
    """CRUD + similarity matching for annotation overrides."""

    def __init__(self):
        self._vector_store = None

    def _get_vector_store(self):
        """Lazy-load vector store (avoids import-time failures)."""
        if self._vector_store is None:
            try:
                from apps.backend.core.vector_store import vector_store

                self._vector_store = vector_store
            except ImportError:
                logger.debug("VectorStore not available for annotation matching")
        return self._vector_store

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create(
        self,
        user_id: str,
        question: str,
        answer: str,
        category: str | None = None,
        score_threshold: float = 0.85,
    ) -> dict[str, Any]:
        """Create a new annotation override and index its embedding."""
        Database = await _get_db()

        anno_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        await Database.execute(
            """
            INSERT INTO annotation_overrides
                (id, user_id, question, answer, score_threshold, category,
                 hit_count, is_active, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            anno_id,
            user_id,
            question,
            answer,
            score_threshold,
            category,
            0,
            True,
            now,
            now,
        )

        # Index question embedding in VectorStore
        self._index_annotation(anno_id, question, user_id, category)

        logger.info("Created annotation override %s for user %s", anno_id, user_id)
        return {
            "id": anno_id,
            "user_id": user_id,
            "question": question,
            "answer": answer,
            "score_threshold": score_threshold,
            "category": category,
            "hit_count": 0,
            "is_active": True,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

    async def update(
        self,
        anno_id: str,
        user_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Update an annotation. Only the owner can update."""
        Database = await _get_db()

        # Fetch current state
        row = await Database.fetchrow(
            "SELECT * FROM annotation_overrides WHERE id = $1 AND user_id = $2",
            anno_id,
            user_id,
        )
        if not row:
            return None

        allowed = {"question", "answer", "category", "score_threshold", "is_active"}
        set_clauses = []
        params = []
        param_idx = 1

        for key, val in updates.items():
            if key in allowed:
                set_clauses.append(f"{key} = ${param_idx}")
                params.append(val)
                param_idx += 1

        if not set_clauses:
            return self._row_to_dict(row)

        set_clauses.append(f"updated_at = ${param_idx}")
        params.append(datetime.now(UTC))
        param_idx += 1

        params.append(anno_id)
        params.append(user_id)

        await Database.execute(
            f"UPDATE annotation_overrides SET {', '.join(set_clauses)} "
            f"WHERE id = ${param_idx} AND user_id = ${param_idx + 1}",
            *params,
        )

        # Re-index if question changed
        if "question" in updates:
            self._delete_index(anno_id)
            new_question = updates["question"]
            new_category = updates.get("category", row["category"])
            self._index_annotation(anno_id, new_question, user_id, new_category)

        # Return updated record
        updated_row = await Database.fetchrow("SELECT * FROM annotation_overrides WHERE id = $1", anno_id)
        return self._row_to_dict(updated_row) if updated_row else None

    async def delete(self, anno_id: str, user_id: str) -> bool:
        """Delete an annotation and remove its embedding."""
        Database = await _get_db()

        result = await Database.execute(
            "DELETE FROM annotation_overrides WHERE id = $1 AND user_id = $2",
            anno_id,
            user_id,
        )

        # asyncpg returns "DELETE N" — check if N > 0
        deleted = result and result.endswith("1")
        if deleted:
            self._delete_index(anno_id)
            logger.info("Deleted annotation override %s", anno_id)
        return bool(deleted)

    async def list_annotations(
        self,
        user_id: str,
        category: str | None = None,
        active_only: bool = True,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        """List annotations with pagination. Returns (items, total_count)."""
        Database = await _get_db()

        where = ["user_id = $1"]
        params: list = [user_id]
        idx = 2

        if active_only:
            where.append("is_active = true")
        if category:
            where.append(f"category = ${idx}")
            params.append(category)
            idx += 1

        where_sql = " AND ".join(where)

        count_row = await Database.fetchrow(
            f"SELECT COUNT(*) as cnt FROM annotation_overrides WHERE {where_sql}",
            *params,
        )
        total = count_row["cnt"] if count_row else 0

        params_with_pagination = list(params)
        params_with_pagination.append(limit)
        params_with_pagination.append(offset)

        rows = await Database.fetch(
            f"SELECT * FROM annotation_overrides WHERE {where_sql} "
            f"ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}",
            *params_with_pagination,
        )

        items = [self._row_to_dict(r) for r in rows]
        return items, total

    async def get(self, anno_id: str, user_id: str) -> dict[str, Any] | None:
        """Get a single annotation by ID."""
        Database = await _get_db()

        row = await Database.fetchrow(
            "SELECT * FROM annotation_overrides WHERE id = $1 AND user_id = $2",
            anno_id,
            user_id,
        )
        return self._row_to_dict(row) if row else None

    # ------------------------------------------------------------------
    # Similarity matching — called before LLM in copilot
    # ------------------------------------------------------------------

    async def check_match(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
    ) -> dict[str, Any] | None:
        """Check if a user query matches any annotation above its threshold.

        Returns the best matching annotation dict (with ``score``) or None.
        """
        vs = self._get_vector_store()
        if vs is None:
            return None

        try:
            results = vs.search(query, top_k=top_k)
        except Exception as e:
            logger.warning("Annotation vector search failed: %s", e)
            return None

        Database = await _get_db()

        # Filter to annotation docs for this user
        for hit in results:
            doc_id = hit.get("id", "")
            if not doc_id.startswith(_ANNO_DOC_PREFIX):
                continue

            meta = hit.get("metadata", {})
            if meta.get("user_id") != user_id:
                continue

            anno_id = doc_id[len(_ANNO_DOC_PREFIX) :]
            score = hit.get("score", 0.0)

            # Load the annotation to check its threshold and active status
            row = await Database.fetchrow(
                "SELECT * FROM annotation_overrides WHERE id = $1 AND is_active = true",
                anno_id,
            )
            if row is None:
                continue

            threshold = row["score_threshold"]
            if score >= threshold:
                # Increment hit counter
                await Database.execute(
                    "UPDATE annotation_overrides SET hit_count = hit_count + 1 WHERE id = $1",
                    anno_id,
                )

                match = self._row_to_dict(row)
                match["score"] = round(score, 4)
                logger.info(
                    "Annotation match for user %s: score=%.4f threshold=%.2f anno=%s",
                    user_id,
                    score,
                    threshold,
                    anno_id,
                )
                return match

        return None

    # ------------------------------------------------------------------
    # Embedding index helpers
    # ------------------------------------------------------------------

    def _index_annotation(
        self,
        anno_id: str,
        question: str,
        user_id: str,
        category: str | None = None,
    ) -> None:
        """Index the annotation question in the vector store."""
        vs = self._get_vector_store()
        if vs is None:
            return
        try:
            vs.add_document(
                doc_id=f"{_ANNO_DOC_PREFIX}{anno_id}",
                text=question,
                metadata={
                    "user_id": user_id,
                    "type": "annotation_override",
                    "category": category or "",
                },
            )
        except Exception as e:
            logger.warning("Failed to index annotation %s: %s", anno_id, e)

    def _delete_index(self, anno_id: str) -> None:
        """Remove the annotation embedding from the vector store."""
        vs = self._get_vector_store()
        if vs is None:
            return
        try:
            vs.delete_document(f"{_ANNO_DOC_PREFIX}{anno_id}")
        except Exception as e:
            logger.warning("Failed to delete annotation index %s: %s", anno_id, e)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row) -> dict[str, Any]:
        d = dict(row)
        for key in ("created_at", "updated_at"):
            if key in d and d[key] is not None:
                d[key] = d[key].isoformat()
        return d


# Singleton
_annotation_service: AnnotationService | None = None


def get_annotation_service() -> AnnotationService:
    global _annotation_service
    if _annotation_service is None:
        _annotation_service = AnnotationService()
    return _annotation_service

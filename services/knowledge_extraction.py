"""
Knowledge Extraction Service

Extracts structured (subject, predicate, object) triples from conversations
using LLM, deduplicates against existing facts, and indexes them in the
VectorStore for embedding-based retrieval.

Copyright (c) 2025 Andrew John Ward. All Rights Reserved.
"""

import difflib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

# In-memory cache TTL for existing entity names (used for fuzzy resolution)
_ENTITY_CACHE_TTL_SECONDS = 3600  # 1 hour

logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT = """\
Extract factual information from this conversation as structured triples.
Return a JSON array: [{"subject": "...", "predicate": "...", "object": "...", "confidence": 0.0-1.0}]

RULES:
1. Only extract concrete, reusable facts: user preferences, decisions, technical details, project info.
2. Do NOT extract conversational filler, greetings, opinions without substance, or ephemeral state.
3. subject and predicate should be concise (a few words). object can be a short sentence.
4. confidence: 1.0 for explicit statements, 0.7-0.9 for strong inferences, below 0.7 for weak signals.
5. Return an empty array [] if no extractable facts exist.
6. Do NOT wrap the JSON in markdown code fences. Return raw JSON only.
7. Maximum 10 facts per extraction.
"""


class KnowledgeExtractionService:
    """Extracts and persists structured knowledge facts from conversations."""

    def __init__(self):
        self._llm = None
        self._vector_store = None
        # Entity name cache: user_id → {"subjects": set[str], "fetched_at": datetime}
        self._entity_cache: dict[str, Any] = {}

    def _get_llm(self):
        if self._llm is None:
            try:
                from apps.backend.services.unified_llm import unified_llm

                self._llm = unified_llm
            except ImportError:
                logger.warning("unified_llm not available — knowledge extraction disabled")
        return self._llm

    def _get_vector_store(self):
        if self._vector_store is None:
            try:
                from apps.backend.core.vector_store import vector_store

                self._vector_store = vector_store
            except ImportError:
                logger.debug("VectorStore not available — semantic search disabled")
        return self._vector_store

    async def extract_facts(
        self,
        user_id: str,
        agent_id: str,
        conversation_id: str,
        messages: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        """Extract knowledge triples from conversation messages via LLM.

        Args:
            user_id: Owner of the conversation
            agent_id: Agent involved in the conversation
            conversation_id: Source conversation ID
            messages: List of {"role": ..., "content": ...} dicts

        Returns:
            List of extracted fact dicts with subject/predicate/object/confidence
        """
        llm = self._get_llm()
        if not llm:
            return []

        # Build a compact conversation summary for extraction
        conv_text = "\n".join(
            f"{m.get('role', 'user').title()}: {m.get('content', '')[:500]}"
            for m in messages[-10:]  # Last 10 messages max
        )

        try:
            response = await llm.chat(
                [
                    {"role": "system", "content": _EXTRACTION_PROMPT},
                    {"role": "user", "content": f"Conversation:\n{conv_text}"},
                ],
                max_tokens=1024,
                temperature=0.1,
            )

            # Parse JSON response
            text = response.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            facts = json.loads(text)
            if not isinstance(facts, list):
                logger.warning("Knowledge extraction returned non-list: %s", type(facts))
                return []

            # Validate and normalize
            valid_facts = []
            for f in facts[:10]:
                if isinstance(f, dict) and f.get("subject") and f.get("predicate") and f.get("object"):
                    valid_facts.append(
                        {
                            "subject": str(f["subject"])[:500],
                            "predicate": str(f["predicate"])[:500],
                            "object": str(f["object"]),
                            "confidence": max(0.0, min(1.0, float(f.get("confidence", 0.8)))),
                        }
                    )
            return valid_facts

        except json.JSONDecodeError as e:
            logger.warning("Knowledge extraction returned invalid JSON: %s", e)
            return []
        except Exception as e:
            logger.warning("Knowledge extraction failed: %s", e)
            return []

    async def store_facts(
        self,
        user_id: str,
        agent_id: str | None,
        facts: list[dict[str, Any]],
        conversation_id: str | None = None,
        message_id: str | None = None,
    ) -> int:
        """Persist extracted facts to PostgreSQL and index in VectorStore.

        Deduplicates by (user_id, subject, predicate) — if an existing fact
        has the same subject+predicate, updates the object and confidence.

        Args:
            user_id: Fact owner
            agent_id: Agent that extracted the facts
            facts: List of fact dicts from extract_facts()
            conversation_id: Source conversation
            message_id: Source message

        Returns:
            Number of facts stored (new + updated)
        """
        from apps.backend.core.unified_auth import Database

        stored = 0
        now = datetime.now(UTC).isoformat()

        # P9: Resolve entity names to canonical forms before dedup/insert
        existing_subjects = await self._get_user_subjects(user_id)
        for fact in facts:
            fact["subject"] = self._resolve_entity_name(fact["subject"], existing_subjects)

        for fact in facts:
            try:
                import uuid

                # Check for existing active fact (same user + subject + predicate)
                # Bi-temporal: also filter invalid_at IS NULL (current facts only)
                existing = await Database.fetchrow(
                    "SELECT id, object, confidence FROM knowledge_facts "
                    "WHERE user_id = $1 AND subject = $2 AND predicate = $3 "
                    "AND is_active = true AND invalid_at IS NULL",
                    user_id,
                    fact["subject"],
                    fact["predicate"],
                )

                if existing and (existing["object"] != fact["object"] or existing["confidence"] < fact["confidence"]):
                    # Bi-temporal supersession: mark old fact as invalid + expired,
                    # then insert a new record.  Old record is preserved for history.
                    await Database.execute(
                        "UPDATE knowledge_facts SET invalid_at = $1, expired_at = $1 WHERE id = $2",
                        now,
                        existing["id"],
                    )
                    fact_id = str(uuid.uuid4())
                    await Database.execute(
                        "INSERT INTO knowledge_facts "
                        "(id, user_id, agent_id, subject, predicate, object, confidence, "
                        "source_conversation_id, source_message_id, extracted_at, "
                        "valid_at, reference_count, is_active) "
                        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $10, 0, true)",
                        fact_id,
                        user_id,
                        agent_id,
                        fact["subject"],
                        fact["predicate"],
                        fact["object"],
                        fact["confidence"],
                        conversation_id,
                        message_id,
                        now,
                    )
                    self._index_fact(fact_id, user_id, fact)
                    stored += 1
                elif not existing:
                    # Insert brand-new fact
                    fact_id = str(uuid.uuid4())
                    await Database.execute(
                        "INSERT INTO knowledge_facts "
                        "(id, user_id, agent_id, subject, predicate, object, confidence, "
                        "source_conversation_id, source_message_id, extracted_at, "
                        "valid_at, reference_count, is_active) "
                        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $10, 0, true)",
                        fact_id,
                        user_id,
                        agent_id,
                        fact["subject"],
                        fact["predicate"],
                        fact["object"],
                        fact["confidence"],
                        conversation_id,
                        message_id,
                        now,
                    )
                    self._index_fact(fact_id, user_id, fact)
                    # Invalidate entity cache so next batch picks up the new subject
                    self._invalidate_entity_cache(user_id)
                    stored += 1

            except Exception as e:
                logger.warning(
                    "Failed to store fact (%s %s %s): %s",
                    fact.get("subject"),
                    fact.get("predicate"),
                    fact.get("object", "")[:50],
                    e,
                )

        if stored:
            logger.info("Stored %d/%d knowledge facts for user %s", stored, len(facts), user_id)
        return stored

    async def promote_to_core_memory(
        self,
        user_id: str,
        agent_id: str,
        facts: list[dict[str, Any]],
    ) -> int:
        """Promote high-confidence facts to core memory for persistent injection into prompts.

        Only promotes facts with confidence >= 0.8 to avoid polluting core memory.
        Core memory is limited to 2KB, so we keep facts concise.

        Args:
            user_id: Fact owner
            agent_id: Agent that extracted the facts
            facts: List of fact dicts from extract_facts()

        Returns:
            Number of facts promoted to core memory
        """
        promoted = 0
        try:
            from apps.backend.integrations.agent_memory_service import get_three_tier_manager

            mem_key = f"{user_id}:{agent_id}" if agent_id else f"{user_id}:helix"
            mem_mgr = get_three_tier_manager(mem_key)

            for fact in facts:
                confidence = fact.get("confidence", 0.5)
                if confidence < 0.8:
                    continue

                subject = fact.get("subject", "")
                predicate = fact.get("predicate", "")
                obj = fact.get("object", "")

                if not all([subject, predicate, obj]):
                    continue

                # Use subject as key, "predicate: object" as value
                core_key = f"fact_{subject.lower().replace(' ', '_')[:30]}"
                core_value = f"{subject} {predicate} {obj}"

                success = await mem_mgr.update_core(core_key, core_value)
                if success:
                    promoted += 1
                else:
                    # Core memory full (2KB limit), stop promoting
                    logger.debug(
                        "Core memory full, stopping fact promotion at %d facts",
                        promoted,
                    )
                    break

            if promoted > 0:
                logger.info(
                    "Promoted %d high-confidence facts to core memory for %s",
                    promoted,
                    mem_key,
                )

        except Exception as e:
            logger.warning("Failed to promote facts to core memory: %s", e)

        return promoted

    @staticmethod
    def _resolve_entity_name(name: str, existing_names: list[str], cutoff: float = 0.85) -> str:
        """Normalize an entity name to its canonical form using fuzzy matching.

        Prevents duplicate graph nodes for the same real-world entity —
        e.g. "OpenAI", "Open AI", and "openai" resolve to the same node.
        (Cognee-inspired, P9)

        Returns the canonical name from `existing_names` if a close match is
        found, otherwise returns the original `name` unchanged.
        """
        if not existing_names or not name:
            return name

        # 1. Exact match — no change needed
        if name in existing_names:
            return name

        # 2. Case-normalized exact match — use the canonical casing
        name_lower = name.lower()
        for existing in existing_names:
            if existing.lower() == name_lower:
                return existing

        # 3. Fuzzy match via difflib
        matches = difflib.get_close_matches(name, existing_names, n=1, cutoff=cutoff)
        if matches:
            logger.debug("Entity resolved: %r -> %r", name, matches[0])
            return matches[0]

        return name

    async def _get_user_subjects(self, user_id: str) -> list[str]:
        """Return cached list of existing subject names for a user (TTL 1h)."""
        now = datetime.now(UTC)
        entry = self._entity_cache.get(user_id)
        if entry and (now - entry["fetched_at"]) < timedelta(seconds=_ENTITY_CACHE_TTL_SECONDS):
            return list(entry["subjects"])

        try:
            from apps.backend.core.unified_auth import Database

            rows = await Database.fetch(
                "SELECT DISTINCT subject FROM knowledge_facts WHERE user_id = $1 AND is_active = true LIMIT 1000",
                user_id,
            )
            subjects = [r["subject"] for r in rows] if rows else []
            self._entity_cache[user_id] = {"subjects": set(subjects), "fetched_at": now}
            return subjects
        except Exception as exc:
            logger.debug("Entity cache fetch failed for %s: %s", user_id, exc)
            return []

    def _invalidate_entity_cache(self, user_id: str) -> None:
        """Invalidate entity name cache after a new subject is stored."""
        self._entity_cache.pop(user_id, None)

    def _index_fact(self, fact_id: str, user_id: str, fact: dict[str, Any]) -> None:
        """Index a fact in the VectorStore for semantic search."""
        vs = self._get_vector_store()
        if not vs:
            return
        try:
            text = f"{fact['subject']} {fact['predicate']} {fact['object']}"
            vs.add_document(
                doc_id=f"kf:{user_id}:{fact_id}",
                text=text,
                metadata={"user_id": user_id, "fact_id": fact_id, "type": "knowledge_fact"},
            )
        except Exception as e:
            logger.debug("VectorStore indexing failed for fact %s: %s", fact_id, e)

    async def search_facts(
        self,
        user_id: str,
        query: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search knowledge facts by semantic similarity, with SQL fallback.

        Args:
            user_id: Only search this user's facts
            query: Natural language search query
            limit: Max results

        Returns:
            List of fact dicts with id, subject, predicate, object, confidence, score
        """
        from apps.backend.core.unified_auth import Database

        # Try vector search first
        vs = self._get_vector_store()
        if vs:
            try:
                results = vs.search(query, top_k=limit * 2)
                # Filter to this user's knowledge facts
                fact_ids = []
                for r in results:
                    doc_id = r.get("doc_id", "")
                    if doc_id.startswith(f"kf:{user_id}:"):
                        fact_id = doc_id.split(":", 2)[2]
                        fact_ids.append(fact_id)
                        if len(fact_ids) >= limit:
                            break

                if fact_ids:
                    # Fetch full facts from DB
                    placeholders = ", ".join(f"${i + 1}" for i in range(len(fact_ids)))
                    rows = await Database.fetch(
                        f"SELECT id, subject, predicate, object, confidence, agent_id, "
                        f"extracted_at, valid_at, reference_count FROM knowledge_facts "
                        f"WHERE id IN ({placeholders}) AND is_active = true AND invalid_at IS NULL",
                        *fact_ids,
                    )

                    # Update reference counts (fire-and-forget)
                    for fid in fact_ids:
                        try:
                            await Database.execute(
                                "UPDATE knowledge_facts SET reference_count = reference_count + 1, "
                                "last_referenced_at = $1 WHERE id = $2",
                                datetime.now(UTC).isoformat(),
                                fid,
                            )
                        except Exception as e:
                            logger.debug("ref count update failed for fact %s: %s", fid, e)

                    return [dict(r) for r in rows] if rows else []
            except Exception as e:
                logger.debug("Vector search failed, falling back to SQL: %s", e)

        # SQL fallback: keyword search on subject and object
        keywords = [w.strip() for w in query.split() if len(w.strip()) > 2]
        if not keywords:
            return []

        conditions = []
        params = [user_id]
        for i, kw in enumerate(keywords[:5]):  # Max 5 keywords
            param_idx = len(params) + 1
            conditions.append(f"(subject ILIKE ${param_idx} OR object ILIKE ${param_idx})")
            params.append(f"%{kw}%")

        where = " OR ".join(conditions)
        param_idx_limit = len(params) + 1
        params.append(int(limit))
        rows = await Database.fetch(
            f"SELECT id, subject, predicate, object, confidence, agent_id, "
            f"extracted_at, valid_at, reference_count FROM knowledge_facts "
            f"WHERE user_id = $1 AND is_active = true AND invalid_at IS NULL AND ({where}) "
            f"ORDER BY confidence DESC, reference_count DESC LIMIT ${param_idx_limit}",
            *params,
        )

        return [dict(r) for r in rows] if rows else []

    async def get_user_facts(
        self,
        user_id: str,
        agent_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get paginated list of user's knowledge facts.

        Args:
            user_id: Fact owner
            agent_id: Optional filter by agent
            limit: Page size
            offset: Page offset

        Returns:
            List of fact dicts
        """
        from apps.backend.core.unified_auth import Database

        if agent_id:
            rows = await Database.fetch(
                "SELECT id, subject, predicate, object, confidence, agent_id, "
                "source_conversation_id, extracted_at, valid_at, last_referenced_at, reference_count "
                "FROM knowledge_facts WHERE user_id = $1 AND agent_id = $2 "
                "AND is_active = true AND invalid_at IS NULL "
                "ORDER BY extracted_at DESC LIMIT $3 OFFSET $4",
                user_id,
                agent_id,
                limit,
                offset,
            )
        else:
            rows = await Database.fetch(
                "SELECT id, subject, predicate, object, confidence, agent_id, "
                "source_conversation_id, extracted_at, valid_at, last_referenced_at, reference_count "
                "FROM knowledge_facts WHERE user_id = $1 "
                "AND is_active = true AND invalid_at IS NULL "
                "ORDER BY extracted_at DESC LIMIT $2 OFFSET $3",
                user_id,
                limit,
                offset,
            )

        return [dict(r) for r in rows] if rows else []

    async def get_stats(self, user_id: str) -> dict[str, Any]:
        """Get knowledge graph stats for a user."""
        from apps.backend.core.unified_auth import Database

        total = await Database.fetchval(
            "SELECT COUNT(*) FROM knowledge_facts WHERE user_id = $1 AND is_active = true AND invalid_at IS NULL",
            user_id,
        )

        top_subjects = await Database.fetch(
            "SELECT subject, COUNT(*) as count FROM knowledge_facts "
            "WHERE user_id = $1 AND is_active = true AND invalid_at IS NULL "
            "GROUP BY subject ORDER BY count DESC LIMIT 10",
            user_id,
        )

        agents = await Database.fetch(
            "SELECT agent_id, COUNT(*) as count FROM knowledge_facts "
            "WHERE user_id = $1 AND is_active = true AND invalid_at IS NULL "
            "AND agent_id IS NOT NULL "
            "GROUP BY agent_id ORDER BY count DESC LIMIT 10",
            user_id,
        )

        return {
            "total_facts": total or 0,
            "top_subjects": [{"subject": r["subject"], "count": r["count"]} for r in (top_subjects or [])],
            "agents": [{"agent_id": r["agent_id"], "count": r["count"]} for r in (agents or [])],
        }

    async def delete_fact(self, user_id: str, fact_id: str) -> bool:
        """Soft-delete a single fact (set is_active=false)."""
        from apps.backend.core.unified_auth import Database

        result = await Database.execute(
            "UPDATE knowledge_facts SET is_active = false WHERE id = $1 AND user_id = $2",
            fact_id,
            user_id,
        )

        # Remove from VectorStore
        vs = self._get_vector_store()
        if vs and hasattr(vs, "delete_document"):
            try:
                vs.delete_document(f"kf:{user_id}:{fact_id}")
            except Exception as e:
                logger.debug("VectorStore cleanup failed for fact %s: %s", fact_id, e)

        return bool(result)

    async def delete_all_user_facts(self, user_id: str) -> int:
        """GDPR erasure: permanently delete all facts for a user.

        Returns:
            Number of facts deleted
        """
        from apps.backend.core.unified_auth import Database

        # Hard delete from DB
        result = await Database.execute(
            "DELETE FROM knowledge_facts WHERE user_id = $1",
            user_id,
        )

        count = 0
        if result:
            try:
                count = int(str(result).split()[-1])
            except (ValueError, IndexError, TypeError):
                count = 0

        logger.info("GDPR: deleted %d knowledge facts for user %s", count, user_id)
        return count


# Module-level singleton
_knowledge_service: KnowledgeExtractionService | None = None


def get_knowledge_service() -> KnowledgeExtractionService:
    """Get or create the singleton KnowledgeExtractionService."""
    global _knowledge_service
    if _knowledge_service is None:
        _knowledge_service = KnowledgeExtractionService()
    return _knowledge_service

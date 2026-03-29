"""
RAG (Retrieval-Augmented Generation) Service
=============================================

Orchestrates the document ingestion pipeline:
  upload → extract text → chunk → embed → index in VectorStore

Also provides retrieval (semantic search over indexed chunks) and
context injection for the copilot/chat flow.
"""

import io
import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy DB access (same pattern as annotation_service / knowledge_extraction)
# ---------------------------------------------------------------------------

_Database = None


async def _get_db():
    global _Database
    if _Database is None:
        try:
            from apps.backend.core.unified_auth import Database

            _Database = Database
        except ImportError:
            from apps.backend.saas_auth import Database

            _Database = Database
    return _Database


# ---------------------------------------------------------------------------
# Text chunking
# ---------------------------------------------------------------------------


def chunk_text(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
    separator: str = "\n\n",
) -> list[dict[str, Any]]:
    """Split text into overlapping chunks.

    Uses a recursive strategy:
    1. Split on ``separator`` (paragraphs by default).
    2. Merge consecutive segments until hitting ``chunk_size`` tokens
       (approximated as chars / 4).
    3. Overlap the last ``chunk_overlap`` tokens from the previous chunk.

    Returns a list of ``{text, index, token_count}`` dicts.
    """
    if not text or not text.strip():
        return []

    # Approximate tokens as chars / 4
    char_limit = chunk_size * 4
    overlap_chars = chunk_overlap * 4

    # Split on paragraph breaks, then on single newlines if paragraphs are huge
    paragraphs = text.split(separator)
    if not paragraphs:
        paragraphs = [text]

    # Further split any paragraph that exceeds char_limit
    segments: list[str] = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(para) <= char_limit:
            segments.append(para)
        else:
            # Split on single newlines
            for line in para.split("\n"):
                line = line.strip()
                if not line:
                    continue
                if len(line) <= char_limit:
                    segments.append(line)
                else:
                    # Hard split at char_limit
                    for i in range(0, len(line), char_limit - overlap_chars):
                        segments.append(line[i : i + char_limit])

    if not segments:
        return []

    # Merge segments into chunks respecting char_limit
    chunks: list[dict[str, Any]] = []
    current = ""
    idx = 0

    for seg in segments:
        candidate = (current + "\n\n" + seg).strip() if current else seg
        if len(candidate) > char_limit and current:
            # Flush current chunk
            token_est = max(1, len(current) // 4)
            chunks.append({"text": current, "index": idx, "token_count": token_est})
            idx += 1
            # Overlap: keep tail of current
            if overlap_chars > 0 and len(current) > overlap_chars:
                current = current[-overlap_chars:] + "\n\n" + seg
            else:
                current = seg
        else:
            current = candidate

    # Flush remaining
    if current.strip():
        token_est = max(1, len(current) // 4)
        chunks.append({"text": current.strip(), "index": idx, "token_count": token_est})

    return chunks


# ---------------------------------------------------------------------------
# Document text extraction (reuses helpers from routes/documents.py)
# ---------------------------------------------------------------------------


async def extract_text(data: bytes, filename: str) -> str:
    """Extract text from file bytes based on file extension."""
    ext = os.path.splitext(filename.lower())[1]

    if ext == ".pdf":
        try:
            import pdfplumber

            parts = []
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    parts.append(page_text)
            return "\n\n".join(filter(None, parts))
        except ImportError:
            raise ValueError("PDF extraction requires pdfplumber")
        except Exception as exc:
            raise ValueError(f"PDF extraction failed: {exc}")

    elif ext in (".docx", ".doc"):
        try:
            from docx import Document

            doc = Document(io.BytesIO(data))
            return "\n".join(para.text for para in doc.paragraphs if para.text)
        except ImportError:
            raise ValueError("DOCX extraction requires python-docx")
        except Exception as exc:
            raise ValueError(f"DOCX extraction failed: {exc}")

    elif ext in (".txt", ".md", ".csv", ".log", ".json", ".rst", ".html"):
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.decode("latin-1")

    else:
        raise ValueError(f"Unsupported file type: {ext}")


# ---------------------------------------------------------------------------
# RAG Service
# ---------------------------------------------------------------------------


class RAGService:
    """Manages RAG datasets, documents, chunks, and retrieval."""

    def __init__(self):
        self._vector_store = None

    def _get_vector_store(self):
        if self._vector_store is None:
            try:
                from apps.backend.core.vector_store import vector_store

                self._vector_store = vector_store
            except Exception as e:
                logger.warning("VectorStore unavailable: %s", e)
        return self._vector_store

    # -----------------------------------------------------------------------
    # Dataset CRUD
    # -----------------------------------------------------------------------

    async def create_dataset(
        self,
        user_id: str,
        name: str,
        description: str | None = None,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
    ) -> dict[str, Any]:
        Database = await _get_db()
        dataset_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        vs = self._get_vector_store()
        embedding_model = vs.config.embedding_model if vs else "all-MiniLM-L6-v2"

        await Database.execute(
            """
            INSERT INTO rag_datasets
                (id, user_id, name, description, status, chunk_size, chunk_overlap, embedding_model, created_at, updated_at)
            VALUES ($1, $2, $3, $4, 'active', $5, $6, $7, $8, $8)
            """,
            dataset_id,
            user_id,
            name,
            description,
            chunk_size,
            chunk_overlap,
            embedding_model,
            now,
        )

        return {
            "id": dataset_id,
            "user_id": user_id,
            "name": name,
            "description": description,
            "status": "active",
            "document_count": 0,
            "chunk_count": 0,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "embedding_model": embedding_model,
            "created_at": now.isoformat(),
        }

    async def list_datasets(self, user_id: str, offset: int = 0, limit: int = 50) -> tuple[list[dict], int]:
        Database = await _get_db()

        rows = await Database.fetch(
            """
            SELECT * FROM rag_datasets
            WHERE user_id = $1 AND status != 'deleted'
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            user_id,
            limit,
            offset,
        )
        count_row = await Database.fetchrow(
            "SELECT COUNT(*) as total FROM rag_datasets WHERE user_id = $1 AND status != 'deleted'",
            user_id,
        )
        total = count_row["total"] if count_row else 0
        return [dict(r) for r in rows], total

    async def get_dataset(self, dataset_id: str, user_id: str) -> dict | None:
        Database = await _get_db()
        row = await Database.fetchrow(
            "SELECT * FROM rag_datasets WHERE id = $1 AND user_id = $2",
            dataset_id,
            user_id,
        )
        return dict(row) if row else None

    async def delete_dataset(self, dataset_id: str, user_id: str) -> bool:
        """Soft-delete a dataset and remove all its chunks from VectorStore."""
        Database = await _get_db()

        dataset = await self.get_dataset(dataset_id, user_id)
        if not dataset:
            return False

        # Remove from VectorStore
        vs = self._get_vector_store()
        if vs:
            chunks = await Database.fetch("SELECT id FROM rag_chunks WHERE dataset_id = $1", dataset_id)
            for chunk in chunks:
                try:
                    vs.delete_document(f"rag:{dataset_id}:{chunk['id']}")
                except Exception as e:
                    logger.warning("Failed to remove chunk %s from VectorStore: %s", chunk["id"], e)

        # Delete chunks, documents, mark dataset deleted
        await Database.execute("DELETE FROM rag_chunks WHERE dataset_id = $1", dataset_id)
        await Database.execute("DELETE FROM rag_documents WHERE dataset_id = $1", dataset_id)
        await Database.execute(
            "UPDATE rag_datasets SET status = 'deleted', updated_at = $2 WHERE id = $1",
            dataset_id,
            datetime.now(UTC),
        )
        return True

    # -----------------------------------------------------------------------
    # Document ingestion
    # -----------------------------------------------------------------------

    async def ingest_document(
        self,
        dataset_id: str,
        user_id: str,
        filename: str,
        file_data: bytes,
    ) -> dict[str, Any]:
        """Full pipeline: extract → chunk → embed → index."""
        Database = await _get_db()

        # Verify dataset ownership
        dataset = await self.get_dataset(dataset_id, user_id)
        if not dataset:
            raise ValueError("Dataset not found")

        ext = os.path.splitext(filename.lower())[1].lstrip(".")
        doc_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        # Create document record
        await Database.execute(
            """
            INSERT INTO rag_documents
                (id, dataset_id, user_id, filename, file_type, file_size, status, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, 'processing', $7)
            """,
            doc_id,
            dataset_id,
            user_id,
            filename,
            ext,
            len(file_data),
            now,
        )

        try:
            # 1. Extract text
            text = await extract_text(file_data, filename)
            if not text or not text.strip():
                raise ValueError("No text could be extracted from the file")

            # 2. Chunk
            chunk_size = dataset.get("chunk_size", 512)
            chunk_overlap = dataset.get("chunk_overlap", 64)
            chunks = chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

            if not chunks:
                raise ValueError("Document produced no chunks after splitting")

            # 3. Embed + index each chunk
            vs = self._get_vector_store()
            chunk_records = []
            for chunk in chunks:
                chunk_id = str(uuid.uuid4())
                chunk_records.append(
                    {
                        "id": chunk_id,
                        "dataset_id": dataset_id,
                        "document_id": doc_id,
                        "chunk_index": chunk["index"],
                        "text": chunk["text"],
                        "token_count": chunk["token_count"],
                    }
                )

                # Index in VectorStore
                if vs:
                    try:
                        vs.add_document(
                            doc_id=f"rag:{dataset_id}:{chunk_id}",
                            text=chunk["text"],
                            metadata={
                                "dataset_id": dataset_id,
                                "document_id": doc_id,
                                "chunk_index": chunk["index"],
                                "filename": filename,
                                "user_id": user_id,
                            },
                        )
                    except Exception as e:
                        logger.warning("Failed to index chunk %s: %s", chunk_id, e)

            # 4. Persist chunks to DB
            for rec in chunk_records:
                await Database.execute(
                    """
                    INSERT INTO rag_chunks (id, dataset_id, document_id, chunk_index, text, token_count, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    rec["id"],
                    rec["dataset_id"],
                    rec["document_id"],
                    rec["chunk_index"],
                    rec["text"],
                    rec["token_count"],
                    now,
                )

            # 5. Update document status
            total_chars = len(text)
            total_chunks = len(chunk_records)
            total_tokens = sum(c["token_count"] for c in chunk_records)

            await Database.execute(
                """
                UPDATE rag_documents
                SET status = 'indexed', chunk_count = $2, char_count = $3
                WHERE id = $1
                """,
                doc_id,
                total_chunks,
                total_chars,
            )

            # 6. Update dataset counters
            await Database.execute(
                """
                UPDATE rag_datasets
                SET document_count = document_count + 1,
                    chunk_count = chunk_count + $2,
                    total_tokens = total_tokens + $3,
                    updated_at = $4
                WHERE id = $1
                """,
                dataset_id,
                total_chunks,
                total_tokens,
                datetime.now(UTC),
            )

            return {
                "document_id": doc_id,
                "filename": filename,
                "status": "indexed",
                "chunks": total_chunks,
                "chars": total_chars,
                "tokens": total_tokens,
            }

        except Exception as e:
            logger.error("Document ingestion failed for %s: %s", filename, e)
            await Database.execute(
                "UPDATE rag_documents SET status = 'error', error_message = $2 WHERE id = $1",
                doc_id,
                str(e),
            )
            raise

    async def list_documents(self, dataset_id: str, user_id: str) -> list[dict]:
        Database = await _get_db()
        rows = await Database.fetch(
            """
            SELECT * FROM rag_documents
            WHERE dataset_id = $1 AND user_id = $2
            ORDER BY created_at DESC
            """,
            dataset_id,
            user_id,
        )
        return [dict(r) for r in rows]

    async def delete_document(self, doc_id: str, dataset_id: str, user_id: str) -> bool:
        Database = await _get_db()

        doc = await Database.fetchrow(
            "SELECT * FROM rag_documents WHERE id = $1 AND dataset_id = $2 AND user_id = $3",
            doc_id,
            dataset_id,
            user_id,
        )
        if not doc:
            return False

        # Remove chunks from VectorStore
        vs = self._get_vector_store()
        chunks = await Database.fetch("SELECT id FROM rag_chunks WHERE document_id = $1", doc_id)
        if vs:
            for chunk in chunks:
                try:
                    vs.delete_document(f"rag:{dataset_id}:{chunk['id']}")
                except Exception as e:
                    logger.warning("Failed to remove chunk from VectorStore: %s", e)

        chunk_count = len(chunks)
        token_count = 0
        if chunks:
            token_row = await Database.fetchrow(
                "SELECT COALESCE(SUM(token_count), 0) as total FROM rag_chunks WHERE document_id = $1", doc_id
            )
            token_count = token_row["total"] if token_row else 0

        await Database.execute("DELETE FROM rag_chunks WHERE document_id = $1", doc_id)
        await Database.execute("DELETE FROM rag_documents WHERE id = $1", doc_id)
        await Database.execute(
            """
            UPDATE rag_datasets
            SET document_count = GREATEST(document_count - 1, 0),
                chunk_count = GREATEST(chunk_count - $2, 0),
                total_tokens = GREATEST(total_tokens - $3, 0),
                updated_at = $4
            WHERE id = $1
            """,
            dataset_id,
            chunk_count,
            token_count,
            datetime.now(UTC),
        )
        return True

    # -----------------------------------------------------------------------
    # Retrieval
    # -----------------------------------------------------------------------

    async def search(
        self,
        dataset_id: str,
        user_id: str,
        query: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Semantic search over a dataset's indexed chunks."""
        # Verify ownership
        dataset = await self.get_dataset(dataset_id, user_id)
        if not dataset:
            raise ValueError("Dataset not found")

        vs = self._get_vector_store()
        if not vs:
            logger.warning("VectorStore unavailable — falling back to SQL keyword search")
            return await self._sql_search(dataset_id, query, top_k)

        results = vs.search(
            query=query,
            top_k=top_k * 3,  # Over-fetch then filter to this dataset
            filter_metadata={"dataset_id": dataset_id},
        )

        # Filter results to this dataset (in case filter_metadata is unsupported)
        filtered = []
        for r in results:
            metadata = r.get("metadata", {})
            if metadata.get("dataset_id") == dataset_id:
                filtered.append(
                    {
                        "chunk_id": (
                            r.get("doc_id", "").split(":")[-1] if ":" in r.get("doc_id", "") else r.get("doc_id")
                        ),
                        "text": r.get("text", ""),
                        "score": round(r.get("score", 0.0), 4),
                        "filename": metadata.get("filename", ""),
                        "chunk_index": metadata.get("chunk_index", 0),
                        "document_id": metadata.get("document_id", ""),
                    }
                )
                if len(filtered) >= top_k:
                    break

        return filtered

    async def _sql_search(self, dataset_id: str, query: str, top_k: int) -> list[dict]:
        """Keyword-based fallback when VectorStore is unavailable."""
        Database = await _get_db()
        words = [w.strip() for w in query.split() if len(w.strip()) >= 3]
        if not words:
            return []

        # Use ILIKE for simple keyword matching
        conditions = " OR ".join(f"c.text ILIKE '%' || ${i+2} || '%'" for i in range(len(words)))
        rows = await Database.fetch(
            f"""
            SELECT c.id, c.text, c.chunk_index, c.token_count, d.filename, c.document_id
            FROM rag_chunks c
            JOIN rag_documents d ON c.document_id = d.id
            WHERE c.dataset_id = $1 AND ({conditions})
            LIMIT {top_k}
            """,
            dataset_id,
            *words,
        )
        return [
            {
                "chunk_id": r["id"],
                "text": r["text"],
                "score": 0.5,  # SQL fallback has no real score
                "filename": r["filename"],
                "chunk_index": r["chunk_index"],
                "document_id": r["document_id"],
            }
            for r in rows
        ]

    async def get_retrieval_context(
        self,
        dataset_ids: list[str],
        user_id: str,
        query: str,
        top_k: int = 5,
    ) -> str:
        """Search across multiple datasets and return formatted context string
        suitable for prepending to an LLM prompt."""
        all_results = []
        for ds_id in dataset_ids:
            try:
                results = await self.search(ds_id, user_id, query, top_k=top_k)
                all_results.extend(results)
            except Exception as e:
                logger.warning("RAG search failed for dataset %s: %s", ds_id, e)

        if not all_results:
            return ""

        # Sort by score descending, take top_k overall
        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        top_results = all_results[:top_k]

        # Format as context block
        context_parts = ["<retrieved_context>"]
        for i, r in enumerate(top_results, 1):
            context_parts.append(
                f"[{i}] (source: {r.get('filename', 'unknown')}, score: {r.get('score', 0):.2f})\n{r['text']}"
            )
        context_parts.append("</retrieved_context>")
        return "\n\n".join(context_parts)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_rag_service: RAGService | None = None


def get_rag_service() -> RAGService:
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service

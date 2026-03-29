"""
Vector Search Service

Provides semantic search capabilities using vector embeddings.
Supports code search, document search, and hybrid search.
"""

import re
from pathlib import Path
from typing import Any

from loguru import logger

from apps.backend.core.vector_store import vector_store


class VectorSearchService:
    """Vector search service for semantic search"""

    def __init__(self):
        self.vector_store = vector_store
        self._indexed = False

    def index_codebase(self, codebase_path: str, languages: list[str] | None = None):
        """
        Index codebase for semantic search

        Args:
            codebase_path: Path to codebase
            languages: Optional list of languages to index (e.g., ['python', 'typescript'])
        """
        try:
            logger.info("Indexing codebase: %s", codebase_path)

            codebase_path = Path(codebase_path)
            if not codebase_path.exists():
                logger.error("Codebase path not found: %s", codebase_path)
                return

            # Collect code files
            code_files = self._collect_code_files(codebase_path, languages)

            logger.info("Found %s code files to index", len(code_files))

            # Index files
            documents = []
            for file_path in code_files:
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    doc_id = str(file_path.relative_to(codebase_path))

                    documents.append(
                        {
                            "id": doc_id,
                            "text": content,
                            "metadata": {
                                "type": "code",
                                "path": doc_id,
                                "extension": file_path.suffix,
                                "language": self._detect_language(file_path.suffix),
                            },
                        }
                    )
                except (OSError, PermissionError) as e:
                    logger.debug("File read error for %s: %s", file_path, e)

            # Add to vector store
            self.vector_store.add_documents(documents)
            self._indexed = True

            logger.info("Indexed %s code files", len(documents))

        except (OSError, PermissionError) as e:
            logger.debug("Codebase indexing filesystem error: %s", e)
        except Exception as e:
            logger.error("Failed to index codebase: %s", e)

    def index_documents(self, documents: list[dict[str, Any]]):
        """
        Index documents for search

        Args:
            documents: List of dicts with 'id', 'text', and optional 'metadata'
        """
        try:
            # Add documents with document type
            for doc in documents:
                doc.setdefault("metadata", {})["type"] = "document"

            self.vector_store.add_documents(documents)
            self._indexed = True

            logger.info("Indexed %s documents", len(documents))

        except Exception as e:
            logger.error("Failed to index documents: %s", e)

    def search_code(self, query: str, top_k: int = 10, language: str | None = None) -> list[dict[str, Any]]:
        """
        Search code semantically

        Args:
            query: Search query
            top_k: Number of results
            language: Optional language filter

        Returns:
            List of code snippets with metadata
        """
        try:
            filter_metadata = {"type": "code"}
            if language:
                filter_metadata["language"] = language

            results = self.vector_store.search(query, top_k, filter_metadata)

            # Format results
            formatted_results = []
            for result in results:
                metadata = result["metadata"]

                # Extract relevant code snippet
                text = result["text"]
                snippet = self._extract_code_snippet(text, query, max_lines=20)

                formatted_results.append(
                    {
                        "file_path": metadata.get("path"),
                        "language": metadata.get("language"),
                        "snippet": snippet,
                        "score": result["score"],
                        "full_text": text,
                    }
                )

            return formatted_results

        except Exception as e:
            logger.error("Failed to search code: %s", e)
            return []

    def search_documents(
        self, query: str, top_k: int = 10, document_type: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Search documents semantically

        Args:
            query: Search query
            top_k: Number of results
            document_type: Optional document type filter

        Returns:
            List of documents with metadata
        """
        try:
            filter_metadata = {"type": "document"}
            if document_type:
                filter_metadata["document_type"] = document_type

            results = self.vector_store.search(query, top_k, filter_metadata)

            # Format results
            formatted_results = []
            for result in results:
                metadata = result["metadata"]
                text = result["text"]

                # Extract relevant snippet
                snippet = self._extract_text_snippet(text, query, max_chars=300)

                formatted_results.append(
                    {
                        "doc_id": result["doc_id"],
                        "title": metadata.get("title", result["doc_id"]),
                        "snippet": snippet,
                        "score": result["score"],
                        "metadata": metadata,
                    }
                )

            return formatted_results

        except Exception as e:
            logger.error("Failed to search documents: %s", e)
            return []

    def search_hybrid(
        self,
        query: str,
        top_k: int = 10,
        semantic_weight: float = 0.7,
        keyword_weight: float = 0.3,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Hybrid search combining semantic and keyword search

        Args:
            query: Search query
            top_k: Number of results
            semantic_weight: Weight for semantic search (0-1)
            keyword_weight: Weight for keyword search (0-1)
            filters: Optional metadata filters

        Returns:
            List of results with combined scores
        """
        try:
            # Semantic search
            semantic_results = self.vector_store.search(query, top_k * 2, filters)

            # Keyword search (simple implementation)
            keyword_results = self._keyword_search(query, top_k * 2, filters)

            # Combine scores
            combined_scores = {}

            # Add semantic scores
            for result in semantic_results:
                doc_id = result["doc_id"]
                combined_scores[doc_id] = {
                    "doc_id": doc_id,
                    "text": result["text"],
                    "metadata": result["metadata"],
                    "semantic_score": result["score"],
                    "keyword_score": 0.0,
                }

            # Add keyword scores
            for result in keyword_results:
                doc_id = result["doc_id"]
                if doc_id in combined_scores:
                    combined_scores[doc_id]["keyword_score"] = result["score"]
                else:
                    combined_scores[doc_id] = {
                        "doc_id": doc_id,
                        "text": result["text"],
                        "metadata": result["metadata"],
                        "semantic_score": 0.0,
                        "keyword_score": result["score"],
                    }

            # Calculate combined score
            for doc_id, data in combined_scores.items():
                data["combined_score"] = (
                    semantic_weight * (1.0 / (1.0 + data["semantic_score"])) + keyword_weight * data["keyword_score"]
                )

            # Sort by combined score and return top_k
            sorted_results = sorted(combined_scores.values(), key=lambda x: x["combined_score"], reverse=True)[:top_k]

            return sorted_results

        except Exception as e:
            logger.error("Failed to perform hybrid search: %s", e)
            return []

    def get_search_suggestions(self, query: str, top_k: int = 5) -> list[str]:
        """
        Get search suggestions based on query

        Args:
            query: Partial query
            top_k: Number of suggestions

        Returns:
            List of suggested queries
        """
        try:
            # Search for similar documents and extract key phrases
            results = self.vector_store.search(query, top_k * 2)

            suggestions = set()
            for result in results:
                text = result["text"]
                # Extract phrases containing query terms
                suggestions.update(self._extract_phrases(text, query))

            return list(suggestions)[:top_k]

        except Exception as e:
            logger.error("Failed to get search suggestions: %s", e)
            return []

    def _collect_code_files(self, base_path: Path, languages: list[str] | None = None) -> list[Path]:
        """Collect code files from directory"""
        code_extensions = {
            "python": [".py"],
            "typescript": [".ts", ".tsx"],
            "javascript": [".js", ".jsx"],
            "java": [".java"],
            "go": [".go"],
            "rust": [".rs"],
            "cpp": [".cpp", ".cc", ".cxx", ".h", ".hpp"],
            "c": [".c", ".h"],
            "ruby": [".rb"],
            "php": [".php"],
            "swift": [".swift"],
            "kotlin": [".kt"],
            "shell": [".sh", ".bash"],
            "sql": [".sql"],
            "yaml": [".yml", ".yaml"],
            "json": [".json"],
            "markdown": [".md"],
            "html": [".html", ".htm"],
            "css": [".css"],
        }

        if languages:
            allowed_extensions = set()
            for lang in languages:
                allowed_extensions.update(code_extensions.get(lang.lower(), []))
        else:
            allowed_extensions = set(ext for exts in code_extensions.values() for ext in exts)

        code_files = []
        for file_path in base_path.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in allowed_extensions:
                code_files.append(file_path)

        return code_files

    def _detect_language(self, extension: str) -> str:
        """Detect programming language from file extension"""
        language_map = {
            ".py": "python",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".js": "javascript",
            ".jsx": "javascript",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            ".cpp": "cpp",
            ".cc": "cpp",
            ".cxx": "cpp",
            ".c": "c",
            ".rb": "ruby",
            ".php": "php",
            ".swift": "swift",
            ".kt": "kotlin",
            ".sh": "shell",
            ".bash": "shell",
            ".sql": "sql",
            ".yml": "yaml",
            ".yaml": "yaml",
            ".json": "json",
            ".md": "markdown",
            ".html": "html",
            ".htm": "html",
            ".css": "css",
        }
        return language_map.get(extension.lower(), "unknown")

    def _extract_code_snippet(self, text: str, query: str, max_lines: int = 20) -> str:
        """Extract relevant code snippet containing query terms"""
        lines = text.split("\n")
        query_terms = set(query.lower().split())

        # Find lines matching query
        matching_lines = []
        for i, line in enumerate(lines):
            line_lower = line.lower()
            if any(term in line_lower for term in query_terms):
                matching_lines.append(i)

        if not matching_lines:
            # Return first max_lines if no matches
            return "\n".join(lines[:max_lines])

        # Extract context around first match
        first_match = matching_lines[0]
        start = max(0, first_match - 5)
        end = min(len(lines), first_match + max_lines - 5)

        snippet_lines = lines[start:end]

        # Add line numbers
        snippet = "\n".join(f"{i+1:4d}: {line}" for i, line in enumerate(snippet_lines, start=start + 1))

        return snippet

    def _extract_text_snippet(self, text: str, query: str, max_chars: int = 300) -> str:
        """Extract relevant text snippet containing query terms"""
        query_lower = query.lower()
        text_lower = text.lower()

        # Find first occurrence
        idx = text_lower.find(query_lower)
        if idx == -1:
            # Return beginning of text
            return text[:max_chars] + "..." if len(text) > max_chars else text

        # Extract context around match
        start = max(0, idx - max_chars // 2)
        end = min(len(text), idx + len(query) + max_chars // 2)

        snippet = text[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."

        return snippet

    def _keyword_search(self, query: str, top_k: int, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Simple keyword search implementation"""
        try:

            # Note: This is a simplified implementation
            # In production, you'd want a proper full-text search engine like Elasticsearch

            # For now, just return empty results
            # The semantic search will handle most cases
            return []

        except Exception as e:
            logger.error("Failed to perform keyword search: %s", e)
            return []

    def _extract_phrases(self, text: str, query: str) -> list[str]:
        """Extract phrases containing query terms"""
        # Simple implementation - extract sentences containing query terms
        sentences = re.split(r"[.!?]", text)
        query_terms = set(query.lower().split())

        phrases = []
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 10:
                continue

            sentence_lower = sentence.lower()
            if any(term in sentence_lower for term in query_terms):
                phrases.append(sentence)

        return phrases

    def get_stats(self) -> dict[str, Any]:
        """Get search service statistics"""
        return {"indexed": self._indexed, "vector_store_stats": self.vector_store.get_stats()}


# Global vector search service instance
vector_search_service = VectorSearchService()

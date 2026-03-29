"""
Helix File Storage Service
===========================

S3-compatible file storage with local filesystem fallback.
Supports upload, download, metadata tracking, and access control.

NOTE: LARGELY SUPERSEDED — apps/backend/routes/file_upload_routes.py provides
the same upload/download/delete/list/stats functionality as direct route handlers
and is already registered in router_registry. This service class is retained as
a reusable abstraction that route handlers could import for file operations.

(c) Helix Collective 2025 - Proprietary Technology Stack
"""

import hashlib
import logging
import mimetypes
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Maximum file sizes per tier
MAX_FILE_SIZES = {
    "free": 10 * 1024 * 1024,
    "pro": 100 * 1024 * 1024,
    "enterprise": 500 * 1024 * 1024,
}

ALLOWED_EXTENSIONS = {
    "documents": {".pdf", ".doc", ".docx", ".txt", ".md", ".rtf", ".odt", ".csv", ".xlsx", ".xls"},
    "images": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"},
    "code": {".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".json", ".yaml", ".yml", ".toml", ".sh", ".sql"},
    "archives": {".zip", ".tar", ".gz", ".7z", ".rar"},
    "data": {".json", ".jsonl", ".csv", ".parquet", ".xml", ".ndjson"},
    "audio": {".mp3", ".wav", ".ogg", ".flac", ".m4a"},
    "video": {".mp4", ".webm", ".avi", ".mov"},
}

ALL_ALLOWED = set()
for exts in ALLOWED_EXTENSIONS.values():
    ALL_ALLOWED.update(exts)


class FileMetadata(BaseModel):
    file_id: str
    filename: str
    original_filename: str
    content_type: str
    size_bytes: int
    size_human: str
    sha256: str
    uploaded_by: str
    uploaded_at: str
    category: str
    storage_backend: str = "local"
    path: str = ""
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FileStorageService:
    def __init__(self, storage_root: str = "/data/files"):
        self.storage_root = Path(storage_root)
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self._metadata: dict[str, FileMetadata] = {}
        self._s3_client = None
        self._s3_bucket = os.getenv("HELIX_S3_BUCKET")
        self.backend = "s3" if self._s3_bucket else "local"
        logger.info("FileStorageService initialized: backend=%s", self.backend)

    @staticmethod
    def _human_size(size_bytes: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"

    @staticmethod
    def _categorize_file(filename: str) -> str:
        ext = Path(filename).suffix.lower()
        for category, extensions in ALLOWED_EXTENSIONS.items():
            if ext in extensions:
                return category
        return "other"

    @staticmethod
    def _compute_sha256(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def validate_file(self, filename: str, size_bytes: int, user_tier: str = "free") -> str | None:
        ext = Path(filename).suffix.lower()
        if ext not in ALL_ALLOWED:
            return f"File type not allowed: {ext}"
        max_size = MAX_FILE_SIZES.get(user_tier, MAX_FILE_SIZES["free"])
        if size_bytes > max_size:
            return f"File too large ({self._human_size(size_bytes)}). Max: {self._human_size(max_size)}"
        if size_bytes == 0:
            return "Empty files are not allowed"
        bad_chars = ["..", "/", chr(92)]
        for ch in bad_chars:
            if ch in filename:
                return "Invalid filename - path traversal detected"
        return None

    async def upload_file(
        self,
        file_data: bytes,
        filename: str,
        user_id: str,
        user_tier: str = "free",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> FileMetadata:
        error = self.validate_file(filename, len(file_data), user_tier)
        if error:
            raise ValueError(error)

        file_id = str(uuid.uuid4())
        ext = Path(filename).suffix.lower()
        safe_filename = f"{file_id}{ext}"
        category = self._categorize_file(filename)
        sha256 = self._compute_sha256(file_data)
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        # Local storage
        user_dir = self.storage_root / user_id / category
        user_dir.mkdir(parents=True, exist_ok=True)
        file_path = user_dir / safe_filename
        file_path.write_bytes(file_data)
        storage_path = str(file_path)

        file_meta = FileMetadata(
            file_id=file_id,
            filename=safe_filename,
            original_filename=filename,
            content_type=content_type,
            size_bytes=len(file_data),
            size_human=self._human_size(len(file_data)),
            sha256=sha256,
            uploaded_by=user_id,
            uploaded_at=datetime.now(UTC).isoformat(),
            category=category,
            storage_backend=self.backend,
            path=storage_path,
            tags=tags or [],
            metadata=metadata or {},
        )

        self._metadata[file_id] = file_meta
        logger.info("File uploaded: %s (%s) by user %s", filename, file_meta.size_human, user_id)
        return file_meta

    async def download_file(self, file_id: str, user_id: str) -> tuple:
        meta = self._metadata.get(file_id)
        if not meta:
            raise FileNotFoundError(f"File {file_id} not found")
        if meta.uploaded_by != user_id:
            raise PermissionError("Access denied")
        file_path = Path(meta.path)
        if not file_path.exists():
            raise FileNotFoundError(f"File data not found at {meta.path}")
        data = file_path.read_bytes()
        return data, meta

    async def delete_file(self, file_id: str, user_id: str) -> bool:
        meta = self._metadata.get(file_id)
        if not meta:
            raise FileNotFoundError(f"File {file_id} not found")
        if meta.uploaded_by != user_id:
            raise PermissionError("Access denied")
        file_path = Path(meta.path)
        if file_path.exists():
            file_path.unlink()
        del self._metadata[file_id]
        return True

    async def list_files(
        self, user_id: str, category: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[FileMetadata]:
        user_files = [
            m
            for m in self._metadata.values()
            if m.uploaded_by == user_id and (category is None or m.category == category)
        ]
        user_files.sort(key=lambda f: f.uploaded_at, reverse=True)
        return user_files[offset : offset + limit]

    async def get_usage(self, user_id: str) -> dict[str, Any]:
        user_files = [m for m in self._metadata.values() if m.uploaded_by == user_id]
        total_bytes = sum(f.size_bytes for f in user_files)
        by_category: dict[str, dict[str, int]] = {}
        for f in user_files:
            if f.category not in by_category:
                by_category[f.category] = {"count": 0, "bytes": 0}
            by_category[f.category]["count"] += 1
            by_category[f.category]["bytes"] += f.size_bytes
        return {
            "total_files": len(user_files),
            "total_bytes": total_bytes,
            "total_human": self._human_size(total_bytes),
            "by_category": {
                cat: {"count": info["count"], "size": self._human_size(info["bytes"])}
                for cat, info in by_category.items()
            },
        }


_file_storage: FileStorageService | None = None


def get_file_storage() -> FileStorageService:
    global _file_storage
    if _file_storage is None:
        storage_root = os.getenv("HELIX_FILE_STORAGE_ROOT", "/data/files")
        _file_storage = FileStorageService(storage_root=storage_root)
    return _file_storage

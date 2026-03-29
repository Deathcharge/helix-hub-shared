"""
Database Backup Service

Provides automated database backup functionality.
Supports PostgreSQL backups with S3/R2 storage.
Parses DATABASE_URL for Railway/production compatibility.
Persists backup metadata to Redis (survives redeploys).
Uses Python gzip (no shell dependency on gzip/gunzip).
"""

import asyncio
import gzip as gzip_module
import json
import os
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from loguru import logger

try:
    import boto3
    from botocore.exceptions import ClientError

    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    logger.warning("boto3 not installed, S3 backups will be limited")

_BACKUP_META_PREFIX = "helix:backup:meta:"
_BACKUP_INDEX_KEY = "helix:backup:index"


async def _get_redis():
    """Get Redis client, returning None if unavailable."""
    try:
        from apps.backend.core.redis_client import get_redis

        return await get_redis()
    except Exception as e:
        logger.debug("Redis unavailable for backup metadata: %s", e)
        return None


def _parse_database_url(url: str) -> dict[str, Any]:
    """Parse a DATABASE_URL into host, port, user, password, dbname."""
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    parsed = urlparse(url)
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "user": parsed.username or "helix",
        "password": parsed.password or "",
        "dbname": (parsed.path or "/helix").lstrip("/") or "helix",
    }


class BackupConfig:
    """Backup configuration"""

    def __init__(self):
        self.backup_type = os.getenv("BACKUP_TYPE", "local")  # local, s3, r2
        self.backup_storage_path = Path(
            os.getenv("BACKUP_STORAGE_PATH", os.path.join(tempfile.gettempdir(), "backups"))
        )
        self.bucket_name = os.getenv("S3_BACKUP_BUCKET", "helix-backups")
        self.region = os.getenv("S3_REGION", "us-east-1")
        self.endpoint_url = os.getenv("S3_ENDPOINT_URL")
        self.access_key_id = os.getenv("S3_ACCESS_KEY_ID")
        self.secret_access_key = os.getenv("S3_SECRET_ACCESS_KEY")

        # Database connection — prefer DATABASE_URL over individual vars
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            parsed = _parse_database_url(database_url)
            self.db_host = parsed["host"]
            self.db_port = parsed["port"]
            self.db_name = parsed["dbname"]
            self.db_user = parsed["user"]
            self.db_password = parsed["password"]
        else:
            self.db_host = os.getenv("DATABASE_HOST", "localhost")
            self.db_port = int(os.getenv("DATABASE_PORT", "5432"))
            self.db_name = os.getenv("DATABASE_NAME", "helix")
            self.db_user = os.getenv("DATABASE_USER", "helix")
            self.db_password = os.getenv("DATABASE_PASSWORD", "")

        # Backup settings
        self.auto_backup_enabled = os.getenv("AUTO_BACKUP_ENABLED", "true").lower() == "true"
        self.auto_backup_time = os.getenv("AUTO_BACKUP_TIME", "02:00")  # 2 AM
        self.retention_days = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))
        self.max_backups = int(os.getenv("MAX_BACKUPS", "100"))


class BackupService:
    """Database backup service"""

    def __init__(self, config: BackupConfig | None = None):
        self.config = config or BackupConfig()
        self._s3_client = None

        # Initialize storage directory
        if self.config.backup_type == "local":
            self._init_local_storage()

    def _safe_backup_path(self, name: str) -> Path:
        """Resolve a backup name to a safe path within backup_storage_path."""
        base = self.config.backup_storage_path.resolve()
        target = (base / name).resolve()
        if not str(target).startswith(str(base)):
            raise ValueError("Invalid backup name — path traversal detected")
        return target

    def _init_local_storage(self):
        """Initialize local backup storage"""
        try:
            self.config.backup_storage_path.mkdir(parents=True, exist_ok=True)
            logger.info("Backup storage initialized: %s", self.config.backup_storage_path)
        except (OSError, PermissionError) as e:
            logger.debug("Backup storage initialization error: %s", e)
            raise
        except Exception as e:
            logger.error("Failed to initialize backup storage: %s", e)
            raise

    def _get_s3_client(self):
        """Get or create S3 client"""
        if self._s3_client is None:
            if not BOTO3_AVAILABLE:
                raise RuntimeError("boto3 is required for S3/R2 backups")

            self._s3_client = boto3.client(
                "s3",
                region_name=self.config.region,
                endpoint_url=self.config.endpoint_url,
                aws_access_key_id=self.config.access_key_id,
                aws_secret_access_key=self.config.secret_access_key,
            )
            logger.info("S3 client initialized for backups: %s", self.config.backup_type)

        return self._s3_client

    async def _persist_backup_meta(self, backup_id: str, meta: dict[str, Any]) -> None:
        """Persist backup metadata to Redis."""
        r = await _get_redis()
        if not r:
            return
        try:
            key = f"{_BACKUP_META_PREFIX}{backup_id}"
            await r.set(key, json.dumps(meta, default=str))
            ts = datetime.fromisoformat(meta.get("created_at", datetime.now(UTC).isoformat())).timestamp()
            await r.zadd(_BACKUP_INDEX_KEY, {backup_id: ts})
        except Exception as e:
            logger.warning("Failed to persist backup metadata to Redis: %s", e)

    async def _load_backup_meta(self, backup_id: str) -> dict[str, Any] | None:
        """Load backup metadata from Redis."""
        r = await _get_redis()
        if not r:
            return None
        try:
            data = await r.get(f"{_BACKUP_META_PREFIX}{backup_id}")
            if data:
                raw = data.decode() if isinstance(data, bytes) else data
                return json.loads(raw)
        except Exception as e:
            logger.debug("Failed to load backup meta %s: %s", backup_id, e)
        return None

    async def _load_all_backup_meta(self, limit: int = 200) -> dict[str, dict[str, Any]]:
        """Load all backup metadata from Redis."""
        r = await _get_redis()
        if not r:
            return {}
        result: dict[str, dict[str, Any]] = {}
        try:
            ids = await r.zrevrange(_BACKUP_INDEX_KEY, 0, limit - 1)
            if not ids:
                return result
            keys = [f"{_BACKUP_META_PREFIX}{(i.decode() if isinstance(i, bytes) else i)}" for i in ids]
            values = await r.mget(keys)
            for raw_id, val in zip(ids, values):
                if val:
                    bid = raw_id.decode() if isinstance(raw_id, bytes) else raw_id
                    raw = val.decode() if isinstance(val, bytes) else val
                    result[bid] = json.loads(raw)
        except Exception as e:
            logger.warning("Failed to load backup metadata from Redis: %s", e)
        return result

    async def _delete_backup_meta(self, backup_id: str) -> None:
        """Delete backup metadata from Redis."""
        r = await _get_redis()
        if not r:
            return
        try:
            await r.delete(f"{_BACKUP_META_PREFIX}{backup_id}")
            await r.zrem(_BACKUP_INDEX_KEY, backup_id)
        except Exception as e:
            logger.warning("Failed to delete backup meta %s: %s", backup_id, e)

    def _generate_backup_name(self) -> str:
        """Generate backup filename"""
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        return f"backup_{self.config.db_name}_{timestamp}.sql.gz"

    def _generate_backup_key(self, backup_name: str) -> str:
        """Generate S3 key for backup"""
        date_path = datetime.now(UTC).strftime("%Y/%m/%d")
        return f"backups/{self.config.db_name}/{date_path}/{backup_name}"

    async def create_backup(
        self, backup_name: str | None = None, description: str | None = None
    ) -> dict[str, Any]:
        """
        Create database backup

        Args:
            backup_name: Optional custom backup name
            description: Optional backup description

        Returns:
            Backup metadata
        """
        try:
            timestamp = datetime.now(UTC)
            backup_name = backup_name or self._generate_backup_name()

            logger.info("Creating backup: %s", backup_name)

            # Create backup file
            backup_path = await self._dump_database()

            # Store backup
            if self.config.backup_type == "local":
                result = await self._store_local(backup_name, backup_path)
            else:
                result = await self._store_s3(backup_name, backup_path)

            # Clean up temporary file
            backup_path.unlink(missing_ok=True)

            # Store metadata to Redis
            backup_id = result.get("backup_id", backup_name)
            meta = {
                "backup_id": backup_id,
                "name": backup_name,
                "description": description,
                "created_at": timestamp.isoformat(),
                "size": result.get("size"),
                "storage_type": self.config.backup_type,
                "status": "completed",
            }
            await self._persist_backup_meta(backup_id, meta)

            logger.info("Backup created successfully: %s", backup_id)
            return meta

        except Exception as e:
            logger.error("Failed to create backup: %s", e)
            raise

    async def _dump_database(self) -> Path:
        """Dump database to a gzip-compressed file."""
        temp_path = None
        try:
            # Create temporary file for the raw SQL dump
            temp_file = tempfile.NamedTemporaryFile(suffix=".sql", delete=False, dir=self.config.backup_storage_path)
            temp_path = Path(temp_file.name)
            temp_file.close()

            # Build pg_dump command
            pg_dump_cmd = [
                "pg_dump",
                "-h",
                self.config.db_host,
                "-p",
                str(self.config.db_port),
                "-U",
                self.config.db_user,
                "-d",
                self.config.db_name,
                "-F",
                "p",  # Plain text format
                "--no-owner",
                "--no-acl",
                "-f",
                str(temp_path),
            ]

            # Set password environment variable
            env = os.environ.copy()
            env["PGPASSWORD"] = self.config.db_password

            # Execute pg_dump
            result = subprocess.run(pg_dump_cmd, env=env, capture_output=True, text=True, timeout=600)

            if result.returncode != 0:
                logger.error("pg_dump failed: %s", result.stderr)
                raise RuntimeError("Database dump failed — check server logs")

            # Compress using Python gzip (no shell dependency)
            compressed_path = temp_path.with_suffix(".sql.gz")
            with open(temp_path, "rb") as f_in, gzip_module.open(compressed_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

            # Remove uncompressed file
            temp_path.unlink(missing_ok=True)

            logger.info("Database dumped to: %s", compressed_path)
            return compressed_path

        except Exception as e:
            # Clean up temp files on failure
            if temp_path:
                temp_path.unlink(missing_ok=True)
                temp_path.with_suffix(".sql.gz").unlink(missing_ok=True)
            logger.error("Failed to dump database: %s", e)
            raise

    async def _store_local(self, backup_name: str, backup_path: Path) -> dict[str, Any]:
        """Store backup locally"""
        try:
            final_path = self._safe_backup_path(backup_name)

            if backup_path != final_path:
                backup_path.rename(final_path)

            size = final_path.stat().st_size

            return {"backup_id": backup_name, "file_path": str(final_path), "size": size, "storage_type": "local"}

        except Exception as e:
            logger.error("Local storage failed: %s", e)
            raise

    async def _store_s3(self, backup_name: str, backup_path: Path) -> dict[str, Any]:
        """Store backup in S3/R2"""
        try:
            s3_client = self._get_s3_client()
            backup_key = self._generate_backup_key(backup_name)

            # Upload to S3
            s3_client.upload_file(str(backup_path), self.config.bucket_name, backup_key)

            size = backup_path.stat().st_size

            return {
                "backup_id": backup_key,
                "file_path": backup_key,
                "size": size,
                "storage_type": self.config.backup_type,
            }

        except ClientError as e:
            logger.error("S3 upload failed: %s", e)
            raise

    async def list_backups(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """
        List all backups

        Args:
            limit: Maximum number of backups
            offset: Pagination offset

        Returns:
            List of backup metadata
        """
        try:
            if self.config.backup_type == "local":
                return await self._list_local_backups(limit, offset)
            else:
                return await self._list_s3_backups(limit, offset)

        except Exception as e:
            logger.error("Failed to list backups: %s", e)
            return []

    async def _list_local_backups(self, limit: int, offset: int) -> list[dict[str, Any]]:
        """List local backups"""
        backups = []

        for backup_file in self.config.backup_storage_path.glob("backup_*.sql.gz"):
            try:
                stat = backup_file.stat()
                backup_name = backup_file.name

                backups.append(
                    {
                        "backup_id": backup_name,
                        "name": backup_name,
                        "created_at": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
                        "size": stat.st_size,
                        "storage_type": "local",
                        "status": "completed",
                    }
                )
            except Exception as e:
                logger.warning("Failed to read backup info for %s: %s", backup_file, e)

        # Sort by creation date (newest first) and paginate
        backups.sort(key=lambda x: x["created_at"], reverse=True)
        return backups[offset : offset + limit]

    async def _list_s3_backups(self, limit: int, offset: int) -> list[dict[str, Any]]:
        """List S3 backups"""
        try:
            s3_client = self._get_s3_client()
            prefix = f"backups/{self.config.db_name}/"

            backups = []

            paginator = s3_client.get_paginator("list_objects_v2")

            for page in paginator.paginate(Bucket=self.config.bucket_name, Prefix=prefix):
                if "Contents" in page:
                    for obj in page["Contents"]:
                        backups.append(
                            {
                                "backup_id": obj["Key"],
                                "name": Path(obj["Key"]).name,
                                "created_at": obj["LastModified"].isoformat(),
                                "size": obj["Size"],
                                "storage_type": "s3",
                                "status": "completed",
                            }
                        )

            # Sort by creation date (newest first) and paginate
            backups.sort(key=lambda x: x["created_at"], reverse=True)
            return backups[offset : offset + limit]

        except ClientError as e:
            logger.error("S3 list failed: %s", e)
            return []

    async def get_backup_info(self, backup_id: str) -> dict[str, Any] | None:
        """
        Get backup information

        Args:
            backup_id: Backup identifier

        Returns:
            Backup metadata or None
        """
        try:
            # Check Redis metadata first
            meta = await self._load_backup_meta(backup_id)
            if meta:
                return meta

            # Fetch from storage
            if self.config.backup_type == "local":
                return await self._get_local_backup_info(backup_id)
            else:
                return await self._get_s3_backup_info(backup_id)

        except Exception as e:
            logger.error("Failed to get backup info: %s", e)
            return None

    async def _get_local_backup_info(self, backup_id: str) -> dict[str, Any] | None:
        """Get local backup info"""
        backup_path = self._safe_backup_path(backup_id)

        if not backup_path.exists():
            return None

        stat = backup_path.stat()

        return {
            "backup_id": backup_id,
            "name": backup_id,
            "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "size": stat.st_size,
            "storage_type": "local",
            "status": "completed",
        }

    async def _get_s3_backup_info(self, backup_id: str) -> dict[str, Any] | None:
        """Get S3 backup info"""
        try:
            s3_client = self._get_s3_client()

            response = s3_client.head_object(Bucket=self.config.bucket_name, Key=backup_id)

            return {
                "backup_id": backup_id,
                "name": Path(backup_id).name,
                "created_at": response["LastModified"].isoformat(),
                "size": response["ContentLength"],
                "storage_type": "s3",
                "status": "completed",
            }

        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return None
            raise

    async def restore_backup(self, backup_id: str) -> bool:
        """
        Restore database from backup

        Args:
            backup_id: Backup identifier

        Returns:
            True if restored successfully
        """
        try:
            logger.info("Restoring backup: %s", backup_id)

            # Download backup
            backup_path = await self._download_backup(backup_id)

            # Decompress using Python gzip (no shell dependency)
            decompressed_path = backup_path.with_suffix(".sql")
            with gzip_module.open(backup_path, "rb") as f_in, open(decompressed_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

            # Restore database
            await self._restore_database(decompressed_path)

            # Clean up
            decompressed_path.unlink(missing_ok=True)

            logger.info("Backup restored successfully: %s", backup_id)
            return True

        except Exception as e:
            logger.error("Failed to restore backup: %s", e)
            raise

    async def _download_backup(self, backup_id: str) -> Path:
        """Download backup"""
        if self.config.backup_type == "local":
            return await self._download_local_backup(backup_id)
        else:
            return await self._download_s3_backup(backup_id)

    async def _download_local_backup(self, backup_id: str) -> Path:
        """Download local backup (just return path)"""
        backup_path = self._safe_backup_path(backup_id)

        if not backup_path.exists():
            raise FileNotFoundError(f"Backup not found: {backup_id}")

        return backup_path

    async def _download_s3_backup(self, backup_id: str) -> Path:
        """Download S3 backup"""
        try:
            s3_client = self._get_s3_client()

            # Download to temp file
            temp_file = tempfile.NamedTemporaryFile(suffix=".sql.gz", delete=False, dir=self.config.backup_storage_path)
            temp_path = Path(temp_file.name)
            temp_file.close()

            s3_client.download_file(self.config.bucket_name, backup_id, str(temp_path))

            return temp_path

        except ClientError as e:
            logger.error("S3 download failed: %s", e)
            raise

    async def _restore_database(self, backup_path: Path):
        """Restore database from backup file"""
        try:
            # Build psql command
            psql_cmd = [
                "psql",
                "-h",
                self.config.db_host,
                "-p",
                str(self.config.db_port),
                "-U",
                self.config.db_user,
                "-d",
                self.config.db_name,
                "-f",
                str(backup_path),
            ]

            # Set password environment variable
            env = os.environ.copy()
            env["PGPASSWORD"] = self.config.db_password

            # Execute psql
            result = subprocess.run(psql_cmd, env=env, capture_output=True, text=True, timeout=600)

            if result.returncode != 0:
                logger.error("psql restore failed: %s", result.stderr)
                raise RuntimeError("Database restore failed — check server logs")

            logger.info("Database restored from: %s", backup_path)

        except Exception as e:
            logger.error("Failed to restore database: %s", e)
            raise

    async def delete_backup(self, backup_id: str) -> bool:
        """
        Delete backup

        Args:
            backup_id: Backup identifier

        Returns:
            True if deleted successfully
        """
        try:
            if self.config.backup_type == "local":
                return await self._delete_local_backup(backup_id)
            else:
                return await self._delete_s3_backup(backup_id)

        except Exception as e:
            logger.error("Failed to delete backup: %s", e)
            raise

    async def _delete_local_backup(self, backup_id: str) -> bool:
        """Delete local backup"""
        backup_path = self._safe_backup_path(backup_id)

        if backup_path.exists():
            backup_path.unlink()
            await self._delete_backup_meta(backup_id)
            logger.info("Local backup deleted: %s", backup_id)
            return True

        return False

    async def _delete_s3_backup(self, backup_id: str) -> bool:
        """Delete S3 backup"""
        try:
            s3_client = self._get_s3_client()

            s3_client.delete_object(Bucket=self.config.bucket_name, Key=backup_id)
            await self._delete_backup_meta(backup_id)

            logger.info("S3 backup deleted: %s", backup_id)
            return True

        except ClientError as e:
            logger.error("S3 delete failed: %s", e)
            raise

    async def cleanup_old_backups(self):
        """Delete backups older than retention period"""
        try:
            cutoff_date = datetime.now(UTC) - timedelta(days=self.config.retention_days)
            backups = await self.list_backups(limit=1000, offset=0)

            deleted = 0
            for backup in backups:
                created_at = datetime.fromisoformat(backup["created_at"])
                if created_at < cutoff_date:
                    try:
                        await self.delete_backup(backup["backup_id"])
                        deleted += 1
                    except Exception as e:
                        logger.warning("Failed to delete old backup %s: %s", backup["backup_id"], e)

            logger.info("Cleanup completed: %s old backups deleted", deleted)

        except Exception as e:
            logger.error("Failed to cleanup old backups: %s", e)

    def get_backup_schedule(self) -> dict[str, Any]:
        """Get backup schedule configuration"""
        return {
            "auto_backup_enabled": self.config.auto_backup_enabled,
            "auto_backup_time": self.config.auto_backup_time,
            "retention_days": self.config.retention_days,
            "max_backups": self.config.max_backups,
        }

    async def verify_backup(self, backup_id: str) -> dict[str, Any]:
        """
        Verify backup integrity

        Args:
            backup_id: Backup identifier

        Returns:
            Verification results
        """
        try:
            info = await self.get_backup_info(backup_id)

            if not info:
                return {"backup_id": backup_id, "valid": False, "error": "Backup not found"}

            # Basic checks
            valid = True
            errors = []

            # Check file size
            if info.get("size", 0) == 0:
                valid = False
                errors.append("Backup file is empty")

            # Check creation date
            try:
                created_at = datetime.fromisoformat(info["created_at"])
                if created_at > datetime.now(UTC):
                    valid = False
                    errors.append("Backup creation date is in the future")
            except Exception as e:
                logger.warning("Backup %s has invalid creation date: %s", backup_id, e)
                errors.append(f"Invalid creation date: {e}")

            return {
                "backup_id": backup_id,
                "valid": valid,
                "errors": errors,
                "verified_at": datetime.now(UTC).isoformat(),
            }

        except Exception as e:
            logger.error("Failed to verify backup: %s", e)
            return {"backup_id": backup_id, "valid": False, "error": "Backup verification failed"}


# Global backup service instance
backup_service = BackupService()

# ---------------------------------------------------------------------------
# Scheduled backup loop
# ---------------------------------------------------------------------------

_backup_scheduler_task: asyncio.Task | None = None


async def _scheduled_backup_loop() -> None:
    """Run automated backups at the configured time (UTC).

    Runs as a long-lived asyncio task started from the app lifespan.
    Each iteration sleeps until the next scheduled time, creates a backup,
    then cleans up expired backups.
    """
    config = backup_service.config
    if not config.auto_backup_enabled:
        logger.info("Automated backups disabled (AUTO_BACKUP_ENABLED=false)")
        return

    logger.info(
        "Backup scheduler started — next backup at %s UTC daily (retention: %d days)",
        config.auto_backup_time,
        config.retention_days,
    )

    while True:
        try:
            # Parse target hour:minute
            parts = config.auto_backup_time.split(":")
            target_hour = int(parts[0])
            target_minute = int(parts[1]) if len(parts) > 1 else 0

            now = datetime.now(UTC)
            target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)

            # If target is in the past today, schedule for tomorrow
            if target <= now:
                target += timedelta(days=1)

            sleep_seconds = (target - now).total_seconds()
            logger.debug("Backup scheduler sleeping %.0f seconds until %s", sleep_seconds, target.isoformat())
            await asyncio.sleep(sleep_seconds)

            # Run backup
            logger.info("Starting scheduled backup...")
            result = await backup_service.create_backup(description="Automated daily backup")
            logger.info(
                "Scheduled backup complete: %s (%s bytes)",
                result.get("backup_id"),
                result.get("size"),
            )

            # Cleanup old backups
            await backup_service.cleanup_old_backups()

        except asyncio.CancelledError:
            logger.info("Backup scheduler cancelled")
            return
        except Exception as e:
            logger.error("Scheduled backup failed: %s", e)
            # Wait 1 hour before retrying after a failure
            await asyncio.sleep(3600)


async def start_backup_scheduler() -> None:
    """Start the backup scheduler as a background task.

    Called from the FastAPI lifespan. Safe to call multiple times
    (subsequent calls are no-ops).
    """
    global _backup_scheduler_task
    if _backup_scheduler_task and not _backup_scheduler_task.done():
        return
    _backup_scheduler_task = asyncio.create_task(_scheduled_backup_loop())


async def stop_backup_scheduler() -> None:
    """Cancel the backup scheduler gracefully."""
    global _backup_scheduler_task
    if _backup_scheduler_task and not _backup_scheduler_task.done():
        _backup_scheduler_task.cancel()
        try:
            await _backup_scheduler_task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("Backup scheduler exited unexpectedly: %s", e)
    _backup_scheduler_task = None

"""
S3-Compatible Storage Service

Provides unified interface for file storage operations.
Supports both local filesystem (development) and S3/R2 (production).
"""

import hashlib
import mimetypes
import os
import posixpath
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

import aiofiles
from fastapi import HTTPException, UploadFile
from loguru import logger

try:
    import boto3
    from botocore.exceptions import ClientError

    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    logger.warning("boto3 not installed, using local storage only")


import tempfile


class StorageConfig:
    """Storage configuration"""

    def __init__(self):
        self.storage_type = os.getenv("STORAGE_TYPE", "local")  # local, s3, r2
        self.local_storage_path = Path(
            os.getenv("LOCAL_STORAGE_PATH", os.path.join(tempfile.gettempdir(), "helix_storage"))
        )
        self.bucket_name = os.getenv("S3_BUCKET_NAME", "helix-uploads")
        self.region = os.getenv("S3_REGION", "us-east-1")
        _raw_endpoint = os.getenv("S3_ENDPOINT_URL")
        # Ensure endpoint has a scheme — boto3 requires a full URL
        if _raw_endpoint and not _raw_endpoint.startswith("http"):
            _raw_endpoint = f"https://{_raw_endpoint}"
        self.endpoint_url = _raw_endpoint
        self.access_key_id = os.getenv("S3_ACCESS_KEY_ID")
        self.secret_access_key = os.getenv("S3_SECRET_ACCESS_KEY")
        self.max_file_size = int(os.getenv("MAX_FILE_SIZE", str(100 * 1024 * 1024)))  # 100MB default
        self.allowed_extensions = set(
            os.getenv("ALLOWED_FILE_EXTENSIONS", "jpg,jpeg,png,gif,pdf,doc,docx,txt,csv,xls,xlsx,zip,tar,gz").split(",")
        )
        self.url_expiry_seconds = int(os.getenv("STORAGE_URL_EXPIRY", "3600"))  # 1 hour default


class StorageService:
    """S3-compatible storage service"""

    def __init__(self, config: StorageConfig | None = None):
        self.config = config or StorageConfig()
        self._s3_client = None
        self._local_storage_initialized = False

        # Initialize local storage directory
        if self.config.storage_type == "local":
            self._init_local_storage()

    def _init_local_storage(self):
        """Initialize local storage directory"""
        try:
            self.config.local_storage_path.mkdir(parents=True, exist_ok=True)
            self._local_storage_initialized = True
            logger.info("Local storage initialized: %s", self.config.local_storage_path)
        except (OSError, PermissionError) as e:
            logger.error("Failed to initialize local storage (filesystem error): %s", e)
            raise
        except Exception as e:
            logger.error("Failed to initialize local storage: %s", e)
            raise

    def _get_s3_client(self):
        """Get or create S3 client"""
        if self._s3_client is None:
            if not BOTO3_AVAILABLE:
                raise RuntimeError("boto3 is required for S3/R2 storage")

            self._s3_client = boto3.client(
                "s3",
                region_name=self.config.region,
                endpoint_url=self.config.endpoint_url,
                aws_access_key_id=self.config.access_key_id,
                aws_secret_access_key=self.config.secret_access_key,
            )
            logger.info("S3 client initialized: %s", self.config.storage_type)

        return self._s3_client

    def _generate_file_key(self, user_id: str, filename: str) -> str:
        """Generate unique file key"""
        # Create hash of filename + timestamp for uniqueness
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        hash_input = f"{user_id}_{filename}_{timestamp}".encode()
        file_hash = hashlib.md5(hash_input).hexdigest()[:8]

        # Extract extension
        ext = Path(filename).suffix.lower()

        # Create key: uploads/user_id/YYYY/MM/hash.ext
        date_path = datetime.now(UTC).strftime("%Y/%m")
        return f"uploads/{user_id}/{date_path}/{file_hash}{ext}"

    async def validate_file(self, file: UploadFile) -> dict[str, Any]:
        """
        Validate uploaded file

        Returns:
            Dict with validation results and metadata
        """
        # Check file extension first (cheap check before reading bytes)
        filename = file.filename or "unknown"
        ext = Path(filename).suffix.lower().lstrip(".")

        if ext not in self.config.allowed_extensions:
            raise HTTPException(
                status_code=415,
                detail=f"File type '.{ext}' is not allowed. Allowed types: {', '.join(sorted(self.config.allowed_extensions))}",
            )

        # Validate MIME type from filename
        mime_type, _ = mimetypes.guess_type(filename)
        if not mime_type:
            logger.warning("Could not determine MIME type for %s", filename)

        # Read file in chunks to enforce the size limit without loading the entire
        # file into memory upfront (prevents OOM when Content-Length is absent).
        max_size = self.config.max_file_size
        _chunk_size = 65536  # 64 KB chunks
        chunks = []
        total_bytes = 0
        sha = hashlib.sha256()
        while True:
            chunk = await file.read(_chunk_size)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > max_size:
                raise HTTPException(
                    status_code=413,
                    detail=f"File size exceeds maximum allowed size of {max_size / (1024*1024):.0f}MB",
                )
            sha.update(chunk)
            chunks.append(chunk)

        content = b"".join(chunks)
        file_hash = sha.hexdigest()

        # Reset file pointer for callers that need to re-read the content
        await file.seek(0)

        return {
            "filename": filename,
            "extension": ext,
            "mime_type": mime_type,
            "size": total_bytes,
            "hash": file_hash,
            "is_valid": True,
        }

    async def upload_file(
        self, file: UploadFile, user_id: str, metadata: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Upload file to storage

        Args:
            file: UploadFile object
            user_id: User ID for file organization
            metadata: Optional metadata to store with file

        Returns:
            Dict with file information including URL
        """
        try:
            # Validate file
            validation_result = await self.validate_file(file)

            # Generate file key
            file_key = self._generate_file_key(user_id, file.filename or "unknown")

            # Upload based on storage type
            if self.config.storage_type == "local":
                result = await self._upload_local(file, file_key)
            else:
                result = await self._upload_s3(file, file_key)

            # Add metadata
            result.update(
                {
                    "user_id": user_id,
                    "filename": file.filename,
                    "mime_type": validation_result["mime_type"],
                    "size": validation_result["size"],
                    "hash": validation_result["hash"],
                    "storage_type": self.config.storage_type,
                    "uploaded_at": datetime.now(UTC).isoformat(),
                    "metadata": metadata or {},
                }
            )

            logger.info("File uploaded successfully: %s", file_key)
            return result

        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to upload file: %s", e)
            raise HTTPException(status_code=500, detail="File upload failed")

    async def _upload_local(self, file: UploadFile, file_key: str) -> dict[str, Any]:
        """Upload to local filesystem"""
        try:
            file_path = self.config.local_storage_path / file_key
            file_path.parent.mkdir(parents=True, exist_ok=True)

            async with aiofiles.open(file_path, "wb") as f:
                content = await file.read()
                await f.write(content)

            return {"file_key": file_key, "file_path": str(file_path), "url": f"/api/files/download/{file_key}"}

        except Exception as e:
            logger.error("Local upload failed: %s", e)
            raise

    async def _upload_s3(self, file: UploadFile, file_key: str) -> dict[str, Any]:
        """Upload to S3/R2"""
        try:
            s3_client = self._get_s3_client()

            content = await file.read()

            s3_client.put_object(
                Bucket=self.config.bucket_name,
                Key=file_key,
                Body=content,
                ContentType=file.content_type,
                Metadata={"uploaded_by": "helix"},
            )

            # Generate presigned URL
            url = s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.config.bucket_name, "Key": file_key},
                ExpiresIn=self.config.url_expiry_seconds,
            )

            return {
                "file_key": file_key,
                "bucket": self.config.bucket_name,
                "url": url,
                "expires_in": self.config.url_expiry_seconds,
            }

        except ClientError as e:
            logger.error("S3 upload failed: %s", e)
            raise HTTPException(status_code=500, detail="Storage upload failed")

    async def download_file(self, file_key: str, user_id: str | None = None) -> tuple[BinaryIO, str, str]:
        """
        Download file from storage

        Args:
            file_key: File key to download
            user_id: Optional user ID for access control

        Returns:
            Tuple of (file_stream, filename, content_type)
        """
        try:
            # Verify user owns the file (if user_id provided)
            if user_id:
                expected_prefix = f"uploads/{user_id}/"
                # Normalize the key first to resolve any '..' traversal attempts
                normalized_key = posixpath.normpath(file_key)
                # Reject absolute paths or keys that escape the uploads directory
                if normalized_key.startswith("/") or normalized_key.startswith(".."):
                    logger.warning("User %s path traversal attempt with key %s", user_id, file_key)
                    raise HTTPException(status_code=403, detail="Access denied")
                if not normalized_key.startswith(expected_prefix):
                    logger.warning("User %s attempted to access %s", user_id, file_key)
                    raise HTTPException(status_code=403, detail="Access denied")

            # Download based on storage type
            if self.config.storage_type == "local":
                return await self._download_local(file_key)
            else:
                return await self._download_s3(file_key)

        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to download file: %s", e)
            raise HTTPException(status_code=500, detail="File download failed")

    async def _download_local(self, file_key: str) -> tuple[BinaryIO, str, str]:
        """Download from local filesystem"""
        try:
            file_path = self.config.local_storage_path / file_key

            if not file_path.exists():
                raise HTTPException(status_code=404, detail="File not found")

            # Get filename from key
            filename = Path(file_key).name

            # Guess content type
            mime_type, _ = mimetypes.guess_type(filename)
            mime_type = mime_type or "application/octet-stream"

            # Open file
            file_stream = open(file_path, "rb")

            return file_stream, filename, mime_type

        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="File not found")

    async def _download_s3(self, file_key: str) -> tuple[BinaryIO, str, str]:
        """Download from S3/R3"""
        try:
            s3_client = self._get_s3_client()

            response = s3_client.get_object(Bucket=self.config.bucket_name, Key=file_key)

            # Get filename from key
            filename = Path(file_key).name

            # Get content type
            content_type = response.get("ContentType", "application/octet-stream")

            # Return file-like object
            return response["Body"], filename, content_type

        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                raise HTTPException(status_code=404, detail="File not found")
            raise HTTPException(status_code=500, detail="File download failed")

    async def delete_file(self, file_key: str, user_id: str | None = None) -> bool:
        """
        Delete file from storage

        Args:
            file_key: File key to delete
            user_id: Optional user ID for access control

        Returns:
            True if deleted successfully
        """
        try:
            # Verify user owns the file (if user_id provided)
            if user_id:
                expected_prefix = f"uploads/{user_id}/"
                # Normalize to prevent '..' path traversal (mirrors download_file logic)
                normalized_key = posixpath.normpath(file_key)
                if normalized_key.startswith("/") or normalized_key.startswith(".."):
                    logger.warning("User %s path traversal attempt with key %s", user_id, file_key)
                    raise HTTPException(status_code=403, detail="Access denied")
                if not normalized_key.startswith(expected_prefix):
                    logger.warning("User %s attempted to delete %s", user_id, file_key)
                    raise HTTPException(status_code=403, detail="Access denied")

            # Delete based on storage type
            if self.config.storage_type == "local":
                return await self._delete_local(file_key)
            else:
                return await self._delete_s3(file_key)

        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to delete file: %s", e)
            raise HTTPException(status_code=500, detail="File deletion failed")

    async def _delete_local(self, file_key: str) -> bool:
        """Delete from local filesystem"""
        try:
            file_path = self.config.local_storage_path / file_key

            if file_path.exists():
                file_path.unlink()
                logger.info("File deleted locally: %s", file_key)
                return True

            raise HTTPException(status_code=404, detail="File not found")

        except Exception as e:
            logger.error("Local delete failed: %s", e)
            raise

    async def _delete_s3(self, file_key: str) -> bool:
        """Delete from S3/R2"""
        try:
            s3_client = self._get_s3_client()

            s3_client.delete_object(Bucket=self.config.bucket_name, Key=file_key)

            logger.info("File deleted from S3: %s", file_key)
            return True

        except ClientError as e:
            logger.error("S3 delete failed: %s", e)
            raise HTTPException(status_code=500, detail="File deletion failed")

    async def list_user_files(self, user_id: str, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """
        List all files for a user

        Args:
            user_id: User ID
            limit: Maximum number of files to return
            offset: Pagination offset

        Returns:
            List of file metadata
        """
        try:
            if self.config.storage_type == "local":
                return await self._list_local(user_id, limit, offset)
            else:
                return await self._list_s3(user_id, limit, offset)

        except Exception as e:
            logger.error("Failed to list files: %s", e)
            return []

    async def _list_local(self, user_id: str, limit: int, offset: int) -> list[dict[str, Any]]:
        """List files from local filesystem"""
        files = []
        user_path = self.config.local_storage_path / f"uploads/{user_id}"

        if not user_path.exists():
            return files

        # Walk through all user files
        for file_path in user_path.rglob("*"):
            if file_path.is_file():
                relative_path = file_path.relative_to(self.config.local_storage_path)
                file_key = str(relative_path)

                stat = file_path.stat()
                files.append(
                    {
                        "file_key": file_key,
                        "filename": file_path.name,
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "storage_type": "local",
                    }
                )

        # Sort by modified date (newest first) and paginate
        files.sort(key=lambda x: x["modified"], reverse=True)
        return files[offset : offset + limit]

    async def _list_s3(self, user_id: str, limit: int, offset: int) -> list[dict[str, Any]]:
        """List files from S3/R2"""
        try:
            s3_client = self._get_s3_client()

            prefix = f"uploads/{user_id}/"
            files = []

            paginator = s3_client.get_paginator("list_objects_v2")

            for page in paginator.paginate(Bucket=self.config.bucket_name, Prefix=prefix):
                if "Contents" in page:
                    for obj in page["Contents"]:
                        files.append(
                            {
                                "file_key": obj["Key"],
                                "filename": Path(obj["Key"]).name,
                                "size": obj["Size"],
                                "modified": obj["LastModified"].isoformat(),
                                "storage_type": "s3",
                            }
                        )

            # Sort by modified date (newest first) and paginate
            files.sort(key=lambda x: x["modified"], reverse=True)
            return files[offset : offset + limit]

        except ClientError as e:
            logger.error("S3 list failed: %s", e)
            return []

    async def get_file_info(self, file_key: str, user_id: str | None = None) -> dict[str, Any]:
        """
        Get file metadata

        Args:
            file_key: File key
            user_id: Optional user ID for access control

        Returns:
            File metadata
        """
        try:
            # Verify user owns the file (if user_id provided)
            if user_id:
                expected_prefix = f"uploads/{user_id}/"
                if not file_key.startswith(expected_prefix):
                    raise HTTPException(status_code=403, detail="Access denied")

            if self.config.storage_type == "local":
                return await self._get_info_local(file_key)
            else:
                return await self._get_info_s3(file_key)

        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to get file info: %s", e)
            raise HTTPException(status_code=500, detail="Failed to get file info")

    async def _get_info_local(self, file_key: str) -> dict[str, Any]:
        """Get file info from local filesystem"""
        file_path = self.config.local_storage_path / file_key

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")

        stat = file_path.stat()

        return {
            "file_key": file_key,
            "filename": file_path.name,
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "storage_type": "local",
        }

    async def _get_info_s3(self, file_key: str) -> dict[str, Any]:
        """Get file info from S3/R2"""
        try:
            s3_client = self._get_s3_client()

            response = s3_client.head_object(Bucket=self.config.bucket_name, Key=file_key)

            return {
                "file_key": file_key,
                "filename": Path(file_key).name,
                "size": response["ContentLength"],
                "modified": response["LastModified"].isoformat(),
                "content_type": response.get("ContentType", "application/octet-stream"),
                "etag": response.get("ETag", "").strip('"'),
                "storage_type": "s3",
            }

        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                raise HTTPException(status_code=404, detail="File not found")
            raise HTTPException(status_code=500, detail="Failed to get file info")


# Global storage service instance
storage_service = StorageService()

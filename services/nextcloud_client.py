#!/usr/bin/env python3
"""
☁️ Helix Collective - Nextcloud Storage Client
services/nextcloud_client.py

Provides WebDAV integration with Nextcloud for:
- UCF state backups
- Discord archive storage
- Configuration file sync
- Long-term data persistence

Environment Variables:
- NEXTCLOUD_URL: https://your-instance.nextcloud.com
- NEXTCLOUD_USER: your-username
- NEXTCLOUD_PASSWORD: your-app-password
- NEXTCLOUD_BASE_PATH: /Helix (default remote folder)
"""

import io
import logging
import os
from pathlib import Path

# NOTE: Do NOT add backend/ to sys.path — it causes apps/backend/discord/ to shadow
# the PyPI 'discord' package. PYTHONPATH=. is sufficient for all apps.backend.* imports.

logger = logging.getLogger(__name__)

try:
    from webdav3.client import Client as WebDAVClient

    WEBDAV_AVAILABLE = True
except ImportError:
    WEBDAV_AVAILABLE = False
    logger.warning(
        "⚠️ webdavclient3 not installed. Nextcloud storage disabled. " "To enable, run: pip install webdavclient3"
    )


class HelixNextcloudClient:
    """Nextcloud WebDAV client for Helix Collective storage."""

    def __init__(self) -> None:
        """Initialize Nextcloud client from environment variables."""
        self.url = os.getenv("NEXTCLOUD_URL")
        self.user = os.getenv("NEXTCLOUD_USER")
        self.password = os.getenv("NEXTCLOUD_PASSWORD")
        self.base_path = os.getenv("NEXTCLOUD_BASE_PATH", "/Helix")

        self.enabled = bool(self.url and self.user and self.password)
        self.client: WebDAVClient | None = None

        if self.enabled and WEBDAV_AVAILABLE:
            try:
                options = {
                    "webdav_hostname": self.url,
                    "webdav_login": self.user,
                    "webdav_password": self.password,
                    "webdav_root": "/remote.php/dav/files/" + self.user,
                }
                self.client = WebDAVClient(options)

                # Ensure base directory exists
                self._ensure_directory(self.base_path)

                logger.info("✅ Nextcloud client initialized: %s", self.url)
            except (ConnectionError, TimeoutError) as e:
                logger.warning("Nextcloud connection failed: %s", e)
            except Exception as e:
                logger.error("❌ Nextcloud initialization failed: %s", e)
                self.enabled = False
        elif not WEBDAV_AVAILABLE:
            logger.warning("⚠️ Nextcloud disabled: webdav3-client not installed")
            self.enabled = False
        else:
            logger.warning("⚠️ Nextcloud disabled: missing environment variables")
            logger.info("   Required: NEXTCLOUD_URL, NEXTCLOUD_USER, NEXTCLOUD_PASSWORD")

    def _ensure_directory(self, path: str) -> bool:
        """Ensure a directory exists on Nextcloud."""
        if not self.client:
            return False

        try:
            self.client.mkdir(path)
            logger.info("📁 Created Nextcloud directory: %s", path)
            return True
        except (ConnectionError, TimeoutError) as e:
            logger.debug("Nextcloud directory creation connection error: %s", e)
        except Exception as e:
            logger.warning("⚠️ Could not create directory %s: %s", path, e)
            return False

    def upload_file(self, local_path: Path, remote_path: str = None) -> bool:
        """
        Upload a file to Nextcloud.

        Args:
            local_path: Local file path
            remote_path: Remote path (if None, uses base_path + filename)

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled or not self.client:
            logger.warning("⚠️ Nextcloud not enabled")
            return False

        try:
            if not local_path.exists():
                logger.error("❌ File not found: %s", local_path)
                return False

            # Determine remote path
            if remote_path is None:
                remote_path = f"{self.base_path}/{local_path.name}"

            # Ensure parent directory exists
            parent_dir = str(Path(remote_path).parent)
            self._ensure_directory(parent_dir)

            # Upload file
            self.client.upload_sync(remote_path=remote_path, local_path=str(local_path))

            logger.info("✅ Uploaded to Nextcloud: %s", remote_path)
            return True

        except Exception as e:
            logger.error("❌ Nextcloud upload failed: %s", e)
            return False

    def upload_string(self, content: str, remote_path: str) -> bool:
        """
        Upload string content as a file to Nextcloud.

        Args:
            content: String content to upload
            remote_path: Remote file path

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled or not self.client:
            return False

        try:
            parent_dir = str(Path(remote_path).parent)
            self._ensure_directory(parent_dir)

            # Upload from buffer
            buffer = io.BytesIO(content.encode("utf-8"))
            self.client.upload_to(buffer, remote_path)

            logger.info("✅ Uploaded content to Nextcloud: %s", remote_path)
            return True

        except Exception as e:
            logger.error("❌ Nextcloud upload failed: %s", e)
            return False

    def download_file(self, remote_path: str, local_path: Path) -> bool:
        """
        Download a file from Nextcloud.

        Args:
            remote_path: Remote file path
            local_path: Local destination path

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled or not self.client:
            return False

        try:
            local_path = Path(local_path)
            local_path.parent.mkdir(parents=True, exist_ok=True)

            # Download file
            self.client.download_sync(remote_path=remote_path, local_path=str(local_path))

            logger.info("✅ Downloaded from Nextcloud: %s → %s", remote_path, local_path)
            return True

        except Exception as e:
            logger.error("❌ Nextcloud download failed: %s", e)
            return False

    def list_files(self, remote_path: str = None) -> list[dict]:
        """
        List files in a Nextcloud directory.

        Args:
            remote_path: Remote directory path (default: base_path)

        Returns:
            List of file info dicts
        """
        if not self.enabled or not self.client:
            return []

        try:
            path = remote_path or self.base_path
            files = self.client.list(path, get_info=True)

            file_list = []
            for file in files:
                if file["path"] != path:  # Skip the directory itself
                    file_list.append(
                        {
                            "name": file.get("name", ""),
                            "path": file.get("path", ""),
                            "size": file.get("size", 0),
                            "modified": file.get("modified", ""),
                            "is_dir": file.get("isdir", False),
                        }
                    )

            return file_list

        except Exception as e:
            logger.error("❌ Nextcloud list failed: %s", e)
            return []

    def delete_file(self, remote_path: str) -> bool:
        """
        Delete a file from Nextcloud.

        Args:
            remote_path: Remote file path

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled or not self.client:
            return False

        try:
            self.client.delete(remote_path)
            logger.info("Deleted from Nextcloud: %s", remote_path)
            return True

        except Exception as e:
            logger.error("Nextcloud delete failed: %s", e)
            return False

    def sync_directory(self, local_dir: Path, remote_dir: str = None) -> dict:
        """
        Sync entire local directory to Nextcloud.

        Args:
            local_dir: Local directory path
            remote_dir: Remote directory path (default: base_path/dirname)

        Returns:
            Dict with sync statistics
        """
        if not self.enabled or not self.client:
            return {"error": "Nextcloud not enabled"}

        local_dir = Path(local_dir)
        if not local_dir.exists():
            return {"error": f"Directory not found: {local_dir}"}

        if remote_dir is None:
            remote_dir = f"{self.base_path}/{local_dir.name}"

        stats = {"uploaded": 0, "failed": 0, "skipped": 0, "total_size": 0}

        try:
            self._ensure_directory(remote_dir)

            # Upload all files
            for file_path in local_dir.rglob("*"):
                if file_path.is_file():
                    # Calculate relative path
                    rel_path = file_path.relative_to(local_dir)
                    remote_path = f"{remote_dir}/{rel_path}"

                    # Upload file
                    if self.upload_file(file_path, remote_path):
                        stats["uploaded"] += 1
                        stats["total_size"] += file_path.stat().st_size
                    else:
                        stats["failed"] += 1

            logger.info("✅ Synced {} files to Nextcloud: {}".format(stats["uploaded"], remote_dir))
            return stats

        except Exception as e:
            logger.error("❌ Directory sync failed: %s", e)
            stats["error"] = str(e)
            return stats

    def get_storage_info(self) -> dict:
        """
        Get Nextcloud storage quota information.

        Returns:
            Dict with storage info
        """
        if not self.enabled or not self.client:
            return {"error": "Nextcloud not enabled"}

        try:
            info = self.client.get_quota()

            return {
                "quota_used": info.get("quota_used", 0),
                "quota_available": info.get("quota_available", 0),
                "quota_total": info.get("quota_total", 0),
                "usage_percentage": (
                    round(
                        (info.get("quota_used", 0) / info.get("quota_total", 1)) * 100,
                        2,
                    )
                    if info.get("quota_total", 0) > 0
                    else 0
                ),
            }

        except Exception as e:
            logger.error("❌ Failed to get storage info: %s", e)
            return {"error": "Failed to retrieve storage info"}


# Global instance
_nextcloud_client: HelixNextcloudClient | None = None


def get_nextcloud_client() -> HelixNextcloudClient | None:
    """Get or create global Nextcloud client instance."""
    global _nextcloud_client
    if _nextcloud_client is None:
        _nextcloud_client = HelixNextcloudClient()
    return _nextcloud_client if _nextcloud_client.enabled else None


# Quick test function
if __name__ == "__main__":
    logger.info("🧪 Testing Nextcloud client...")
    client = HelixNextcloudClient()

    if client.enabled:
        logger.info("\n✅ Nextcloud connection successful!")

        # Test storage info
        storage = client.get_storage_info()
        if "error" not in storage:
            logger.info(
                "📊 Storage: {.2f} GB / {.2f} GB ({}%)".format(
                    storage["quota_used"] / (1024**3),
                    storage["quota_total"] / (1024**3),
                    storage["usage_percentage"],
                )
            )

        # Test list files
        files = client.list_files()
        logger.info("📁 Files in %s: %s", client.base_path, len(files))
        for file in files[:5]:  # Show first 5
            logger.info("   - {} ({} bytes)".format(file["name"], file["size"]))
    else:
        logger.error("❌ Nextcloud not configured")
        logger.info("Set: NEXTCLOUD_URL, NEXTCLOUD_USER, NEXTCLOUD_PASSWORD")

"""
Coordination Snapshot Service
=============================

Periodically captures UCF state and persists to DB for historical tracking.
Used by coordination predictor and analytics for trend analysis.

Author: Claude (GitHub Copilot)
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc

logger = logging.getLogger(__name__)


class CoordinationSnapshotService:
    """Service for recording and querying coordination state history"""

    def __init__(self):
        self._db_available = False
        try:
            from apps.backend.db_models import CoordinationSnapshot  # noqa: F401

            self._db_available = True
        except ImportError:
            logger.warning("DB models not available for coordination snapshots")

    def capture_snapshot(
        self, source: str = "background_task", metadata: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """
        Capture current UCF state and persist to database.

        Args:
            source: What triggered the snapshot (background_task, cycle, manual)
            metadata: Extra context (cycle name, trigger event, etc.)

        Returns:
            The saved snapshot dict, or None if save failed
        """
        try:
            from apps.backend.coordination_engine import load_ucf_state

            ucf = load_ucf_state()
        except Exception as e:
            logger.error("Failed to load UCF state for snapshot: %s", e)
            return None

        snapshot_data = {
            "harmony": ucf.get("harmony", 0.5),
            "resilience": ucf.get("resilience", 0.7),
            "throughput": ucf.get("throughput", 0.6),
            "focus": ucf.get("focus", 0.5),
            "friction": ucf.get("friction", 0.1),
            "velocity": ucf.get("velocity", 1.0),
            "performance_score": ucf.get("coordination", ucf.get("harmony", 0.5)),
            "source": source,
            "timestamp": datetime.now(UTC),
        }

        if not self._db_available:
            return snapshot_data

        try:
            from apps.backend.db_models import CoordinationSnapshot, get_session

            session = get_session()
            snapshot = CoordinationSnapshot(
                harmony=snapshot_data["harmony"],
                resilience=snapshot_data["resilience"],
                throughput=snapshot_data["throughput"],
                focus=snapshot_data["focus"],
                friction=snapshot_data["friction"],
                velocity=snapshot_data["velocity"],
                performance_score=snapshot_data["performance_score"],
                source=source,
                snapshot_metadata=metadata,
            )
            session.add(snapshot)
            session.commit()
            snapshot_data["id"] = snapshot.id
            logger.info(
                "Coordination snapshot captured (id=%s, source=%s)",
                snapshot.id,
                source,
            )
            return snapshot_data
        except Exception as e:
            logger.error("Failed to save coordination snapshot: %s", e)
            return snapshot_data

    def get_history(self, minutes: int = 240, limit: int = 500) -> list[dict[str, Any]]:
        """
        Get coordination history from database.

        Args:
            minutes: How far back to look
            limit: Maximum number of snapshots to return

        Returns:
            List of snapshot dicts ordered by timestamp ascending
        """
        if not self._db_available:
            return self._get_ucf_fallback(minutes)

        try:
            from apps.backend.db_models import CoordinationSnapshot, get_session

            session = get_session()
            cutoff = datetime.now(UTC) - timedelta(minutes=minutes)

            snapshots = (
                session.query(CoordinationSnapshot)
                .filter(CoordinationSnapshot.timestamp >= cutoff)
                .order_by(CoordinationSnapshot.timestamp.asc())
                .limit(limit)
                .all()
            )

            if not snapshots:
                return self._get_ucf_fallback(minutes)

            return [
                {
                    "timestamp": s.timestamp.isoformat() if s.timestamp else "",
                    "performance_score": s.performance_score or 0.5,
                    "harmony": s.harmony or 0.5,
                    "resilience": s.resilience or 0.7,
                    "throughput": s.throughput or 0.6,
                    "focus": s.focus or 0.5,
                    "friction": s.friction or 0.1,
                    "source": s.source or "unknown",
                }
                for s in snapshots
            ]
        except Exception as e:
            logger.error("Failed to query coordination history: %s", e)
            return self._get_ucf_fallback(minutes)

    def _get_ucf_fallback(self, minutes: int) -> list[dict[str, Any]]:
        """Fallback: return current UCF state as single data point"""
        try:
            from apps.backend.coordination_engine import load_ucf_state

            ucf = load_ucf_state()
            return [
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "performance_score": ucf.get("coordination", ucf.get("harmony", 0.5)),
                    "harmony": ucf.get("harmony", 0.5),
                    "resilience": ucf.get("resilience", 0.7),
                    "throughput": ucf.get("throughput", 0.6),
                    "focus": ucf.get("focus", 0.5),
                    "friction": ucf.get("friction", 0.1),
                    "source": "ucf_state_file",
                }
            ]
        except (ImportError, ModuleNotFoundError) as e:
            logger.debug("UCF state module not available for fallback: %s", e)
            return []
        except OSError as e:
            logger.debug("UCF state file not accessible: %s", e)
            return []
        except Exception as e:
            logger.warning("UCF state file fallback failed: %s", e)
            return []

    def get_latest(self) -> dict[str, Any] | None:
        """Get the most recent coordination snapshot"""
        if not self._db_available:
            fallback = self._get_ucf_fallback(1)
            return fallback[0] if fallback else None

        try:
            from apps.backend.db_models import CoordinationSnapshot, get_session

            session = get_session()
            snapshot = session.query(CoordinationSnapshot).order_by(desc(CoordinationSnapshot.timestamp)).first()

            if snapshot:
                return {
                    "timestamp": (snapshot.timestamp.isoformat() if snapshot.timestamp else ""),
                    "performance_score": snapshot.performance_score or 0.5,
                    "harmony": snapshot.harmony or 0.5,
                    "resilience": snapshot.resilience or 0.7,
                    "throughput": snapshot.throughput or 0.6,
                    "focus": snapshot.focus or 0.5,
                    "friction": snapshot.friction or 0.1,
                }
            return self._get_ucf_fallback(1)[0] if self._get_ucf_fallback(1) else None
        except (ImportError, ModuleNotFoundError) as e:
            logger.debug("UCF state module not available: %s", e)
            fallback = self._get_ucf_fallback(1)
            return fallback[0] if fallback else None
        except (AttributeError, TypeError) as e:
            logger.debug("UCF state data error: %s", e)
            fallback = self._get_ucf_fallback(1)
            return fallback[0] if fallback else None
        except Exception as e:
            logger.warning("Error retrieving latest snapshot: %s", e)
            fallback = self._get_ucf_fallback(1)
            return fallback[0] if fallback else None

    def cleanup_old_snapshots(self, days: int = 90) -> int:
        """Delete snapshots older than specified days"""
        if not self._db_available:
            return 0

        try:
            from apps.backend.db_models import CoordinationSnapshot, get_session

            session = get_session()
            cutoff = datetime.now(UTC) - timedelta(days=days)
            deleted = session.query(CoordinationSnapshot).filter(CoordinationSnapshot.timestamp < cutoff).delete()
            session.commit()
            logger.info("Cleaned up %d old coordination snapshots", deleted)
            return deleted
        except Exception as e:
            logger.error("Failed to cleanup snapshots: %s", e)
            return 0


# Singleton instance
_snapshot_service: CoordinationSnapshotService | None = None


def get_snapshot_service() -> CoordinationSnapshotService:
    """Get singleton coordination snapshot service"""
    global _snapshot_service
    if _snapshot_service is None:
        _snapshot_service = CoordinationSnapshotService()
    return _snapshot_service

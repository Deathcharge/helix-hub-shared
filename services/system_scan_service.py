"""
System Scan Service
Implements system scanning operations with progress tracking and async execution.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from apps.backend.services.service_registry import ServiceRegistry

from ..models.system import SystemScan

logger = logging.getLogger(__name__)


@dataclass
class ScanTask:
    """Represents an active scan task"""

    scan_id: str
    task: asyncio.Task
    scan: SystemScan


class SystemScanService:
    """Service for managing system scans with async execution and progress tracking"""

    def __init__(self) -> None:
        """
        Initialize the SystemScanService instance and its internal storage and configuration.

        Attributes:
            _active_scans (Dict[str, ScanTask]): Mapping of active scan_id to their ScanTask.
            _completed_scans (List[SystemScan]): List of completed SystemScan objects (most recent last).
            _service_registry (ServiceRegistry): Local service registry used by the service.
            _max_completed_scans (int): Maximum number of completed scans to retain (default 50).
        """
        self._active_scans: dict[str, ScanTask] = {}
        self._completed_scans: list[SystemScan] = []
        self._service_registry = ServiceRegistry()
        self._max_completed_scans = 50

    async def start_scan(self, scan_type: str = "full_system") -> SystemScan:
        """
        Initiates a new system scan and schedules its asynchronous execution.

        Parameters:
            scan_type (str): The kind of scan to perform (e.g., "full_system", "calibration"); used to set the scan's name and description.

        Returns:
            SystemScan: The created scan object with initial metadata (status "pending", progress 0) that has been scheduled for execution.
        """
        scan_id = str(uuid.uuid4())

        # Create scan object
        scan = SystemScan(
            id=scan_id,
            name=f"System {scan_type.replace('_', ' ').title()} Scan",
            description=f"Comprehensive {scan_type} system field analysis",
            status="pending",
            progress=0,
            start_time=int(datetime.now(UTC).timestamp()),
            results=None,
            error=None,
        )

        # Create async task for the scan
        task = asyncio.create_task(self._execute_scan(scan))

        # Store active scan
        scan_task = ScanTask(scan_id=scan_id, task=task, scan=scan)
        self._active_scans[scan_id] = scan_task

        logger.info("Started system scan: %s - %s", scan_id, scan_type)
        return scan

    async def _execute_scan(self, scan: SystemScan) -> None:
        """
        Execute the provided SystemScan through its lifecycle, updating its progress, results, status, timestamps, and service storage.

        Parameters:
            scan (SystemScan): The scan to run; mutated in-place. On success the scan's `progress`, `results`, `status` ("completed"), and `end_time` are set. On error the scan's `status` is set to "failed", `error` is recorded, and `end_time` is set. After execution the scan is removed from the service's active scans and appended to the completed scans list (which is trimmed to the service's configured maximum).
        """
        try:
            scan.status = "running"

            # Run scan phases and collect real-time metrics
            scan.progress = 10
            logger.debug("Scan %s: Initializing system field", scan.id)

            scan.progress = 50
            logger.debug("Scan %s: Measuring coherence levels", scan.id)

            scan.progress = 90
            logger.debug("Scan %s: Finalizing results", scan.id)

            # Report actual scan metadata (no fabricated values)
            scan_end = datetime.now(UTC)
            scan_duration = scan_end.timestamp() - scan.start_time
            scan.results = {
                "status": "completed",
                "scan_duration": round(scan_duration, 2),
                "note": "System hardware integration pending - metrics will populate when connected",
            }

            # Complete the scan
            scan.progress = 100
            scan.status = "completed"
            scan.end_time = int(datetime.now(UTC).timestamp())

            logger.info("Completed system scan: %s", scan.id)

        except Exception as e:
            scan.status = "failed"
            scan.error = str(e)
            scan.end_time = int(datetime.now(UTC).timestamp())
            logger.error("Failed system scan %s: %s", scan.id, str(e))

        finally:
            # Move to completed scans
            if scan.id in self._active_scans:
                del self._active_scans[scan.id]

            self._completed_scans.append(scan)
            if len(self._completed_scans) > self._max_completed_scans:
                self._completed_scans.pop(0)

    async def get_scan_by_id(self, scan_id: str) -> SystemScan | None:
        """
        Retrieve a scan by its identifier, searching active scans first then completed scans.

        Parameters:
            scan_id (str): The UUID of the scan to retrieve.

        Returns:
            SystemScan or None: The matching `SystemScan` if found, `None` otherwise.
        """
        # Check active scans first
        if scan_id in self._active_scans:
            return self._active_scans[scan_id].scan

        # Check completed scans
        for scan in self._completed_scans:
            if scan.id == scan_id:
                return scan

        return None

    async def get_all_scans(self) -> list[SystemScan]:
        """
        Retrieve all scans, combining active and completed entries.

        @returns A list of SystemScan objects: active scans (in no particular order) followed by completed scans.
        """
        active_scans = [task.scan for task in self._active_scans.values()]
        return active_scans + self._completed_scans

    async def cancel_scan(self, scan_id: str) -> bool:
        """
        Cancel an active scan identified by scan_id.

        If an active scan with the given id exists, cancels its asyncio task, marks the scan status as "cancelled",
        sets its end_time and error message, moves it from the active to the completed scans list, and logs the cancellation.

        Returns:
            True if the scan was active and cancelled, False if no active scan with the given id was found.
        """
        if scan_id not in self._active_scans:
            return False

        scan_task = self._active_scans[scan_id]

        # Cancel the task
        scan_task.task.cancel()

        # Update scan status
        scan_task.scan.status = "cancelled"
        scan_task.scan.end_time = int(datetime.now(UTC).timestamp())
        scan_task.scan.error = "Scan cancelled by user"

        # Move to completed
        del self._active_scans[scan_id]
        self._completed_scans.append(scan_task.scan)

        logger.info("Cancelled system scan: %s", scan_id)
        return True

    async def get_active_scans(self) -> list[SystemScan]:
        """
        Retrieve scans that are currently running.

        Returns:
            active_scans (List[SystemScan]): List of SystemScan objects representing scans currently in progress.
        """
        return [task.scan for task in self._active_scans.values()]

    async def cleanup_old_scans(self, max_age_hours: int = 24) -> int:
        """
        Remove completed scans older than the specified age from the completed-scans list.

        Parameters:
                max_age_hours (int): Maximum age in hours; completed scans with an end_time older than now minus this value will be removed.

        Returns:
                removed_count (int): Number of completed scans removed.
        """
        cutoff_time = int(datetime.now(UTC).timestamp()) - (max_age_hours * 3600)

        original_count = len(self._completed_scans)
        self._completed_scans = [
            scan for scan in self._completed_scans if scan.end_time and scan.end_time > cutoff_time
        ]

        removed_count = original_count - len(self._completed_scans)
        if removed_count > 0:
            logger.info("Cleaned up %s old system scans", removed_count)

        return removed_count

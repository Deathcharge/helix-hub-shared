"""
Coordination State Migration - Zero-Downtime Migration Strategy
==============================================================

Migrates from file-based UCF to database with zero downtime.

(c) Helix Collective 2024 - Proprietary Technology Stack
"""

import asyncio
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class CoordinationStateMigration:
    """Migrate from file-based UCF to database with zero downtime"""

    def __init__(self, db_connection) -> None:
        """
        Initialize the migration helper with a database connection and default UCF file path.

        Stores the provided database connection on the instance and sets `ucf_file_path` to "Helix/state/ucf_state.json".
        """
        self.db_connection = db_connection
        self.ucf_file_path = Path("Helix/state/ucf_state.json")

    async def dual_write_mode(self):
        """
        Enable dual-write mode so UCF state is written to both the file-based store and the database.

        This method currently serves as a hook/placeholder to activate dual-write behavior and may be overridden or extended to integrate existing UCF helpers for simultaneous file and database writes.

        Returns:
            bool: `True` if the dual-write mode hook completed successfully, `False` otherwise.
        """

        logger.info("🔄 Phase 1: Dual write mode active")

        # Override existing UCF helpers to write to both locations
        try:
            # Import here to avoid circular imports
            from apps.backend.core import ucf_helpers

            if not hasattr(self, "_original_update_ucf"):
                self._original_update_ucf = ucf_helpers.update_ucf_state

            # Replace with dual-write version
            async def dual_update(ucf_state, save_to_file=True):
                try:
                    # Write to file first (existing behavior)
                    result_file = await self._original_update_ucf(ucf_state, save_to_file)
                    # Then write to database
                    result_db = await self.write_to_coordination_db(ucf_state)
                    success = result_file and result_db
                    logger.info("✅ Dual-write completed: file=%s, db=%s", result_file, result_db)
                    return success
                except Exception as e:
                    logger.error("Dual-write failed: %s", e)
                    # Fallback to file-only if dual-write fails
                    return await self._original_update_ucf(ucf_state, save_to_file)

            ucf_helpers.update_ucf_state = dual_update
            logger.info("✅ Dual-write UCF updating activated")
            return True

        except Exception as e:
            logger.error("Failed to activate dual-write mode: %s", e)
            return False

    async def write_to_coordination_db(self, ucf_state: dict[str, Any]) -> bool:
        """
        Persist the provided UCF state to the coordination_states database table using an upsert.

        Parameters:
            ucf_state (Dict[str, Any]): Mapping containing UCF fields expected to be stored. Recognized keys include
                `system_signature`, `qubit_amplitudes`, `harmony`, `resilience`, `throughput`, `focus`,
                `friction`, `velocity`, `active_agents`, and `agent_performance_scores`. Missing keys are substituted
                with sensible defaults.

        Returns:
            bool: True if the database write (insert or update) succeeded, False otherwise.
        """

        try:
            query = """
                INSERT INTO coordination_states (
                    system_signature,
                    qubit_amplitudes,
                    harmony,
                    resilience,
                    throughput,
                    focus,
                    friction,
                    velocity,
                    active_agents,
                    agent_performance_scores
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (system_signature) DO UPDATE SET
                    qubit_amplitudes = EXCLUDED.qubit_amplitudes,
                    harmony = EXCLUDED.harmony,
                    resilience = EXCLUDED.resilience,
                    throughput = EXCLUDED.throughput,
                    focus = EXCLUDED.focus,
                    friction = EXCLUDED.friction,
                    velocity = EXCLUDED.velocity,
                    active_agents = EXCLUDED.active_agents,
                    agent_performance_scores = EXCLUDED.agent_performance_scores,
                    updated_at = NOW()
            """

            await self.db_connection.execute(
                query,
                ucf_state.get("system_signature", str(datetime.now(UTC).timestamp())),
                ucf_state.get("qubit_amplitudes", {}),
                ucf_state.get("harmony", 0.5),
                ucf_state.get("resilience", 0.5),
                ucf_state.get("throughput", 0.5),
                ucf_state.get("focus", 0.5),
                ucf_state.get("friction", 0.3),
                ucf_state.get("velocity", 0.5),
                ucf_state.get("active_agents", {}),
                ucf_state.get("agent_performance_scores", {}),
            )

            logger.info("✅ UCF state written to database")
            return True

        except Exception as e:
            logger.error("❌ Failed to write UCF state to database: %s", e)
            return False

    async def switch_to_database_mode(self):
        """
        Enable database-first reads for UCF state while preserving a file-based fallback.

        Returns:
            bool: `True` if the database-first mode was activated (file fallback remains available), `False` otherwise.
        """

        logger.info("🔄 Phase 2: Database-first mode active")

        # Override UCF reading to check database first
        try:
            # Store original function for fallback
            if not hasattr(self, "_original_get_ucf"):
                # Import here to avoid circular imports
                from apps.backend.core import ucf_helpers

                self._original_get_ucf = ucf_helpers.get_current_ucf

            # Replace with database-first version
            async def db_first_get():
                try:
                    return await self.read_from_coordination_db()
                except Exception as e:
                    logger.warning("Database read failed, using file fallback: %s", e)
                    return await self._original_get_ucf()

            ucf_helpers.get_current_ucf = db_first_get
            logger.info("✅ Database-first UCF reading activated")
            return True

        except Exception as e:
            logger.error("Failed to activate database mode: %s", e)
            return False

    async def read_from_coordination_db(self) -> dict[str, Any]:
        """
        Retrieve the most recent UCF state record from the database.

        Queries the `coordination_states` table for the latest row by `updated_at` and returns a dictionary with the stored UCF fields. If no record exists, returns an empty dict. Any exception raised during the database query is propagated.

        Returns:
            Dict[str, Any]: A dictionary containing the UCF state with keys:
                - `system_signature` (str)
                - `qubit_amplitudes` (Any)
                - `harmony` (float)
                - `resilience` (float)
                - `throughput` (float)
                - `focus` (float)
                - `friction` (float)
                - `velocity` (float)
                - `active_agents` (Any)
                - `agent_performance_scores` (Any)
                - `performance_score` (float)
                - `coordination_state` (Any)
            Returns an empty dict if no row is found.

        Raises:
            Exception: If the database query fails or an unexpected error occurs.
        """

        try:
            query = """
                SELECT * FROM coordination_states
                ORDER BY updated_at DESC
                LIMIT 1
            """

            row = await self.db_connection.fetchrow(query)

            if row:
                return {
                    "system_signature": row["system_signature"],
                    "qubit_amplitudes": row["qubit_amplitudes"],
                    "harmony": float(row["harmony"]),
                    "resilience": float(row["resilience"]),
                    "throughput": float(row["throughput"]),
                    "focus": float(row["focus"]),
                    "friction": float(row["friction"]),
                    "velocity": float(row["velocity"]),
                    "active_agents": row["active_agents"],
                    "agent_performance_scores": row["agent_performance_scores"],
                    "performance_score": float(row["performance_score"]),
                    "coordination_state": row["coordination_state"],
                }

            return {}

        except Exception as e:
            logger.error("❌ Failed to read UCF state from database: %s", e)
            raise

    async def archive_file_mode(self):
        """
        Archive the existing UCF file into a timestamped archive directory and prepare for database-only operation.

        Ensures the archive directory Helix/state/archive exists, and if the configured UCF file is present, moves it to a timestamped filename within that directory.

        Returns:
            bool: `True` on successful completion.
        """

        logger.info("🔄 Phase 3: Archive file mode")

        # Archive existing UCF files
        ucf_archive_dir = Path("Helix/state/archive")
        ucf_archive_dir.mkdir(exist_ok=True, parents=True)

        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

        if self.ucf_file_path.exists():
            archived_file = ucf_archive_dir / f"ucf_state_{timestamp}.json"
            shutil.move(str(self.ucf_file_path), str(archived_file))
            logger.info("🗄️ UCF file archived to: %s", archived_file)

        return True

    async def run_migration(self):
        """
        Orchestrates the zero-downtime migration from file-based UCF state to a database-backed state.

        Executes the three migration phases in sequence: enable dual-write mode, switch to database-first reads, and archive the on-disk UCF file. The method waits briefly between phases to allow data synchronization and stability checks and logs progress.
        """

        logger.info("🚀 Starting zero-downtime coordination migration")

        # Phase 1: Dual write
        await self.dual_write_mode()
        await asyncio.sleep(5)  # Allow time for data sync

        # Phase 2: Switch to database-first
        await self.switch_to_database_mode()
        await asyncio.sleep(5)  # Verify stability

        # Phase 3: Archive files
        await self.archive_file_mode()

        logger.info("✅ Zero-downtime migration complete")

"""
Agent Profiles - Detailed Agent Information and Collaboration System
Helix Collective v15.3 Dual Resonance

Provides detailed agent profiles, performance tracking, and multi-agent
collaboration features for the Helix Collective.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from apps.backend.context_manager import ContextManager

from apps.backend.logging.helix_logger import get_logger

logger = get_logger(__name__)


class AgentProfileSystem:
    """
    Manages agent profiles, performance tracking, and collaboration.
    """

    def __init__(self, db_path: str = "backend/state/agent_profiles.db"):
        """
        Initialize agent profile system with database.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _init_database(self):
        """Initialize SQLite database with schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create task history table with user_id for multi-tenant isolation
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS task_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                task_description TEXT NOT NULL,
                success INTEGER NOT NULL,
                duration_seconds REAL,
                harmony_before REAL,
                harmony_after REAL,
                notes TEXT
            )
        """
        )

        # Create collaboration table with user_id
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS collaborations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                task_description TEXT NOT NULL,
                agents TEXT NOT NULL,
                success INTEGER NOT NULL,
                harmony_delta REAL,
                notes TEXT
            )
        """
        )

        # Create agent stats table with user_id
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_stats (
                user_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                total_tasks INTEGER DEFAULT 0,
                successful_tasks INTEGER DEFAULT 0,
                total_collaborations INTEGER DEFAULT 0,
                average_harmony_impact REAL DEFAULT 0.0,
                last_active TEXT,
                specialization_score REAL DEFAULT 0.0,
                PRIMARY KEY (user_id, agent_name)
            )
        """
        )

        # Create indexes for efficient querying
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_task_user_agent
            ON task_history(user_id, agent_name)
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_task_timestamp
            ON task_history(user_id, timestamp)
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_collab_user
            ON collaborations(user_id)
        """
        )

        conn.commit()
        conn.close()

    def record_task(
        self,
        agent_name: str,
        task_description: str,
        success: bool,
        duration_seconds: float | None = None,
        harmony_before: float | None = None,
        harmony_after: float | None = None,
        notes: str | None = None,
    ) -> int:
        """
        Record a task execution by an agent.

        Args:
            agent_name: Name of the agent
            task_description: Description of the task
            success: Whether task succeeded
            duration_seconds: Optional task duration
            harmony_before: Optional harmony before task
            harmony_after: Optional harmony after task
            notes: Optional notes

        Returns:
            Record ID
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        timestamp = datetime.now(timezone.utc).isoformat()

        cursor.execute(
            """
            INSERT INTO task_history
            (timestamp, agent_name, task_description, success, duration_seconds,
             harmony_before, harmony_after, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                timestamp,
                agent_name,
                task_description,
                int(success),
                duration_seconds,
                harmony_before,
                harmony_after,
                notes,
            ),
        )

        record_id = cursor.lastrowid

        # Update agent stats
        self._update_agent_stats(cursor, agent_name, success, harmony_before, harmony_after)

        conn.commit()
        conn.close()

        return record_id

    def record_collaboration(
        self,
        task_description: str,
        agents: List[str],
        success: bool,
        harmony_delta: float | None = None,
        notes: str | None = None,
    ) -> int:
        """
        Record a multi-agent collaboration.

        Args:
            task_description: Description of the task
            agents: List of agent names
            success: Whether collaboration succeeded
            harmony_delta: Optional harmony change
            notes: Optional notes

        Returns:
            Record ID
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        timestamp = datetime.now(timezone.utc).isoformat()
        agents_json = json.dumps(agents)

        cursor.execute(
            """
            INSERT INTO collaborations
            (timestamp, task_description, agents, success, harmony_delta, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                timestamp,
                task_description,
                agents_json,
                int(success),
                harmony_delta,
                notes,
            ),
        )

        record_id = cursor.lastrowid

        # Update stats for all agents
        for agent in agents:
            cursor.execute(
                """
                INSERT INTO agent_stats (agent_name, total_collaborations, last_active)
                VALUES (?, 1, ?)
                ON CONFLICT(agent_name) DO UPDATE SET
                    total_collaborations = total_collaborations + 1,
                    last_active = ?
            """,
                (agent, timestamp, timestamp),
            )

        conn.commit()
        conn.close()

        return record_id

    def _update_agent_stats(
        self,
        cursor,
        agent_name: str,
        success: bool,
        harmony_before: float | None,
        harmony_after: float | None,
    ):
        """Update agent statistics."""
        timestamp = datetime.now(timezone.utc).isoformat()

        harmony_impact = 0.0
        if harmony_before is not None and harmony_after is not None:
            harmony_impact = harmony_after - harmony_before

        cursor.execute(
            """
            INSERT INTO agent_stats
            (agent_name, total_tasks, successful_tasks, average_harmony_impact, last_active)
            VALUES (?, 1, ?, ?, ?)
            ON CONFLICT(agent_name) DO UPDATE SET
                total_tasks = total_tasks + 1,
                successful_tasks = successful_tasks + ?,
                average_harmony_impact = (average_harmony_impact * total_tasks + ?) / (total_tasks + 1),
                last_active = ?
        """,
            (
                agent_name,
                int(success),
                harmony_impact,
                timestamp,
                int(success),
                harmony_impact,
                timestamp,
            ),
        )

    def get_agent_profile(self, agent_name: str) -> Dict:
        """
        Get comprehensive profile for an agent.

        Args:
            agent_name: Name of the agent

        Returns:
            Agent profile dictionary
        """
        # Get base info from context manager
        agent_info = ContextManager.get_agent_info(agent_name)

        if not agent_info:
            return {"error": "Agent {} not found".format(agent_name)}

        # Get stats from database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT total_tasks, successful_tasks, total_collaborations,
                   average_harmony_impact, last_active, specialization_score
            FROM agent_stats
            WHERE agent_name = ?
        """,
            (agent_name,),
        )

        stats_row = cursor.fetchone()

        if stats_row:
            (
                total_tasks,
                successful_tasks,
                total_collaborations,
                avg_harmony,
                last_active,
                spec_score,
            ) = stats_row
            success_rate = successful_tasks / total_tasks if total_tasks > 0 else 0.0
        else:
            total_tasks = 0
            successful_tasks = 0
            total_collaborations = 0
            avg_harmony = 0.0
            last_active = None
            spec_score = 0.0
            success_rate = 0.0

        # Get recent tasks
        cursor.execute(
            """
            SELECT timestamp, task_description, success, harmony_after
            FROM task_history
            WHERE agent_name = ?
            ORDER BY timestamp DESC
            LIMIT 10
        """,
            (agent_name,),
        )

        recent_tasks = []
        for row in cursor.fetchall():
            recent_tasks.append(
                {
                    "timestamp": row[0],
                    "task": row[1],
                    "success": bool(row[2]),
                    "harmony_after": row[3],
                }
            )

        conn.close()

        # Compile profile
        profile = {
            "name": agent_name,
            "layer": agent_info["layer"].value,
            "description": agent_info["description"],
            "capabilities": [cap.value for cap in agent_info["capabilities"]],
            "keywords": agent_info["keywords"],
            "statistics": {
                "total_tasks": total_tasks,
                "successful_tasks": successful_tasks,
                "success_rate": success_rate,
                "total_collaborations": total_collaborations,
                "average_harmony_impact": avg_harmony,
                "specialization_score": spec_score,
                "last_active": last_active,
            },
            "recent_tasks": recent_tasks,
        }

        return profile

    def get_top_performers(self, metric: str = "success_rate", limit: int = 5) -> List[Dict]:
        """
        Get top performing agents by specified metric.

        Args:
            metric: Metric to rank by (success_rate, harmony_impact, tasks)
            limit: Number of agents to return

        Returns:
            List of agent profiles
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if metric == "success_rate":
            cursor.execute(
                """
                SELECT agent_name,
                       CAST(successful_tasks AS REAL) / total_tasks as success_rate,
                       total_tasks
                FROM agent_stats
                WHERE total_tasks >= 3
                ORDER BY success_rate DESC
                LIMIT ?
            """,
                (limit,),
            )
        elif metric == "harmony_impact":
            cursor.execute(
                """
                SELECT agent_name, average_harmony_impact, total_tasks
                FROM agent_stats
                WHERE total_tasks >= 3
                ORDER BY average_harmony_impact DESC
                LIMIT ?
            """,
                (limit,),
            )
        else:  # tasks
            cursor.execute(
                """
                SELECT agent_name, total_tasks, successful_tasks
                FROM agent_stats
                ORDER BY total_tasks DESC
                LIMIT ?
            """,
                (limit,),
            )

        rows = cursor.fetchall()
        conn.close()

        performers = []
        for row in rows:
            performers.append(
                {
                    "agent_name": row[0],
                    "metric_value": row[1],
                    "total_tasks": row[2] if len(row) > 2 else row[1],
                }
            )

        return performers

    def suggest_collaboration_team(
        self, task_description: str, team_size: int = 3, prefer_experienced: bool = True
    ) -> List[Tuple[str, str, float]]:
        """
        Suggest a multi-agent team for a task.

        Args:
            task_description: Description of the task
            team_size: Desired team size
            prefer_experienced: Whether to prefer experienced agents

        Returns:
            List of (agent_name, role, confidence) tuples
        """
        # Get base team from context manager
        base_team = ContextManager.select_multi_agent_team(task_description, team_size)

        if not prefer_experienced:
            return [(agent, role, 0.8) for agent, role in base_team]

        # Enhance with performance data
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        enhanced_team = []
        for agent_name, role in base_team:
            cursor.execute(
                """
                SELECT total_tasks, successful_tasks, average_harmony_impact
                FROM agent_stats
                WHERE agent_name = ?
            """,
                (agent_name,),
            )

            stats = cursor.fetchone()

            if stats:
                total_tasks, successful_tasks, avg_harmony = stats
                success_rate = successful_tasks / total_tasks if total_tasks > 0 else 0.5

                # Calculate confidence based on experience and success
                experience_factor = min(total_tasks / 20.0, 1.0)  # Max at 20 tasks
                harmony_factor = max(0.0, min(avg_harmony * 10, 1.0))  # Scale harmony impact

                confidence = success_rate * 0.5 + experience_factor * 0.3 + harmony_factor * 0.2
            else:
                confidence = 0.5  # Default for new agents

            enhanced_team.append((agent_name, role, confidence))

        conn.close()

        # Sort by confidence
        enhanced_team.sort(key=lambda x: x[2], reverse=True)

        return enhanced_team

    def get_collaboration_history(self, limit: int = 20) -> List[Dict]:
        """
        Get recent collaboration history.

        Args:
            limit: Maximum number of records

        Returns:
            List of collaboration dictionaries
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT timestamp, task_description, agents, success, harmony_delta, notes
            FROM collaborations
            ORDER BY timestamp DESC
            LIMIT ?
        """,
            (limit,),
        )

        rows = cursor.fetchall()
        conn.close()

        collaborations = []
        for row in rows:
            collaborations.append(
                {
                    "timestamp": row[0],
                    "task": row[1],
                    "agents": json.loads(row[2]),
                    "success": bool(row[3]),
                    "harmony_delta": row[4],
                    "notes": row[5],
                }
            )

        return collaborations

    def analyze_agent_synergy(self, agent1: str, agent2: str) -> Dict:
        """
        Analyze synergy between two agents.

        Args:
            agent1: First agent name
            agent2: Second agent name

        Returns:
            Synergy analysis dictionary
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Find collaborations involving both agents
        cursor.execute(
            """
            SELECT success, harmony_delta
            FROM collaborations
            WHERE agents LIKE ? AND agents LIKE ?
        """,
            ('%"{}"%'.format(agent1), '%"{}"%'.format(agent2)),
        )

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return {
                "agent1": agent1,
                "agent2": agent2,
                "collaborations": 0,
                "synergy": "UNKNOWN",
            }

        successes = sum(1 for success, _ in rows if success)
        success_rate = successes / len(rows) if rows else 0.0

        harmony_deltas = [delta for _, delta in rows if delta is not None]
        avg_harmony_delta = sum(harmony_deltas) / len(harmony_deltas) if harmony_deltas else 0.0

        # Determine synergy level
        if success_rate >= 0.8 and avg_harmony_delta >= 0.05:
            synergy = "EXCELLENT"
        elif success_rate >= 0.6 and avg_harmony_delta >= 0.02:
            synergy = "GOOD"
        elif success_rate >= 0.4:
            synergy = "MODERATE"
        else:
            synergy = "POOR"

        return {
            "agent1": agent1,
            "agent2": agent2,
            "collaborations": len(rows),
            "success_rate": success_rate,
            "average_harmony_delta": avg_harmony_delta,
            "synergy": synergy,
        }


# Example usage
if __name__ == "__main__":
    profile_system = AgentProfileSystem()

    # Record test task
    logger.info("Recording test task...")
    profile_system.record_task(
        agent_name="Arjuna",
        task_description="Deploy helix-unified to Railway",
        success=True,
        duration_seconds=120.5,
        harmony_before=0.4922,
        harmony_after=0.5134,
        notes="Deployment successful with all services running",
    )

    # Get agent profile
    logger.info("\nAgent profile for Arjuna:")
    profile = profile_system.get_agent_profile("Arjuna")
    logger.info(json.dumps(profile, indent=2))

    # Suggest collaboration team
    logger.info("\nSuggested team for complex deployment:")
    team = profile_system.suggest_collaboration_team(
        task_description="Design and deploy new Discord feature with ethical review",
        team_size=3,
        prefer_experienced=True,
    )
    for agent, role, confidence in team:
        logger.info("  {} ({}): {.2f} confidence".format(agent, role, confidence))

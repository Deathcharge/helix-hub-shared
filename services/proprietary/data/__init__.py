"""
Coordination Data Management
============================

Database schema and migration utilities for coordination state management.

- coordination_schema.sql: Optimized PostgreSQL schema for UCF metrics
- coordination_migration.py: Zero-downtime migration from file-based to database
"""

from .coordination_migration import CoordinationStateMigration

__all__ = [
    "CoordinationStateMigration",
]

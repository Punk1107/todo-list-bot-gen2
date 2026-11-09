"""
tests/test_migration_v38.py — Verification suite for Gen 5.0 Database Schema Evolution (v38).
Covers:
  - Pillar 4 Schema: Version 38 completeness and monotonic continuity.
  - _KNOWN_TABLES expansion to 47 tables.
  - Table detection for active_time_timers and user_workload_capacities.
  - SQL statement split and syntax integrity for v38 migration.
  - Idempotency safety guards (IF NOT EXISTS, ON CONFLICT DO UPDATE).
"""
from __future__ import annotations

from core.database import (
    MIGRATIONS,
    SCHEMA_VERSION,
    _KNOWN_TABLES,
    _detect_tables,
    _split_sql_statements,
)


def test_schema_version_is_38():
    """Verify that current schema version constant is set to at least 38."""
    assert SCHEMA_VERSION >= 38


def test_migrations_continuity_v1_to_v38():
    """Verify migrations list contains all versions from 1 to 38 monotonically without gaps."""
    versions = [v for v, _ in MIGRATIONS]
    assert versions[:38] == list(range(1, 39)), f"Migration versions gap or mismatch in first 38: {versions[:38]}"


def test_known_tables_contains_all_pillar4_tables():
    """Verify that _KNOWN_TABLES contains at least 47 tables including all new Pillar 4 tables."""
    assert len(_KNOWN_TABLES) >= 47

    pillar4_tables = {
        "active_time_timers",
        "user_workload_capacities",
    }
    for table in pillar4_tables:
        assert table in _KNOWN_TABLES, f"Table {table} missing from _KNOWN_TABLES"


def test_detect_tables_detects_pillar4_tables():
    """Verify _detect_tables correctly extracts table names from Pillar 4 queries."""
    sample_queries = [
        ("SELECT * FROM active_time_timers WHERE user_id = $1", {"active_time_timers"}),
        ("INSERT INTO user_workload_capacities (user_id, weekly_capacity_hours) VALUES ($1, $2)", {"user_workload_capacities"}),
        ("SELECT * FROM active_time_timers JOIN tasks ON active_time_timers.task_id = tasks.task_id", {"active_time_timers", "tasks"}),
    ]
    for sql, expected in sample_queries:
        detected = _detect_tables(sql)
        assert expected.issubset(detected), f"Expected {expected} in detected {detected} for query: {sql}"


def test_v38_migration_splits_cleanly():
    """Verify migration 38 parses into executable SQL statements with no errors."""
    v38_sql = next(s for v, s in MIGRATIONS if v == 38)
    statements = _split_sql_statements(v38_sql)
    assert len(statements) == 7, f"Migration v38 expected 7 statements, got {len(statements)}"

    last_stmt = statements[-1]
    assert "INSERT INTO schema_version VALUES (38)" in last_stmt, (
        f"Migration v38 does not properly upsert schema_version: {last_stmt}"
    )


def test_v38_migration_idempotency_guards():
    """Verify all table creation, alter, and index statements in v38 use IF NOT EXISTS."""
    v38_sql = next(s for v, s in MIGRATIONS if v == 38)
    statements = _split_sql_statements(v38_sql)
    for stmt in statements:
        if "CREATE TABLE" in stmt:
            assert "IF NOT EXISTS" in stmt, f"CREATE TABLE missing IF NOT EXISTS in v38: {stmt}"
        if "ALTER TABLE" in stmt and "ADD COLUMN" in stmt:
            assert "IF NOT EXISTS" in stmt, f"ALTER TABLE missing IF NOT EXISTS in v38: {stmt}"
        if "CREATE INDEX" in stmt:
            assert "IF NOT EXISTS" in stmt, f"CREATE INDEX missing IF NOT EXISTS in v38: {stmt}"


def test_v38_schema_elements_presence():
    """Verify all new tables and columns are present in v38."""
    v38_sql = next(s for v, s in MIGRATIONS if v == 38)
    expected_elements = [
        "CREATE TABLE IF NOT EXISTS active_time_timers",
        "user_id TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE",
        "task_id INTEGER NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE",
        "CREATE TABLE IF NOT EXISTS user_workload_capacities",
        "weekly_capacity_hours NUMERIC(5, 2) NOT NULL DEFAULT 40.0",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS budget NUMERIC(12, 2) DEFAULT 0.0;",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS currency TEXT NOT NULL DEFAULT 'THB';",
        "ALTER TABLE project_members ADD COLUMN IF NOT EXISTS hourly_rate NUMERIC(10, 2) NOT NULL DEFAULT 0.0;",
    ]
    for elem in expected_elements:
        assert elem in v38_sql, f"Expected schema element missing in v38: {elem}"


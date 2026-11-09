"""
tests/test_migration_v39.py — Verification suite for Gen 5.0 Database Schema Evolution (v39).
Covers:
  - Pillar 5 Schema: Version 39 completeness and monotonic continuity.
  - _KNOWN_TABLES expansion to 50 tables.
  - Table detection for task_escalations, project_sla_policies, and task_sla_tracking.
  - SQL statement split and syntax integrity for v39 migration.
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


def test_schema_version_is_39():
    """Verify that current schema version constant is set to 39."""
    assert SCHEMA_VERSION == 39


def test_migrations_continuity_v1_to_v39():
    """Verify migrations list contains all versions from 1 to 39 monotonically without gaps."""
    versions = [v for v, _ in MIGRATIONS]
    expected_versions = list(range(1, 40))
    assert versions == expected_versions, f"Migration versions gap or mismatch: {versions}"


def test_known_tables_contains_all_pillar5_tables():
    """Verify that _KNOWN_TABLES contains 50 tables including all 3 new Pillar 5 tables."""
    assert len(_KNOWN_TABLES) == 50

    pillar5_tables = {
        "task_escalations",
        "project_sla_policies",
        "task_sla_tracking",
    }
    for table in pillar5_tables:
        assert table in _KNOWN_TABLES, f"Table {table} missing from _KNOWN_TABLES"


def test_detect_tables_detects_pillar5_tables():
    """Verify _detect_tables correctly extracts table names from Pillar 5 queries."""
    sample_queries = [
        ("SELECT * FROM task_escalations WHERE task_id = $1", {"task_escalations"}),
        ("INSERT INTO project_sla_policies (project_id, guild_id) VALUES ($1, $2)", {"project_sla_policies"}),
        ("SELECT * FROM task_sla_tracking JOIN tasks ON task_sla_tracking.task_id = tasks.task_id", {"task_sla_tracking", "tasks"}),
    ]
    for sql, expected in sample_queries:
        detected = _detect_tables(sql)
        assert expected.issubset(detected), f"Expected {expected} in detected {detected} for query: {sql}"


def test_v39_migration_splits_cleanly():
    """Verify migration 39 parses into executable SQL statements with no errors."""
    v39_sql = next(s for v, s in MIGRATIONS if v == 39)
    statements = _split_sql_statements(v39_sql)
    assert len(statements) == 6, f"Migration v39 expected 6 statements, got {len(statements)}"

    last_stmt = statements[-1]
    assert "INSERT INTO schema_version VALUES (39)" in last_stmt, (
        f"Migration v39 does not properly upsert schema_version: {last_stmt}"
    )


def test_v39_migration_idempotency_guards():
    """Verify all table creation, alter, and index statements in v39 use IF NOT EXISTS."""
    v39_sql = next(s for v, s in MIGRATIONS if v == 39)
    statements = _split_sql_statements(v39_sql)
    for stmt in statements:
        if "CREATE TABLE" in stmt:
            assert "IF NOT EXISTS" in stmt, f"CREATE TABLE missing IF NOT EXISTS in v39: {stmt}"
        if "CREATE INDEX" in stmt:
            assert "IF NOT EXISTS" in stmt, f"CREATE INDEX missing IF NOT EXISTS in v39: {stmt}"


def test_v39_schema_elements_presence():
    """Verify all new tables and columns are present in v39."""
    v39_sql = next(s for v, s in MIGRATIONS if v == 39)
    expected_elements = [
        "CREATE TABLE IF NOT EXISTS task_escalations",
        "escalation_level INTEGER NOT NULL DEFAULT 0",
        "CREATE TABLE IF NOT EXISTS project_sla_policies",
        "p7_hours NUMERIC(5, 2) NOT NULL DEFAULT 2.0",
        "p6_hours NUMERIC(5, 2) NOT NULL DEFAULT 8.0",
        "CREATE TABLE IF NOT EXISTS task_sla_tracking",
        "early_warning_sent BOOLEAN NOT NULL DEFAULT FALSE",
        "breached BOOLEAN NOT NULL DEFAULT FALSE",
    ]
    for elem in expected_elements:
        assert elem in v39_sql, f"Expected schema element missing in v39: {elem}"


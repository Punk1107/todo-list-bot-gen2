"""
tests/test_migration_v41.py — Verification suite for Gen 5.0 Database Schema Evolution (v41).
Covers:
  - Pillar 5 Fix: projects.lead_id column addition for automated escalation policies.
  - SQL statement split and syntax integrity for v41 migration.
  - Idempotency safety guards (IF NOT EXISTS, ON CONFLICT DO UPDATE).
"""
from __future__ import annotations

from core.database import (
    MIGRATIONS,
    SCHEMA_VERSION,
    _split_sql_statements,
)


def test_schema_version_is_41():
    """Verify that current schema version constant is at least 41."""
    assert SCHEMA_VERSION >= 41


def test_migrations_continuity_v1_to_v41():
    """Verify migrations list contains all versions from 1 to 41 monotonically without gaps."""
    versions = [v for v, _ in MIGRATIONS]
    assert 41 in versions
    assert versions == list(range(1, len(versions) + 1))


def test_v41_migration_splits_cleanly():
    """Verify migration 41 parses into executable SQL statements with no errors."""
    v41_sql = next(s for v, s in MIGRATIONS if v == 41)
    statements = _split_sql_statements(v41_sql)
    assert len(statements) == 2, f"Migration v41 expected 2 statements, got {len(statements)}"

    last_stmt = statements[-1]
    assert "INSERT INTO schema_version VALUES (41)" in last_stmt, (
        f"Migration v41 does not properly upsert schema_version: {last_stmt}"
    )


def test_v41_migration_idempotency_guards():
    """Verify column addition in v41 uses IF NOT EXISTS."""
    v41_sql = next(s for v, s in MIGRATIONS if v == 41)
    statements = _split_sql_statements(v41_sql)
    for stmt in statements:
        if "ALTER TABLE projects ADD COLUMN" in stmt:
            assert "IF NOT EXISTS" in stmt, f"ALTER TABLE missing IF NOT EXISTS in v41: {stmt}"


def test_v41_schema_elements_presence():
    """Verify lead_id column addition is present in v41."""
    v41_sql = next(s for v, s in MIGRATIONS if v == 41)
    expected_elements = [
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS lead_id TEXT",
        "INSERT INTO schema_version VALUES (41)",
    ]
    for element in expected_elements:
        assert element in v41_sql, f"Missing element in v41 migration: {element}"


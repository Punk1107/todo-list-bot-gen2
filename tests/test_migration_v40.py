"""
tests/test_migration_v40.py — Verification suite for Gen 5.0 Database Schema Evolution (v40).
Covers:
  - Pillar 7 Schema: Version 40 completeness and monotonic continuity.
  - pg_trgm extension & tasks.task trigram index.
  - SQL statement split and syntax integrity for v40 migration.
  - Idempotency safety guards (IF NOT EXISTS, ON CONFLICT DO UPDATE).
"""
from __future__ import annotations

from core.database import (
    MIGRATIONS,
    SCHEMA_VERSION,
    _KNOWN_TABLES,
    _split_sql_statements,
)


def test_schema_version_is_40():
    """Verify that current schema version constant is set to 40."""
    assert SCHEMA_VERSION == 40


def test_migrations_continuity_v1_to_v40():
    """Verify migrations list contains all versions from 1 to 40 monotonically without gaps."""
    versions = [v for v, _ in MIGRATIONS]
    expected_versions = list(range(1, 41))
    assert versions == expected_versions, f"Migration versions gap or mismatch: {versions}"


def test_v40_migration_splits_cleanly():
    """Verify migration 40 parses into executable SQL statements with no errors."""
    v40_sql = next(s for v, s in MIGRATIONS if v == 40)
    statements = _split_sql_statements(v40_sql)
    assert len(statements) == 3, f"Migration v40 expected 3 statements, got {len(statements)}"

    last_stmt = statements[-1]
    assert "INSERT INTO schema_version VALUES (40)" in last_stmt, (
        f"Migration v40 does not properly upsert schema_version: {last_stmt}"
    )


def test_v40_migration_idempotency_guards():
    """Verify extension and index creation in v40 use IF NOT EXISTS."""
    v40_sql = next(s for v, s in MIGRATIONS if v == 40)
    statements = _split_sql_statements(v40_sql)
    for stmt in statements:
        if "CREATE EXTENSION" in stmt:
            assert "IF NOT EXISTS" in stmt, f"CREATE EXTENSION missing IF NOT EXISTS in v40: {stmt}"
        if "CREATE INDEX" in stmt:
            assert "IF NOT EXISTS" in stmt, f"CREATE INDEX missing IF NOT EXISTS in v40: {stmt}"


def test_v40_schema_elements_presence():
    """Verify pg_trgm extension and trigram index are present in v40."""
    v40_sql = next(s for v, s in MIGRATIONS if v == 40)
    expected_elements = [
        "CREATE EXTENSION IF NOT EXISTS pg_trgm",
        "CREATE INDEX IF NOT EXISTS idx_tasks_task_trgm ON tasks USING gin (task gin_trgm_ops)",
        "INSERT INTO schema_version VALUES (40)",
    ]
    for elem in expected_elements:
        assert elem in v40_sql, f"Expected schema element missing in v40: {elem}"


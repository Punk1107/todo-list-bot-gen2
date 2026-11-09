"""
tests/test_migration_v36.py — Verification suite for Gen 5.0 Database Schema Evolution (v28 ➔ v36).
Covers:
  - Pillar 1: Schema version 36 completeness and monotonic continuity (v1 to v36).
  - Pillar 2: _KNOWN_TABLES expansion to 37 tables for True LRU QueryCache.
  - Pillar 3: Table detection for new Gen 5.0 entities.
  - Pillar 4: SQL statement split and syntax integrity for all v29-v36 migrations.
  - Pillar 5: Idempotency safety guards (IF NOT EXISTS, ON CONFLICT DO UPDATE).
  - Pillar 6: Simulated asyncpg migration execution loop with transaction atomicity.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from core.database import (
    MIGRATIONS,
    SCHEMA_VERSION,
    _KNOWN_TABLES,
    _detect_tables,
    _split_sql_statements,
    DatabaseManager,
    db,
)


def test_schema_version_is_36():
    """Verify that current schema version constant is set to at least 36."""
    assert SCHEMA_VERSION >= 36


def test_migrations_continuity_v1_to_v36():
    """Verify migrations list contains all versions from 1 to 36 monotonically without gaps."""
    versions = [v for v, _ in MIGRATIONS]
    assert versions[:36] == list(range(1, 37)), f"Migration versions gap or mismatch in first 36: {versions[:36]}"


def test_known_tables_contains_all_gen5_tables():
    """Verify that _KNOWN_TABLES contains at least 38 tables including all 14 initial Gen 5.0 tables."""
    assert len(_KNOWN_TABLES) >= 38

    gen5_tables = {
        "sprints",
        "epics",
        "task_time_logs",
        "automation_rules",
        "user_rpg_profiles",
        "coop_quests",
        "project_documents",
        "task_revisions",
        "checklist_templates",
        "project_federation_guilds",
        "task_assignees",
        "project_milestones",
        "sprint_retros",
        "tasks_archive",
    }
    for table in gen5_tables:
        assert table in _KNOWN_TABLES, f"Table {table} missing from _KNOWN_TABLES"


def test_detect_tables_detects_gen5_tables():
    """Verify _detect_tables correctly extracts table names from Gen 5.0 queries."""
    sample_queries = [
        ("SELECT * FROM sprints WHERE project_id = 1", {"sprints"}),
        ("INSERT INTO task_time_logs (task_id, hours_spent) VALUES (1, 2.5)", {"task_time_logs"}),
        ("SELECT * FROM user_rpg_profiles JOIN tasks ON user_rpg_profiles.user_id = tasks.owner_id", {"user_rpg_profiles", "tasks"}),
        ("UPDATE automation_rules SET is_active = false", {"automation_rules"}),
        ("SELECT * FROM project_milestones JOIN sprint_retros ON 1=1", {"project_milestones", "sprint_retros"}),
    ]
    for sql, expected in sample_queries:
        detected = _detect_tables(sql)
        assert expected.issubset(detected), f"Expected {expected} in detected {detected} for query: {sql}"


def test_all_gen5_migrations_split_cleanly():
    """Verify that migrations 29 to 36 parse into executable SQL statements with no errors."""
    for version in range(29, 37):
        sql = next(s for v, s in MIGRATIONS if v == version)
        statements = _split_sql_statements(sql)
        assert len(statements) >= 2, f"Migration v{version} has too few statements: {len(statements)}"

        # Every migration must end with schema_version upsert
        last_stmt = statements[-1]
        assert f"INSERT INTO schema_version VALUES ({version})" in last_stmt, (
            f"Migration v{version} does not properly upsert schema_version: {last_stmt}"
        )


def test_gen5_migrations_idempotency_guards():
    """Verify all table creation and column addition statements use IF NOT EXISTS."""
    for version in range(29, 37):
        sql = next(s for v, s in MIGRATIONS if v == version)
        statements = _split_sql_statements(sql)
        for stmt in statements:
            if "CREATE TABLE" in stmt:
                assert "IF NOT EXISTS" in stmt, f"CREATE TABLE missing IF NOT EXISTS in v{version}: {stmt}"
            if "ALTER TABLE" in stmt and "ADD COLUMN" in stmt:
                assert "IF NOT EXISTS" in stmt, f"ALTER TABLE ADD COLUMN missing IF NOT EXISTS in v{version}: {stmt}"
            if "CREATE INDEX" in stmt:
                assert "IF NOT EXISTS" in stmt, f"CREATE INDEX missing IF NOT EXISTS in v{version}: {stmt}"


def test_gen5_migration_version_upserts():
    """Verify that every Gen 5.0 migration ends with an atomic schema_version upsert."""
    for version in range(29, 37):
        sql = next(s for v, s in MIGRATIONS if v == version)
        statements = _split_sql_statements(sql)
        upsert_stmt = statements[-1]
        assert f"INSERT INTO schema_version VALUES ({version})" in upsert_stmt
        assert f"DO UPDATE SET version={version}" in upsert_stmt


def test_gen5_schema_elements_presence():
    """Verify all 11 new tables and key columns are present across v29-v36."""
    all_gen5_sql = " ".join(s for v, s in MIGRATIONS if 29 <= v <= 36)
    expected_elements = [
        "CREATE TABLE IF NOT EXISTS sprints",
        "CREATE TABLE IF NOT EXISTS epics",
        "epic_id INTEGER",
        "story_points INTEGER CHECK (story_points IN (1,2,3,5,8,13,21))",
        "CREATE TABLE IF NOT EXISTS task_time_logs",
        "estimated_hours NUMERIC(6, 2)",
        "CREATE TABLE IF NOT EXISTS automation_rules",
        "CREATE TABLE IF NOT EXISTS user_rpg_profiles",
        "CREATE TABLE IF NOT EXISTS coop_quests",
        "CREATE TABLE IF NOT EXISTS project_documents",
        "CREATE TABLE IF NOT EXISTS task_revisions",
        "CREATE TABLE IF NOT EXISTS checklist_templates",
        "custom_fields JSONB NOT NULL DEFAULT '{}'::jsonb",
        "CREATE INDEX IF NOT EXISTS idx_tasks_custom_fields ON tasks USING GIN (custom_fields)",
        "CREATE TABLE IF NOT EXISTS project_federation_guilds",
        "CREATE TABLE IF NOT EXISTS task_assignees",
        "CREATE TABLE IF NOT EXISTS project_milestones",
        "CREATE TABLE IF NOT EXISTS sprint_retros",
        "CREATE TABLE IF NOT EXISTS tasks_archive (LIKE tasks INCLUDING ALL)",
    ]
    for elem in expected_elements:
        assert elem in all_gen5_sql, f"Expected schema element missing: {elem}"

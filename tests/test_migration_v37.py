"""
tests/test_migration_v37.py — Verification suite for Gen 5.0 Database Schema Evolution (v37).
Covers:
  - Pillar 3 Schema: Version 37 completeness and continuity.
  - _KNOWN_TABLES expansion to 45 tables.
  - Table detection for all 7 new Pillar 3 entities.
  - SQL statement split and syntax integrity for v37 migration.
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


def test_schema_version_is_37():
    """Verify that current schema version constant is set to 37."""
    assert SCHEMA_VERSION == 37


def test_migrations_continuity_v1_to_v37():
    """Verify migrations list contains all versions from 1 to 37 monotonically without gaps."""
    versions = [v for v, _ in MIGRATIONS]
    expected_versions = list(range(1, 38))
    assert versions == expected_versions, f"Migration versions gap or mismatch: {versions}"


def test_known_tables_contains_all_pillar3_tables():
    """Verify that _KNOWN_TABLES contains 45 tables including all 7 new Pillar 3 tables."""
    assert len(_KNOWN_TABLES) == 45

    pillar3_tables = {
        "voice_focus_rooms",
        "user_chime_settings",
        "project_scheduled_events",
        "project_forum_configs",
        "task_forum_posts",
        "standup_configs",
        "daily_standups",
    }
    for table in pillar3_tables:
        assert table in _KNOWN_TABLES, f"Table {table} missing from _KNOWN_TABLES"


def test_detect_tables_detects_pillar3_tables():
    """Verify _detect_tables correctly extracts table names from Pillar 3 queries."""
    sample_queries = [
        ("SELECT * FROM voice_focus_rooms WHERE guild_id = 1", {"voice_focus_rooms"}),
        ("INSERT INTO user_chime_settings (user_id, chime_enabled) VALUES (1, true)", {"user_chime_settings"}),
        ("SELECT * FROM project_scheduled_events WHERE project_id = 1", {"project_scheduled_events"}),
        ("SELECT * FROM project_forum_configs WHERE project_id = 1", {"project_forum_configs"}),
        ("SELECT * FROM task_forum_posts WHERE task_id = 1", {"task_forum_posts"}),
        ("SELECT * FROM standup_configs WHERE guild_id = 1", {"standup_configs"}),
        ("SELECT * FROM daily_standups WHERE guild_id = 1 AND standup_date = CURRENT_DATE", {"daily_standups"}),
    ]
    for sql, expected in sample_queries:
        detected = _detect_tables(sql)
        assert expected.issubset(detected), f"Expected {expected} in detected {detected} for query: {sql}"


def test_v37_migration_splits_cleanly():
    """Verify migration 37 parses into executable SQL statements with no errors."""
    v37_sql = next(s for v, s in MIGRATIONS if v == 37)
    statements = _split_sql_statements(v37_sql)
    assert len(statements) == 12, f"Migration v37 expected 12 statements, got {len(statements)}"

    last_stmt = statements[-1]
    assert "INSERT INTO schema_version VALUES (37)" in last_stmt, (
        f"Migration v37 does not properly upsert schema_version: {last_stmt}"
    )


def test_v37_migration_idempotency_guards():
    """Verify all table creation and index statements in v37 use IF NOT EXISTS."""
    v37_sql = next(s for v, s in MIGRATIONS if v == 37)
    statements = _split_sql_statements(v37_sql)
    for stmt in statements:
        if "CREATE TABLE" in stmt:
            assert "IF NOT EXISTS" in stmt, f"CREATE TABLE missing IF NOT EXISTS in v37: {stmt}"
        if "CREATE INDEX" in stmt:
            assert "IF NOT EXISTS" in stmt, f"CREATE INDEX missing IF NOT EXISTS in v37: {stmt}"


def test_v37_schema_elements_presence():
    """Verify all 7 new tables and key columns are present in v37."""
    v37_sql = next(s for v, s in MIGRATIONS if v == 37)
    expected_elements = [
        "CREATE TABLE IF NOT EXISTS voice_focus_rooms",
        "channel_id TEXT PRIMARY KEY",
        "current_phase TEXT NOT NULL DEFAULT 'idle'",
        "CREATE TABLE IF NOT EXISTS user_chime_settings",
        "chime_enabled BOOLEAN NOT NULL DEFAULT TRUE",
        "CREATE TABLE IF NOT EXISTS project_scheduled_events",
        "event_id TEXT PRIMARY KEY",
        "CREATE TABLE IF NOT EXISTS project_forum_configs",
        "forum_channel_id TEXT NOT NULL",
        "CREATE TABLE IF NOT EXISTS task_forum_posts",
        "thread_id TEXT NOT NULL",
        "CREATE TABLE IF NOT EXISTS standup_configs",
        "standup_time TEXT NOT NULL DEFAULT '09:30'",
        "CREATE TABLE IF NOT EXISTS daily_standups",
        "blockers_text TEXT",
    ]
    for elem in expected_elements:
        assert elem in v37_sql, f"Expected schema element missing in v37: {elem}"

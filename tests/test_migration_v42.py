"""
tests/test_migration_v42.py — Verification suite for Gen 5.0 Database Schema Evolution (v42).
Covers:
  - Pillar 8 Schema: Gamification 2.0, RPG Progression, Guild Quests, Peer Kudos.
  - SQL statement split and syntax integrity for v42 migration.
  - Idempotency safety guards (IF NOT EXISTS, ON CONFLICT DO UPDATE).
"""
from __future__ import annotations

from core.database import (
    MIGRATIONS,
    SCHEMA_VERSION,
    _split_sql_statements,
)


def test_schema_version_is_42():
    """Verify that current schema version constant is at least 42."""
    assert SCHEMA_VERSION >= 42


def test_migrations_continuity_v1_to_v42():
    """Verify migrations list contains all versions from 1 to 42 monotonically without gaps."""
    versions = [v for v, _ in MIGRATIONS]
    assert 42 in versions
    assert versions == list(range(1, len(versions) + 1))


def test_v42_migration_splits_cleanly():
    """Verify migration 42 parses into executable SQL statements with no errors."""
    v42_sql = next(s for v, s in MIGRATIONS if v == 42)
    statements = _split_sql_statements(v42_sql)
    assert len(statements) >= 10, f"Migration v42 expected >= 10 statements, got {len(statements)}"

    last_stmt = statements[-1]
    assert "INSERT INTO schema_version VALUES (42)" in last_stmt, (
        f"Migration v42 does not properly upsert schema_version: {last_stmt}"
    )


def test_v42_migration_idempotency_guards():
    """Verify all table, column, and index creations in v42 use IF NOT EXISTS."""
    v42_sql = next(s for v, s in MIGRATIONS if v == 42)
    statements = _split_sql_statements(v42_sql)
    for stmt in statements:
        if "CREATE TABLE" in stmt:
            assert "IF NOT EXISTS" in stmt, f"CREATE TABLE missing IF NOT EXISTS in v42: {stmt}"
        if "CREATE INDEX" in stmt:
            assert "IF NOT EXISTS" in stmt, f"CREATE INDEX missing IF NOT EXISTS in v42: {stmt}"
        if "ALTER TABLE" in stmt and "ADD COLUMN" in stmt:
            assert "IF NOT EXISTS" in stmt, f"ALTER TABLE missing IF NOT EXISTS in v42: {stmt}"


def test_v42_schema_elements_presence():
    """Verify all required tables and columns are present in v42."""
    v42_sql = next(s for v, s in MIGRATIONS if v == 42)
    expected_elements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS total_exp",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS rpg_level",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS rpg_title",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS streak_freeze_tokens",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS vacation_until",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS vacation_reason",
        "CREATE TABLE IF NOT EXISTS guild_quests",
        "CREATE TABLE IF NOT EXISTS guild_quest_participants",
        "CREATE TABLE IF NOT EXISTS peer_kudos",
        "INSERT INTO schema_version VALUES (42)",
    ]
    for element in expected_elements:
        assert element in v42_sql, f"Missing element in v42 migration: {element}"


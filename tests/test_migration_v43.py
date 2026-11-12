"""
tests/test_migration_v43.py — Schema Migration v43 verification (Gen 5.0 Pillar 9).
"""
from __future__ import annotations

from core import database


def test_schema_version_at_least_43():
    assert database.SCHEMA_VERSION >= 43


def test_known_tables_contains_project_custom_fields():
    for tbl in ("project_documents", "task_revisions", "project_custom_fields"):
        assert tbl in database._KNOWN_TABLES, f"{tbl} missing from _KNOWN_TABLES"


def test_migration_v43_exists_and_splits_cleanly():
    versions = [ver for ver, _ in database.MIGRATIONS]
    assert 43 in versions
    assert versions == sorted(versions), "MIGRATIONS must stay strictly ordered"

    sql_v43 = dict(database.MIGRATIONS)[43]
    stmts = database._split_sql_statements(sql_v43)
    assert len(stmts) >= 12

    combined = "\n".join(stmts).lower()
    assert "alter table project_documents add column if not exists guild_id" in combined
    assert "add column if not exists search_vector tsvector" in combined
    assert "using gin (search_vector)" in combined
    assert "alter table task_revisions add column if not exists new_description" in combined
    assert "create table if not exists project_custom_fields" in combined
    assert "alter table projects add column if not exists release_channel_id" in combined
    assert "insert into schema_version values (43)" in combined


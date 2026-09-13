"""
security_rls/migration_runner.py — Standalone Runner for RLS Migrations

Can be run directly:
    python -m security_rls.migration_runner --dry-run
    python -m security_rls.migration_runner --apply
    python -m security_rls.migration_runner --export
    python -m security_rls.migration_runner --rollback
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Sequence

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("rls_migration")

SQL_DIR = Path(__file__).resolve().parent / "sql"

SQL_FILES = [
    "01_rls_functions.sql",
    "02_rls_tasks.sql",
    "03_rls_projects_and_members.sql",
    "04_rls_categories_attachments.sql",
]

ROLLBACK_SQL = """
-- Rollback RLS policies and disable RLS on tables
ALTER TABLE IF EXISTS tasks DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS task_assignments DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS projects DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS project_members DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS categories DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS task_attachments DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS project_activity_log DISABLE ROW LEVEL SECURITY;

-- Drop Task Policies
DROP POLICY IF EXISTS tasks_personal_select ON tasks;
DROP POLICY IF EXISTS tasks_personal_insert ON tasks;
DROP POLICY IF EXISTS tasks_personal_update ON tasks;
DROP POLICY IF EXISTS tasks_personal_delete ON tasks;
DROP POLICY IF EXISTS tasks_group_select ON tasks;
DROP POLICY IF EXISTS tasks_group_insert ON tasks;
DROP POLICY IF EXISTS tasks_group_update ON tasks;
DROP POLICY IF EXISTS tasks_group_delete ON tasks;
DROP POLICY IF EXISTS task_assignments_select ON task_assignments;
DROP POLICY IF EXISTS task_assignments_insert ON task_assignments;
DROP POLICY IF EXISTS task_assignments_delete ON task_assignments;

-- Drop Project Policies
DROP POLICY IF EXISTS projects_select ON projects;
DROP POLICY IF EXISTS projects_insert ON projects;
DROP POLICY IF EXISTS projects_update ON projects;
DROP POLICY IF EXISTS projects_delete ON projects;
DROP POLICY IF EXISTS project_members_select ON project_members;
DROP POLICY IF EXISTS project_members_insert ON project_members;
DROP POLICY IF EXISTS project_members_update ON project_members;
DROP POLICY IF EXISTS project_members_delete ON project_members;

-- Drop Category & Attachment Policies
DROP POLICY IF EXISTS categories_select ON categories;
DROP POLICY IF EXISTS categories_insert ON categories;
DROP POLICY IF EXISTS categories_update ON categories;
DROP POLICY IF EXISTS categories_delete ON categories;
DROP POLICY IF EXISTS attachments_select ON task_attachments;
DROP POLICY IF EXISTS attachments_insert ON task_attachments;
DROP POLICY IF EXISTS attachments_delete ON task_attachments;
DROP POLICY IF EXISTS activity_log_select ON project_activity_log;
DROP POLICY IF EXISTS activity_log_insert ON project_activity_log;

-- Drop Helper Functions
DROP FUNCTION IF EXISTS can_manage_project_tasks(INTEGER, TEXT);
DROP FUNCTION IF EXISTS get_project_role(INTEGER, TEXT);
DROP FUNCTION IF EXISTS is_project_member(INTEGER, TEXT);
DROP FUNCTION IF EXISTS current_app_user();
"""


def load_all_sql() -> str:
    """Concatenate all RLS SQL migration scripts."""
    combined: list[str] = []
    for fname in SQL_FILES:
        fpath = SQL_DIR / fname
        if not fpath.exists():
            raise FileNotFoundError(f"Migration file missing: {fpath}")
        combined.append(f"-- ==================== {fname} ====================")
        combined.append(fpath.read_text(encoding="utf-8"))
    return "\n\n".join(combined)


async def apply_migration(dry_run: bool = False, rollback: bool = False) -> None:
    from core.database import db, _split_sql_statements

    if rollback:
        sql = ROLLBACK_SQL
        log.info("Preparing to ROLLBACK Row Level Security policies...")
    else:
        sql = load_all_sql()
        log.info("Preparing to APPLY Row Level Security policies...")

    statements = _split_sql_statements(sql)
    log.info("Parsed %d SQL statements.", len(statements))

    if dry_run:
        log.info("[DRY RUN] Would execute %d statements against database. No changes made.", len(statements))
        return

    await db.initialize()
    async with db.acquire() as conn:
        async with conn.transaction():
            for idx, stmt in enumerate(statements, 1):
                clean = stmt.strip()
                if not clean:
                    continue
                log.info("Executing statement %d/%d: %.60s...", idx, len(statements), clean.replace("\n", " "))
                await conn.execute(clean)

    log.info("Successfully executed all RLS statements!")


def main(args: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Manage Supabase Row Level Security (RLS) Migrations")
    parser.add_argument("--dry-run", action="store_true", help="Validate SQL without applying to DB")
    parser.add_argument("--apply", action="store_true", help="Apply RLS policies to the database")
    parser.add_argument("--rollback", action="store_true", help="Remove RLS policies and disable RLS")
    parser.add_argument("--export", action="store_true", help="Print concatenated SQL to stdout for Supabase SQL Editor")

    parsed = parser.parse_args(args)

    if parsed.export:
        print(load_all_sql())
        return

    if not (parsed.dry_run or parsed.apply or parsed.rollback):
        parser.print_help()
        sys.exit(1)

    asyncio.run(apply_migration(dry_run=parsed.dry_run, rollback=parsed.rollback))


if __name__ == "__main__":
    main()

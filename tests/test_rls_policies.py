"""
tests/test_rls_policies.py — Unit Tests for Row Level Security (RLS) Module

Tests:
  1. SQL script loading and statement parsing
  2. Scoped user context manager (setting/resetting contextvars and DB session config)
  3. RLSClient query delegation under user scope
  4. Isolation logic verification (Personal tasks vs Group tasks)
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from security_rls.context import scoped_user_context, get_current_scoped_user
from security_rls.client import RLSClient
from security_rls.migration_runner import load_all_sql, ROLLBACK_SQL
from core.database import _split_sql_statements


# ─────────────────────────────────────────────────────────────────────────────
# 1. SQL Script & Migration Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRLSSQLParsing:
    def test_load_all_sql_contains_expected_policies(self):
        sql = load_all_sql()
        assert "CREATE OR REPLACE FUNCTION current_app_user()" in sql
        assert "tasks_personal_select" in sql
        assert "tasks_personal_insert" in sql
        assert "tasks_personal_update" in sql
        assert "tasks_personal_delete" in sql
        assert "tasks_group_select" in sql
        assert "tasks_group_insert" in sql
        assert "projects_select" in sql
        assert "categories_select" in sql
        assert "attachments_select" in sql

    def test_split_statements_count(self):
        sql = load_all_sql()
        statements = _split_sql_statements(sql)
        assert len(statements) > 40
        # Ensure all statements are non-empty
        for s in statements:
            assert s.strip() != ""

    def test_rollback_sql_syntax(self):
        statements = _split_sql_statements(ROLLBACK_SQL)
        assert len(statements) > 10
        assert any("DROP POLICY" in s for s in statements)
        assert any("DROP FUNCTION" in s for s in statements)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Context Manager Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRLSContext:
    @pytest.mark.asyncio
    async def test_scoped_user_context_activates_and_cleans_up(self):
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()

        assert get_current_scoped_user() is None

        async with scoped_user_context(mock_conn, "user_12345") as uid:
            assert uid == "user_12345"
            assert get_current_scoped_user() == "user_12345"
            # Verify set_config was called with user_12345
            mock_conn.execute.assert_any_call(
                "SELECT set_config('app.current_user_id', $1, true)", "user_12345"
            )

        # After block, contextvar should be reset to None
        assert get_current_scoped_user() is None
        # And cleanup execute was called
        mock_conn.execute.assert_called_with("SELECT set_config('app.current_user_id', '', true)")

    @pytest.mark.asyncio
    async def test_empty_user_id_raises_value_error(self):
        mock_conn = AsyncMock()
        with pytest.raises(ValueError):
            async with scoped_user_context(mock_conn, ""):
                pass


# ─────────────────────────────────────────────────────────────────────────────
# 3. RLSClient Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRLSClient:
    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        conn = MagicMock()
        conn.execute = AsyncMock(return_value="UPDATE 1")
        conn.fetchrow = AsyncMock(return_value={"task_id": 1, "task": "Secret personal task", "owner_id": "alice"})
        conn.fetch = AsyncMock(return_value=[
            {"task_id": 1, "task": "Task 1", "owner_id": "alice"},
            {"task_id": 2, "task": "Task 2", "owner_id": "alice"},
        ])

        # Transaction context manager
        tx = MagicMock()
        tx.__aenter__ = AsyncMock(return_value=tx)
        tx.__aexit__ = AsyncMock(return_value=None)
        conn.transaction.return_value = tx

        # Acquire context manager
        acquire_ctx = MagicMock()
        acquire_ctx.__aenter__ = AsyncMock(return_value=conn)
        acquire_ctx.__aexit__ = AsyncMock(return_value=None)
        db.acquire.return_value = acquire_ctx

        return db, conn

    @pytest.mark.asyncio
    async def test_fetchone_as_user(self, mock_db):
        db, conn = mock_db
        client = RLSClient(db)

        row = await client.fetchone_as_user("alice", "SELECT * FROM tasks WHERE task_id = $1", 1)
        assert row is not None
        assert row["task_id"] == 1
        assert row["owner_id"] == "alice"
        # Verify set_config was executed
        conn.execute.assert_any_call("SELECT set_config('app.current_user_id', $1, true)", "alice")

    @pytest.mark.asyncio
    async def test_fetchall_as_user(self, mock_db):
        db, conn = mock_db
        client = RLSClient(db)

        rows = await client.fetchall_as_user("alice", "SELECT * FROM tasks")
        assert len(rows) == 2
        assert rows[0]["task"] == "Task 1"

    @pytest.mark.asyncio
    async def test_fetch_accessible_tasks_personal_vs_project(self, mock_db):
        db, conn = mock_db
        client = RLSClient(db)

        # Without project_id
        await client.fetch_accessible_tasks("alice")
        conn.fetch.assert_called_with("SELECT * FROM tasks ORDER BY task_id DESC")

        # With project_id
        await client.fetch_accessible_tasks("alice", project_id=10)
        conn.fetch.assert_called_with(
            "SELECT * FROM tasks WHERE project_id = $1 ORDER BY task_id DESC", 10
        )

    @pytest.mark.asyncio
    async def test_execute_as_user(self, mock_db):
        db, conn = mock_db
        client = RLSClient(db)

        res = await client.execute_as_user(
            "alice",
            "INSERT INTO tasks (task, owner_id) VALUES ($1, $2)",
            "My personal task",
            "alice"
        )
        assert res == "UPDATE 1"
        conn.execute.assert_any_call("SELECT set_config('app.current_user_id', $1, true)", "alice")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Policy Rules Isolation Simulation
# ─────────────────────────────────────────────────────────────────────────────

class TestRLSPermissionMatrix:
    """
    Simulates the RLS policy predicates in Python to assert security invariants:
      - Personal tasks cannot be read by strangers
      - Group tasks can only be managed by leads or members
      - Viewers cannot insert or update group tasks
    """

    @staticmethod
    def can_select_task(task: dict, actor: str, is_member: bool, is_assigned: bool) -> bool:
        if task.get("project_id") is None:
            # Personal: owner or assigned
            return task.get("owner_id") == actor or is_assigned
        else:
            # Group: must be project member
            return is_member

    @staticmethod
    def can_manage_task(task: dict, actor: str, role: str | None) -> bool:
        if task.get("project_id") is None:
            return task.get("owner_id") == actor
        else:
            return role in ("lead", "member")

    @staticmethod
    def can_delete_group_task(task: dict, actor: str, role: str | None) -> bool:
        return role == "lead" or task.get("owner_id") == actor

    def test_personal_task_isolation(self):
        personal_task = {"task_id": 1, "task": "Doctor appt", "owner_id": "alice", "project_id": None}
        
        # Owner can read
        assert self.can_select_task(personal_task, actor="alice", is_member=False, is_assigned=False)
        # Stranger cannot read
        assert not self.can_select_task(personal_task, actor="bob", is_member=False, is_assigned=False)
        # Assigned user can read
        assert self.can_select_task(personal_task, actor="bob", is_member=False, is_assigned=True)

        # Only owner can manage
        assert self.can_manage_task(personal_task, actor="alice", role=None)
        assert not self.can_manage_task(personal_task, actor="bob", role=None)

    def test_group_task_permissions_and_viewer_restriction(self):
        group_task = {"task_id": 2, "task": "Sprint goal", "owner_id": "alice", "project_id": 42}

        # Members can read
        assert self.can_select_task(group_task, actor="bob", is_member=True, is_assigned=False)
        # Non-members cannot read
        assert not self.can_select_task(group_task, actor="charlie", is_member=False, is_assigned=False)

        # Lead and member can manage
        assert self.can_manage_task(group_task, actor="bob", role="lead")
        assert self.can_manage_task(group_task, actor="bob", role="member")
        # Viewer CANNOT manage (strictly read-only)
        assert not self.can_manage_task(group_task, actor="bob", role="viewer")

        # Delete: only lead or creator
        assert self.can_delete_group_task(group_task, actor="charlie", role="lead")
        assert self.can_delete_group_task(group_task, actor="alice", role="member") # creator
        assert not self.can_delete_group_task(group_task, actor="bob", role="member") # regular member not creator


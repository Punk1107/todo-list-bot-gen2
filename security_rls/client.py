"""
security_rls/client.py — RLS-enforced Database Client Adapter

Executes database operations wrapped in the appropriate user context, ensuring
that PostgreSQL Row Level Security (RLS) denies unauthorised access at the engine level.
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional, Sequence

from security_rls.context import scoped_user_context

log = logging.getLogger(__name__)


class RLSClient:
    """
    Executes database operations with user-scoped RLS context.

    Can be used alongside or wrapped around core.database.db without
    altering existing codebase interfaces.
    """

    def __init__(self, db_manager: Any) -> None:
        self._db = db_manager

    async def execute_as_user(
        self,
        user_id: str,
        sql: str,
        *args: Any,
    ) -> str:
        """Execute a write statement (INSERT/UPDATE/DELETE) under user_id RLS context."""
        async with self._db.acquire() as conn:
            async with conn.transaction():
                async with scoped_user_context(conn, user_id):
                    return await conn.execute(sql, *args)

    async def fetchone_as_user(
        self,
        user_id: str,
        sql: str,
        *args: Any,
    ) -> Optional[dict[str, Any]]:
        """Fetch a single row under user_id RLS context."""
        async with self._db.acquire() as conn:
            async with conn.transaction():
                async with scoped_user_context(conn, user_id):
                    record = await conn.fetchrow(sql, *args)
                    return dict(record) if record else None

    async def fetchall_as_user(
        self,
        user_id: str,
        sql: str,
        *args: Any,
    ) -> list[dict[str, Any]]:
        """Fetch multiple rows under user_id RLS context."""
        async with self._db.acquire() as conn:
            async with conn.transaction():
                async with scoped_user_context(conn, user_id):
                    records = await conn.fetch(sql, *args)
                    return [dict(r) for r in records]

    async def fetch_accessible_tasks(
        self,
        user_id: str,
        project_id: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch all tasks visible to user_id.
        Thanks to RLS, 'SELECT * FROM tasks' returns ONLY tasks the user is permitted to see!
        """
        if project_id is not None:
            sql = "SELECT * FROM tasks WHERE project_id = $1 ORDER BY task_id DESC"
            return await self.fetchall_as_user(user_id, sql, project_id)
        else:
            sql = "SELECT * FROM tasks ORDER BY task_id DESC"
            return await self.fetchall_as_user(user_id, sql)

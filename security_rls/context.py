"""
security_rls/context.py — Task-safe Scoped User Context for Row Level Security

Provides async context managers that set PostgreSQL session variables (SET LOCAL app.current_user_id)
inside transactions, enabling strict RLS policy enforcement for direct database connections.
"""
from __future__ import annotations

import contextvars
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Optional

log = logging.getLogger(__name__)

# Task-local storage for current user ID context
_current_user_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_rls_user", default=None
)


def get_current_scoped_user() -> Optional[str]:
    """Return the active user_id for the current async task, or None if in system context."""
    return _current_user_var.get()


@asynccontextmanager
async def scoped_user_context(
    conn: Any,
    user_id: str,
) -> AsyncGenerator[str, None]:
    """
    Context manager that sets the PostgreSQL session context to user_id.

    Usage:
        async with db.acquire() as conn:
            async with conn.transaction():
                async with scoped_user_context(conn, "123456789"):
                    # All queries executed on conn now evaluate current_app_user() == '123456789'
                    rows = await conn.fetch("SELECT * FROM tasks")

    Args:
        conn: An asyncpg Connection object.
        user_id: Discord Snowflake ID string or Supabase auth UID.

    Yields:
        The active user_id.
    """
    if not user_id:
        raise ValueError("user_id cannot be empty when activating scoped_user_context")

    token = _current_user_var.set(user_id)
    try:
        # SET LOCAL only lasts for the duration of the current transaction.
        # It prevents leaking the identity to subsequent pooled connection uses.
        await conn.execute("SELECT set_config('app.current_user_id', $1, true)", str(user_id))
        yield user_id
    finally:
        try:
            # Clear explicitly if connection remains open outside transaction
            await conn.execute("SELECT set_config('app.current_user_id', '', true)")
        except Exception:
            pass
        _current_user_var.reset(token)

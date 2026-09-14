"""
search_recommendation/query_builder.py — Safe Parameterized SQL Builder

Constructs asyncpg-compatible PostgreSQL queries using $1, $2, ... placeholders.
Never uses string interpolation for user-supplied values.

Design goals:
  - Composable: each method returns (fragment, params_list) tuples that can
    be assembled by the engine methods.
  - Single source of truth for field names, table aliases, and index hints.
  - Easy to extend: adding a new filter = adding one _add_xxx method.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from search_recommendation.models import SearchFilter, SortBy


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

_BASE_SELECT = """
SELECT
    t.task_id, t.task, t.deadline, t.priority, t.status,
    t.tags, t.description, t.note, t.owner_id, t.guild_id,
    t.project_id, t.is_pinned, t.created_at, t.updated_at,
    t.completed_at, t.search_vector
"""

_BASE_FROM = "FROM tasks t"

# FTS-enabled base (adds computed rank column)
_FTS_RANK_EXPR = "ts_rank_cd(t.search_vector, q.query, 32) AS rank_score"

_SORT_MAP: dict[SortBy, str] = {
    SortBy.RELEVANCE:    "rank_score DESC, t.priority DESC, t.deadline ASC",
    SortBy.DEADLINE_ASC: "t.deadline ASC NULLS LAST, t.priority DESC",
    SortBy.DEADLINE_DESC:"t.deadline DESC, t.priority DESC",
    SortBy.PRIORITY_DESC:"t.priority DESC, t.deadline ASC NULLS LAST",
    SortBy.CREATED_DESC: "t.created_at DESC",
}

# Maximum characters allowed in a search query string (security limit)
_MAX_QUERY_LEN = 200


# ─────────────────────────────────────────────────────────────────────────────
# Query Builder
# ─────────────────────────────────────────────────────────────────────────────

class SqlQueryBuilder:
    """
    Builds parameterized PostgreSQL queries for task search and recommendation.
    Usage:
        builder = SqlQueryBuilder()
        sql, params = builder.build_fts_query(query)
        rows = await db.fetchall(sql, params)
    """

    # ── FTS Query (Full Text Search) ──────────────────────────────────────────

    def build_fts_query(
        self,
        text: str,
        search_filter: SearchFilter,
        sort_by: SortBy,
        page: int,
        page_size: int,
    ) -> tuple[str, list[Any]]:
        """
        Build a full text search query using websearch_to_tsquery.
        Falls back gracefully if the query produces an empty tsquery.
        Returns (sql, params).
        """
        params: list[Any] = []
        idx = [1]  # mutable counter for $N placeholder

        def p(val: Any) -> str:
            """Add a parameter and return its $N placeholder."""
            params.append(val)
            placeholder = f"${idx[0]}"
            idx[0] += 1
            return placeholder

        # 1. Sanitize and prepare tsquery
        clean_text = self._sanitize_query(text)
        tsquery_placeholder = p(clean_text)

        where_clauses: list[str] = [
            f"t.search_vector @@ q.query"
        ]

        # 2. Scope filters
        self._apply_scope(search_filter, where_clauses, params, idx)

        # 3. Additional field filters
        self._apply_field_filters(search_filter, where_clauses, params, idx)

        where_sql = " AND ".join(where_clauses)

        # 4. Sorting
        order_sql = _SORT_MAP.get(sort_by, _SORT_MAP[SortBy.RELEVANCE])

        # 5. Pagination
        limit_placeholder  = p(min(page_size, 25))
        offset_placeholder = p((page - 1) * min(page_size, 25))

        sql = f"""
WITH q AS (
    SELECT websearch_to_tsquery('simple', {tsquery_placeholder}) AS query
)
SELECT
    t.task_id, t.task, t.deadline, t.priority, t.status,
    t.tags, t.description, t.note, t.owner_id, t.guild_id,
    t.project_id, t.is_pinned, t.created_at, t.updated_at,
    t.completed_at,
    {_FTS_RANK_EXPR}
FROM tasks t, q
WHERE {where_sql}
ORDER BY {order_sql}
LIMIT {limit_placeholder} OFFSET {offset_placeholder}
"""
        return sql.strip(), params

    def build_fts_count_query(
        self,
        text: str,
        search_filter: SearchFilter,
    ) -> tuple[str, list[Any]]:
        """Build the matching COUNT(*) query for pagination total."""
        params: list[Any] = []
        idx = [1]

        def p(val: Any) -> str:
            params.append(val)
            placeholder = f"${idx[0]}"
            idx[0] += 1
            return placeholder

        clean_text = self._sanitize_query(text)
        tsquery_placeholder = p(clean_text)

        where_clauses: list[str] = ["t.search_vector @@ q.query"]
        self._apply_scope(search_filter, where_clauses, params, idx)
        self._apply_field_filters(search_filter, where_clauses, params, idx)

        where_sql = " AND ".join(where_clauses)

        sql = f"""
WITH q AS (
    SELECT websearch_to_tsquery('simple', {tsquery_placeholder}) AS query
)
SELECT COUNT(*) AS total
FROM tasks t, q
WHERE {where_sql}
"""
        return sql.strip(), params

    # ── Filter-Only Query (no text) ───────────────────────────────────────────

    def build_filter_query(
        self,
        search_filter: SearchFilter,
        sort_by: SortBy,
        page: int,
        page_size: int,
    ) -> tuple[str, list[Any]]:
        """Build a filter-only query (no full text search, uses B-Tree indexes)."""
        params: list[Any] = []
        idx = [1]

        def p(val: Any) -> str:
            params.append(val)
            placeholder = f"${idx[0]}"
            idx[0] += 1
            return placeholder

        where_clauses: list[str] = []
        self._apply_scope(search_filter, where_clauses, params, idx)
        self._apply_field_filters(search_filter, where_clauses, params, idx)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        # Sort — relevance falls back to priority+deadline for filter-only
        effective_sort = sort_by if sort_by != SortBy.RELEVANCE else SortBy.PRIORITY_DESC
        order_sql = _SORT_MAP[effective_sort]

        limit_placeholder  = p(min(page_size, 25))
        offset_placeholder = p((page - 1) * min(page_size, 25))

        sql = f"""
SELECT
    t.task_id, t.task, t.deadline, t.priority, t.status,
    t.tags, t.description, t.note, t.owner_id, t.guild_id,
    t.project_id, t.is_pinned, t.created_at, t.updated_at,
    t.completed_at,
    0.0::real AS rank_score
FROM tasks t
{where_sql}
ORDER BY {order_sql}
LIMIT {limit_placeholder} OFFSET {offset_placeholder}
"""
        return sql.strip(), params

    def build_filter_count_query(
        self,
        search_filter: SearchFilter,
    ) -> tuple[str, list[Any]]:
        """Build the matching COUNT(*) for filter-only pagination."""
        params: list[Any] = []
        idx = [1]

        where_clauses: list[str] = []
        self._apply_scope(search_filter, where_clauses, params, idx)
        self._apply_field_filters(search_filter, where_clauses, params, idx)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        sql = f"""
SELECT COUNT(*) AS total
FROM tasks t
{where_sql}
"""
        return sql.strip(), params

    # ── Recommendation Candidate Query ────────────────────────────────────────

    def build_recommendation_candidates_query(
        self,
        user_id: str,
        guild_id: Optional[str],
        limit: int = 200,
    ) -> tuple[str, list[Any]]:
        """
        Fetch candidate tasks for the recommendation engine.
        Fetches up to `limit` non-completed, non-cancelled tasks for scoring.
        Deliberately over-fetches so the Python scorer can re-rank accurately.
        """
        params: list[Any] = []
        idx = [1]

        def p(val: Any) -> str:
            params.append(val)
            placeholder = f"${idx[0]}"
            idx[0] += 1
            return placeholder

        where_clauses = [
            f"t.status NOT IN ('Completed', 'Cancelled')",
            f"t.parent_task_id IS NULL",   # top-level tasks only by default
        ]

        if guild_id:
            # Shared project mode: tasks in this guild
            where_clauses.append(f"t.guild_id = {p(guild_id)}")
        else:
            # Personal mode: tasks owned by the user (no guild scope)
            where_clauses.append(f"t.owner_id = {p(user_id)}")
            where_clauses.append("t.guild_id IS NULL")

        where_sql = " AND ".join(where_clauses)
        limit_placeholder = p(min(limit, 500))

        sql = f"""
SELECT
    t.task_id, t.task, t.deadline, t.priority, t.status,
    t.tags, t.description, t.note, t.owner_id, t.guild_id,
    t.project_id, t.is_pinned, t.created_at, t.updated_at,
    t.completed_at,
    (
        SELECT STRING_AGG(ta.user_id, ',')
        FROM task_assignments ta
        WHERE ta.task_id = t.task_id
    ) AS assignee_ids
FROM tasks t
WHERE {where_sql}
ORDER BY t.priority DESC, t.deadline ASC NULLS LAST
LIMIT {limit_placeholder}
"""
        return sql.strip(), params

    # ── Internal Helpers ──────────────────────────────────────────────────────

    def _apply_scope(
        self,
        f: SearchFilter,
        clauses: list[str],
        params: list[Any],
        idx: list[int],
    ) -> None:
        """Apply owner_id / guild_id scoping and subtask filter."""
        def p(val: Any) -> str:
            params.append(val)
            placeholder = f"${idx[0]}"
            idx[0] += 1
            return placeholder

        if f.owner_id and f.guild_id:
            # Both specified: personal tasks in guild context (rare but supported)
            clauses.append(f"t.owner_id = {p(f.owner_id)}")
            clauses.append(f"t.guild_id = {p(f.guild_id)}")
        elif f.guild_id:
            clauses.append(f"t.guild_id = {p(f.guild_id)}")
        elif f.owner_id:
            clauses.append(f"t.owner_id = {p(f.owner_id)}")
            clauses.append("t.guild_id IS NULL")

        if not f.include_subtasks:
            clauses.append("t.parent_task_id IS NULL")

    def _apply_field_filters(
        self,
        f: SearchFilter,
        clauses: list[str],
        params: list[Any],
        idx: list[int],
    ) -> None:
        """Apply status, priority range, date range, and assignee filters."""
        def p(val: Any) -> str:
            params.append(val)
            placeholder = f"${idx[0]}"
            idx[0] += 1
            return placeholder

        if f.status:
            clauses.append(f"t.status = {p(f.status)}")

        if f.priority_min is not None:
            clauses.append(f"t.priority >= {p(f.priority_min)}")

        if f.priority_max is not None:
            clauses.append(f"t.priority <= {p(f.priority_max)}")

        if f.due_before:
            clauses.append(f"t.deadline <= {p(f.due_before)}")

        if f.due_after:
            clauses.append(f"t.deadline >= {p(f.due_after)}")

        if f.assignee_id:
            clauses.append(
                f"EXISTS ("
                f"  SELECT 1 FROM task_assignments ta"
                f"  WHERE ta.task_id = t.task_id AND ta.user_id = {p(f.assignee_id)}"
                f")"
            )

    @staticmethod
    def _sanitize_query(text: str) -> str:
        """
        Sanitize a user-provided search string for websearch_to_tsquery.
        - Truncate to _MAX_QUERY_LEN characters
        - Strip null bytes and control characters
        - Collapse excessive whitespace
        websearch_to_tsquery handles all other escaping internally.
        """
        text = text[:_MAX_QUERY_LEN]
        text = text.replace("\x00", "")
        text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

"""
search_recommendation/fts_engine.py — PostgreSQL Full Text Search Engine

Implements SearchEngineProtocol using PostgreSQL's native tsvector/tsquery
Full Text Search capabilities via asyncpg.

Features:
  - ts_rank_cd for cover-density ranking (honours field weights A/B/C/D)
  - websearch_to_tsquery ('simple' dictionary — multi-language safe)
  - Hybrid fallback: if tsquery produces zero results, falls back to ILIKE
    which helps with unsegmented languages (Thai) and single-char queries
  - Pagination with accurate total counts
  - Keyword highlighting in result snippets
"""
from __future__ import annotations

import logging
import re
from typing import Any

from core.database import db
from search_recommendation.models import (
    SearchFilter,
    SearchQuery,
    SearchResult,
    SearchResultPage,
    SortBy,
)
from search_recommendation.query_builder import SqlQueryBuilder

log = logging.getLogger(__name__)

_builder = SqlQueryBuilder()

# Minimum text length to activate FTS (shorter queries go direct to ILIKE fallback)
_MIN_FTS_LENGTH = 2

# Maximum snippet length shown in embed
_SNIPPET_MAX = 80


class FtsEngine:
    """
    Full Text Search engine backed by PostgreSQL tsvector + GIN index.
    Implements SearchEngineProtocol.
    """

    async def search(self, query: SearchQuery) -> SearchResultPage:
        """Execute search and return a paginated SearchResultPage."""
        text = (query.text or "").strip()
        use_fts = len(text) >= _MIN_FTS_LENGTH

        if use_fts:
            return await self._fts_search(query, text)
        else:
            return await self._filter_search(query)

    # ── FTS Path ──────────────────────────────────────────────────────────────

    async def _fts_search(self, query: SearchQuery, text: str) -> SearchResultPage:
        """Primary FTS path using tsvector @@ websearch_to_tsquery."""
        page_size = max(1, min(query.page_size, 25))
        page = max(1, query.page)

        # Build parameterized queries
        count_sql, count_params = _builder.build_fts_count_query(text, query.filter)
        data_sql, data_params = _builder.build_fts_query(
            text, query.filter, query.sort_by, page, page_size
        )

        try:
            count_row = await db.fetchone(count_sql, count_params)
            total = int(count_row["total"]) if count_row else 0
        except Exception as exc:
            log.error("FTS count query failed: %s", exc)
            # Fallback to ILIKE on any DB error
            return await self._ilike_fallback(query, text)

        # If FTS returns 0 results, attempt ILIKE fallback
        if total == 0:
            return await self._ilike_fallback(query, text)

        try:
            rows = await db.fetchall(data_sql, data_params)
        except Exception as exc:
            log.error("FTS data query failed: %s", exc)
            return await self._ilike_fallback(query, text)

        items = [self._row_to_result(row, text) for row in rows]
        total_pages = max(1, (total + page_size - 1) // page_size)

        return SearchResultPage(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            query_text=text,
            sort_by=query.sort_by,
        )

    # ── ILIKE Fallback ────────────────────────────────────────────────────────

    async def _ilike_fallback(self, query: SearchQuery, text: str) -> SearchResultPage:
        """
        ILIKE fallback for short/unsegmented text (Thai without spaces, etc.)
        Also used when websearch_to_tsquery returns empty for special char inputs.
        """
        page_size = max(1, min(query.page_size, 25))
        page = max(1, query.page)

        params: list[Any] = []
        idx = [1]

        def p(val: Any) -> str:
            params.append(val)
            placeholder = f"${idx[0]}"
            idx[0] += 1
            return placeholder

        like_pattern = f"%{text}%"
        like_ph = p(like_pattern)

        where_clauses = [
            f"(t.task ILIKE {like_ph} OR COALESCE(t.tags,'') ILIKE {like_ph} OR COALESCE(t.description,'') ILIKE {like_ph} OR COALESCE(t.note,'') ILIKE {like_ph})"
        ]

        # Apply scope from filter
        _builder._apply_scope(query.filter, where_clauses, params, idx)
        _builder._apply_field_filters(query.filter, where_clauses, params, idx)

        where_sql = " AND ".join(where_clauses)

        # Sort — ILIKE has no relevance, default to priority+deadline
        effective_sort = query.sort_by
        if effective_sort == SortBy.RELEVANCE:
            effective_sort = SortBy.PRIORITY_DESC

        sort_map = {
            SortBy.PRIORITY_DESC: "t.priority DESC, t.deadline ASC NULLS LAST",
            SortBy.DEADLINE_ASC:  "t.deadline ASC NULLS LAST, t.priority DESC",
            SortBy.DEADLINE_DESC: "t.deadline DESC, t.priority DESC",
            SortBy.CREATED_DESC:  "t.created_at DESC",
        }
        order_sql = sort_map.get(effective_sort, "t.priority DESC, t.deadline ASC NULLS LAST")

        count_ph = p(0)  # dummy — we need separate count
        count_sql = f"""
SELECT COUNT(*) AS total
FROM tasks t
WHERE {where_sql}
"""
        # Re-build params for count without the limit/offset
        count_params = params[:]

        limit_ph = p(page_size)
        offset_ph = p((page - 1) * page_size)

        data_sql = f"""
SELECT
    t.task_id, t.task, t.deadline, t.priority, t.status,
    t.tags, t.description, t.note, t.owner_id, t.guild_id,
    t.project_id, t.is_pinned, t.created_at, t.updated_at,
    t.completed_at,
    0.0::real AS rank_score
FROM tasks t
WHERE {where_sql}
ORDER BY {order_sql}
LIMIT {limit_ph} OFFSET {offset_ph}
"""

        try:
            # Count uses params without limit/offset (before those were added)
            count_row = await db.fetchone(count_sql, count_params)
            total = int(count_row["total"]) if count_row else 0
            rows = await db.fetchall(data_sql, params)
        except Exception as exc:
            log.error("ILIKE fallback query failed: %s", exc)
            return SearchResultPage(
                items=[], total=0, page=page, page_size=page_size,
                total_pages=1, query_text=text, sort_by=query.sort_by
            )

        items = [self._row_to_result(row, text) for row in rows]
        total_pages = max(1, (total + page_size - 1) // page_size)

        return SearchResultPage(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            query_text=text,
            sort_by=query.sort_by,
        )

    # ── Filter-Only Path (no text) ────────────────────────────────────────────

    async def _filter_search(self, query: SearchQuery) -> SearchResultPage:
        """Filter-only search (browse) when no text query is given."""
        page_size = max(1, min(query.page_size, 25))
        page = max(1, query.page)

        count_sql, count_params = _builder.build_filter_count_query(query.filter)
        data_sql, data_params = _builder.build_filter_query(
            query.filter, query.sort_by, page, page_size
        )

        try:
            count_row = await db.fetchone(count_sql, count_params)
            total = int(count_row["total"]) if count_row else 0
            rows = await db.fetchall(data_sql, data_params) if total > 0 else []
        except Exception as exc:
            log.error("Filter search failed: %s", exc)
            return SearchResultPage(
                items=[], total=0, page=page, page_size=page_size,
                total_pages=1, query_text="", sort_by=query.sort_by
            )

        items = [self._row_to_result(row, "") for row in rows]
        total_pages = max(1, (total + page_size - 1) // page_size)

        return SearchResultPage(
            items=items, total=total, page=page, page_size=page_size,
            total_pages=total_pages, query_text="", sort_by=query.sort_by,
        )

    # ── Row → Model ───────────────────────────────────────────────────────────

    def _row_to_result(self, row: Any, query_text: str) -> SearchResult:
        """Convert an asyncpg Record to a SearchResult, generating a snippet."""
        snippet = self._make_snippet(row, query_text)
        return SearchResult(
            task_id      = row["task_id"],
            task         = row["task"],
            deadline     = row["deadline"],
            priority     = row["priority"],
            status       = row["status"],
            tags         = row.get("tags"),
            description  = row.get("description"),
            note         = row.get("note"),
            owner_id     = row["owner_id"],
            guild_id     = row.get("guild_id"),
            project_id   = row.get("project_id"),
            is_pinned    = row.get("is_pinned", 0),
            created_at   = row.get("created_at"),
            updated_at   = row.get("updated_at"),
            completed_at = row.get("completed_at"),
            rank_score   = float(row.get("rank_score") or 0.0),
            snippet      = snippet,
        )

    @staticmethod
    def _make_snippet(row: Any, query_text: str) -> str:
        """
        Build a short highlighted snippet from description or tags.
        Highlights matching terms with Discord's __underline__ markdown.
        """
        text = (row.get("description") or row.get("tags") or "").strip()
        if not text:
            return ""
        # Truncate to snippet length
        text = text[:_SNIPPET_MAX]
        if not query_text:
            return text
        # Highlight matching substrings (case-insensitive)
        try:
            pattern = re.compile(re.escape(query_text), re.IGNORECASE)
            text = pattern.sub(lambda m: f"__{m.group(0)}__", text)
        except re.error:
            pass
        return text

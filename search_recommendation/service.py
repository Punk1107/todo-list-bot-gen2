"""
search_recommendation/service.py — Service Facade

High-level API used by cog.py (and future integrations).
Coordinates FtsEngine and RecommendationEngine, applies caching,
and enforces security boundaries (user/guild scope).

This is the single entrypoint for all search and recommendation operations.
"""
from __future__ import annotations

import logging
from typing import Optional

from search_recommendation.fts_engine import FtsEngine
from search_recommendation.models import (
    SearchFilter,
    SearchQuery,
    SearchResultPage,
    SortBy,
    TaskRecommendation,
    WeightConfig,
)
from search_recommendation.recommendation import RecommendationEngine

log = logging.getLogger(__name__)


class SearchRecommendationService:
    """
    Service facade for the Search & Recommendation engine.

    Usage:
        svc = SearchRecommendationService()
        page = await svc.search(query)
        recs = await svc.recommend(user_id, guild_id, limit=5)
    """

    def __init__(
        self,
        fts_engine: Optional[FtsEngine] = None,
        rec_engine: Optional[RecommendationEngine] = None,
    ) -> None:
        self._fts: FtsEngine = fts_engine or FtsEngine()
        self._rec: RecommendationEngine = rec_engine or RecommendationEngine()

    # ── Search ────────────────────────────────────────────────────────────────

    async def search(self, query: SearchQuery) -> SearchResultPage:
        """
        Execute a full text search + filter query.

        The caller must ensure that either query.filter.owner_id or
        query.filter.guild_id is set to enforce data scoping.

        Returns a SearchResultPage (may be empty if no results).
        """
        if not query.filter.owner_id and not query.filter.guild_id:
            log.warning("search() called without scope (owner_id/guild_id) — returning empty")
            return SearchResultPage(
                items=[], total=0, page=query.page,
                page_size=query.page_size, total_pages=1,
                query_text=query.text, sort_by=query.sort_by,
            )

        try:
            return await self._fts.search(query)
        except Exception as exc:
            log.error("SearchRecommendationService.search error: %s", exc, exc_info=True)
            return SearchResultPage(
                items=[], total=0, page=query.page,
                page_size=query.page_size, total_pages=1,
                query_text=query.text, sort_by=query.sort_by,
            )

    async def search_personal(
        self,
        user_id: str,
        text: str,
        *,
        status: Optional[str] = None,
        priority_min: Optional[int] = None,
        priority_max: Optional[int] = None,
        due_before: Optional[str] = None,
        due_after: Optional[str] = None,
        sort_by: SortBy = SortBy.RELEVANCE,
        page: int = 1,
        page_size: int = 10,
    ) -> SearchResultPage:
        """Convenience wrapper for personal task search."""
        query = SearchQuery(
            text=text,
            filter=SearchFilter(
                owner_id=user_id,
                status=status,
                priority_min=priority_min,
                priority_max=priority_max,
                due_before=due_before,
                due_after=due_after,
            ),
            sort_by=sort_by,
            page=page,
            page_size=page_size,
        )
        return await self.search(query)

    async def search_guild(
        self,
        guild_id: str,
        text: str,
        *,
        status: Optional[str] = None,
        priority_min: Optional[int] = None,
        priority_max: Optional[int] = None,
        assignee_id: Optional[str] = None,
        due_before: Optional[str] = None,
        due_after: Optional[str] = None,
        sort_by: SortBy = SortBy.RELEVANCE,
        page: int = 1,
        page_size: int = 10,
    ) -> SearchResultPage:
        """Convenience wrapper for guild-scoped (shared project) task search."""
        query = SearchQuery(
            text=text,
            filter=SearchFilter(
                guild_id=guild_id,
                status=status,
                priority_min=priority_min,
                priority_max=priority_max,
                assignee_id=assignee_id,
                due_before=due_before,
                due_after=due_after,
            ),
            sort_by=sort_by,
            page=page,
            page_size=page_size,
        )
        return await self.search(query)

    # ── Recommend ─────────────────────────────────────────────────────────────

    async def recommend(
        self,
        user_id: str,
        guild_id: Optional[str] = None,
        limit: int = 5,
        weights: Optional[WeightConfig] = None,
    ) -> list[TaskRecommendation]:
        """
        Return ranked task recommendations for the given user context.

        Args:
            user_id:  Discord user ID (scope for personal tasks).
            guild_id: Optional guild ID (scope for shared project tasks).
            limit:    Maximum number of recommendations to return (1–10).
            weights:  Custom WeightConfig; defaults to WeightConfig.default().
        """
        try:
            return await self._rec.recommend(
                user_id=user_id,
                guild_id=guild_id,
                limit=limit,
                weights=weights,
            )
        except Exception as exc:
            log.error("SearchRecommendationService.recommend error: %s", exc, exc_info=True)
            return []


# Module-level singleton (lazy — initialized when first imported)
search_svc = SearchRecommendationService()

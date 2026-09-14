"""
search_recommendation/__init__.py

Public API surface for the Search & Recommendation engine.
Import from here to keep internal module structure flexible.
"""
from search_recommendation.models import (
    SearchFilter,
    SearchQuery,
    SearchResult,
    SearchResultPage,
    ScoreBreakdown,
    TaskRecommendation,
    WeightConfig,
    SortBy,
)
from search_recommendation.service import SearchRecommendationService

__all__ = [
    "SearchFilter",
    "SearchQuery",
    "SearchResult",
    "SearchResultPage",
    "ScoreBreakdown",
    "TaskRecommendation",
    "WeightConfig",
    "SortBy",
    "SearchRecommendationService",
]

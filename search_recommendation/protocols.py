"""
search_recommendation/protocols.py — AI-Ready Abstraction Contracts

Defines structural (typing.Protocol) interfaces for the Search & Recommendation
system. Current implementations are all pure PostgreSQL / rule-based, but these
protocols are designed so that future AI/embedding integrations (pgvector,
local sentence transformers, etc.) can be plugged in without touching any
calling code in service.py, cog.py, or views.py.

AI-Ready Roadmap:
  Phase 1 (now):   FtsEngine  →  implements SearchEngineProtocol
                   RuleBasedScorer → implements ScorerProtocol
  Phase 2 (future): HybridEngine → FTS + pgvector cosine similarity
                    EmbeddingProvider → local model (e.g. multilingual-e5-small)
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from search_recommendation.models import (
    SearchQuery,
    SearchResultPage,
    TaskRecommendation,
    WeightConfig,
    ScoreBreakdown,
)


# ─────────────────────────────────────────────────────────────────────────────
# Search Engine Protocol
# ─────────────────────────────────────────────────────────────────────────────

@runtime_checkable
class SearchEngineProtocol(Protocol):
    """
    Contract for any text search implementation.
    Conforming classes:
      - FtsEngine         (PostgreSQL tsvector, current implementation)
      - HybridEngine      (FTS + pgvector cosine similarity, future phase)
    """

    async def search(self, query: SearchQuery) -> SearchResultPage:
        """Execute the search and return a paginated result page."""
        ...


# ─────────────────────────────────────────────────────────────────────────────
# Scorer Protocol
# ─────────────────────────────────────────────────────────────────────────────

@runtime_checkable
class ScorerProtocol(Protocol):
    """
    Contract for a task scoring/ranking implementation.
    Conforming classes:
      - RuleBasedScorer   (deterministic rules, current implementation)
    """

    def score_task(
        self,
        task_row: Any,
        user_id: str,
        now: Any,
        weights: WeightConfig,
    ) -> ScoreBreakdown:
        """
        Compute a full ScoreBreakdown for a single task.
        Must be synchronous to allow efficient bulk scoring without await overhead.
        """
        ...


# ─────────────────────────────────────────────────────────────────────────────
# Recommendation Engine Protocol
# ─────────────────────────────────────────────────────────────────────────────

@runtime_checkable
class RecommendationEngineProtocol(Protocol):
    """
    Contract for a recommendation/ranking engine.
    Takes a pool of candidate tasks and returns ordered recommendations.
    """

    async def recommend(
        self,
        user_id: str,
        guild_id: str | None,
        limit: int,
        weights: WeightConfig,
    ) -> list[TaskRecommendation]:
        """Return top-K task recommendations for the given user/guild context."""
        ...


# ─────────────────────────────────────────────────────────────────────────────
# Embedding Provider Protocol (AI-Ready Stub — NOT used in Phase 1)
# ─────────────────────────────────────────────────────────────────────────────

@runtime_checkable
class EmbeddingProviderProtocol(Protocol):
    """
    AI-Ready contract for a text embedding provider.
    Not used in Phase 1 (rule-based only). Provided so:
      - The interface is stable before any AI model is integrated.
      - Future implementations (multilingual-e5-small, BGE, etc.) slot in
        without touching SearchEngineProtocol or service.py.

    Example future usage:
        class LocalEmbeddingProvider:
            async def embed_text(self, text: str) -> list[float]: ...
            async def batch_embed(self, texts: list[str]) -> list[list[float]]: ...
    """

    async def embed_text(self, text: str) -> list[float]:
        """Return a dense embedding vector for the given text."""
        ...

    async def batch_embed(self, texts: list[str]) -> list[list[float]]:
        """Return embedding vectors for a batch of texts."""
        ...

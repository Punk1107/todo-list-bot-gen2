"""
search_recommendation/models.py — Data Models

All immutable dataclasses used throughout the Search & Recommendation system.
No external dependencies — pure Python + dataclasses.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class SortBy(str, Enum):
    """Available sort orders for search results."""
    RELEVANCE      = "relevance"      # ts_rank_cd score DESC
    DEADLINE_ASC   = "deadline_asc"   # earliest deadline first
    DEADLINE_DESC  = "deadline_desc"  # latest deadline first
    PRIORITY_DESC  = "priority_desc"  # highest priority first
    CREATED_DESC   = "created_desc"   # newest tasks first


# ─────────────────────────────────────────────────────────────────────────────
# Search Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SearchFilter:
    """
    Optional filters applied to a search query.
    All fields are optional — omitting means 'no restriction'.

    Multi-tenancy: either owner_id (personal tasks) or guild_id (shared project
    tasks) must be supplied by the service layer from the authenticated context.
    """
    # Scope (caller must set at least one)
    owner_id:        Optional[str]      = None   # personal task owner
    guild_id:        Optional[str]      = None   # shared project guild scope

    # Field filters
    status:          Optional[str]      = None   # 'Pending', 'In_Progress', 'Completed', 'Cancelled'
    priority_min:    Optional[int]      = None   # 0–7
    priority_max:    Optional[int]      = None   # 0–7
    due_before:      Optional[str]      = None   # ISO 8601 datetime string
    due_after:       Optional[str]      = None   # ISO 8601 datetime string
    assignee_id:     Optional[str]      = None   # task_assignments.user_id
    include_subtasks: bool              = False  # False = top-level tasks only


@dataclass
class SearchQuery:
    """Full query object passed to SearchRecommendationService.search()."""
    text:      str                       # Free-text search term (may be empty for filter-only)
    filter:    SearchFilter              = field(default_factory=SearchFilter)
    sort_by:   SortBy                   = SortBy.RELEVANCE
    page:      int                       = 1    # 1-indexed
    page_size: int                       = 10   # results per page (max 25)


@dataclass
class SearchResult:
    """A single task returned from a search query, enriched with relevance data."""
    task_id:       int
    task:          str
    deadline:      str
    priority:      int
    status:        str
    tags:          Optional[str]
    description:   Optional[str]
    note:          Optional[str]
    owner_id:      str
    guild_id:      Optional[str]
    project_id:    Optional[int]
    is_pinned:     int
    created_at:    Any
    updated_at:    Any
    completed_at:  Optional[Any]

    # Search-specific enrichment
    rank_score:    float = 0.0    # ts_rank_cd relevance score (0.0–1.0)
    snippet:       str  = ""      # highlighted title/description excerpt


@dataclass
class SearchResultPage:
    """Paginated container for SearchResult items."""
    items:       list[SearchResult]
    total:       int         # total matching rows
    page:        int         # current page (1-indexed)
    page_size:   int
    total_pages: int
    query_text:  str         # echo of the query for display
    sort_by:     SortBy


# ─────────────────────────────────────────────────────────────────────────────
# Recommendation Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class WeightConfig:
    """
    Scoring weights for the recommendation engine.
    Must sum to 1.0 (validated in __post_init__).
    Tweak per-guild or per-user in the future without changing the engine code.

    AI-Ready Note: Future pgvector integration would add a 'semantic_weight'
    factor here. The engine is designed to accept this without structural changes.
    """
    priority:   float = 0.25   # P7 (SOS) scores highest
    urgency:    float = 0.30   # proximity to deadline (non-linear curve)
    overdue:    float = 0.20   # severity of being past deadline
    age:        float = 0.10   # task staleness (prevents old tasks being forgotten)
    assignment: float = 0.10   # direct assignee ownership match
    status:     float = 0.05   # momentum bonus for In_Progress tasks

    def __post_init__(self) -> None:
        total = round(
            self.priority + self.urgency + self.overdue +
            self.age + self.assignment + self.status, 6
        )
        if abs(total - 1.0) > 0.001:
            raise ValueError(
                f"WeightConfig weights must sum to 1.0, got {total}. "
                "Adjust factors so they add up to exactly 1.0."
            )

    @classmethod
    def default(cls) -> "WeightConfig":
        return cls()

    @classmethod
    def urgency_focused(cls) -> "WeightConfig":
        """Preset: heavily favour deadline proximity for time-critical work."""
        return cls(priority=0.15, urgency=0.45, overdue=0.25,
                   age=0.05, assignment=0.05, status=0.05)

    @classmethod
    def priority_focused(cls) -> "WeightConfig":
        """Preset: heavily favour explicit priority labels."""
        return cls(priority=0.50, urgency=0.20, overdue=0.15,
                   age=0.05, assignment=0.05, status=0.05)


@dataclass
class FactorScore:
    """Score and human-readable explanation for a single scoring factor."""
    raw_score:    float   # 0–100 sub-score before weight multiplication
    weighted:     float   # raw_score * weight
    label:        str     # e.g. "🆘 P7 (SOS)" or "🚨 Overdue +3 days"
    weight:       float   # the configured weight for this factor


@dataclass
class ScoreBreakdown:
    """Full scoring explanation for one task recommendation."""
    priority:   FactorScore
    urgency:    FactorScore
    overdue:    FactorScore
    age:        FactorScore
    assignment: FactorScore
    status:     FactorScore
    total_score: float     # 0–100 final score

    def summary_badges(self) -> list[str]:
        """
        Return the top contributing factors as emoji-badge strings for Discord
        embed display. Filters to factors that contribute more than 5 points.
        """
        factors = [
            (self.overdue,    "🚨"),
            (self.urgency,    "⏰"),
            (self.priority,   "🔴"),
            (self.age,        "📅"),
            (self.assignment, "👤"),
            (self.status,     "🏃"),
        ]
        badges = []
        for factor, _emoji in sorted(factors, key=lambda x: -x[0].weighted):
            if factor.weighted >= 5.0:
                badges.append(f"{factor.label} `+{factor.weighted:.0f}pt`")
        return badges[:4]  # show at most 4 badges per task to avoid clutter


@dataclass
class TaskRecommendation:
    """A task with its rank, raw data, score breakdown, and suggested action."""
    rank:       int              # 1-indexed (1 = most recommended)
    task_id:    int
    task:       str
    deadline:   str
    priority:   int
    status:     str
    owner_id:   str
    guild_id:   Optional[str]
    project_id: Optional[int]
    breakdown:  ScoreBreakdown
    action_hint: str             # Localisation key for the suggested action

    @property
    def total_score(self) -> float:
        return self.breakdown.total_score

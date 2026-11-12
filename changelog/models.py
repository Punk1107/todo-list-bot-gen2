"""
changelog/models.py — Data structures for Semantic Release Notes & CHANGELOG.md generation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class ReleaseCategory(str, Enum):
    FEATURES = "features"
    FIXES    = "fixes"
    DOCS     = "docs"
    PERF     = "perf"
    OTHER    = "other"


CATEGORY_HEADINGS: dict[ReleaseCategory, str] = {
    ReleaseCategory.FEATURES: "🚀 Features",
    ReleaseCategory.FIXES:    "🐛 Bug Fixes",
    ReleaseCategory.DOCS:     "📚 Documentation",
    ReleaseCategory.PERF:     "⚡ Performance",
    ReleaseCategory.OTHER:    "🔧 Other Changes",
}

ORDERED_CATEGORIES: tuple[ReleaseCategory, ...] = (
    ReleaseCategory.FEATURES,
    ReleaseCategory.FIXES,
    ReleaseCategory.DOCS,
    ReleaseCategory.PERF,
    ReleaseCategory.OTHER,
)


@dataclass
class ChangelogEntry:
    """Single categorized completed task item in a release note."""
    task_id: int
    category: ReleaseCategory
    summary: str
    scope: Optional[str] = None
    is_breaking: bool = False
    raw_tags: Optional[str] = None
    story_points: int = 0
    completed_at: Optional[datetime] = None

    def format_bullet(self) -> str:
        prefix = "⚠️ **BREAKING** · " if self.is_breaking else ""
        scope_part = f"**{self.scope}**: " if self.scope else ""
        pts = f" *({self.story_points}pt)*" if self.story_points > 0 else ""
        return f"- {prefix}{scope_part}{self.summary} (`#{self.task_id}`){pts}"


@dataclass
class GeneratedChangelog:
    """Categorized Release Notes bundle ready for Embed preview, #releases post, and CHANGELOG.md export."""
    project_id: int
    project_name: str
    guild_id: str
    version_label: str
    period_label: str
    sprint_id: Optional[int] = None
    sprint_name: Optional[str] = None
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    grouped: dict[ReleaseCategory, list[ChangelogEntry]] = field(
        default_factory=lambda: {cat: [] for cat in ORDERED_CATEGORIES}
    )
    total_tasks: int = 0
    total_points: int = 0


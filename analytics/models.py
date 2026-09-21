"""
analytics/models.py — Data models for Weekly Productivity Analytics

These are Python-side mirrors of the TypeScript types in:
  supabase/functions/weekly-analytics/types.ts
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class WeeklyMetrics:
    """Snapshot metrics returned by the Edge Function."""
    user_id:                   str
    start_date:                str          # ISO date string YYYY-MM-DD
    end_date:                  str          # ISO date string YYYY-MM-DD
    total_tasks:               int
    completed_count:           int
    completed_on_time_count:   int
    completed_overdue_count:   int
    pending_count:             int
    cancelled_count:           int
    on_time_rate_percent:      float        # 0.0 – 100.0
    completion_rate_percent:   float        # 0.0 – 100.0
    productivity_score:        int          # 0 – 100
    daily_completions:         list[int]    # 7 elements (Mon–Sun)
    priority_breakdown:        dict[int, int]
    top_categories:            list[dict]   # [{"name": str, "count": int}]

    @classmethod
    def from_dict(cls, data: dict) -> "WeeklyMetrics":
        """Parse the JSON response from the Edge Function."""
        return cls(
            user_id=                   data["userId"],
            start_date=                data["startDate"],
            end_date=                  data["endDate"],
            total_tasks=               data["totalTasks"],
            completed_count=           data["completedCount"],
            completed_on_time_count=   data["completedOnTimeCount"],
            completed_overdue_count=   data["completedOverdueCount"],
            pending_count=             data["pendingCount"],
            cancelled_count=           data["cancelledCount"],
            on_time_rate_percent=      float(data["onTimeRatePercent"]),
            completion_rate_percent=   float(data["completionRatePercent"]),
            productivity_score=        int(data["productivityScore"]),
            daily_completions=         data["dailyCompletions"],
            priority_breakdown=        {int(k): v for k, v in data.get("priorityBreakdown", {}).items()},
            top_categories=            data.get("topCategories", []),
        )

    @property
    def productivity_emoji(self) -> str:
        """Returns an emoji based on productivity score."""
        if self.productivity_score >= 80: return "🏆"
        if self.productivity_score >= 60: return "⭐"
        if self.productivity_score >= 40: return "📈"
        return "💪"


@dataclass(frozen=True)
class SnapshotConfig:
    """
    Per-user configuration for weekly snapshot delivery.
    Stored conceptually in users table (future column: weekly_summary_enabled).
    """
    user_id:                 str
    enabled:                 bool = True
    lang:                    str  = "en"    # one of SUPPORTED_LANGS (th/en/zh/ja/ko/es/ru/fr/de)
    send_dm:                 bool = True

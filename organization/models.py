"""
organization/models.py — Data models for Eisenhower Matrix & Custom Saved Filters
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Optional


# ─────────────────────────────────────────────────────────────────────────────
# 1. Eisenhower Matrix Models
# ─────────────────────────────────────────────────────────────────────────────

class EisenhowerQuadrant(str, Enum):
    """The 4 quadrants of the Eisenhower Decision Matrix."""
    Q1_DO_FIRST   = "q1_do_first"    # Important (P4-P7) + Urgent (<= 48h / Overdue)
    Q2_SCHEDULE   = "q2_schedule"    # Important (P4-P7) + Not Urgent (> 48h / No deadline)
    Q3_DELEGATE   = "q3_delegate"    # Not Important (P0-P3) + Urgent (<= 48h / Overdue)
    Q4_ELIMINATE  = "q4_eliminate"   # Not Important (P0-P3) + Not Urgent (> 48h / No deadline)


@dataclass(frozen=True)
class QuadrantMeta:
    key: EisenhowerQuadrant
    name_key: str
    desc_key: str
    emoji: str
    color_int: int


QUADRANT_META: dict[EisenhowerQuadrant, QuadrantMeta] = {
    EisenhowerQuadrant.Q1_DO_FIRST: QuadrantMeta(
        key=EisenhowerQuadrant.Q1_DO_FIRST,
        name_key="matrix_q1_title",
        desc_key="matrix_q1_desc",
        emoji="🔴",
        color_int=0xED4245,  # Red
    ),
    EisenhowerQuadrant.Q2_SCHEDULE: QuadrantMeta(
        key=EisenhowerQuadrant.Q2_SCHEDULE,
        name_key="matrix_q2_title",
        desc_key="matrix_q2_desc",
        emoji="🔵",
        color_int=0x5865F2,  # Blurple / Blue
    ),
    EisenhowerQuadrant.Q3_DELEGATE: QuadrantMeta(
        key=EisenhowerQuadrant.Q3_DELEGATE,
        name_key="matrix_q3_title",
        desc_key="matrix_q3_desc",
        emoji="🟡",
        color_int=0xFEE75C,  # Yellow
    ),
    EisenhowerQuadrant.Q4_ELIMINATE: QuadrantMeta(
        key=EisenhowerQuadrant.Q4_ELIMINATE,
        name_key="matrix_q4_title",
        desc_key="matrix_q4_desc",
        emoji="⚪",
        color_int=0x95A5A6,  # Grey
    ),
}


@dataclass
class EisenhowerTask:
    """Task item classified into an Eisenhower Matrix quadrant."""
    task_id: int
    task: str
    priority: int
    status: str
    deadline: Optional[str] = None
    tags: Optional[str] = None
    description: Optional[str] = None
    owner_id: str = ""
    guild_id: Optional[str] = None
    project_id: Optional[int] = None
    is_private: bool = False
    quadrant: EisenhowerQuadrant = EisenhowerQuadrant.Q4_ELIMINATE
    is_urgent: bool = False
    is_important: bool = False
    relative_time: str = ""

    @property
    def priority_emoji(self) -> str:
        return ["⚪", "🔵", "🟡", "🟠", "🔴", "🔴", "💀", "🚨"][self.priority] \
            if 0 <= self.priority <= 7 else "⚪"


@dataclass
class EisenhowerMatrixData:
    """Aggregated container for all 4 quadrants in a matrix view."""
    q1_tasks: list[EisenhowerTask] = field(default_factory=list)
    q2_tasks: list[EisenhowerTask] = field(default_factory=list)
    q3_tasks: list[EisenhowerTask] = field(default_factory=list)
    q4_tasks: list[EisenhowerTask] = field(default_factory=list)

    @property
    def total_count(self) -> int:
        return len(self.q1_tasks) + len(self.q2_tasks) + len(self.q3_tasks) + len(self.q4_tasks)

    @property
    def total_tasks(self) -> int:
        return self.total_count

    @property
    def q1_count(self) -> int:
        return len(self.q1_tasks)

    @property
    def q2_count(self) -> int:
        return len(self.q2_tasks)

    @property
    def q3_count(self) -> int:
        return len(self.q3_tasks)

    @property
    def q4_count(self) -> int:
        return len(self.q4_tasks)

    def get_quadrant_tasks(self, quadrant: EisenhowerQuadrant) -> list[EisenhowerTask]:
        if quadrant == EisenhowerQuadrant.Q1_DO_FIRST:
            return self.q1_tasks
        elif quadrant == EisenhowerQuadrant.Q2_SCHEDULE:
            return self.q2_tasks
        elif quadrant == EisenhowerQuadrant.Q3_DELEGATE:
            return self.q3_tasks
        else:
            return self.q4_tasks


# ─────────────────────────────────────────────────────────────────────────────
# 2. Saved Filters / Smart Lists Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SavedFilterCriteria:
    """Filter specifications stored in SavedFilter."""
    tags: list[str] = field(default_factory=list)
    min_priority: Optional[int] = None
    max_priority: Optional[int] = None
    status: Optional[str] = None               # 'Pending', 'In_Progress', 'Active', 'Completed'
    project_id: Optional[int] = None
    has_deadline: Optional[bool] = None
    due_within_days: Optional[int] = None
    sort_by: str = "priority_desc"             # 'priority_desc', 'deadline_asc', 'created_desc'

    def to_dict(self) -> dict[str, Any]:
        return {
            "tags": self.tags,
            "min_priority": self.min_priority,
            "max_priority": self.max_priority,
            "status": self.status,
            "project_id": self.project_id,
            "has_deadline": self.has_deadline,
            "due_within_days": self.due_within_days,
            "sort_by": self.sort_by,
        }

    @classmethod
    def from_dict(cls, data: Optional[Mapping[str, Any]]) -> SavedFilterCriteria:
        if not data:
            return cls()
        tags = data.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        return cls(
            tags=list(tags),
            min_priority=data.get("min_priority"),
            max_priority=data.get("max_priority"),
            status=data.get("status"),
            project_id=data.get("project_id"),
            has_deadline=data.get("has_deadline"),
            due_within_days=data.get("due_within_days"),
            sort_by=data.get("sort_by") or "priority_desc",
        )


@dataclass
class SavedFilter:
    """A user-saved smart list view with custom filter criteria."""
    filter_id: int
    owner_id: str
    name: str
    criteria: SavedFilterCriteria
    guild_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_record(cls, row: Mapping[str, Any]) -> SavedFilter:
        raw_crit = row.get("criteria")
        if isinstance(raw_crit, str):
            try:
                crit_dict = json.loads(raw_crit)
            except Exception:
                crit_dict = {}
        elif isinstance(raw_crit, dict):
            crit_dict = raw_crit
        else:
            crit_dict = {}

        return cls(
            filter_id   = int(row["filter_id"]),
            owner_id    = str(row["owner_id"]),
            guild_id    = str(row["guild_id"]) if row.get("guild_id") else None,
            name        = str(row["name"]),
            criteria    = SavedFilterCriteria.from_dict(crit_dict),
            created_at  = row.get("created_at"),
            updated_at  = row.get("updated_at"),
        )

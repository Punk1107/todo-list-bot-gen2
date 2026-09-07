"""
collaboration/models.py — Data Models & Enums for Shared Projects

These are lightweight dataclasses that map 1-to-1 with database rows
(asyncpg.Record -> Model) to make service + view code cleaner.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class ProjectStatus(str, Enum):
    ACTIVE    = "active"
    ARCHIVED  = "archived"
    COMPLETED = "completed"


class ProjectRole(str, Enum):
    LEAD   = "lead"
    MEMBER = "member"
    VIEWER = "viewer"


class SharedTaskStatus(str, Enum):
    PENDING     = "Pending"
    IN_PROGRESS = "In_Progress"
    COMPLETED   = "Completed"
    CANCELLED   = "Cancelled"


# ─────────────────────────────────────────────────────────────────────────────
# Data Models (constructed from asyncpg Records)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Project:
    project_id:  int
    guild_id:    str
    name:        str
    description: Optional[str]
    owner_id:    str
    status:      str   # ProjectStatus value
    color:       str   # hex string e.g. "#5865F2"
    emoji:       str
    channel_id:  Optional[int]
    role_id:     Optional[int]
    created_at:  datetime
    updated_at:  datetime

    @classmethod
    def from_record(cls, row) -> "Project":
        return cls(
            project_id  = row["project_id"],
            guild_id    = row["guild_id"],
            name        = row["name"],
            description = row["description"],
            owner_id    = row["owner_id"],
            status      = row["status"],
            color       = row["color"],
            emoji       = row["emoji"],
            channel_id  = row["channel_id"],
            role_id     = row["role_id"],
            created_at  = row["created_at"],
            updated_at  = row["updated_at"],
        )

    @property
    def status_emoji(self) -> str:
        return {
            "active":    "🟢",
            "archived":  "📦",
            "completed": "✅",
        }.get(self.status, "⚪")


@dataclass
class ProjectMember:
    project_id: int
    user_id:    str
    role:       str   # ProjectRole value
    joined_at:  datetime

    @classmethod
    def from_record(cls, row) -> "ProjectMember":
        return cls(
            project_id = row["project_id"],
            user_id    = row["user_id"],
            role       = row["role"],
            joined_at  = row["joined_at"],
        )

    @property
    def role_emoji(self) -> str:
        return {"lead": "👑", "member": "👤", "viewer": "👁️"}.get(self.role, "")


@dataclass
class ProjectTask:
    """A Task that belongs to a Shared Project (project_id + guild_id are set)."""
    task_id:     int
    project_id:  int
    guild_id:    str
    task:        str       # title
    status:      str       # SharedTaskStatus value
    priority:    int
    deadline:    str       # ISO timestamp string
    owner_id:    str       # creator
    description: Optional[str]
    tags:        Optional[str]
    created_at:  datetime
    updated_at:  datetime
    # Populated after JOIN with task_assignments:
    assignees:   list[str] = field(default_factory=list)

    @classmethod
    def from_record(cls, row, assignees: list[str] | None = None) -> "ProjectTask":
        return cls(
            task_id     = row["task_id"],
            project_id  = row["project_id"],
            guild_id    = row["guild_id"],
            task        = row["task"],
            status      = row["status"],
            priority    = row["priority"],
            deadline    = row["deadline"],
            owner_id    = row["owner_id"],
            description = row.get("description"),
            tags        = row.get("tags"),
            created_at  = row["created_at"],
            updated_at  = row["updated_at"],
            assignees   = assignees or [],
        )

    @property
    def status_emoji(self) -> str:
        return {
            "Pending":     "📋",
            "In_Progress": "⚡",
            "Completed":   "✅",
            "Cancelled":   "❌",
        }.get(self.status, "❓")

    @property
    def priority_emoji(self) -> str:
        return ["⚪", "🔵", "🟡", "🟠", "🔴", "🔴", "💀", "🚨"].get(self.priority, "⚪") \
            if isinstance(self.priority, int) and 0 <= self.priority <= 7 else "⚪"


@dataclass
class ProjectActivity:
    activity_id: int
    project_id:  int
    guild_id:    str
    user_id:     str
    action:      str
    detail:      Optional[str]
    created_at:  datetime

    @classmethod
    def from_record(cls, row) -> "ProjectActivity":
        return cls(
            activity_id = row["activity_id"],
            project_id  = row["project_id"],
            guild_id    = row["guild_id"],
            user_id     = row["user_id"],
            action      = row["action"],
            detail      = row.get("detail"),
            created_at  = row["created_at"],
        )

    @property
    def action_emoji(self) -> str:
        return {
            "project_created":  "🎉",
            "task_created":     "➕",
            "task_claimed":     "🙋",
            "task_assigned":    "📌",
            "task_started":     "⚡",
            "task_completed":   "✅",
            "task_cancelled":   "❌",
            "task_deleted":     "🗑️",
            "member_added":     "👋",
            "member_removed":   "🚪",
            "project_archived": "📦",
            "project_completed":"🏁",
        }.get(self.action, "📝")


@dataclass
class BoardData:
    """Aggregated view of tasks grouped into Kanban columns."""
    project:     Project
    pending:     list[ProjectTask]
    in_progress: list[ProjectTask]
    completed:   list[ProjectTask]
    cancelled:   list[ProjectTask]

    @property
    def total(self) -> int:
        return len(self.pending) + len(self.in_progress) + len(self.completed) + len(self.cancelled)

    @property
    def done_count(self) -> int:
        return len(self.completed)

    @property
    def progress_pct(self) -> float:
        non_cancelled = self.total - len(self.cancelled)
        if non_cancelled <= 0:
            return 0.0
        return round(self.done_count / non_cancelled * 100, 1)


@dataclass
class ProjectStats:
    project:      Project
    total_tasks:  int
    pending:      int
    in_progress:  int
    completed:    int
    cancelled:    int
    overdue:      int
    members:      int
    progress_pct: float
    # Leaderboard: list of (user_id, completed_count)
    leaderboard:  list[tuple[str, int]] = field(default_factory=list)

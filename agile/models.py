"""
agile/models.py — Data models, dataclasses, and enums for Agile & Scrum Full Suite.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Optional


FIBONACCI_POINTS: tuple[int, ...] = (1, 2, 3, 5, 8, 13, 21)


class SprintStatus(str, Enum):
    PLANNED = "planned"
    ACTIVE  = "active"
    CLOSED  = "closed"


class EpicStatus(str, Enum):
    OPEN      = "open"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class RetroColumn(str, Enum):
    WELL    = "well"
    IMPROVE = "improve"
    ACTION  = "action"


@dataclass
class Sprint:
    sprint_id: int
    project_id: int
    name: str
    status: str = SprintStatus.PLANNED.value
    goal: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    total_tasks: int = 0
    completed_tasks: int = 0
    total_points: int = 0
    completed_points: int = 0

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Sprint":
        start_dt = row.get("start_date")
        end_dt = row.get("end_date")
        created_dt = row.get("created_at")

        if isinstance(start_dt, str):
            start_dt = datetime.fromisoformat(start_dt)
        if isinstance(end_dt, str):
            end_dt = datetime.fromisoformat(end_dt)
        if isinstance(created_dt, str):
            created_dt = datetime.fromisoformat(created_dt)

        return cls(
            sprint_id=int(row["sprint_id"]),
            project_id=int(row["project_id"]),
            name=str(row["name"]),
            status=str(row.get("status", SprintStatus.PLANNED.value)),
            goal=row.get("goal"),
            start_date=start_dt,
            end_date=end_dt,
            created_at=created_dt or datetime.now(timezone.utc),
            total_tasks=int(row.get("total_tasks", 0)),
            completed_tasks=int(row.get("completed_tasks", 0)),
            total_points=int(row.get("total_points", 0)),
            completed_points=int(row.get("completed_points", 0)),
        )

    @property
    def is_active(self) -> bool:
        return self.status == SprintStatus.ACTIVE.value

    @property
    def is_closed(self) -> bool:
        return self.status == SprintStatus.CLOSED.value

    @property
    def completion_pct(self) -> int:
        if self.total_tasks <= 0:
            return 0
        return int(round((self.completed_tasks / self.total_tasks) * 100))

    @property
    def points_completion_pct(self) -> int:
        if self.total_points <= 0:
            return self.completion_pct
        return int(round((self.completed_points / self.total_points) * 100))

    @property
    def days_remaining(self) -> Optional[int]:
        if not self.end_date:
            return None
        now = datetime.now(timezone.utc)
        target = self.end_date
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)
        diff = (target - now).total_seconds()
        return max(0, int(diff // 86400))


@dataclass
class Epic:
    epic_id: int
    project_id: int
    name: str
    description: Optional[str] = None
    color: str = "#5865F2"
    status: str = EpicStatus.OPEN.value
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    total_tasks: int = 0
    completed_tasks: int = 0
    total_points: int = 0
    completed_points: int = 0

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Epic":
        created_dt = row.get("created_at")
        if isinstance(created_dt, str):
            created_dt = datetime.fromisoformat(created_dt)

        return cls(
            epic_id=int(row["epic_id"]),
            project_id=int(row["project_id"]),
            name=str(row["name"]),
            description=row.get("description"),
            color=str(row.get("color", "#5865F2")),
            status=str(row.get("status", EpicStatus.OPEN.value)),
            created_at=created_dt or datetime.now(timezone.utc),
            total_tasks=int(row.get("total_tasks", 0)),
            completed_tasks=int(row.get("completed_tasks", 0)),
            total_points=int(row.get("total_points", 0)),
            completed_points=int(row.get("completed_points", 0)),
        )

    @property
    def progress_pct(self) -> int:
        if self.total_points > 0:
            return int(round((self.completed_points / self.total_points) * 100))
        if self.total_tasks > 0:
            return int(round((self.completed_tasks / self.total_tasks) * 100))
        return 0


@dataclass
class PlanningPokerSession:
    task_id: int
    task_title: str
    host_id: str
    guild_id: Optional[str] = None
    votes: dict[str, int] = field(default_factory=dict)  # user_id -> points
    is_revealed: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def cast_vote(self, user_id: str, points: int) -> None:
        if points in FIBONACCI_POINTS:
            self.votes[str(user_id)] = points

    @property
    def voter_count(self) -> int:
        return len(self.votes)

    @property
    def mean(self) -> float:
        if not self.votes:
            return 0.0
        return round(sum(self.votes.values()) / len(self.votes), 1)

    @property
    def median(self) -> float:
        if not self.votes:
            return 0.0
        sorted_vals = sorted(self.votes.values())
        n = len(sorted_vals)
        mid = n // 2
        if n % 2 == 1:
            return float(sorted_vals[mid])
        return round((sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0, 1)

    @property
    def consensus(self) -> Optional[int]:
        if not self.votes:
            return None
        values = list(self.votes.values())
        if all(v == values[0] for v in values):
            return values[0]
        return None

    @property
    def nearest_fibonacci(self) -> int:
        """Snap the mean score to the nearest standard Fibonacci number."""
        target = self.median if self.median > 0 else self.mean
        if target <= 0:
            return 1
        return min(FIBONACCI_POINTS, key=lambda x: abs(x - target))


@dataclass
class RetroCard:
    retro_id: int
    sprint_id: int
    column_type: str  # 'well', 'improve', 'action'
    content: str
    author_id: Optional[str] = None
    votes: int = 0

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "RetroCard":
        return cls(
            retro_id=int(row["retro_id"]),
            sprint_id=int(row["sprint_id"]),
            column_type=str(row["column_type"]),
            content=str(row["content"]),
            author_id=row.get("author_id"),
            votes=int(row.get("votes", 0)),
        )


@dataclass
class VelocityStats:
    project_id: int
    sprint_history: list[tuple[str, int]]  # [(sprint_name, completed_points)]
    average_velocity: float
    backlog_tasks_count: int
    backlog_points: int
    forecast_sprints: int


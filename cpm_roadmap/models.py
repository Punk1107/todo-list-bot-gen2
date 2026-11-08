"""
cpm_roadmap/models.py — Data models, Enums, and structures for CPM, Gantt, and Strategic Roadmaps.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Optional


class HealthStatus(str, Enum):
    """Milestone and project health classification."""
    ON_TRACK = "on_track"
    AT_RISK  = "at_risk"
    DELAYED  = "delayed"

    @property
    def emoji(self) -> str:
        return {
            HealthStatus.ON_TRACK: "🟢",
            HealthStatus.AT_RISK:  "🟡",
            HealthStatus.DELAYED:  "🔴",
        }.get(self, "⚪")

    @property
    def label_th(self) -> str:
        return {
            HealthStatus.ON_TRACK: "ตามแผน (On Track)",
            HealthStatus.AT_RISK:  "มีความเสี่ยง (At Risk)",
            HealthStatus.DELAYED:  "ล่าช้ากว่ากำหนด (Delayed)",
        }.get(self, "ไม่ทราบสถานะ")


@dataclass
class CPMNode:
    """Represents a single node (task) in the CPM network graph."""
    task_id: int
    task_name: str
    duration_hours: float = 8.0          # Work duration in hours
    early_start: float = 0.0             # ES
    early_finish: float = 0.0            # EF = ES + duration
    late_start: float = 0.0              # LS = LF - duration
    late_finish: float = 0.0             # LF
    slack: float = 0.0                   # Slack = LS - ES = LF - EF
    is_critical: bool = False            # True when slack == 0.0
    status: str = "Pending"
    deadline: Optional[datetime] = None
    predecessors: list[int] = field(default_factory=list)  # Tasks that block this task
    successors: list[int] = field(default_factory=list)    # Tasks blocked by this task

    @property
    def duration_days(self) -> float:
        """Convert duration hours to standard 8-hour work days."""
        return max(0.5, round(self.duration_hours / 8.0, 1))


@dataclass
class CPMGraphResult:
    """Complete analysis result of a Critical Path Method network graph."""
    project_id: int
    nodes: dict[int, CPMNode]
    critical_path: list[int]               # Ordered sequence of task IDs on critical path
    total_duration_hours: float
    total_duration_days: float
    project_deadline: Optional[datetime] = None
    is_at_risk: bool = False
    risk_reason: Optional[str] = None
    has_cycle: bool = False

    @property
    def critical_nodes(self) -> list[CPMNode]:
        """Return list of CPMNodes on the critical path."""
        return [self.nodes[tid] for tid in self.critical_path if tid in self.nodes]


@dataclass
class GanttTask:
    """Represents a bar item in the Gantt chart."""
    task_id: int
    name: str
    start_day: float
    duration_days: float
    status: str
    is_critical: bool
    dependencies: list[int] = field(default_factory=list)

    @property
    def end_day(self) -> float:
        return self.start_day + self.duration_days


@dataclass
class ProjectMilestone:
    """Strategic Milestone entity for long-term Roadmap."""
    milestone_id: int
    project_id: int
    title: str
    target_date: datetime
    status: str = "active"
    total_tasks: int = 0
    completed_tasks: int = 0
    total_points: int = 0
    completed_points: int = 0

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "ProjectMilestone":
        return cls(
            milestone_id=int(row["milestone_id"]),
            project_id=int(row["project_id"]),
            title=str(row["title"]),
            target_date=row["target_date"],
            status=str(row.get("status", "active")),
            total_tasks=int(row.get("total_tasks") or 0),
            completed_tasks=int(row.get("completed_tasks") or 0),
            total_points=int(row.get("total_points") or 0),
            completed_points=int(row.get("completed_points") or 0),
        )

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


@dataclass
class MilestoneHealth:
    """Calculated health prediction metrics for a milestone."""
    milestone_id: int
    title: str
    target_date: datetime
    status: HealthStatus
    elapsed_pct: float
    progress_pct: float
    gap_pct: float
    recommendation: str
    bottleneck_tasks: list[dict[str, Any]] = field(default_factory=list)


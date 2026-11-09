"""
time_tracking/models.py — Data models for Time Tracking, Capacity & Estimation Engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional


@dataclass
class TimeLogEntry:
    """Represents an individual logged time record."""
    log_id: int
    task_id: int
    user_id: str
    hours_spent: float
    is_billable: bool = False
    logged_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    note: Optional[str] = None
    task_title: Optional[str] = None
    project_id: Optional[int] = None
    project_name: Optional[str] = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> TimeLogEntry:
        return cls(
            log_id=int(row["log_id"]),
            task_id=int(row["task_id"]),
            user_id=str(row["user_id"]),
            hours_spent=float(row["hours_spent"]),
            is_billable=bool(row.get("is_billable", False)),
            logged_at=row.get("logged_at") or datetime.now(timezone.utc),
            note=row.get("note"),
            task_title=row.get("task_title"),
            project_id=row.get("project_id"),
            project_name=row.get("project_name"),
        )


@dataclass
class ActiveTimer:
    """Represents a currently running stopwatch timer for a user."""
    user_id: str
    task_id: int
    started_at: datetime
    note: Optional[str] = None
    task_title: Optional[str] = None

    def elapsed_seconds(self, now: Optional[datetime] = None) -> float:
        current_time = now or datetime.now(timezone.utc)
        if self.started_at.tzinfo is None:
            started = self.started_at.replace(tzinfo=timezone.utc)
        else:
            started = self.started_at
        delta = current_time - started
        return max(0.0, delta.total_seconds())

    def elapsed_hours(self, now: Optional[datetime] = None) -> float:
        return round(self.elapsed_seconds(now) / 3600.0, 2)

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> ActiveTimer:
        return cls(
            user_id=str(row["user_id"]),
            task_id=int(row["task_id"]),
            started_at=row["started_at"],
            note=row.get("note"),
            task_title=row.get("task_title"),
        )


@dataclass
class TimesheetSummary:
    """Aggregated timesheet summary for a given user and period."""
    user_id: str
    period: str  # 'today', 'week', 'month', 'all'
    total_hours: float
    billable_hours: float
    non_billable_hours: float
    entries: List[TimeLogEntry] = field(default_factory=list)
    project_hours: Dict[str, float] = field(default_factory=dict)


@dataclass
class EstimationMetric:
    """Estimation vs actual accuracy comparison for a task."""
    task_id: int
    task_name: str
    estimated_hours: float
    actual_hours: float
    variance_pct: float
    accuracy_pct: float
    category: str  # 'accurate', 'underestimated', 'overestimated'

    @classmethod
    def calculate(
        cls,
        task_id: int,
        task_name: str,
        estimated_hours: float,
        actual_hours: float,
    ) -> EstimationMetric:
        est = max(0.0, float(estimated_hours))
        act = max(0.0, float(actual_hours))

        if est <= 0.0:
            variance_pct = 0.0
            accuracy_pct = 100.0 if act == 0.0 else 0.0
            category = "accurate" if act == 0.0 else "underestimated"
        else:
            variance_pct = round(((act - est) / est) * 100.0, 1)
            accuracy_pct = round(max(0.0, 100.0 - abs(variance_pct)), 1)
            if abs(variance_pct) <= 15.0:
                category = "accurate"
            elif variance_pct > 15.0:
                category = "underestimated"
            else:
                category = "overestimated"

        return cls(
            task_id=task_id,
            task_name=task_name,
            estimated_hours=est,
            actual_hours=act,
            variance_pct=variance_pct,
            accuracy_pct=accuracy_pct,
            category=category,
        )


@dataclass
class CapacityMetric:
    """Workload capacity assessment for a user in the current week."""
    user_id: str
    weekly_capacity_hours: float
    assigned_estimated_hours: float
    workload_pct: float
    is_overloaded: bool
    active_task_count: int

    @classmethod
    def compute(
        cls,
        user_id: str,
        weekly_capacity_hours: float,
        assigned_estimated_hours: float,
        active_task_count: int,
    ) -> CapacityMetric:
        cap = max(1.0, float(weekly_capacity_hours))
        assigned = max(0.0, float(assigned_estimated_hours))
        pct = round((assigned / cap) * 100.0, 1)
        return cls(
            user_id=user_id,
            weekly_capacity_hours=cap,
            assigned_estimated_hours=assigned,
            workload_pct=pct,
            is_overloaded=(pct > 100.0),
            active_task_count=active_task_count,
        )


@dataclass
class ProjectBudgetMetric:
    """Budget consumption and hourly cost metrics for a project."""
    project_id: int
    project_name: str
    budget: float
    currency: str
    spent_amount: float
    spent_pct: float
    total_billable_hours: float
    total_non_billable_hours: float
    is_near_limit: bool
    is_over_budget: bool
    member_costs: Dict[str, float] = field(default_factory=dict)


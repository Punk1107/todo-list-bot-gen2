"""Data models for ECA Automations, Task Escalations, and SLA Monitoring."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class ECARule:
    rule_id: int
    guild_id: str
    name: str
    trigger_event: str
    condition_json: dict[str, Any] = field(default_factory=dict)
    action_json: dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> ECARule:
        cond = row.get("condition_json") or {}
        if isinstance(cond, str):
            try:
                cond = json.loads(cond)
            except Exception:
                cond = {}

        act = row.get("action_json") or {}
        if isinstance(act, str):
            try:
                act = json.loads(act)
            except Exception:
                act = {}

        return cls(
            rule_id=int(row["rule_id"]),
            guild_id=str(row["guild_id"]),
            name=str(row["name"]),
            trigger_event=str(row.get("trigger_event") or row.get("event_type") or ""),
            condition_json=cond,
            action_json=act,
            is_active=bool(row.get("is_active", True)),
            created_by=str(row["created_by"]) if row.get("created_by") else None,
            created_at=row.get("created_at"),
        )


@dataclass
class TaskEscalation:
    task_id: int
    escalation_level: int = 0
    level1_escalated_at: Optional[datetime] = None
    level2_escalated_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> TaskEscalation:
        return cls(
            task_id=int(row["task_id"]),
            escalation_level=int(row.get("escalation_level", 0)),
            level1_escalated_at=row.get("level1_escalated_at"),
            level2_escalated_at=row.get("level2_escalated_at"),
        )


@dataclass
class SLAPolicy:
    project_id: int
    guild_id: str
    p7_hours: float = 2.0
    p6_hours: float = 8.0
    p5_hours: float = 24.0
    p4_hours: float = 48.0
    is_active: bool = True
    created_at: Optional[datetime] = None

    def get_hours_for_priority(self, priority: int) -> float:
        """Returns the allowed SLA duration in hours based on task priority."""
        if priority >= 7:
            return float(self.p7_hours)
        elif priority == 6:
            return float(self.p6_hours)
        elif priority == 5:
            return float(self.p5_hours)
        elif priority == 4:
            return float(self.p4_hours)
        return float(self.p4_hours)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> SLAPolicy:
        return cls(
            project_id=int(row["project_id"]),
            guild_id=str(row["guild_id"]),
            p7_hours=float(row.get("p7_hours", 2.0)),
            p6_hours=float(row.get("p6_hours", 8.0)),
            p5_hours=float(row.get("p5_hours", 24.0)),
            p4_hours=float(row.get("p4_hours", 48.0)),
            is_active=bool(row.get("is_active", True)),
            created_at=row.get("created_at"),
        )


@dataclass
class TaskSLATracking:
    task_id: int
    target_deadline: datetime
    project_id: Optional[int] = None
    early_warning_sent: bool = False
    breached: bool = False
    resolved_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> TaskSLATracking:
        return cls(
            task_id=int(row["task_id"]),
            project_id=int(row["project_id"]) if row.get("project_id") is not None else None,
            target_deadline=row["target_deadline"],
            early_warning_sent=bool(row.get("early_warning_sent", False)),
            breached=bool(row.get("breached", False)),
            resolved_at=row.get("resolved_at"),
        )

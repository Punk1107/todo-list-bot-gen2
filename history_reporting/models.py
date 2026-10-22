"""
history_reporting/models.py — Data structures for Audit History, Offline Reporting & Retrospectives
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class TaskAuditEvent:
    log_id: int
    user_id: str
    action: str
    target_id: Optional[str]
    detail: Optional[str]
    created_at: datetime

    @property
    def icon(self) -> str:
        icon_map = {
            "task_created": "➕",
            "task_snoozed": "⏰",
            "task_priority_changed": "⚡",
            "task_category_changed": "🏷️",
            "task_completed": "✅",
            "task_edited": "📝",
            "task_pinned": "📌",
            "task_unpinned": "📍",
            "task_commented": "💬",
            "task_soft_deleted": "🗑️",
            "task_restored": "♻️",
            "task_recurring_set": "🔁",
            "template_used": "📋",
        }
        return icon_map.get(self.action, "📜")

    def format_description(self) -> str:
        """Format event detail into user-friendly summary."""
        detail_str = self.detail or ""
        if self.action == "task_created":
            return f"Created task: {detail_str}" if detail_str else "Task created"
        elif self.action == "task_snoozed":
            if "new_dl=" in detail_str:
                val = detail_str.split("new_dl=")[-1]
                return f"Deadline snoozed to {val}"
            elif "preset=" in detail_str:
                val = detail_str.split("preset=")[-1]
                return f"Deadline snoozed (+{val})"
            return f"Deadline snoozed: {detail_str}" if detail_str else "Deadline snoozed"
        elif self.action == "task_priority_changed":
            return f"Priority changed: {detail_str}"
        elif self.action == "task_category_changed":
            return f"Category changed: {detail_str}"
        elif self.action == "task_completed":
            return "Marked as completed"
        elif self.action == "task_edited":
            return f"Title edited: {detail_str}" if detail_str else "Task edited"
        elif self.action == "task_pinned":
            return "Task pinned to top"
        elif self.action == "task_unpinned":
            return "Task unpinned"
        elif self.action == "task_commented":
            return "Comment added"
        elif self.action == "task_soft_deleted":
            return "Moved to Recycle Bin"
        elif self.action == "task_restored":
            return "Restored from Recycle Bin"
        elif self.action == "task_recurring_set":
            return f"Recurrence set: {detail_str}"
        elif self.action == "template_used":
            return f"Created from template: {detail_str}"
        return detail_str if detail_str else self.action


@dataclass
class TaskAuditHistory:
    task_id: int
    task_name: str
    owner_id: str
    created_at: Optional[datetime]
    snooze_count: int
    events: List[TaskAuditEvent] = field(default_factory=list)
    current_status: str = "pending"
    current_priority: int = 1
    current_deadline: Optional[datetime] = None
    category_name: Optional[str] = None
    creator_id: Optional[str] = None
    is_deleted: bool = False


@dataclass
class WeeklyRetrospectiveData:
    user_id: str
    start_date: datetime
    end_date: datetime
    week_str: str
    total_tasks: int
    completed_tasks: int
    completion_rate: float
    snooze_count_total: int
    top_snoozed_tasks: List[Dict[str, Any]] = field(default_factory=list)
    category_distribution: Dict[str, int] = field(default_factory=dict)
    overdue_carryover_tasks: List[Dict[str, Any]] = field(default_factory=list)
    coaching_tip: str = ""

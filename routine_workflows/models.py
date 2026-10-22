"""Data models for Task Templates, Definition of Done checklists, and Routine rules."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class TemplateSubtask:
    task: str
    priority: int = 0
    relative_days: int = 0
    description: Optional[str] = None
    checklists: list[str] = field(default_factory=list)


@dataclass
class TaskTemplate:
    template_id: Optional[int]
    name: str
    description: Optional[str]
    category: Optional[str]
    priority: int
    owner_id: Optional[str]
    guild_id: Optional[str]
    items: dict[str, Any]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @property
    def is_built_in(self) -> bool:
        return self.owner_id is None and self.guild_id is None


@dataclass
class ChecklistItem:
    checklist_id: int
    task_id: int
    title: str
    is_done: bool
    position: int
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


@dataclass
class RoutineEventRule:
    rule_id: int
    guild_id: str
    event_type: str
    trigger_role_id: Optional[int]
    template_name: str
    is_active: bool
    created_by: str
    created_at: Optional[datetime] = None

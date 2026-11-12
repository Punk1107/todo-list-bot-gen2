"""Data models for Multi-Assignees & Collective Sign-off (Feature 39)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AssignmentSummary:
    """Snapshot of all users, roles, mode, and sign-off progress on a task."""
    task_id: int
    assignment_mode: str = "first_wins"
    user_ids: list[str] = field(default_factory=list)
    role_ids: list[int] = field(default_factory=list)
    signed_user_ids: list[str] = field(default_factory=list)
    pending_user_ids: list[str] = field(default_factory=list)

    @property
    def total_required(self) -> int:
        return len(self.signed_user_ids) + len(self.pending_user_ids)


@dataclass
class SignoffResult:
    """Outcome of a task completion or sign-off attempt."""
    task_id: int
    completed: bool
    mode: str
    signed_users: list[str] = field(default_factory=list)
    pending_users: list[str] = field(default_factory=list)
    already_signed: bool = False


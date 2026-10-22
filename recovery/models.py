"""
recovery/models.py — Data models for Soft Delete & Recycle Bin
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional


@dataclass
class TrashTask:
    """Represents a soft-deleted task residing in the Recycle Bin."""
    task_id: int
    task: str
    owner_id: str = ""
    deadline: Optional[str] = None
    priority: int = 0
    status: str = "Pending"
    guild_id: Optional[str] = None
    project_id: Optional[int] = None
    parent_task_id: Optional[int] = None
    is_private: bool = False
    deleted_at: Optional[datetime] = None

    @property
    def days_remaining(self) -> int:
        """Calculate how many days remain before permanent deletion (30-day limit)."""
        if not self.deleted_at:
            return 30
        now = datetime.now(timezone.utc)
        # Ensure deleted_at is timezone-aware
        del_at = self.deleted_at if self.deleted_at.tzinfo else self.deleted_at.replace(tzinfo=timezone.utc)
        diff = now - del_at
        remaining = 30 - diff.days
        return max(0, remaining)

    @property
    def is_expired(self) -> bool:
        """Check if 30-day recovery window has expired."""
        return self.days_remaining <= 0

    @classmethod
    def from_record(cls, row: Mapping[str, Any]) -> TrashTask:
        deleted_at = row.get("deleted_at")
        if isinstance(deleted_at, str):
            try:
                deleted_at = datetime.fromisoformat(deleted_at)
            except Exception:
                deleted_at = None

        return cls(
            task_id        = int(row["task_id"]),
            task           = str(row["task"]),
            deadline       = row.get("deadline"),
            priority       = int(row.get("priority") or 0),
            status         = str(row.get("status") or "Pending"),
            owner_id       = str(row["owner_id"]),
            guild_id       = str(row["guild_id"]) if row.get("guild_id") else None,
            project_id     = int(row["project_id"]) if row.get("project_id") is not None else None,
            parent_task_id = int(row["parent_task_id"]) if row.get("parent_task_id") is not None else None,
            is_private     = bool(row.get("is_private") or False),
            deleted_at     = deleted_at,
        )

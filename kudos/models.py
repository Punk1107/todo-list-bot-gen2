"""
kudos/models.py — Data models for Peer Kudos & Team Gratitude.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


@dataclass
class PeerKudos:
    kudos_id: int
    guild_id: str
    from_user_id: str
    to_user_id: str
    reason: str
    points: int
    created_at: datetime
    task_id: Optional[int] = None
    task_title: Optional[str] = None

    @classmethod
    def from_row(cls, row: Any) -> PeerKudos:
        return cls(
            kudos_id=int(row["kudos_id"]),
            guild_id=str(row["guild_id"]),
            from_user_id=str(row["from_user_id"]),
            to_user_id=str(row["to_user_id"]),
            task_id=int(row["task_id"]) if row.get("task_id") is not None else None,
            task_title=row.get("task_title"),
            reason=row["reason"],
            points=int(row.get("points") or 30),
            created_at=row["created_at"],
        )


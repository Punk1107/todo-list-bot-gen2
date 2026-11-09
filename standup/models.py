"""
standup/models.py — Data structures for Asynchronous Daily Standup.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping, Optional


@dataclass
class StandupConfig:
    guild_id: str
    channel_id: str
    standup_time: str = "09:30"
    is_active: bool = True
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "StandupConfig":
        return cls(
            guild_id=str(row["guild_id"]),
            channel_id=str(row["channel_id"]),
            standup_time=str(row.get("standup_time", "09:30")),
            is_active=bool(row.get("is_active", True)),
            created_by=str(row["created_by"]) if row.get("created_by") else None,
            created_at=row.get("created_at"),
        )


@dataclass
class DailyStandupEntry:
    standup_id: int
    guild_id: str
    user_id: str
    standup_date: date
    yesterday_text: str
    today_text: str
    blockers_text: Optional[str] = None
    submitted_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "DailyStandupEntry":
        return cls(
            standup_id=int(row["standup_id"]),
            guild_id=str(row["guild_id"]),
            user_id=str(row["user_id"]),
            standup_date=row["standup_date"] if isinstance(row["standup_date"], date) else date.today(),
            yesterday_text=str(row["yesterday_text"]),
            today_text=str(row["today_text"]),
            blockers_text=str(row["blockers_text"]) if row.get("blockers_text") else None,
            submitted_at=row.get("submitted_at"),
        )


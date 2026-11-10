"""
quests/models.py — Data models for Server Co-op Quests and Guild Raids.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


@dataclass
class GuildQuest:
    quest_id: int
    guild_id: str
    creator_id: str
    title: str
    description: Optional[str]
    target_tasks: int
    completed_tasks: int
    min_tasks_per_member: int
    exp_reward: int
    badge_reward: str
    start_date: datetime
    end_date: datetime
    status: str
    created_at: datetime

    @property
    def progress_pct(self) -> float:
        if self.target_tasks <= 0:
            return 100.0
        return round(min(100.0, (self.completed_tasks / self.target_tasks) * 100.0), 1)

    @property
    def is_completed(self) -> bool:
        return self.status == "completed" or self.completed_tasks >= self.target_tasks

    def render_progress_bar(self, length: int = 12) -> str:
        pct = self.progress_pct
        filled = max(0, min(length, int(round((pct / 100.0) * length))))
        bar = "█" * filled + "░" * (length - filled)
        return f"[{bar}] {self.completed_tasks:,}/{self.target_tasks:,} ({pct:.1f}%)"

    @classmethod
    def from_row(cls, row: Any) -> GuildQuest:
        return cls(
            quest_id=int(row["quest_id"]),
            guild_id=str(row["guild_id"]),
            creator_id=str(row["creator_id"]),
            title=row["title"],
            description=row.get("description"),
            target_tasks=int(row["target_tasks"]),
            completed_tasks=int(row["completed_tasks"]),
            min_tasks_per_member=int(row.get("min_tasks_per_member") or 3),
            exp_reward=int(row.get("exp_reward") or 500),
            badge_reward=row.get("badge_reward") or "Guild Raid Hero",
            start_date=row["start_date"],
            end_date=row["end_date"],
            status=row["status"],
            created_at=row["created_at"],
        )


@dataclass
class QuestParticipant:
    quest_id: int
    user_id: str
    tasks_contributed: int
    reward_claimed: bool
    last_contributed_at: datetime

    @classmethod
    def from_row(cls, row: Any) -> QuestParticipant:
        return cls(
            quest_id=int(row["quest_id"]),
            user_id=str(row["user_id"]),
            tasks_contributed=int(row["tasks_contributed"]),
            reward_claimed=bool(row["reward_claimed"]),
            last_contributed_at=row["last_contributed_at"],
        )


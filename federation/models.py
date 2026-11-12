"""Data models for Cross-Guild Project Federation (Feature 38)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


@dataclass
class FederatedGuildLink:
    """Represents a linked Discord guild on a shared project."""
    project_id: int
    guild_id: str
    role_scope: str = "member"
    status: str = "active"
    sync_channel_id: Optional[int] = None
    linked_by: Optional[str] = None
    linked_at: Optional[datetime] = None

    @classmethod
    def from_record(cls, row: Any) -> "FederatedGuildLink":
        return cls(
            project_id=int(row["project_id"]),
            guild_id=str(row["guild_id"]),
            role_scope=str(row.get("role_scope") or "member"),
            status=str(row.get("status") or "active"),
            sync_channel_id=int(row["sync_channel_id"]) if row.get("sync_channel_id") else None,
            linked_by=row.get("linked_by"),
            linked_at=row.get("linked_at"),
        )


@dataclass
class FederationInvite:
    """Short-lived invitation code linking a partner guild into a home project."""
    invite_code: str
    project_id: int
    home_guild_id: str
    target_guild_id: str
    created_by: str
    default_role: str = "member"
    expires_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    accepted_by: Optional[str] = None

    @classmethod
    def from_record(cls, row: Any) -> "FederationInvite":
        return cls(
            invite_code=str(row["invite_code"]),
            project_id=int(row["project_id"]),
            home_guild_id=str(row["home_guild_id"]),
            target_guild_id=str(row["target_guild_id"]),
            created_by=str(row["created_by"]),
            default_role=str(row.get("default_role") or "member"),
            expires_at=row.get("expires_at"),
            accepted_at=row.get("accepted_at"),
            accepted_by=row.get("accepted_by"),
        )


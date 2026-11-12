"""Business logic for Cross-Guild Project Federation (Feature 38)."""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from core.database import db
from federation.models import FederatedGuildLink, FederationInvite

log = logging.getLogger(__name__)

VALID_FEDERATION_ROLES = ("viewer", "member", "lead")


class FederationError(Exception):
    """Base error for federation operations."""


class FederationPermissionError(FederationError):
    """Raised when the actor lacks authorization to manage federation."""


class FederationInviteNotFound(FederationError):
    """Raised when an invite code is invalid, already used, or expired."""


async def has_federated_access(project_id: int, guild_id: str) -> bool:
    """Return True if `guild_id` is the project's home guild or an active federated guild."""
    row = await db.fetchone(
        """SELECT 1 AS ok
           FROM projects p
           WHERE p.project_id = $1
             AND (
                 p.guild_id = $2
                 OR EXISTS (
                     SELECT 1 FROM project_federation_guilds f
                     WHERE f.project_id = p.project_id
                       AND f.guild_id = $2
                       AND f.status = 'active'
                 )
             )
           LIMIT 1""",
        (project_id, str(guild_id)),
    )
    return bool(row)


async def _require_home_lead_or_admin(
    project_id: int,
    guild_id: str,
    actor_id: str,
    is_guild_admin: bool = False,
) -> dict:
    """Verify `project_id` is owned by `guild_id` and `actor_id` is lead/owner/admin."""
    proj = await db.fetchone(
        "SELECT * FROM projects WHERE project_id=$1 AND guild_id=$2",
        (project_id, str(guild_id)),
    )
    if not proj:
        raise FederationError(f"Project {project_id} is not hosted in this server.")
    if is_guild_admin or str(proj["owner_id"]) == str(actor_id):
        return dict(proj)

    mem = await db.fetchone(
        "SELECT role FROM project_members WHERE project_id=$1 AND user_id=$2",
        (project_id, str(actor_id)),
    )
    if mem and mem["role"] == "lead":
        return dict(proj)
    raise FederationPermissionError("Only the home project Lead or Server Admin can manage federation.")


async def create_federation_invite(
    project_id: int,
    home_guild_id: str,
    target_guild_id: str,
    actor_id: str,
    *,
    default_role: str = "member",
    is_guild_admin: bool = False,
    ttl_hours: int = 48,
) -> FederationInvite:
    """Generate a single-use invite code allowing `target_guild_id` to link into `project_id`."""
    home_gid = str(home_guild_id).strip()
    target_gid = str(target_guild_id).strip()
    if not target_gid.isdigit():
        raise ValueError("Target guild ID must be a numeric Discord Server ID.")
    if home_gid == target_gid:
        raise ValueError("Cannot federate a project with its own home server.")
    if default_role not in VALID_FEDERATION_ROLES:
        raise ValueError(f"Invalid role '{default_role}'.")

    await _require_home_lead_or_admin(project_id, home_gid, str(actor_id), is_guild_admin=is_guild_admin)

    code = secrets.token_hex(4).upper()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)

    row = await db.fetchone(
        """INSERT INTO federation_invites
               (invite_code, project_id, home_guild_id, target_guild_id,
                created_by, default_role, expires_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7)
           RETURNING *""",
        (code, project_id, home_gid, target_gid, str(actor_id), default_role, expires_at),
    )
    db.query_cache.invalidate_table("federation_invites")
    log.info(
        "Federation invite created: project=%s home=%s target=%s by=%s",
        project_id, home_gid, target_gid, actor_id,
    )
    return FederationInvite.from_record(row) if row else FederationInvite(
        invite_code=code,
        project_id=project_id,
        home_guild_id=home_gid,
        target_guild_id=target_gid,
        created_by=str(actor_id),
        default_role=default_role,
        expires_at=expires_at,
    )


async def accept_federation_invite(
    invite_code: str,
    target_guild_id: str,
    actor_id: str,
    *,
    sync_channel_id: Optional[int] = None,
    is_guild_admin: bool = False,
) -> FederatedGuildLink:
    """Accept a pending federation invite on behalf of `target_guild_id`."""
    if not is_guild_admin:
        raise FederationPermissionError("Server Admin or Manage Guild permission is required to link servers.")

    clean_code = invite_code.strip().upper()
    invite_row = await db.fetchone(
        """SELECT * FROM federation_invites
           WHERE invite_code=$1 AND target_guild_id=$2""",
        (clean_code, str(target_guild_id)),
    )
    if not invite_row:
        raise FederationInviteNotFound("Federation invite code not found for this server.")
    if invite_row.get("accepted_at") is not None:
        raise FederationInviteNotFound("Federation invite code has already been used.")

    expires_at = invite_row.get("expires_at")
    if isinstance(expires_at, datetime):
        exp_utc = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
        if exp_utc < datetime.now(timezone.utc):
            raise FederationInviteNotFound("Federation invite code has expired.")

    project_id = int(invite_row["project_id"])
    default_role = str(invite_row.get("default_role") or "member")

    from utils.helpers import ensure_user
    await ensure_user(str(actor_id))

    link_row = await db.fetchone(
        """INSERT INTO project_federation_guilds
               (project_id, guild_id, linked_by, sync_channel_id, role_scope, status, linked_at)
           VALUES ($1,$2,$3,$4,$5,'active',NOW())
           ON CONFLICT (project_id, guild_id) DO UPDATE SET
               linked_by=EXCLUDED.linked_by,
               sync_channel_id=COALESCE(EXCLUDED.sync_channel_id, project_federation_guilds.sync_channel_id),
               role_scope=EXCLUDED.role_scope,
               status='active',
               linked_at=NOW()
           RETURNING *""",
        (project_id, str(target_guild_id), str(actor_id), sync_channel_id, default_role),
    )

    await db.execute(
        """UPDATE federation_invites
           SET accepted_at=NOW(), accepted_by=$2
           WHERE invite_code=$1""",
        (clean_code, str(actor_id)),
    )

    # Ensure accepting server admin is enrolled in project_members so per-guild RBAC works smoothly
    member_role = "lead" if default_role == "lead" else "member"
    await db.execute(
        """INSERT INTO project_members (project_id, user_id, role)
           VALUES ($1,$2,$3)
           ON CONFLICT (project_id, user_id) DO NOTHING""",
        (project_id, str(actor_id), member_role),
    )

    db.query_cache.invalidate_tables(
        ["project_federation_guilds", "federation_invites", "project_members", "projects"]
    )
    from collaboration import service as collab_service
    await collab_service.log_activity(
        project_id, str(invite_row["home_guild_id"]), str(actor_id),
        "guild_federated", f"guild={target_guild_id}",
    )
    return FederatedGuildLink.from_record(link_row) if link_row else FederatedGuildLink(
        project_id=project_id,
        guild_id=str(target_guild_id),
        role_scope=default_role,
        status="active",
        sync_channel_id=sync_channel_id,
        linked_by=str(actor_id),
    )


async def unlink_project_guild(
    project_id: int,
    actor_guild_id: str,
    target_guild_id: str,
    actor_id: str,
    is_guild_admin: bool = False,
) -> bool:
    """
    Revoke a cross-guild federation link.
    Allowed if actor is Lead/Admin on the home guild OR Admin on the linked partner guild.
    """
    proj = await db.fetchone("SELECT guild_id, owner_id FROM projects WHERE project_id=$1", (project_id,))
    if not proj:
        raise FederationError(f"Project {project_id} not found.")

    home_guild_id = str(proj["guild_id"])
    actor_gid = str(actor_guild_id)
    target_gid = str(target_guild_id)

    if target_gid == home_guild_id:
        raise ValueError("Cannot unlink the project's primary home server.")

    if actor_gid == home_guild_id:
        await _require_home_lead_or_admin(project_id, home_guild_id, str(actor_id), is_guild_admin=is_guild_admin)
    elif actor_gid == target_gid and is_guild_admin:
        pass
    else:
        raise FederationPermissionError("You do not have permission to unlink this server.")

    row = await db.fetchone(
        """UPDATE project_federation_guilds
           SET status='revoked'
           WHERE project_id=$1 AND guild_id=$2 AND status='active'
           RETURNING project_id""",
        (project_id, target_gid),
    )
    if not row:
        return False
    db.query_cache.invalidate_tables(["project_federation_guilds", "projects"])
    from collaboration import service as collab_service
    await collab_service.log_activity(
        project_id, home_guild_id, str(actor_id),
        "guild_unlinked", f"guild={target_gid}",
    )
    return True


async def update_sync_channel(
    project_id: int,
    guild_id: str,
    channel_id: Optional[int],
    actor_id: str,
    is_guild_admin: bool = False,
) -> bool:
    """Update the Discord announcement channel for a federated guild (or home guild)."""
    if not is_guild_admin:
        raise FederationPermissionError("Manage Guild or Admin permission required to configure sync channels.")

    proj = await db.fetchone("SELECT guild_id FROM projects WHERE project_id=$1", (project_id,))
    if not proj:
        raise FederationError(f"Project {project_id} not found.")

    gid = str(guild_id)
    if str(proj["guild_id"]) == gid:
        await db.execute(
            "UPDATE projects SET notification_channel_id=$2 WHERE project_id=$1 AND guild_id=$3",
            (project_id, channel_id, gid),
        )
        db.query_cache.invalidate_table("projects")
        return True

    row = await db.fetchone(
        """UPDATE project_federation_guilds
           SET sync_channel_id=$3
           WHERE project_id=$1 AND guild_id=$2 AND status='active'
           RETURNING project_id""",
        (project_id, gid, channel_id),
    )
    if not row:
        return False
    db.query_cache.invalidate_table("project_federation_guilds")
    return True


async def get_project_federation_links(project_id: int) -> list[FederatedGuildLink]:
    """Return active federated guild links for `project_id`."""
    rows = await db.fetchall(
        """SELECT * FROM project_federation_guilds
           WHERE project_id=$1 AND status='active'
           ORDER BY linked_at ASC""",
        (project_id,),
    )
    return [FederatedGuildLink.from_record(r) for r in (rows or [])]


async def get_federated_sync_channels(project_id: int) -> list[int]:
    """Return all distinct notification/sync channel IDs across active federated guilds."""
    rows = await db.fetchall(
        """SELECT sync_channel_id
           FROM project_federation_guilds
           WHERE project_id=$1 AND status='active' AND sync_channel_id IS NOT NULL""",
        (project_id,),
    )
    return [int(r["sync_channel_id"]) for r in (rows or []) if r.get("sync_channel_id")]


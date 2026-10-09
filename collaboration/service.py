"""
collaboration/service.py — Business Logic & Scope Isolation for Shared Projects

KEY DESIGN RULES (enforced in EVERY query):
  1. All SELECT/UPDATE/DELETE on projects include WHERE guild_id = $N  (Multi-tenancy)
  2. All SELECT/UPDATE/DELETE on project tasks include WHERE project_id = $N AND guild_id = $N
  3. Personal tasks (project_id IS NULL) are NEVER touched here — separate query paths
  4. Permission model:
       - project LEAD     → full control (edit project, assign tasks, manage members)
       - project MEMBER   → create tasks, claim/update own tasks, mark tasks done
       - project VIEWER   → read-only
       - guild ADMIN      → override (checked via discord.Member.guild_permissions.administrator)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import discord

from collaboration.models import (
    BoardData, Project, ProjectActivity, ProjectMember, ProjectStats, ProjectTask,
)
from core.database import db
from utils.helpers import get_user_lang

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────────

class ProjectNotFound(Exception):
    """Raised when a project doesn't exist in the given guild."""


class ProjectPermissionError(Exception):
    """Raised when an actor lacks the permission for the operation."""
    def __init__(self, required: str = "member"):
        self.required = required
        super().__init__(f"Requires role: {required}")


class TaskNotFound(Exception):
    """Raised when a task doesn't exist in the given project/guild."""


class AlreadyClaimed(Exception):
    """Raised when a user tries to claim an already-assigned task."""


# ─────────────────────────────────────────────────────────────────────────────
# Permission Helpers
# ─────────────────────────────────────────────────────────────────────────────

async def get_member_role(project_id: int, user_id: str) -> Optional[str]:
    """Return the ProjectRole of user_id in project_id, or None if not a member."""
    row = await db.fetchone(
        "SELECT role FROM project_members WHERE project_id=$1 AND user_id=$2",
        (project_id, user_id),
    )
    return row["role"] if row else None


async def require_role(
    project: Project,
    user_id: str,
    minimum_role: str,          # "viewer" | "member" | "lead"
    is_guild_admin: bool = False,
) -> None:
    """
    Raise ProjectPermissionError if user_id does not meet minimum_role.
    Guild admins bypass all checks.
    """
    if is_guild_admin:
        return
    if project.owner_id == user_id:
        return  # owner always passes
    role = await get_member_role(project.project_id, user_id)
    if role is None:
        raise ProjectPermissionError(minimum_role)
    order = {"viewer": 0, "member": 1, "lead": 2}
    if order.get(role, -1) < order.get(minimum_role, 99):
        raise ProjectPermissionError(minimum_role)


# ─────────────────────────────────────────────────────────────────────────────
# Project CRUD (Guild-scoped)
# ─────────────────────────────────────────────────────────────────────────────

async def create_project(
    guild_id: str,
    name: str,
    owner_id: str,
    description: Optional[str] = None,
    color: str = "#5865F2",
    emoji: str = "📁",
    channel_id: Optional[int] = None,
    role_id: Optional[int] = None,
    priority: int = 0,
) -> Project:
    """
    Create a new Shared Project scoped to guild_id.
    The creator is automatically added as a Lead member.
    """
    prio_val = max(0, min(7, int(priority)))
    row = await db.fetchone(
        """INSERT INTO projects
           (guild_id, name, description, owner_id, color, emoji, channel_id, role_id, priority)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
           RETURNING *""",
        (guild_id, name, description, owner_id, color, emoji, channel_id, role_id, prio_val),
    )
    project = Project.from_record(row)
    # Auto-add creator as Lead
    await db.execute(
        "INSERT INTO project_members (project_id, user_id, role) VALUES ($1,$2,'lead')"
        " ON CONFLICT (project_id, user_id) DO UPDATE SET role='lead'",
        (project.project_id, owner_id),
    )
    await log_activity(project.project_id, guild_id, owner_id, "project_created", name)
    log.info("Project created: guild=%s project_id=%s name=%r priority=%s", guild_id, project.project_id, name, prio_val)
    return project


async def get_project(project_id: int, guild_id: str) -> Project:
    """
    Fetch a single project. ALWAYS scoped to guild_id to prevent cross-guild access.
    Raises ProjectNotFound if not found or wrong guild.
    """
    row = await db.fetchone(
        "SELECT * FROM projects WHERE project_id=$1 AND guild_id=$2",
        (project_id, guild_id),
    )
    if not row:
        raise ProjectNotFound(f"Project {project_id} not found in guild {guild_id}")
    return Project.from_record(row)


async def get_guild_projects(guild_id: str, status: Optional[str] = "active") -> list[Project]:
    """
    Fetch all projects for a guild. Optionally filtered by status.
    ALL rows are guaranteed to belong to guild_id (enforced in WHERE clause).
    """
    if status:
        rows = await db.fetchall(
            "SELECT * FROM projects WHERE guild_id=$1 AND status=$2 ORDER BY priority DESC, updated_at DESC",
            (guild_id, status),
        )
    else:
        rows = await db.fetchall(
            "SELECT * FROM projects WHERE guild_id=$1 ORDER BY priority DESC, updated_at DESC",
            (guild_id,),
        )
    return [Project.from_record(r) for r in rows] if rows else []


async def update_project_status(
    project_id: int, guild_id: str, new_status: str,
    actor_id: str, is_guild_admin: bool = False,
) -> Project:
    """Archive or complete a project. Requires Lead or Admin."""
    project = await get_project(project_id, guild_id)
    await require_role(project, actor_id, "lead", is_guild_admin)
    await db.execute(
        "UPDATE projects SET status=$1, updated_at=NOW() WHERE project_id=$2 AND guild_id=$3",
        (new_status, project_id, guild_id),
    )
    action = "project_archived" if new_status == "archived" else "project_completed"
    await log_activity(project_id, guild_id, actor_id, action)
    return await get_project(project_id, guild_id)


async def update_project_priority(
    project_id: int, guild_id: str, priority: int,
    actor_id: str, is_guild_admin: bool = False,
) -> Project:
    """Change a project's priority (0-7). Requires Lead or Admin."""
    project = await get_project(project_id, guild_id)
    await require_role(project, actor_id, "lead", is_guild_admin)
    prio_val = max(0, min(7, int(priority)))
    await db.execute(
        "UPDATE projects SET priority=$1, updated_at=NOW() WHERE project_id=$2 AND guild_id=$3",
        (prio_val, project_id, guild_id),
    )
    db.query_cache.invalidate_tables(["projects"])
    await log_activity(project_id, guild_id, actor_id, "project_priority_changed", str(prio_val))
    return await get_project(project_id, guild_id)


async def update_project_manual_progress(
    project_id: int, guild_id: str, progress: int,
    actor_id: str, is_guild_admin: bool = False,
) -> Project:
    """Update manual progress percentage (0-100) for projects. Requires Member, Lead, or Admin."""
    project = await get_project(project_id, guild_id)
    actor_role = await get_member_role(project_id, actor_id)
    if not (actor_role is not None or is_guild_admin):
        raise ProjectPermissionError("member")
    prog_val = max(0, min(100, int(progress)))
    await db.execute(
        "UPDATE projects SET manual_progress=$1, updated_at=NOW() WHERE project_id=$2 AND guild_id=$3",
        (prog_val, project_id, guild_id),
    )
    db.query_cache.invalidate_tables(["projects"])
    await log_activity(project_id, guild_id, actor_id, "project_progress_updated", f"{prog_val}%")
    return await get_project(project_id, guild_id)


async def complete_project_with_tasks(
    project_id: int, guild_id: str,
    actor_id: str, complete_all_tasks: bool = True,
    is_guild_admin: bool = False,
) -> Project:
    """Mark project as completed, optionally auto-completing all remaining pending/in_progress tasks. Requires Lead or Admin."""
    project = await get_project(project_id, guild_id)
    await require_role(project, actor_id, "lead", is_guild_admin)

    if complete_all_tasks:
        await db.execute(
            """UPDATE tasks
               SET status='Completed', completed_at=NOW(), updated_at=NOW()
               WHERE project_id=$1 AND guild_id=$2 AND status IN ('Pending', 'In_Progress')""",
            (project_id, guild_id),
        )
        db.query_cache.invalidate_tables(["tasks", "task_assignments"])

    await db.execute(
        "UPDATE projects SET status='completed', updated_at=NOW() WHERE project_id=$1 AND guild_id=$2",
        (project_id, guild_id),
    )
    db.query_cache.invalidate_tables(["projects"])
    await log_activity(project_id, guild_id, actor_id, "project_completed", "Completed via dashboard")
    return await get_project(project_id, guild_id)


# ─────────────────────────────────────────────────────────────────────────────
# Member Management
# ─────────────────────────────────────────────────────────────────────────────

async def add_member(
    project_id: int, guild_id: str,
    target_user_id: str, role: str,
    actor_id: str, is_guild_admin: bool = False,
) -> Project:
    """Add or update a member's role. Requires Lead or Admin."""
    project = await get_project(project_id, guild_id)
    await require_role(project, actor_id, "lead", is_guild_admin)
    from utils.helpers import ensure_user
    await ensure_user(target_user_id)
    await db.execute(
        """INSERT INTO project_members (project_id, user_id, role)
           VALUES ($1,$2,$3)
           ON CONFLICT (project_id, user_id) DO UPDATE SET role=$3""",
        (project_id, target_user_id, role),
    )
    await log_activity(project_id, guild_id, actor_id, "member_added",
                       f"{target_user_id} as {role}")
    return project


async def remove_member(
    project_id: int, guild_id: str,
    target_user_id: str,
    actor_id: str, is_guild_admin: bool = False,
) -> None:
    """Remove a member from a project. Requires Lead or Admin. Cannot remove the owner."""
    project = await get_project(project_id, guild_id)
    if target_user_id == project.owner_id:
        raise ProjectPermissionError("Cannot remove the project owner.")
    await require_role(project, actor_id, "lead", is_guild_admin)
    await db.execute(
        "DELETE FROM project_members WHERE project_id=$1 AND user_id=$2",
        (project_id, target_user_id),
    )
    await log_activity(project_id, guild_id, actor_id, "member_removed", target_user_id)


async def get_project_members(project_id: int, guild_id: str) -> list[ProjectMember]:
    """Return all members of a project (guild-scoped via project validation)."""
    await get_project(project_id, guild_id)  # validates ownership
    rows = await db.fetchall(
        """SELECT pm.* FROM project_members pm
           WHERE pm.project_id=$1
           ORDER BY pm.role DESC, pm.joined_at ASC""",
        (project_id,),
    )
    return [ProjectMember.from_record(r) for r in rows] if rows else []


async def send_project_invite_dm(
    target_user: discord.User | discord.Member,
    project: Project,
    guild_name: str,
    actor: discord.User | discord.Member,
    role: str,
) -> bool:
    """
    Send an invitation/notification DM to a newly added project member.
    Returns True if sent successfully, False if DMs are disabled or failed.
    """
    from utils.helpers import get_user_lang
    from locales.i18n import t

    try:
        lang = await get_user_lang(str(target_user.id))
    except Exception:
        lang = "th"

    color = int(project.color.lstrip("#"), 16) if project.color.startswith("#") else 0x5865F2
    role_label = t(f"proj_role_{role}", lang) if role in ("lead", "member", "viewer") else role.capitalize()

    embed = discord.Embed(
        title=f"📁 {t('proj_member_dm_title', lang)}",
        description=t(
            "proj_member_dm_body", lang,
            project_emoji=project.emoji,
            project_name=project.name,
            guild_name=guild_name,
            role=role_label,
            actor=actor.mention,
        ),
        color=color,
        timestamp=datetime.now(timezone.utc),
    )

    if project.description:
        embed.add_field(
            name=f"📝 {t('proj_dm_desc_field', lang)}",
            value=f"> {project.description[:300]}",
            inline=False,
        )

    embed.add_field(
        name=f"💡 {t('proj_dm_hint_title', lang)}",
        value=t("proj_member_dm_hint", lang),
        inline=False,
    )

    embed.set_footer(text=f"{project.emoji} {project.name} · To-Do List Bot Gen 2")

    try:
        await target_user.send(embed=embed)
        return True
    except discord.Forbidden:
        log.debug("Could not send project invite DM to %s (DMs disabled)", target_user.id)
        return False
    except Exception as exc:
        log.warning("send_project_invite_dm failed for %s: %s", target_user.id, exc)
        return False


async def get_project_stakeholder_ids(project_id: int, guild_id: str) -> set[str]:
    """
    Return all unique user IDs associated with a project:
    - Project owner
    - Members in project_members
    - Assignees in task_assignments for tasks in this project
    - Task owners for tasks in this project
    """
    stakeholders: set[str] = set()

    # 1. Project Owner
    try:
        p_row = await db.fetchone(
            "SELECT owner_id FROM projects WHERE project_id=$1 AND guild_id=$2",
            (project_id, guild_id),
        )
        if p_row and p_row.get("owner_id"):
            stakeholders.add(str(p_row["owner_id"]))
    except Exception as exc:
        log.warning("Could not fetch owner for project %d: %s", project_id, exc)

    # 2. Project Members
    try:
        pm_rows = await db.fetchall(
            "SELECT user_id FROM project_members WHERE project_id=$1",
            (project_id,),
        )
        for r in (pm_rows or []):
            if r.get("user_id"):
                stakeholders.add(str(r["user_id"]))
    except Exception as exc:
        log.warning("Could not fetch project_members for project %d: %s", project_id, exc)

    # 3. Task Assignees
    try:
        ta_rows = await db.fetchall(
            """SELECT DISTINCT ta.user_id
               FROM task_assignments ta
               JOIN tasks t ON t.task_id = ta.task_id
               WHERE t.project_id=$1 AND t.guild_id=$2""",
            (project_id, guild_id),
        )
        for r in (ta_rows or []):
            if r.get("user_id"):
                stakeholders.add(str(r["user_id"]))
    except Exception as exc:
        log.warning("Could not fetch task_assignments for project %d: %s", project_id, exc)

    # 4. Task Owners
    try:
        to_rows = await db.fetchall(
            """SELECT DISTINCT owner_id
               FROM tasks
               WHERE project_id=$1 AND guild_id=$2 AND owner_id IS NOT NULL""",
            (project_id, guild_id),
        )
        for r in (to_rows or []):
            if r.get("owner_id"):
                stakeholders.add(str(r["owner_id"]))
    except Exception as exc:
        log.warning("Could not fetch task owners for project %d: %s", project_id, exc)

    return stakeholders


async def notify_project_completed(
    bot: discord.Client,
    project: Project,
    actor: discord.User | discord.Member,
    guild: Optional[discord.Guild] = None,
    trigger_channel: Optional[discord.abc.Messageable] = None,
    complete_all_tasks: bool = True,
) -> None:
    """
    Broadcast project completion to the real Discord channel(s)
    and send completion DMs to all project stakeholders.
    """
    from utils.helpers import get_user_lang
    from locales.i18n import t

    # ── 1. Determine Broadcast Channel(s) ──────────────────────────────────
    channels_to_send: list[discord.abc.Messageable] = []
    sent_channel_ids: set[int] = set()

    # Priority A: trigger_channel (the actual channel where the action was taken)
    if trigger_channel and hasattr(trigger_channel, "id") and trigger_channel.id:
        channels_to_send.append(trigger_channel)
        sent_channel_ids.add(trigger_channel.id)

    # Priority B: notification_channel_id or channel_id configured on project
    notif_channel_id = getattr(project, "notification_channel_id", None) or project.channel_id
    if not notif_channel_id:
        try:
            row = await db.fetchone(
                "SELECT notification_channel_id, channel_id FROM projects WHERE project_id=$1 AND guild_id=$2",
                (project.project_id, project.guild_id),
            )
            if row:
                notif_channel_id = row.get("notification_channel_id") or row.get("channel_id")
        except Exception:
            pass

    if notif_channel_id and int(notif_channel_id) not in sent_channel_ids:
        try:
            chan = bot.get_channel(int(notif_channel_id))
            if chan is None:
                chan = await bot.fetch_channel(int(notif_channel_id))
            if chan:
                channels_to_send.append(chan)
                sent_channel_ids.add(chan.id)
        except Exception as exc:
            log.warning("Could not fetch notification channel %s: %s", notif_channel_id, exc)

    # Determine language for public channel announcement
    try:
        ch_lang = await get_user_lang(str(actor.id))
    except Exception:
        ch_lang = "th"

    color = int(project.color.lstrip("#"), 16) if (project.color and project.color.startswith("#")) else 0x57F287

    # ── 2. Send Public Channel Broadcast ("ส่งลงดิสจริง") ────────────────────
    if channels_to_send:
        ch_embed = discord.Embed(
            title=t("proj_broadcast_completed_title", ch_lang),
            description=t(
                "proj_broadcast_completed_desc", ch_lang,
                actor=actor.mention,
                project=f"{project.emoji} **{project.name}**",
            ),
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        note_text = t("proj_complete_all_note", ch_lang) if complete_all_tasks else t("proj_complete_status_only_note", ch_lang)
        ch_embed.add_field(name="📋 " + t("status", ch_lang), value=f"> {note_text}", inline=False)
        ch_embed.set_footer(text=t("proj_footer_id", ch_lang, project_id=project.project_id))

        for ch in channels_to_send:
            try:
                await ch.send(embed=ch_embed)
            except Exception as exc:
                log.warning("Failed to broadcast project completion to channel %s: %s", getattr(ch, "id", ch), exc)

    # ── 3. Send DMs to Everyone Listed in the Project ("ส่งไปที่ DMs") ───────
    stakeholder_ids = await get_project_stakeholder_ids(project.project_id, project.guild_id)
    guild_name = guild.name if guild else "Discord"
    bot_user_id = str(bot.user.id) if getattr(bot, "user", None) else None

    for uid in stakeholder_ids:
        if not uid or uid == bot_user_id:
            continue

        target_user = None
        if guild:
            target_user = guild.get_member(int(uid))
        if target_user is None:
            target_user = bot.get_user(int(uid))
        if target_user is None:
            try:
                target_user = await bot.fetch_user(int(uid))
            except Exception:
                target_user = None

        if not target_user or getattr(target_user, "bot", False):
            continue

        try:
            u_lang = await get_user_lang(uid)
        except Exception:
            u_lang = "th"

        dm_embed = discord.Embed(
            title=t("proj_dm_completed_title", u_lang, name=project.name),
            description=t(
                "proj_dm_completed_desc", u_lang,
                project=f"{project.emoji} **{project.name}**",
                guild=guild_name,
                actor=actor.mention,
            ),
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        dm_note = t("proj_complete_all_note", u_lang) if complete_all_tasks else t("proj_complete_status_only_note", u_lang)
        dm_embed.add_field(name="📋 " + t("status", u_lang), value=f"> {dm_note}", inline=False)
        dm_embed.set_footer(text=f"{project.emoji} {project.name} · To-Do List Bot Gen 2")

        try:
            await target_user.send(embed=dm_embed)
        except discord.Forbidden:
            log.debug("Could not send completion DM to %s (DMs closed)", uid)
        except Exception as exc:
            log.warning("Could not send completion DM to %s: %s", uid, exc)



# ─────────────────────────────────────────────────────────────────────────────
# Task CRUD (Project-scoped, always includes guild_id guard)
# ─────────────────────────────────────────────────────────────────────────────

async def add_project_task(
    project_id: int, guild_id: str,
    task_name: str, deadline_iso: str,
    creator_id: str,
    priority: int = 0,
    description: Optional[str] = None,
    tags: Optional[str] = None,
) -> ProjectTask:
    """
    Create a task inside a Shared Project.
    project_id AND guild_id are set on the task row — this is what distinguishes
    a Shared Task from a Personal Task (where both are NULL).
    Requires minimum 'member' role.
    """
    project = await get_project(project_id, guild_id)
    await require_role(project, creator_id, "member")
    from utils.helpers import ensure_user
    await ensure_user(creator_id)
    row = await db.fetchone(
        """INSERT INTO tasks
           (task, deadline, priority, description, tags, owner_id, project_id, guild_id)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
           RETURNING *""",
        (task_name, deadline_iso, priority, description, tags, creator_id, project_id, guild_id),
    )
    db.invalidate_stats(creator_id)
    task = ProjectTask.from_record(row)
    await log_activity(project_id, guild_id, creator_id, "task_created", task_name)
    return task


async def get_project_task(task_id: int, project_id: int, guild_id: str) -> ProjectTask:
    """
    Fetch a single project task. ALWAYS validates both project_id AND guild_id.
    Raises TaskNotFound if not found or if task doesn't belong to this project/guild.
    """
    row = await db.fetchone(
        "SELECT * FROM tasks WHERE task_id=$1 AND project_id=$2 AND guild_id=$3",
        (task_id, project_id, guild_id),
    )
    if not row:
        raise TaskNotFound(f"Task {task_id} not found in project {project_id} / guild {guild_id}")
    assignees = await _get_task_assignees(task_id)
    return ProjectTask.from_record(row, assignees=assignees)


async def _get_task_assignees(task_id: int) -> list[str]:
    rows = await db.fetchall(
        "SELECT user_id FROM task_assignments WHERE task_id=$1", (task_id,)
    )
    return [r["user_id"] for r in rows] if rows else []


async def delete_project_task(
    task_id: int, project_id: int, guild_id: str,
    actor_id: str, is_guild_admin: bool = False,
) -> None:
    """Delete a task. Creator, Lead, or Admin can delete. Validates guild_id."""
    project = await get_project(project_id, guild_id)
    task = await get_project_task(task_id, project_id, guild_id)
    # Allow: creator, lead role, or guild admin
    if task.owner_id != actor_id:
        await require_role(project, actor_id, "lead", is_guild_admin)
    await db.execute(
        "DELETE FROM tasks WHERE task_id=$1 AND project_id=$2 AND guild_id=$3",
        (task_id, project_id, guild_id),
    )
    await log_activity(project_id, guild_id, actor_id, "task_deleted", task.task)


# ─────────────────────────────────────────────────────────────────────────────
# Task Claiming & Assignment
# ─────────────────────────────────────────────────────────────────────────────

async def claim_task(
    task_id: int, project_id: int, guild_id: str,
    claimer_id: str,
) -> ProjectTask:
    """
    Allow any server member to self-assign an unassigned / unclaimed task.
    Sets status to In_Progress automatically.
    """
    project = await get_project(project_id, guild_id)  # guild scope guard
    task = await get_project_task(task_id, project_id, guild_id)

    if task.status in ("Completed", "Cancelled"):
        raise ValueError("Cannot claim a completed or cancelled task.")

    # Auto-add claimant as member if not already in project
    existing_role = await get_member_role(project_id, claimer_id)
    if existing_role is None:
        from utils.helpers import ensure_user
        await ensure_user(claimer_id)
        await db.execute(
            "INSERT INTO project_members (project_id, user_id, role) VALUES ($1,$2,'member')"
            " ON CONFLICT (project_id, user_id) DO NOTHING",
            (project_id, claimer_id),
        )

    # Insert into task_assignments (ignore if already assigned to this user)
    await db.execute(
        """INSERT INTO task_assignments (task_id, user_id)
           VALUES ($1,$2)
           ON CONFLICT (task_id, user_id) DO NOTHING""",
        (task_id, claimer_id),
    )
    # Move to In_Progress if still Pending
    if task.status == "Pending":
        await db.execute(
            "UPDATE tasks SET status='In_Progress', updated_at=NOW()"
            " WHERE task_id=$1 AND project_id=$2 AND guild_id=$3",
            (task_id, project_id, guild_id),
        )
    db.query_cache.invalidate_tables(["tasks", "task_assignments"])
    await log_activity(project_id, guild_id, claimer_id, "task_claimed", task.task)
    return await get_project_task(task_id, project_id, guild_id)


async def assign_task(
    task_id: int, project_id: int, guild_id: str,
    assignee_id: str,
    actor_id: str, is_guild_admin: bool = False,
) -> ProjectTask:
    """
    Lead or Admin assigns a task to a specific member.
    Auto-promotes assignee to member if they're not already in the project.
    """
    project = await get_project(project_id, guild_id)
    await require_role(project, actor_id, "lead", is_guild_admin)
    task = await get_project_task(task_id, project_id, guild_id)

    if task.status in ("Completed", "Cancelled"):
        raise ValueError("Cannot assign a completed or cancelled task.")

    # Ensure assignee is a user in our DB
    from utils.helpers import ensure_user
    await ensure_user(assignee_id)
    # Add assignee to project members if not already present
    await db.execute(
        "INSERT INTO project_members (project_id, user_id, role) VALUES ($1,$2,'member')"
        " ON CONFLICT (project_id, user_id) DO NOTHING",
        (project_id, assignee_id),
    )
    await db.execute(
        """INSERT INTO task_assignments (task_id, user_id)
           VALUES ($1,$2)
           ON CONFLICT (task_id, user_id) DO NOTHING""",
        (task_id, assignee_id),
    )
    if task.status == "Pending":
        await db.execute(
            "UPDATE tasks SET status='In_Progress', updated_at=NOW()"
            " WHERE task_id=$1 AND project_id=$2 AND guild_id=$3",
            (task_id, project_id, guild_id),
        )
    db.query_cache.invalidate_tables(["tasks", "task_assignments"])
    await log_activity(project_id, guild_id, actor_id, "task_assigned",
                       f"#{task_id} → {assignee_id}")
    return await get_project_task(task_id, project_id, guild_id)


async def update_task_status(
    task_id: int, project_id: int, guild_id: str,
    new_status: str, actor_id: str, is_guild_admin: bool = False,
) -> ProjectTask:
    """
    Change a task's status. Valid transitions:
      Pending      → In_Progress, Cancelled
      In_Progress  → Completed, Pending, Cancelled
      Completed    → (no change allowed, must re-open via Lead/Admin only)
    Allowed actors: assignee, task creator, project lead, guild admin.
    """
    project = await get_project(project_id, guild_id)
    task = await get_project_task(task_id, project_id, guild_id)

    # Permission: assignee OR task creator OR lead/admin
    is_assignee = actor_id in task.assignees
    is_creator  = task.owner_id == actor_id
    actor_role  = await get_member_role(project_id, actor_id)
    is_lead     = actor_role == "lead" or project.owner_id == actor_id
    is_member   = actor_role is not None

    # Anyone who is a member of the project can mark tasks as Completed
    if new_status == "Completed":
        allowed = is_member or is_assignee or is_creator or is_lead or is_guild_admin
    else:
        allowed = is_assignee or is_creator or is_lead or is_guild_admin

    if not allowed:
        raise ProjectPermissionError("member")

    extra_sql = ""
    params: tuple = (new_status, task_id, project_id, guild_id)
    if new_status == "Completed":
        extra_sql = ", completed_at=NOW()"
        for uid in task.assignees:
            db.invalidate_stats(uid)
        db.invalidate_stats(task.owner_id)

    await db.execute(
        f"UPDATE tasks SET status=$1, updated_at=NOW(){extra_sql}"
        " WHERE task_id=$2 AND project_id=$3 AND guild_id=$4",
        params,
    )
    db.query_cache.invalidate_tables(["tasks", "task_assignments"])

    action_map = {
        "In_Progress": "task_started",
        "Completed":   "task_completed",
        "Cancelled":   "task_cancelled",
        "Pending":     "task_created",   # re-open
    }
    await log_activity(project_id, guild_id, actor_id,
                       action_map.get(new_status, "task_status_changed"),
                       f"#{task_id} → {new_status}")
    return await get_project_task(task_id, project_id, guild_id)


# ─────────────────────────────────────────────────────────────────────────────
# Board View (Kanban)
# ─────────────────────────────────────────────────────────────────────────────

async def get_project_board(project_id: int, guild_id: str) -> BoardData:
    """
    Return all tasks for a project grouped into Kanban columns.
    ALWAYS scoped via both project_id AND guild_id.
    """
    project = await get_project(project_id, guild_id)
    rows = await db.fetchall(
        """SELECT * FROM tasks
           WHERE project_id=$1 AND guild_id=$2
           ORDER BY priority DESC, deadline ASC""",
        (project_id, guild_id),
    )

    # Fetch all assignees in one query to avoid N+1
    if rows:
        task_ids = [r["task_id"] for r in rows]
        if task_ids:
            placeholders = ",".join(f"${i+1}" for i in range(len(task_ids)))
            assign_rows = await db.fetchall(
                f"SELECT task_id, user_id FROM task_assignments WHERE task_id IN ({placeholders})",
                task_ids,
            )
        else:
            assign_rows = []
        assignees_map: dict[int, list[str]] = {}
        for ar in (assign_rows or []):
            assignees_map.setdefault(ar["task_id"], []).append(ar["user_id"])
    else:
        assignees_map = {}

    tasks = [ProjectTask.from_record(r, assignees=assignees_map.get(r["task_id"], []))
             for r in (rows or [])]

    return BoardData(
        project     = project,
        pending     = [t for t in tasks if t.status == "Pending"],
        in_progress = [t for t in tasks if t.status == "In_Progress"],
        completed   = [t for t in tasks if t.status == "Completed"],
        cancelled   = [t for t in tasks if t.status == "Cancelled"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Project Stats & Leaderboard
# ─────────────────────────────────────────────────────────────────────────────

async def get_project_stats(project_id: int, guild_id: str) -> ProjectStats:
    """
    Compute a comprehensive stats snapshot for a project:
    task breakdown, progress percentage, member count, and contributor leaderboard.
    ALWAYS scoped to guild_id.
    """
    project = await get_project(project_id, guild_id)
    now_iso = datetime.now(timezone.utc).isoformat()

    count_row = await db.fetchone(
        """SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status='Pending'     THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN status='In_Progress' THEN 1 ELSE 0 END) AS in_progress,
            SUM(CASE WHEN status='Completed'   THEN 1 ELSE 0 END) AS completed,
            SUM(CASE WHEN status='Cancelled'   THEN 1 ELSE 0 END) AS cancelled,
            SUM(CASE WHEN status='Pending' AND deadline < $1 THEN 1 ELSE 0 END) AS overdue
           FROM tasks WHERE project_id=$2 AND guild_id=$3""",
        (now_iso, project_id, guild_id),
    )
    totals = {k: int(count_row[k] or 0) for k in
              ("total", "pending", "in_progress", "completed", "cancelled", "overdue")} \
             if count_row else {k: 0 for k in
                                ("total", "pending", "in_progress", "completed", "cancelled", "overdue")}

    member_row = await db.fetchone(
        "SELECT COUNT(*) AS c FROM project_members WHERE project_id=$1", (project_id,)
    )
    member_count = int(member_row["c"] or 0) if member_row else 0

    # Contributor leaderboard: who completed the most tasks
    lb_rows = await db.fetchall(
        """SELECT ta.user_id, COUNT(*) AS done
           FROM task_assignments ta
           JOIN tasks t ON t.task_id = ta.task_id
           WHERE t.project_id=$1 AND t.guild_id=$2 AND t.status='Completed'
           GROUP BY ta.user_id
           ORDER BY done DESC
           LIMIT 5""",
        (project_id, guild_id),
    )
    leaderboard = [(r["user_id"], int(r["done"])) for r in (lb_rows or [])]

    non_cancelled = totals["total"] - totals["cancelled"]
    if non_cancelled > 0:
        progress = round(totals["completed"] / non_cancelled * 100, 1)
    elif project.manual_progress is not None:
        progress = float(project.manual_progress)
    else:
        progress = 0.0

    return ProjectStats(
        project      = project,
        total_tasks  = totals["total"],
        pending      = totals["pending"],
        in_progress  = totals["in_progress"],
        completed    = totals["completed"],
        cancelled    = totals["cancelled"],
        overdue      = totals["overdue"],
        members      = member_count,
        progress_pct = progress,
        leaderboard  = leaderboard,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Cross-Scope "My Tasks" — tasks assigned to a user across all guild projects
# ─────────────────────────────────────────────────────────────────────────────

async def get_user_assigned_tasks(guild_id: str, user_id: str) -> list[ProjectTask]:
    """
    Return all tasks assigned to user_id across ALL projects in guild_id.
    Combines task_assignments JOIN tasks JOIN projects — always guild-scoped.
    """
    rows = await db.fetchall(
        """SELECT t.*, p.project_id AS _proj_id
           FROM task_assignments ta
           JOIN tasks t ON t.task_id = ta.task_id
           JOIN projects p ON p.project_id = t.project_id
           WHERE ta.user_id=$1
             AND t.guild_id=$2
             AND p.guild_id=$2
             AND t.status NOT IN ('Completed','Cancelled')
           ORDER BY t.priority DESC, t.deadline ASC
           LIMIT 30""",
        (user_id, guild_id),
    )
    if not rows:
        return []
    # fetch assignees per task
    task_ids = [r["task_id"] for r in rows]
    placeholders = ",".join(f"${i+1}" for i in range(len(task_ids)))
    assign_rows = await db.fetchall(
        f"SELECT task_id, user_id FROM task_assignments WHERE task_id IN ({placeholders})",
        task_ids,
    )
    assignees_map: dict[int, list[str]] = {}
    for ar in (assign_rows or []):
        assignees_map.setdefault(ar["task_id"], []).append(ar["user_id"])
    return [ProjectTask.from_record(r, assignees=assignees_map.get(r["task_id"], []))
            for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Activity Log
# ─────────────────────────────────────────────────────────────────────────────

async def log_activity(
    project_id: int, guild_id: str, user_id: str,
    action: str, detail: Optional[str] = None,
) -> None:
    """Append a record to project_activity_log (non-blocking via BulkWriter)."""
    sql = (
        "INSERT INTO project_activity_log (project_id, guild_id, user_id, action, detail)"
        " VALUES ($1,$2,$3,$4,$5)"
    )
    try:
        db.bulk_writer.enqueue(sql, (project_id, guild_id, user_id, action, detail))
    except Exception as exc:
        log.warning("log_activity enqueue failed, direct write: %s", exc)
        import asyncio
        asyncio.ensure_future(db.execute(sql, (project_id, guild_id, user_id, action, detail)))


async def get_project_activity(
    project_id: int, guild_id: str, limit: int = 20,
) -> list[ProjectActivity]:
    """Return the most recent activity log entries for a project."""
    await get_project(project_id, guild_id)  # guild scope guard
    rows = await db.fetchall(
        """SELECT * FROM project_activity_log
           WHERE project_id=$1 AND guild_id=$2
           ORDER BY created_at DESC
           LIMIT $3""",
        (project_id, guild_id, limit),
    )
    return [ProjectActivity.from_record(r) for r in (rows or [])]

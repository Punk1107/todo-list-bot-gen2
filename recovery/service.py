"""
recovery/service.py — Business logic for Soft Delete, Safe Recovery & Recycle Bin
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from core.database import db
from recovery.models import TrashTask

log = logging.getLogger(__name__)


async def soft_delete_task(
    task_id: int,
    user_id: str,
    is_guild_admin: bool = False,
    project_id: Optional[int] = None,
    guild_id: Optional[str] = None,
) -> bool:
    """
    Mark a task and its subtasks as soft-deleted (is_deleted = TRUE, deleted_at = NOW()).
    Validates ownership or project delete permissions before deletion.
    Returns True if task was soft-deleted, False if not found or unauthorized.
    """
    row = await db.afetchone(
        "SELECT task_id, task, owner_id, project_id, guild_id, is_deleted FROM tasks WHERE task_id=$1",
        (task_id,),
    )
    if not row or row["is_deleted"]:
        return False

    task_owner = str(row["owner_id"])
    t_proj_id = row.get("project_id")
    t_guild_id = row.get("guild_id")

    # Permission check
    if t_proj_id and t_guild_id:
        if not is_guild_admin and task_owner != user_id:
            from collaboration import service as collab_service
            # Check project role permission
            can_delete = await collab_service.check_project_permission(
                int(t_proj_id), user_id, "can_delete_tasks", is_guild_admin=is_guild_admin
            )
            if not can_delete:
                # Fall back to checking if user is lead
                proj = await collab_service.get_project(int(t_proj_id), str(t_guild_id))
                if proj.owner_id != user_id:
                    role = await collab_service.get_member_role(int(t_proj_id), user_id)
                    if role != "lead":
                        return False
    else:
        # Personal task — only the owner or guild admin can delete
        if task_owner != user_id and not is_guild_admin:
            return False

    # Perform soft delete on task and its subtasks
    await db.aexecute(
        """UPDATE tasks
           SET is_deleted=TRUE, deleted_at=NOW()
           WHERE task_id=$1 OR parent_task_id=$1""",
        (task_id,),
    )

    # Stop any active focus session on this task or its subtasks
    await db.aexecute(
        """UPDATE focus_sessions
           SET status='stopped', notification_pending=FALSE, updated_at=NOW()
           WHERE (task_id=$1 OR task_id IN (SELECT task_id FROM tasks WHERE parent_task_id=$1))
             AND status='active'""",
        (task_id,),
    )

    # Invalidate caches
    db.invalidate_stats(task_owner)
    if task_owner != user_id:
        db.invalidate_stats(user_id)
    db.query_cache.invalidate_tables(["tasks", "focus_sessions"])

    # Audit logging
    await db.alog_action(user_id, "task_soft_deleted", str(task_id))
    if t_proj_id and t_guild_id:
        try:
            from collaboration import service as collab_service
            await collab_service.log_activity(
                int(t_proj_id), str(t_guild_id), user_id, "task_deleted", str(row["task"])
            )
            db.query_cache.invalidate_tables(["tasks", "project_activity_log"])
        except Exception as exc:
            log.warning("Could not log project activity for task soft-delete %d: %s", task_id, exc)

    log.info("Task %d soft-deleted by user %s", task_id, user_id)
    return True


async def restore_task(
    task_id: int,
    user_id: str,
    is_guild_admin: bool = False,
    project_id: Optional[int] = None,
    guild_id: Optional[str] = None,
) -> tuple[bool, str, Optional[int]]:
    """
    Restore a soft-deleted task from Recycle Bin.
    Returns:
        (success, message_key, restored_task_id)
    """
    row = await db.afetchone(
        """SELECT task_id, task, owner_id, project_id, guild_id, parent_task_id, is_deleted, deleted_at
           FROM tasks WHERE task_id=$1""",
        (task_id,),
    )
    if not row or not row["is_deleted"]:
        return False, "trash_not_found", None

    # Check 30-day expiration window
    del_at = row["deleted_at"]
    if del_at:
        now = datetime.now(timezone.utc)
        aware_del_at = del_at if del_at.tzinfo else del_at.replace(tzinfo=timezone.utc)
        if (now - aware_del_at).days > 30:
            return False, "trash_expired", None

    task_owner = str(row["owner_id"])
    t_proj_id = row.get("project_id")
    t_guild_id = row.get("guild_id")
    parent_id = row.get("parent_task_id")

    # Permission check
    if t_proj_id and t_guild_id:
        if not is_guild_admin and task_owner != user_id:
            from collaboration import service as collab_service
            proj = await collab_service.get_project(int(t_proj_id), str(t_guild_id))
            if proj.owner_id != user_id:
                role = await collab_service.get_member_role(int(t_proj_id), user_id)
                if role != "lead":
                    return False, "permission_denied", None
    else:
        if task_owner != user_id and not is_guild_admin:
            return False, "permission_denied", None

    # Restore main task and any subtasks
    await db.aexecute(
        """UPDATE tasks
           SET is_deleted=FALSE, deleted_at=NULL
           WHERE task_id=$1 OR parent_task_id=$1""",
        (task_id,),
    )

    # If this was a subtask, restore parent if parent is currently soft-deleted
    if parent_id is not None:
        p_row = await db.afetchone(
            "SELECT is_deleted FROM tasks WHERE task_id=$1", (parent_id,)
        )
        if p_row and p_row["is_deleted"]:
            await db.aexecute(
                "UPDATE tasks SET is_deleted=FALSE, deleted_at=NULL WHERE task_id=$1",
                (parent_id,),
            )

    # Invalidate caches
    db.invalidate_stats(task_owner)
    if task_owner != user_id:
        db.invalidate_stats(user_id)
    db.query_cache.invalidate_table("tasks")

    # Audit logging
    await db.alog_action(user_id, "task_restored", str(task_id))
    if t_proj_id and t_guild_id:
        try:
            from collaboration import service as collab_service
            await collab_service.log_activity(
                int(t_proj_id), str(t_guild_id), user_id, "task_restored", str(row["task"])
            )
            db.query_cache.invalidate_tables(["tasks", "project_activity_log"])
        except Exception as exc:
            log.warning("Could not log project activity for task restore %d: %s", task_id, exc)

    log.info("Task %d restored by user %s", task_id, user_id)
    return True, "trash_restored", task_id


async def list_trash(
    user_id: str,
    guild_id: Optional[str] = None,
    limit: int = 50,
) -> list[TrashTask]:
    """
    Fetch all soft-deleted tasks within 30 days.
    If in guild context: includes personal tasks for user plus any project tasks user owns or leads.
    """
    if guild_id:
        rows = await db.afetchall(
            """SELECT t.*
               FROM tasks t
               WHERE t.is_deleted = TRUE
                 AND (t.deleted_at IS NULL OR t.deleted_at >= NOW() - INTERVAL '30 days')
                 AND (
                     (t.owner_id = $1 AND (t.guild_id = $2 OR t.guild_id IS NULL))
                     OR (t.guild_id = $2 AND t.project_id IS NOT NULL AND EXISTS (
                         SELECT 1 FROM project_members pm
                         WHERE pm.project_id = t.project_id
                           AND pm.user_id = $1
                           AND pm.role = 'lead'
                     ))
                     OR (t.guild_id = $2 AND t.project_id IS NOT NULL AND EXISTS (
                         SELECT 1 FROM projects p
                         WHERE p.project_id = t.project_id
                           AND p.owner_id = $1
                     ))
                 )
               ORDER BY t.deleted_at DESC NULLS LAST, t.task_id DESC
               LIMIT $3""",
            (user_id, guild_id, limit),
        )
    else:
        rows = await db.afetchall(
            """SELECT *
               FROM tasks
               WHERE is_deleted = TRUE
                 AND (deleted_at IS NULL OR deleted_at >= NOW() - INTERVAL '30 days')
                 AND owner_id = $1
                 AND guild_id IS NULL
               ORDER BY deleted_at DESC NULLS LAST, task_id DESC
               LIMIT $2""",
            (user_id, limit),
        )

    return [TrashTask.from_record(r) for r in (rows or [])]


async def hard_delete_trash(
    task_id: int,
    user_id: str,
    is_guild_admin: bool = False,
) -> bool:
    """Permanently delete a soft-deleted task directly from the trash bin."""
    row = await db.afetchone(
        "SELECT task_id, owner_id, project_id, guild_id, is_deleted FROM tasks WHERE task_id=$1",
        (task_id,),
    )
    if not row or not row["is_deleted"]:
        return False

    task_owner = str(row["owner_id"])
    t_proj_id = row.get("project_id")
    t_guild_id = row.get("guild_id")

    if t_proj_id and t_guild_id:
        if not is_guild_admin and task_owner != user_id:
            from collaboration import service as collab_service
            proj = await collab_service.get_project(int(t_proj_id), str(t_guild_id))
            if proj.owner_id != user_id:
                role = await collab_service.get_member_role(int(t_proj_id), user_id)
                if role != "lead":
                    return False
    else:
        if task_owner != user_id and not is_guild_admin:
            return False

    await db.aexecute(
        "DELETE FROM tasks WHERE task_id=$1 OR parent_task_id=$1",
        (task_id,),
    )
    db.invalidate_stats(task_owner)
    db.query_cache.invalidate_table("tasks")
    await db.alog_action(user_id, "task_permanently_deleted", str(task_id))
    return True


async def purge_expired_trash(days: int = 30) -> int:
    """
    Permanently delete all tasks that have been in the Recycle Bin for longer than `days`.
    Returns count of deleted tasks.
    """
    rows = await db.afetchall(
        f"""DELETE FROM tasks
           WHERE is_deleted = TRUE
             AND deleted_at < NOW() - INTERVAL '{int(days)} days'
           RETURNING task_id""",
    )
    count = len(rows or [])
    if count > 0:
        db.query_cache.invalidate_table("tasks")
        log.info("Purged %d expired soft-deleted tasks from Recycle Bin", count)
    return count

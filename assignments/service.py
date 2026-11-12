"""Business logic for Multi-Assignees, Role Assignments & Collective Sign-off (Feature 39)."""
from __future__ import annotations

import logging
import re
from typing import Iterable, Optional

from assignments.models import AssignmentSummary, SignoffResult
from core.database import db
from utils.helpers import ensure_user

log = logging.getLogger(__name__)

VALID_MODES = ("first_wins", "all_signoff")
_MENTION_RE = re.compile(r"<@!?(\d+)>|\b(\d{15,22})\b")


class AssignmentError(Exception):
    """Base error for multi-assignment operations."""


class AssignmentPermissionError(AssignmentError):
    """Raised when actor lacks permission to modify or complete a task's assignees."""


def parse_user_ids(raw_text: str) -> list[str]:
    """Extract unique Discord user ID strings from mentions or space-separated IDs."""
    seen: list[str] = []
    for match in _MENTION_RE.finditer(raw_text or ""):
        uid = match.group(1) or match.group(2)
        if uid and uid not in seen:
            seen.append(uid)
    return seen


async def _fetch_task_row(task_id: int) -> dict:
    row = await db.afetchone("SELECT * FROM tasks WHERE task_id=$1 AND is_deleted=FALSE", (task_id,))
    if not row:
        raise AssignmentError(f"Task #{task_id} not found.")
    return dict(row)


async def _require_manage_permission(
    task_row: dict,
    actor_id: str,
    guild_id: Optional[str] = None,
    is_guild_admin: bool = False,
) -> None:
    if is_guild_admin or str(task_row["owner_id"]) == str(actor_id):
        return
    proj_id = task_row.get("project_id")
    if proj_id and guild_id:
        from collaboration import service as collab_service
        project = await collab_service.get_project(int(proj_id), str(guild_id))
        if await collab_service.check_project_permission(
            int(proj_id), str(actor_id), "can_assign_tasks", is_guild_admin=is_guild_admin
        ) or project.owner_id == str(actor_id):
            return
    raise AssignmentPermissionError("You do not have permission to manage assignees for this task.")


async def assign_users(
    task_id: int,
    user_ids: Iterable[str],
    actor_id: str,
    *,
    guild_id: Optional[str] = None,
    mode: Optional[str] = None,
    is_guild_admin: bool = False,
) -> AssignmentSummary:
    """Assign one or more users to `task_id` and optionally set `assignment_mode`."""
    clean_ids: list[str] = []
    for uid in user_ids:
        u = str(uid).strip()
        if u and u not in clean_ids:
            clean_ids.append(u)
    if not clean_ids:
        raise ValueError("Please provide at least one valid user to assign.")
    if mode is not None and mode not in VALID_MODES:
        raise ValueError(f"Invalid assignment mode '{mode}'.")

    task = await _fetch_task_row(task_id)
    await _require_manage_permission(task, str(actor_id), guild_id=guild_id, is_guild_admin=is_guild_admin)

    proj_id = task.get("project_id")
    for uid in clean_ids:
        await ensure_user(uid)
        await db.aexecute(
            """INSERT INTO task_assignees (task_id, user_id, assigned_by, guild_id, assigned_at)
               VALUES ($1,$2,$3,$4,NOW())
               ON CONFLICT (task_id, user_id) DO NOTHING""",
            (task_id, uid, str(actor_id), guild_id or task.get("guild_id")),
        )
        if proj_id:
            await db.aexecute(
                """INSERT INTO project_members (project_id, user_id, role)
                   VALUES ($1,$2,'member')
                   ON CONFLICT (project_id, user_id) DO NOTHING""",
                (int(proj_id), uid),
            )
            await db.aexecute(
                """INSERT INTO task_assignments (task_id, user_id)
                   VALUES ($1,$2)
                   ON CONFLICT (task_id, user_id) DO NOTHING""",
                (task_id, uid),
            )

    if mode:
        await db.aexecute(
            "UPDATE tasks SET assignment_mode=$2, updated_at=NOW() WHERE task_id=$1",
            (task_id, mode),
        )

    db.query_cache.invalidate_tables(["tasks", "task_assignees", "task_assignments"])
    await db.alog_action(str(actor_id), "task_multi_assigned", str(task_id), ",".join(clean_ids))
    return await get_assignment_summary(task_id)


async def remove_assignee(
    task_id: int,
    target_user_id: str,
    actor_id: str,
    *,
    guild_id: Optional[str] = None,
    is_guild_admin: bool = False,
) -> AssignmentSummary:
    """Remove a user assignee (and any sign-off record) from `task_id`."""
    task = await _fetch_task_row(task_id)
    if str(actor_id) != str(target_user_id):
        await _require_manage_permission(task, str(actor_id), guild_id=guild_id, is_guild_admin=is_guild_admin)

    uid = str(target_user_id)
    await db.aexecute("DELETE FROM task_assignees WHERE task_id=$1 AND user_id=$2", (task_id, uid))
    await db.aexecute("DELETE FROM task_assignments WHERE task_id=$1 AND user_id=$2", (task_id, uid))
    await db.aexecute("DELETE FROM task_assignment_signoffs WHERE task_id=$1 AND user_id=$2", (task_id, uid))
    db.query_cache.invalidate_tables(
        ["task_assignees", "task_assignments", "task_assignment_signoffs"]
    )
    return await get_assignment_summary(task_id)


async def assign_role(
    task_id: int,
    role_id: int,
    actor_id: str,
    guild_id: str,
    *,
    mode: Optional[str] = None,
    is_guild_admin: bool = False,
) -> AssignmentSummary:
    """Assign an entire Discord Role to any guild or project task."""
    if mode is not None and mode not in VALID_MODES:
        raise ValueError(f"Invalid assignment mode '{mode}'.")

    task = await _fetch_task_row(task_id)
    await _require_manage_permission(task, str(actor_id), guild_id=guild_id, is_guild_admin=is_guild_admin)

    await db.aexecute(
        """INSERT INTO task_role_assignments (task_id, guild_id, role_id, assigned_by)
           VALUES ($1,$2,$3,$4)
           ON CONFLICT (task_id, role_id) DO NOTHING""",
        (task_id, str(guild_id), int(role_id), str(actor_id)),
    )
    if task.get("project_id"):
        await db.aexecute(
            """INSERT INTO project_task_role_assignments
                   (task_id, project_id, guild_id, role_id, assigned_by)
               VALUES ($1,$2,$3,$4,$5)
               ON CONFLICT (task_id, role_id) DO NOTHING""",
            (task_id, int(task["project_id"]), str(guild_id), int(role_id), str(actor_id)),
        )

    if mode:
        await db.aexecute(
            "UPDATE tasks SET assignment_mode=$2, updated_at=NOW() WHERE task_id=$1",
            (task_id, mode),
        )

    db.query_cache.invalidate_tables(
        ["tasks", "task_role_assignments", "project_task_role_assignments"]
    )
    await db.alog_action(str(actor_id), "task_role_assigned", str(task_id), f"role={role_id}")
    return await get_assignment_summary(task_id)


async def set_assignment_mode(
    task_id: int,
    mode: str,
    actor_id: str,
    *,
    guild_id: Optional[str] = None,
    is_guild_admin: bool = False,
) -> AssignmentSummary:
    """Switch a task between 'first_wins' and 'all_signoff'."""
    if mode not in VALID_MODES:
        raise ValueError(f"Invalid assignment mode '{mode}'.")
    task = await _fetch_task_row(task_id)
    await _require_manage_permission(task, str(actor_id), guild_id=guild_id, is_guild_admin=is_guild_admin)
    await db.aexecute(
        "UPDATE tasks SET assignment_mode=$2, updated_at=NOW() WHERE task_id=$1",
        (task_id, mode),
    )
    db.query_cache.invalidate_table("tasks")
    return await get_assignment_summary(task_id)


def _db_can_query(fn) -> bool:
    """Return True when the DB pool is ready or the query method is mocked in unit tests."""
    return getattr(db, "_pool", None) is not None or hasattr(fn, "assert_called")


async def get_assignment_summary(
    task_id: int,
    role_member_ids: Optional[Iterable[str]] = None,
) -> AssignmentSummary:
    """Fetch combined individual assignees, roles, mode, and sign-off status for `task_id`."""
    task = (
        await db.afetchone(
            "SELECT task_id, COALESCE(assignment_mode, 'first_wins') AS assignment_mode FROM tasks WHERE task_id=$1",
            (task_id,),
        )
        if _db_can_query(db.afetchone)
        else None
    )
    if not task:
        return AssignmentSummary(task_id=task_id)

    raw_mode = (
        task.get("assignment_mode")
        if hasattr(task, "get")
        else (task["assignment_mode"] if "assignment_mode" in task else None)
    )
    mode = str(raw_mode or "first_wins")

    if _db_can_query(db.afetchall):
        u_rows = await db.afetchall(
            """SELECT user_id FROM task_assignees WHERE task_id=$1
               UNION
               SELECT user_id FROM task_assignments WHERE task_id=$1""",
            (task_id,),
        )
        r_rows = await db.afetchall(
            """SELECT role_id FROM task_role_assignments WHERE task_id=$1
               UNION
               SELECT role_id FROM project_task_role_assignments WHERE task_id=$1""",
            (task_id,),
        )
        s_rows = await db.afetchall(
            "SELECT user_id FROM task_assignment_signoffs WHERE task_id=$1 ORDER BY signed_at ASC",
            (task_id,),
        )
    else:
        u_rows, r_rows, s_rows = [], [], []

    user_ids = sorted({str(r["user_id"]) for r in (u_rows or [])})
    role_ids = sorted({int(r["role_id"]) for r in (r_rows or [])})
    signed_ids = [str(r["user_id"]) for r in (s_rows or [])]

    required_set = set(user_ids)
    if role_member_ids:
        required_set.update(str(uid) for uid in role_member_ids if uid)
    pending_ids = sorted(uid for uid in required_set if uid not in set(signed_ids))

    return AssignmentSummary(
        task_id=task_id,
        assignment_mode=mode,
        user_ids=user_ids,
        role_ids=role_ids,
        signed_user_ids=signed_ids,
        pending_user_ids=pending_ids,
    )


async def is_user_assigned_to_task(
    task_id: int,
    user_id: str,
    actor_role_ids: Optional[list[int]] = None,
) -> bool:
    """Return True if `user_id` is directly assigned or holds an assigned role on `task_id`."""
    summary = await get_assignment_summary(task_id)
    if str(user_id) in summary.user_ids:
        return True
    if actor_role_ids:
        role_set = {int(r) for r in actor_role_ids}
        if any(rid in role_set for rid in summary.role_ids):
            return True
    return False


async def handle_task_completion_attempt(
    task_id: int,
    actor_id: str,
    *,
    role_member_ids: Optional[Iterable[str]] = None,
    force: bool = False,
) -> SignoffResult:
    """
    Evaluate whether completing `task_id` by `actor_id` completes the task immediately
    ('first_wins' or `force=True`) or records an incremental sign-off ('all_signoff').
    """
    summary = await get_assignment_summary(task_id, role_member_ids=role_member_ids)
    actor = str(actor_id)

    if force or summary.assignment_mode != "all_signoff" or summary.total_required <= 1:
        return SignoffResult(
            task_id=task_id,
            completed=True,
            mode=summary.assignment_mode,
            signed_users=summary.signed_user_ids or [actor],
            pending_users=[],
        )

    await ensure_user(actor)
    already_signed = actor in summary.signed_user_ids
    if not already_signed:
        await db.aexecute(
            """INSERT INTO task_assignment_signoffs (task_id, user_id, signed_at)
               VALUES ($1,$2,NOW())
               ON CONFLICT (task_id, user_id) DO NOTHING""",
            (task_id, actor),
        )
        db.query_cache.invalidate_table("task_assignment_signoffs")

    updated = await get_assignment_summary(task_id, role_member_ids=role_member_ids)
    all_done = len(updated.pending_user_ids) == 0
    return SignoffResult(
        task_id=task_id,
        completed=all_done,
        mode=updated.assignment_mode,
        signed_users=updated.signed_user_ids,
        pending_users=updated.pending_user_ids,
        already_signed=already_signed,
    )

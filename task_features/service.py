"""Persistence and access checks for task comments and progress."""
from __future__ import annotations

from typing import Any

from core.database import db
from utils.helpers import ensure_user


class TaskFeatureError(Exception):
    """Base exception for task feature operations."""


class TaskNotFound(TaskFeatureError):
    """Raised when the task does not exist."""


class TaskAccessDenied(TaskFeatureError):
    """Raised when the actor cannot access or modify the task."""


class InvalidComment(TaskFeatureError):
    """Raised when a comment is empty or exceeds the supported length."""


class InvalidProgress(TaskFeatureError):
    """Raised when progress is not an integer between 0 and 100."""


async def get_accessible_task(
    task_id: int,
    user_id: str,
    minimum_role: str = "viewer",
) -> Any:
    """Return a task after verifying personal ownership or project membership."""
    task = await db.afetchone(
        """SELECT task_id, task, owner_id, project_id, guild_id, progress_pct
           FROM tasks WHERE task_id=$1""",
        (task_id,),
    )
    if not task:
        raise TaskNotFound(task_id)

    if task["project_id"] is None:
        if task["owner_id"] != user_id:
            raise TaskAccessDenied(task_id)
        return task

    if not task["guild_id"]:
        raise TaskAccessDenied(task_id)

    from collaboration import service as collaboration_service

    try:
        project = await collaboration_service.get_project(
            task["project_id"], task["guild_id"]
        )
    except collaboration_service.ProjectNotFound as exc:
        raise TaskNotFound(task_id) from exc

    if project.owner_id == user_id:
        return task

    role = await collaboration_service.get_member_role(task["project_id"], user_id)
    role_level = {"viewer": 0, "member": 1, "lead": 2}
    if role is None or role_level.get(role, -1) < role_level[minimum_role]:
        raise TaskAccessDenied(task_id)
    return task


async def get_comments(
    task_id: int,
    user_id: str,
    page: int,
    page_size: int = 5,
) -> tuple[Any, list[Any], int]:
    """Return the task, one page of comments, and the total comment count."""
    task = await get_accessible_task(task_id, user_id)
    count_row = await db.afetchone(
        "SELECT COUNT(*) AS total FROM task_comments WHERE task_id=$1",
        (task_id,),
    )
    total = int(count_row["total"] or 0) if count_row else 0
    last_page = max(0, (total - 1) // page_size)
    page = min(max(page, 0), last_page)
    comments = await db.afetchall(
        """SELECT comment_id, user_id, content, created_at
           FROM task_comments
           WHERE task_id=$1
           ORDER BY created_at DESC, comment_id DESC
           LIMIT $2 OFFSET $3""",
        (task_id, page_size, page * page_size),
    )
    return task, list(comments), total


async def add_comment(task_id: int, user_id: str, content: str) -> None:
    """Add a comment after verifying the actor may contribute to the task."""
    from core.security import validator

    cleaned = validator.sanitize(content, max_length=1000)
    if not cleaned:
        raise InvalidComment("comment cannot be empty")

    await get_accessible_task(task_id, user_id, minimum_role="member")
    await ensure_user(user_id)
    await db.aexecute(
        """INSERT INTO task_comments (task_id, user_id, content)
           VALUES ($1, $2, $3)""",
        (task_id, user_id, cleaned),
    )
    db.query_cache.invalidate_tables(["task_comments"])
    await db.alog_action(user_id, "task_commented", str(task_id))


async def update_progress(task_id: int, user_id: str, progress_pct: int) -> Any:
    """Update task progress; personal tasks require ownership and project tasks a member role."""
    if isinstance(progress_pct, bool) or not isinstance(progress_pct, int) or not 0 <= progress_pct <= 100:
        raise InvalidProgress(progress_pct)

    task = await get_accessible_task(task_id, user_id, minimum_role="member")
    update_result = await db.aexecute(
        """UPDATE tasks
           SET progress_pct=$1, updated_at=NOW()
           WHERE task_id=$2""",
        (progress_pct, task_id),
    )
    if update_result != "UPDATE 1":
        raise TaskNotFound(task_id)

    db.invalidate_stats(task["owner_id"])
    await db.alog_action(
        user_id, "task_progress_updated", str(task_id), f"progress_pct={progress_pct}"
    )
    return {
        "task_id": task_id,
        "task": task["task"],
        "progress_pct": progress_pct,
    }

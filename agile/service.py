"""
agile/service.py — Core business logic, formulas, and database operations for Agile & Scrum Full Suite.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, Tuple

from agile.models import (
    FIBONACCI_POINTS,
    Epic,
    EpicStatus,
    PlanningPokerSession,
    RetroCard,
    RetroColumn,
    Sprint,
    SprintStatus,
    VelocityStats,
)
from core.database import db

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# In-Memory State for Active Poker & Dot Voting
# ─────────────────────────────────────────────────────────────────────────────

_POKER_SESSIONS: dict[int, PlanningPokerSession] = {}
_RETRO_USER_VOTES: dict[tuple[int, str], int] = {}  # (sprint_id, user_id) -> count of votes cast


# ─────────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────────

class AgileError(Exception):
    """Base exception for agile operations."""


class SprintNotFoundError(AgileError):
    """Raised when sprint is not found."""


class SprintAlreadyActiveError(AgileError):
    """Raised when an active sprint already exists for the project."""


class EpicNotFoundError(AgileError):
    """Raised when epic is not found."""


class DotVotesExhaustedError(AgileError):
    """Raised when a user has used all 3 dot votes in a retrospective."""


class InvalidStoryPointError(AgileError):
    """Raised when a point is not in Fibonacci sequence."""


# ─────────────────────────────────────────────────────────────────────────────
# Sprints Lifecycle Service
# ─────────────────────────────────────────────────────────────────────────────

async def create_sprint(
    project_id: int,
    name: str,
    duration_days: int = 14,
    goal: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Sprint:
    """Create a new planned sprint."""
    now = datetime.now(timezone.utc)
    end_date = now + timedelta(days=max(1, duration_days))

    row = await db.afetchone(
        """
        INSERT INTO sprints (project_id, name, status, goal, start_date, end_date, created_at)
        VALUES ($1, $2, 'planned', $3, $4, $5, $6)
        RETURNING sprint_id, project_id, name, status, goal, start_date, end_date, created_at
        """,
        (project_id, name.strip(), goal.strip() if goal else None, now, end_date, now),
    )
    if not row:
        raise AgileError("Could not create sprint in database.")
    return Sprint.from_row(row)


async def start_sprint(
    sprint_id: int,
    project_id: int,
    user_id: Optional[str] = None,
) -> Sprint:
    """Start a sprint and set its status to active."""
    # Check if an active sprint already exists for this project
    active_row = await db.afetchone(
        "SELECT sprint_id, name FROM sprints WHERE project_id = $1 AND status = 'active' AND sprint_id != $2",
        (project_id, sprint_id),
    )
    if active_row:
        raise SprintAlreadyActiveError(
            f"Sprint #{active_row['sprint_id']} ({active_row['name']}) is already active. Only one active sprint is allowed per project."
        )

    now = datetime.now(timezone.utc)
    updated = await db.afetchone(
        """
        UPDATE sprints
        SET status = 'active', start_date = COALESCE(start_date, $1)
        WHERE sprint_id = $2 AND project_id = $3
        RETURNING sprint_id, project_id, name, status, goal, start_date, end_date, created_at
        """,
        (now, sprint_id, project_id),
    )
    if not updated:
        raise SprintNotFoundError(f"Sprint #{sprint_id} not found in project #{project_id}.")
    return Sprint.from_row(updated)


async def close_sprint(
    sprint_id: int,
    project_id: int,
    user_id: Optional[str] = None,
    carryover_target: str = "backlog",  # 'backlog' or 'next'
    next_sprint_id: Optional[int] = None,
) -> Tuple[Sprint, int, int, int]:
    """Close an active sprint and resolve carryover tasks.
    Returns: (Sprint, completed_tasks_count, carried_tasks_count, completed_points)
    """
    sprint = await get_sprint(sprint_id)
    if not sprint:
        raise SprintNotFoundError(f"Sprint #{sprint_id} not found.")

    # 1. Query tasks in this sprint
    tasks = await db.afetchall(
        "SELECT task_id, status, story_points FROM tasks WHERE sprint_id = $1 AND is_deleted = FALSE",
        (sprint_id,),
    )
    completed_tasks = [t for t in tasks if t["status"] == "Completed"]
    unfinished_tasks = [t for t in tasks if t["status"] != "Completed"]

    completed_points = sum(int(t["story_points"] or 0) for t in completed_tasks)

    # 2. Carryover unfinished tasks
    carried_count = len(unfinished_tasks)
    if unfinished_tasks:
        if carryover_target == "next" and next_sprint_id:
            await db.aexecute(
                """
                UPDATE tasks
                SET sprint_id = $1
                WHERE sprint_id = $2 AND status != 'Completed' AND is_deleted = FALSE
                """,
                (next_sprint_id, sprint_id),
            )
        else:
            await db.aexecute(
                """
                UPDATE tasks
                SET sprint_id = NULL
                WHERE sprint_id = $1 AND status != 'Completed' AND is_deleted = FALSE
                """,
                (sprint_id,),
            )

    # 3. Mark sprint as closed
    now = datetime.now(timezone.utc)
    updated = await db.afetchone(
        """
        UPDATE sprints
        SET status = 'closed', end_date = $1
        WHERE sprint_id = $2 AND project_id = $3
        RETURNING sprint_id, project_id, name, status, goal, start_date, end_date, created_at
        """,
        (now, sprint_id, project_id),
    )
    if not updated:
        raise SprintNotFoundError(f"Sprint #{sprint_id} update failed.")

    closed_sprint = Sprint.from_row(updated)
    closed_sprint.total_tasks = len(tasks)
    closed_sprint.completed_tasks = len(completed_tasks)
    closed_sprint.completed_points = completed_points

    return closed_sprint, len(completed_tasks), carried_count, completed_points


async def get_sprint(sprint_id: int) -> Optional[Sprint]:
    """Retrieve sprint details with aggregated task and story point metrics."""
    row = await db.afetchone(
        """
        SELECT
            s.sprint_id, s.project_id, s.name, s.status, s.goal, s.start_date, s.end_date, s.created_at,
            COUNT(t.task_id) AS total_tasks,
            COUNT(t.task_id) FILTER (WHERE t.status = 'Completed') AS completed_tasks,
            COALESCE(SUM(t.story_points), 0) AS total_points,
            COALESCE(SUM(t.story_points) FILTER (WHERE t.status = 'Completed'), 0) AS completed_points
        FROM sprints s
        LEFT JOIN tasks t ON t.sprint_id = s.sprint_id AND t.is_deleted = FALSE
        WHERE s.sprint_id = $1
        GROUP BY s.sprint_id
        """,
        (sprint_id,),
    )
    if not row:
        return None
    return Sprint.from_row(row)


async def get_active_sprint(project_id: int) -> Optional[Sprint]:
    """Return the currently active sprint for a project."""
    row = await db.afetchone(
        "SELECT sprint_id FROM sprints WHERE project_id = $1 AND status = 'active' LIMIT 1",
        (project_id,),
    )
    if not row:
        return None
    return await get_sprint(int(row["sprint_id"]))


async def list_sprints(project_id: int, status: Optional[str] = None) -> list[Sprint]:
    """List all sprints for a project."""
    if status:
        rows = await db.afetchall(
            """
            SELECT
                s.sprint_id, s.project_id, s.name, s.status, s.goal, s.start_date, s.end_date, s.created_at,
                COUNT(t.task_id) AS total_tasks,
                COUNT(t.task_id) FILTER (WHERE t.status = 'Completed') AS completed_tasks,
                COALESCE(SUM(t.story_points), 0) AS total_points,
                COALESCE(SUM(t.story_points) FILTER (WHERE t.status = 'Completed'), 0) AS completed_points
            FROM sprints s
            LEFT JOIN tasks t ON t.sprint_id = s.sprint_id AND t.is_deleted = FALSE
            WHERE s.project_id = $1 AND s.status = $2
            GROUP BY s.sprint_id
            ORDER BY s.created_at DESC
            """,
            (project_id, status),
        )
    else:
        rows = await db.afetchall(
            """
            SELECT
                s.sprint_id, s.project_id, s.name, s.status, s.goal, s.start_date, s.end_date, s.created_at,
                COUNT(t.task_id) AS total_tasks,
                COUNT(t.task_id) FILTER (WHERE t.status = 'Completed') AS completed_tasks,
                COALESCE(SUM(t.story_points), 0) AS total_points,
                COALESCE(SUM(t.story_points) FILTER (WHERE t.status = 'Completed'), 0) AS completed_points
            FROM sprints s
            LEFT JOIN tasks t ON t.sprint_id = s.sprint_id AND t.is_deleted = FALSE
            WHERE s.project_id = $1
            GROUP BY s.sprint_id
            ORDER BY
                CASE s.status WHEN 'active' THEN 1 WHEN 'planned' THEN 2 ELSE 3 END,
                s.created_at DESC
            """,
            (project_id,),
        )
    return [Sprint.from_row(r) for r in (rows or [])]


async def get_backlog_tasks(project_id: int) -> list[dict[str, Any]]:
    """Retrieve all open tasks not currently assigned to any sprint."""
    rows = await db.afetchall(
        """
        SELECT task_id, task, priority, deadline, status, story_points, epic_id
        FROM tasks
        WHERE project_id = $1 AND sprint_id IS NULL AND is_deleted = FALSE AND status != 'Completed'
        ORDER BY priority DESC, created_at ASC
        LIMIT 50
        """,
        (project_id,),
    )
    return [dict(r) for r in (rows or [])]


async def add_task_to_sprint(task_id: int, sprint_id: int, project_id: int) -> bool:
    """Attach a task to a sprint."""
    res = await db.aexecute(
        """
        UPDATE tasks
        SET sprint_id = $1
        WHERE task_id = $2 AND project_id = $3 AND is_deleted = FALSE
        """,
        (sprint_id, task_id, project_id),
    )
    return "UPDATE 1" in res


async def remove_task_from_sprint(task_id: int, project_id: int) -> bool:
    """Remove a task from its sprint and send it back to the backlog."""
    res = await db.aexecute(
        """
        UPDATE tasks
        SET sprint_id = NULL
        WHERE task_id = $1 AND project_id = $2 AND is_deleted = FALSE
        """,
        (task_id, project_id),
    )
    return "UPDATE 1" in res


# ─────────────────────────────────────────────────────────────────────────────
# Story Points & Velocity Service
# ─────────────────────────────────────────────────────────────────────────────

async def set_task_story_points(task_id: int, points: int) -> bool:
    """Set the Fibonacci story points for a task."""
    if points not in FIBONACCI_POINTS:
        raise InvalidStoryPointError(
            f"Story points must be one of the Fibonacci values: {FIBONACCI_POINTS}"
        )
    res = await db.aexecute(
        "UPDATE tasks SET story_points = $1 WHERE task_id = $2 AND is_deleted = FALSE",
        (points, task_id),
    )
    return "UPDATE 1" in res


async def get_velocity_stats(project_id: int) -> VelocityStats:
    """Compute historical velocity across closed sprints and forecast backlog clearance."""
    # 1. Last 5 closed sprints with completed story points
    rows = await db.afetchall(
        """
        SELECT
            s.sprint_id, s.name,
            COALESCE(SUM(t.story_points) FILTER (WHERE t.status = 'Completed'), 0) AS completed_points
        FROM sprints s
        LEFT JOIN tasks t ON t.sprint_id = s.sprint_id AND t.is_deleted = FALSE
        WHERE s.project_id = $1 AND s.status = 'closed'
        GROUP BY s.sprint_id, s.name, s.created_at
        ORDER BY s.created_at DESC
        LIMIT 5
        """,
        (project_id,),
    )
    history: list[tuple[str, int]] = []
    total_pts = 0
    if rows:
        for r in reversed(rows):
            name = str(r["name"])
            pts = int(r["completed_points"])
            history.append((name, pts))
            total_pts += pts

    avg_velocity = round(total_pts / len(rows), 1) if rows else 0.0

    # 2. Backlog points
    backlog_row = await db.afetchone(
        """
        SELECT
            COUNT(task_id) AS backlog_count,
            COALESCE(SUM(story_points), 0) AS backlog_points
        FROM tasks
        WHERE project_id = $1 AND sprint_id IS NULL AND is_deleted = FALSE AND status != 'Completed'
        """,
        (project_id,),
    )
    backlog_count = int(backlog_row["backlog_count"]) if backlog_row else 0
    backlog_points = int(backlog_row["backlog_points"]) if backlog_row else 0

    forecast = (
        int(math.ceil(backlog_points / avg_velocity))
        if avg_velocity > 0 and backlog_points > 0
        else (1 if backlog_count > 0 else 0)
    )

    return VelocityStats(
        project_id=project_id,
        sprint_history=history,
        average_velocity=avg_velocity,
        backlog_tasks_count=backlog_count,
        backlog_points=backlog_points,
        forecast_sprints=forecast,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Planning Poker Service
# ─────────────────────────────────────────────────────────────────────────────

async def start_poker(task_id: int, host_id: str, guild_id: Optional[str] = None) -> PlanningPokerSession:
    """Start an interactive planning poker session for a task."""
    task_row = await db.afetchone(
        "SELECT task FROM tasks WHERE task_id = $1 AND is_deleted = FALSE",
        (task_id,),
    )
    title = str(task_row["task"]) if task_row else f"Task #{task_id}"

    session = PlanningPokerSession(
        task_id=task_id,
        task_title=title,
        host_id=host_id,
        guild_id=guild_id,
    )
    _POKER_SESSIONS[task_id] = session
    return session


def get_poker_session(task_id: int) -> Optional[PlanningPokerSession]:
    """Retrieve active poker session for a task."""
    return _POKER_SESSIONS.get(task_id)


def cast_poker_vote(task_id: int, user_id: str, points: int) -> bool:
    """Record a secret vote for a planning poker session."""
    session = _POKER_SESSIONS.get(task_id)
    if not session or session.is_revealed:
        return False
    session.cast_vote(user_id, points)
    return True


def reveal_poker(task_id: int) -> Optional[PlanningPokerSession]:
    """Reveal cards for an active planning poker session."""
    session = _POKER_SESSIONS.get(task_id)
    if not session:
        return None
    session.is_revealed = True
    return session


async def save_poker_points(task_id: int, points: int) -> bool:
    """Save finalized points from poker to the task and close session."""
    ok = await set_task_story_points(task_id, points)
    if ok:
        _POKER_SESSIONS.pop(task_id, None)
    return ok


# ─────────────────────────────────────────────────────────────────────────────
# Epics Hierarchy Service
# ─────────────────────────────────────────────────────────────────────────────

async def create_epic(
    project_id: int,
    name: str,
    description: Optional[str] = None,
    color: str = "#5865F2",
) -> Epic:
    """Create a new Epic within a project."""
    row = await db.afetchone(
        """
        INSERT INTO epics (project_id, name, description, color, status)
        VALUES ($1, $2, $3, $4, 'open')
        RETURNING epic_id, project_id, name, description, color, status, created_at
        """,
        (project_id, name.strip(), description.strip() if description else None, color),
    )
    if not row:
        raise AgileError("Could not create epic in database.")
    return Epic.from_row(row)


async def list_epics(project_id: int, status: Optional[str] = None) -> list[Epic]:
    """List all epics for a project with task completion counts."""
    query = """
        SELECT
            e.epic_id, e.project_id, e.name, e.description, e.color, e.status, e.created_at,
            COUNT(t.task_id) AS total_tasks,
            COUNT(t.task_id) FILTER (WHERE t.status = 'Completed') AS completed_tasks,
            COALESCE(SUM(t.story_points), 0) AS total_points,
            COALESCE(SUM(t.story_points) FILTER (WHERE t.status = 'Completed'), 0) AS completed_points
        FROM epics e
        LEFT JOIN tasks t ON t.epic_id = e.epic_id AND t.is_deleted = FALSE
        WHERE e.project_id = $1
    """
    params: list[Any] = [project_id]
    if status:
        query += " AND e.status = $2"
        params.append(status)

    query += " GROUP BY e.epic_id ORDER BY e.created_at ASC"
    rows = await db.afetchall(query, tuple(params))
    return [Epic.from_row(r) for r in (rows or [])]


async def get_epic(epic_id: int) -> Optional[Epic]:
    """Retrieve epic details and aggregated progress metrics."""
    row = await db.afetchone(
        """
        SELECT
            e.epic_id, e.project_id, e.name, e.description, e.color, e.status, e.created_at,
            COUNT(t.task_id) AS total_tasks,
            COUNT(t.task_id) FILTER (WHERE t.status = 'Completed') AS completed_tasks,
            COALESCE(SUM(t.story_points), 0) AS total_points,
            COALESCE(SUM(t.story_points) FILTER (WHERE t.status = 'Completed'), 0) AS completed_points
        FROM epics e
        LEFT JOIN tasks t ON t.epic_id = e.epic_id AND t.is_deleted = FALSE
        WHERE e.epic_id = $1
        GROUP BY e.epic_id
        """,
        (epic_id,),
    )
    if not row:
        return None
    return Epic.from_row(row)


async def attach_task_to_epic(task_id: int, epic_id: int, project_id: int) -> bool:
    """Link a task to an epic."""
    res = await db.aexecute(
        "UPDATE tasks SET epic_id = $1 WHERE task_id = $2 AND project_id = $3 AND is_deleted = FALSE",
        (epic_id, task_id, project_id),
    )
    return "UPDATE 1" in res


async def get_epic_tree(epic_id: int) -> dict[str, Any]:
    """Fetch an Epic along with its full multi-tier hierarchy:
    Epic -> Tasks -> Subtasks -> Checklists.
    """
    epic = await get_epic(epic_id)
    if not epic:
        raise EpicNotFoundError(f"Epic #{epic_id} not found.")

    # Fetch main tasks
    tasks = await db.afetchall(
        """
        SELECT task_id, task, status, priority, story_points, parent_task_id
        FROM tasks
        WHERE epic_id = $1 AND is_deleted = FALSE
        ORDER BY parent_task_id NULLS FIRST, task_id ASC
        """,
        (epic_id,),
    )

    root_tasks = [dict(t) for t in tasks if t["parent_task_id"] is None]
    subtasks_map: dict[int, list[dict]] = {}
    for t in tasks:
        parent = t["parent_task_id"]
        if parent is not None:
            subtasks_map.setdefault(parent, []).append(dict(t))

    for rt in root_tasks:
        tid = rt["task_id"]
        rt["subtasks"] = subtasks_map.get(tid, [])

    return {
        "epic": epic,
        "tasks": root_tasks,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Sprint Retrospective & Dot Voting Service
# ─────────────────────────────────────────────────────────────────────────────

async def add_retro_card(
    sprint_id: int,
    column_type: str,
    content: str,
    author_id: Optional[str] = None,
) -> RetroCard:
    """Submit a retrospective card."""
    if column_type not in (RetroColumn.WELL.value, RetroColumn.IMPROVE.value, RetroColumn.ACTION.value):
        raise AgileError(f"Invalid column type: {column_type}")

    row = await db.afetchone(
        """
        INSERT INTO sprint_retros (sprint_id, column_type, content, author_id, votes)
        VALUES ($1, $2, $3, $4, 0)
        RETURNING retro_id, sprint_id, column_type, content, author_id, votes
        """,
        (sprint_id, column_type, content.strip(), author_id),
    )
    if not row:
        raise AgileError("Could not save retrospective card.")
    return RetroCard.from_row(row)


async def get_retro_board(sprint_id: int) -> dict[str, list[RetroCard]]:
    """Fetch all retrospective cards for a sprint grouped by column."""
    rows = await db.afetchall(
        """
        SELECT retro_id, sprint_id, column_type, content, author_id, votes
        FROM sprint_retros
        WHERE sprint_id = $1
        ORDER BY votes DESC, retro_id ASC
        """,
        (sprint_id,),
    )
    grouped: dict[str, list[RetroCard]] = {
        RetroColumn.WELL.value: [],
        RetroColumn.IMPROVE.value: [],
        RetroColumn.ACTION.value: [],
    }
    for r in (rows or []):
        card = RetroCard.from_row(r)
        if card.column_type in grouped:
            grouped[card.column_type].append(card)
    return grouped


async def vote_retro_card(retro_id: int, sprint_id: int, user_id: str) -> int:
    """Cast a dot vote on a retrospective card (max 3 dot votes per user per sprint)."""
    key = (sprint_id, str(user_id))
    current_votes = _RETRO_USER_VOTES.get(key, 0)
    if current_votes >= 3:
        raise DotVotesExhaustedError("คุณใช้โควตาโหวต (Dot Votes) ครบ 3 คะแนนสำหรับรอบนี้แล้วครับ!")

    updated = await db.afetchone(
        """
        UPDATE sprint_retros
        SET votes = votes + 1
        WHERE retro_id = $1 AND sprint_id = $2
        RETURNING votes
        """,
        (retro_id, sprint_id),
    )
    if not updated:
        raise AgileError(f"Card #{retro_id} not found in sprint #{sprint_id}.")

    _RETRO_USER_VOTES[key] = current_votes + 1
    return int(updated["votes"])


def get_user_remaining_votes(sprint_id: int, user_id: str) -> int:
    """Return remaining dot votes for a user in a sprint."""
    key = (sprint_id, str(user_id))
    return max(0, 3 - _RETRO_USER_VOTES.get(key, 0))


async def convert_action_items_to_tasks(
    sprint_id: int,
    project_id: int,
    user_id: str,
) -> int:
    """Convert top-voted Action Items from retrospective to backlog tasks."""
    rows = await db.afetchall(
        """
        SELECT content FROM sprint_retros
        WHERE sprint_id = $1 AND column_type = 'action'
        ORDER BY votes DESC, retro_id ASC
        """,
        (sprint_id,),
    )
    if not rows:
        return 0

    count = 0
    now = datetime.now(timezone.utc)
    for r in rows:
        title = str(r["content"])[:200]
        await db.aexecute(
            """
            INSERT INTO tasks (task, project_id, owner_id, status, priority, is_deleted, created_at)
            VALUES ($1, $2, $3, 'Pending', 2, FALSE, $4)
            """,
            (title, project_id, str(user_id), now),
        )
        count += 1
    return count


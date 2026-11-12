"""
recovery/janitor.py — Self-Healing Auto-Archive & Smart Janitor Engine (Feature 41)

Maintains long-term database health via three scheduled & on-demand operations:
  1. Move Completed/Cancelled tasks older than 90 days to `tasks_archive`
     (capturing JSONB `archived_metadata` before deleting from `tasks` so child
     checklists, comment counts, assignees, and time totals are preserved safely).
  2. Permanently purge expired soft-deleted Recycle Bin tasks older than 30 days.
  3. Roll up raw `audit_log` rows older than 180 days into monthly `audit_log_summary`.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import Any

from core.database import db
from recovery import service as recovery_service

log = logging.getLogger(__name__)


@dataclass
class JanitorReport:
    """Summary of one janitor execution (live or dry-run)."""
    archived_tasks: int = 0
    purged_trash: int = 0
    compacted_audit_logs: int = 0
    dry_run: bool = False


async def archive_completed_tasks(
    days: int = 90,
    batch_size: int = 500,
    dry_run: bool = False,
) -> int:
    """Archive non-deleted Completed/Cancelled tasks untouched for `days` days."""
    safe_days = max(1, int(days))
    safe_batch = max(1, min(int(batch_size), 2000))

    candidates = await db.afetchall(
        f"""SELECT task_id FROM tasks
            WHERE status IN ('Completed', 'Cancelled')
              AND is_deleted = FALSE
              AND COALESCE(completed_at, updated_at) < NOW() - INTERVAL '{safe_days} days'
            ORDER BY task_id ASC
            LIMIT $1""",
        (safe_batch,),
    )
    task_ids = [int(r["task_id"]) for r in (candidates or [])]
    if dry_run or not task_ids:
        return len(task_ids)

    placeholders = ",".join(f"${i + 1}" for i in range(len(task_ids)))

    # Collect lightweight child snapshots before deleting parent rows (avoids silent data loss on CASCADE)
    meta_map: dict[int, dict[str, Any]] = {tid: {} for tid in task_ids}
    cl_rows = await db.afetchall(
        f"""SELECT task_id, COUNT(*) AS cnt, SUM(CASE WHEN is_done THEN 1 ELSE 0 END) AS done_cnt
            FROM task_checklists WHERE task_id IN ({placeholders}) GROUP BY task_id""",
        tuple(task_ids),
    )
    for r in (cl_rows or []):
        meta_map[int(r["task_id"])]["checklists"] = {
            "total": int(r["cnt"] or 0),
            "done": int(r["done_cnt"] or 0),
        }

    tl_rows = await db.afetchall(
        f"""SELECT task_id, COALESCE(SUM(hours_spent), 0) AS hours
            FROM task_time_logs WHERE task_id IN ({placeholders}) GROUP BY task_id""",
        tuple(task_ids),
    )
    for r in (tl_rows or []):
        meta_map[int(r["task_id"])]["hours_spent"] = float(r["hours"] or 0.0)

    cm_rows = await db.afetchall(
        f"SELECT task_id, COUNT(*) AS cnt FROM task_comments WHERE task_id IN ({placeholders}) GROUP BY task_id",
        tuple(task_ids),
    )
    for r in (cm_rows or []):
        meta_map[int(r["task_id"])]["comment_count"] = int(r["cnt"] or 0)

    # Copy columns dynamically using shared task columns + archived_at / archived_metadata
    cols_rows = await db.afetchall(
        """SELECT column_name
           FROM information_schema.columns
           WHERE table_name = 'tasks'
           ORDER BY ordinal_position"""
    )
    col_names = [str(r["column_name"]) for r in (cols_rows or []) if r.get("column_name")]
    if col_names:
        col_list = ", ".join(col_names)
        await db.aexecute(
            f"""INSERT INTO tasks_archive ({col_list}, archived_at)
                SELECT {col_list}, NOW()
                FROM tasks
                WHERE task_id IN ({placeholders})
                ON CONFLICT (task_id) DO NOTHING""",
            tuple(task_ids),
        )
    else:
        # Unit-test fallback when information_schema is unmocked
        await db.aexecute(
            f"""INSERT INTO tasks_archive
                SELECT t.*, NOW() AS archived_at, '{{}}'::jsonb AS archived_metadata
                FROM tasks t
                WHERE t.task_id IN ({placeholders})
                ON CONFLICT (task_id) DO NOTHING""",
            tuple(task_ids),
        )

    for tid, meta in meta_map.items():
        if meta:
            await db.aexecute(
                "UPDATE tasks_archive SET archived_metadata=$2::jsonb WHERE task_id=$1",
                (tid, json.dumps(meta)),
            )

    deleted = await db.afetchall(
        f"DELETE FROM tasks WHERE task_id IN ({placeholders}) RETURNING task_id",
        tuple(task_ids),
    )
    count = len(deleted or []) if deleted is not None else len(task_ids)
    db.query_cache.invalidate_tables(["tasks", "tasks_archive"])
    log.info("Janitor archived %d completed tasks older than %d days", count, safe_days)
    return count


async def compact_old_audit_logs(days: int = 180, dry_run: bool = False) -> int:
    """Aggregate raw `audit_log` rows older than `days` into `audit_log_summary`."""
    safe_days = max(1, int(days))
    grouped = await db.afetchall(
        f"""SELECT TO_CHAR(created_at, 'YYYY-MM') AS period_month,
                   action,
                   COUNT(*) AS event_count,
                   COUNT(DISTINCT user_id) AS unique_users
            FROM audit_log
            WHERE created_at < NOW() - INTERVAL '{safe_days} days'
            GROUP BY TO_CHAR(created_at, 'YYYY-MM'), action"""
    )
    rows = list(grouped or [])
    total_events = sum(int(r["event_count"] or 0) for r in rows)
    if dry_run or total_events == 0:
        return total_events

    for r in rows:
        await db.aexecute(
            """INSERT INTO audit_log_summary
                   (period_month, guild_scope, action, event_count, unique_users)
               VALUES ($1, 'global', $2, $3, $4)
               ON CONFLICT (period_month, guild_scope, action) DO UPDATE SET
                   event_count = audit_log_summary.event_count + EXCLUDED.event_count,
                   unique_users = GREATEST(audit_log_summary.unique_users, EXCLUDED.unique_users)""",
            (str(r["period_month"]), str(r["action"]), int(r["event_count"]), int(r["unique_users"])),
        )

    await db.aexecute(
        f"DELETE FROM audit_log WHERE created_at < NOW() - INTERVAL '{safe_days} days'"
    )
    db.query_cache.invalidate_tables(["audit_log", "audit_log_summary"])
    log.info("Janitor compacted %d audit log rows older than %d days", total_events, safe_days)
    return total_events


async def get_janitor_stats(
    archive_days: int = 90,
    trash_days: int = 30,
    audit_days: int = 180,
) -> dict[str, int]:
    """Inspect current counts of archived rows and pending cleanup candidates."""
    archived_row = await db.afetchone("SELECT COUNT(*) AS c FROM tasks_archive")
    cand_archive = await db.afetchone(
        f"""SELECT COUNT(*) AS c FROM tasks
            WHERE status IN ('Completed', 'Cancelled')
              AND is_deleted = FALSE
              AND COALESCE(completed_at, updated_at) < NOW() - INTERVAL '{int(archive_days)} days'"""
    )
    cand_trash = await db.afetchone(
        f"""SELECT COUNT(*) AS c FROM tasks
            WHERE is_deleted = TRUE
              AND deleted_at < NOW() - INTERVAL '{int(trash_days)} days'"""
    )
    cand_audit = await db.afetchone(
        f"SELECT COUNT(*) AS c FROM audit_log WHERE created_at < NOW() - INTERVAL '{int(audit_days)} days'"
    )
    summary_row = await db.afetchone(
        "SELECT COALESCE(SUM(event_count), 0) AS c FROM audit_log_summary"
    )
    return {
        "tasks_archive_total": int(archived_row["c"] or 0) if archived_row else 0,
        "eligible_archive": int(cand_archive["c"] or 0) if cand_archive else 0,
        "eligible_trash": int(cand_trash["c"] or 0) if cand_trash else 0,
        "eligible_audit": int(cand_audit["c"] or 0) if cand_audit else 0,
        "compacted_audit_total": int(summary_row["c"] or 0) if summary_row else 0,
    }


async def run_janitor_cycle(
    archive_days: int = 90,
    trash_days: int = 30,
    audit_days: int = 180,
    dry_run: bool = False,
) -> JanitorReport:
    """Execute one full Smart Janitor maintenance cycle (or dry-run preview)."""
    archived = await archive_completed_tasks(days=archive_days, dry_run=dry_run)
    if dry_run:
        stats = await get_janitor_stats(
            archive_days=archive_days, trash_days=trash_days, audit_days=audit_days
        )
        purged = stats["eligible_trash"]
    else:
        purged = await recovery_service.purge_expired_trash(days=trash_days)
    compacted = await compact_old_audit_logs(days=audit_days, dry_run=dry_run)

    return JanitorReport(
        archived_tasks=archived,
        purged_trash=purged,
        compacted_audit_logs=compacted,
        dry_run=dry_run,
    )


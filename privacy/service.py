"""Business logic for GDPR Right to be Forgotten (/privacy delete-my-data)."""
from __future__ import annotations

import logging

from core.database import db
from privacy.models import GdprDeletionReport, GdprImpactSummary

log = logging.getLogger(__name__)

DELETED_USER_SENTINEL_ID = "deleted_user"
DELETED_USER_DISPLAY = "[Deleted User]"


async def _ensure_sentinel_user() -> None:
    """Guarantee the `[Deleted User]` sentinel account exists before anonymizing FK rows."""
    await db.aexecute(
        """INSERT INTO users (user_id, lang, timezone, role, theme)
           VALUES ($1, 'en', 'UTC', 'user', 'default')
           ON CONFLICT (user_id) DO NOTHING""",
        (DELETED_USER_SENTINEL_ID,),
    )


async def get_gdpr_impact(user_id: str) -> GdprImpactSummary:
    """Inspect how many personal and shared records will be erased or anonymized."""
    uid = str(user_id)
    if uid == DELETED_USER_SENTINEL_ID:
        return GdprImpactSummary(user_id=uid)

    personal = await db.afetchone(
        "SELECT COUNT(*) AS c FROM tasks WHERE owner_id=$1 AND project_id IS NULL", (uid,)
    )
    shared = await db.afetchone(
        "SELECT COUNT(*) AS c FROM tasks WHERE owner_id=$1 AND project_id IS NOT NULL", (uid,)
    )
    projs = await db.afetchone("SELECT COUNT(*) AS c FROM projects WHERE owner_id=$1", (uid,))
    comments = await db.afetchone("SELECT COUNT(*) AS c FROM task_comments WHERE user_id=$1", (uid,))
    docs = await db.afetchone("SELECT COUNT(*) AS c FROM project_documents WHERE author_id=$1", (uid,))
    time_logs = await db.afetchone("SELECT COUNT(*) AS c FROM task_time_logs WHERE user_id=$1", (uid,))
    themes = await db.afetchone("SELECT COUNT(*) AS c FROM user_themes WHERE user_id=$1", (uid,))

    return GdprImpactSummary(
        user_id=uid,
        personal_tasks=int(personal["c"] or 0) if personal else 0,
        shared_project_tasks=int(shared["c"] or 0) if shared else 0,
        owned_projects=int(projs["c"] or 0) if projs else 0,
        comments_and_docs=(
            (int(comments["c"] or 0) if comments else 0)
            + (int(docs["c"] or 0) if docs else 0)
        ),
        time_logs=int(time_logs["c"] or 0) if time_logs else 0,
        custom_themes=int(themes["c"] or 0) if themes else 0,
    )


async def execute_gdpr_deletion(user_id: str) -> GdprDeletionReport:
    """
    Permanently delete personal user data while anonymizing shared project history
    to `[Deleted User]` (`deleted_user` sentinel) without violating FK constraints.
    """
    uid = str(user_id)
    if uid == DELETED_USER_SENTINEL_ID:
        raise ValueError("Cannot delete system sentinel account.")

    await _ensure_sentinel_user()
    report = GdprDeletionReport(user_id=uid)

    # 1. Transfer ownership of shared projects to another lead/member when possible; else sentinel
    owned_projects = await db.afetchall(
        "SELECT project_id FROM projects WHERE owner_id=$1", (uid,)
    )
    for prow in (owned_projects or []):
        pid = int(prow["project_id"])
        successor = await db.afetchone(
            """SELECT user_id FROM project_members
               WHERE project_id=$1 AND user_id <> $2
               ORDER BY CASE WHEN role='lead' THEN 0 ELSE 1 END, joined_at ASC
               LIMIT 1""",
            (pid, uid),
        )
        if successor:
            new_owner = str(successor["user_id"])
            await db.aexecute(
                "UPDATE projects SET owner_id=$2, updated_at=NOW() WHERE project_id=$1",
                (pid, new_owner),
            )
            report.projects_transferred += 1
        else:
            await db.aexecute(
                "UPDATE projects SET owner_id=$2, updated_at=NOW() WHERE project_id=$1",
                (pid, DELETED_USER_SENTINEL_ID),
            )
            report.projects_anonymized += 1

    # 2. Anonymize shared tasks & collaborative artifact FK columns (preserving Data Integrity)
    shared_rows = await db.afetchall(
        "UPDATE tasks SET owner_id=$2 WHERE owner_id=$1 AND project_id IS NOT NULL RETURNING task_id",
        (uid, DELETED_USER_SENTINEL_ID),
    )
    report.shared_tasks_anonymized = len(shared_rows or [])

    await db.aexecute(
        "UPDATE tasks_archive SET owner_id=$2 WHERE owner_id=$1 AND project_id IS NOT NULL",
        (uid, DELETED_USER_SENTINEL_ID),
    )

    fk_anonymize_statements = [
        ("task_comments", "user_id"),
        ("task_attachments", "uploader_id"),
        ("project_documents", "author_id"),
        ("task_revisions", "edited_by"),
        ("sprint_retros", "author_id"),
        ("automation_rules", "created_by"),
        ("voice_focus_rooms", "bound_by"),
        ("standup_configs", "created_by"),
        ("project_custom_fields", "created_by"),
    ]
    for table_name, col_name in fk_anonymize_statements:
        await db.aexecute(
            f"UPDATE {table_name} SET {col_name}=$2 WHERE {col_name}=$1",
            (uid, DELETED_USER_SENTINEL_ID),
        )

    # Shared checklist templates stay usable; personal ones are deleted below
    await db.aexecute(
        "UPDATE checklist_templates SET owner_id=$2 WHERE owner_id=$1 AND is_shared=TRUE",
        (uid, DELETED_USER_SENTINEL_ID),
    )

    # Anonymize non-FK actor logs cleanly as '[Deleted User]'
    await db.aexecute(
        "UPDATE audit_log SET user_id=$2 WHERE user_id=$1",
        (uid, DELETED_USER_DISPLAY),
    )
    await db.aexecute(
        "UPDATE project_activity_log SET user_id=$2 WHERE user_id=$1",
        (uid, DELETED_USER_DISPLAY),
    )
    await db.aexecute(
        "UPDATE peer_kudos SET from_user_id=$2 WHERE from_user_id=$1",
        (uid, DELETED_USER_DISPLAY),
    )
    await db.aexecute(
        "UPDATE peer_kudos SET to_user_id=$2 WHERE to_user_id=$1",
        (uid, DELETED_USER_DISPLAY),
    )

    # 3. Clear shared memberships / assignments lacking CASCADE
    for tbl in ("project_members", "task_assignments", "task_assignees", "task_assignment_signoffs"):
        await db.aexecute(f"DELETE FROM {tbl} WHERE user_id=$1", (uid,))

    # 4. Hard-delete personal data
    del_personal = await db.afetchall(
        "DELETE FROM tasks WHERE owner_id=$1 AND project_id IS NULL RETURNING task_id",
        (uid,),
    )
    report.personal_tasks_deleted = len(del_personal or [])

    personal_delete_tables = [
        ("tasks_archive", "owner_id"),
        ("categories", "owner_id"),
        ("checklist_templates", "owner_id"),
        ("user_achievements", "user_id"),
        ("task_time_logs", "user_id"),
        ("focus_sessions", "user_id"),
        ("active_time_timers", "user_id"),
        ("user_workload_capacities", "user_id"),
        ("user_rpg_profiles", "user_id"),
        ("guild_quest_participants", "user_id"),
        ("calendar_feed_tokens", "user_id"),
        ("task_templates", "owner_id"),
        ("routine_event_rules", "created_by"),
        ("saved_filters", "user_id"),
        ("user_chime_settings", "user_id"),
        ("user_themes", "user_id"),
        ("daily_standups", "user_id"),
        ("task_completion_events", "user_id"),
    ]
    for tbl, col in personal_delete_tables:
        await db.aexecute(f"DELETE FROM {tbl} WHERE {col}=$1", (uid,))

    # 5. Finally remove the user row & purge all caches
    deleted_user_row = await db.afetchone(
        "DELETE FROM users WHERE user_id=$1 RETURNING user_id", (uid,)
    )
    report.user_deleted = bool(deleted_user_row)

    db.user_cache.invalidate(uid)
    db.invalidate_stats(uid)
    db.query_cache.invalidate_all()
    await db.alog_action("system", "gdpr_erasure_completed", detail="Anonymized & erased user account")
    log.info(
        "GDPR erasure completed: personal_deleted=%d shared_anonymized=%d",
        report.personal_tasks_deleted, report.shared_tasks_anonymized,
    )
    return report


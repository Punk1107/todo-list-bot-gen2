"""
Engine layer for Event-Condition-Action (ECA) automations,
Automated Escalation Policies, and SLA Monitoring & Breaches.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import discord

from core.database import db
from automation.models import ECARule, SLAPolicy, TaskEscalation, TaskSLATracking

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. ECA Automation Engine (Feature 20)
# ─────────────────────────────────────────────────────────────────────────────

def eval_conditions(condition_json: dict[str, Any], context: dict[str, Any]) -> bool:
    """
    Evaluates condition rules against context (task or event data).
    Supported conditions:
    - priority_gte (int): task priority >= value
    - priority_lte (int): task priority <= value
    - category (str): task category or tags match
    - has_tag (str): specific tag present in tags list or string
    - due_within_hours (float): deadline is within next N hours
    - project_id (int): matches project ID
    """
    if not condition_json:
        return True

    # Priority comparisons
    if "priority_gte" in condition_json:
        req = int(condition_json["priority_gte"])
        actual = int(context.get("priority", 0))
        if actual < req:
            return False

    if "priority_lte" in condition_json:
        req = int(condition_json["priority_lte"])
        actual = int(context.get("priority", 0))
        if actual > req:
            return False

    # Category / Tag matching
    if "category" in condition_json:
        req_cat = str(condition_json["category"]).lower()
        actual_cat = str(context.get("tags") or context.get("category") or "").lower()
        if req_cat not in actual_cat:
            return False

    if "has_tag" in condition_json:
        req_tag = str(condition_json["has_tag"]).lower()
        actual_tags = str(context.get("tags") or "").lower()
        if req_tag not in actual_tags:
            return False

    # Due within hours
    if "due_within_hours" in condition_json:
        dl_raw = context.get("deadline")
        if not dl_raw:
            return False
        try:
            if isinstance(dl_raw, str):
                dl = datetime.fromisoformat(dl_raw.replace("Z", "+00:00"))
            else:
                dl = dl_raw
            if dl.tzinfo is None:
                dl = dl.replace(tzinfo=timezone.utc)
            now_utc = datetime.now(timezone.utc)
            diff_hours = (dl - now_utc).total_seconds() / 3600.0
            if diff_hours < 0 or diff_hours > float(condition_json["due_within_hours"]):
                return False
        except Exception:
            return False

    # Project ID match
    if "project_id" in condition_json:
        req_pid = int(condition_json["project_id"])
        actual_pid = context.get("project_id")
        if actual_pid is None or int(actual_pid) != req_pid:
            return False

    return True


async def execute_actions(
    bot: Any,
    action_json: dict[str, Any],
    context: dict[str, Any],
    guild: Optional[discord.Guild] = None,
) -> list[str]:
    """
    Executes automation actions based on action_json.
    Supported actions:
    - notify_channel: {"channel_id": "123", "message": "..."}
    - assign_role: {"role_id": "123", "target_user_id": "..."}
    - add_tag: {"tag": "urgent"}
    - move_to_sprint: {"sprint_id": 5}
    - create_thread: {"channel_id": "123", "thread_name": "..."}
    """
    results: list[str] = []
    if not action_json:
        return results

    task_id = context.get("task_id")

    # 1. Notify Channel
    notify_act = action_json.get("notify_channel")
    if notify_act and isinstance(notify_act, dict):
        ch_id = notify_act.get("channel_id")
        msg_text = notify_act.get("message") or f"🔔 Automation triggered for Task #{task_id}: {context.get('task', '')}"
        try:
            channel = bot.get_channel(int(ch_id)) if bot else None
            if channel:
                await channel.send(msg_text)
                results.append(f"Notified channel {ch_id}")
        except Exception as e:
            log.warning("Automation notify_channel failed: %s", e)

    # 2. Add Tag
    add_tag_act = action_json.get("add_tag")
    if add_tag_act and task_id:
        new_tag = add_tag_act.get("tag") if isinstance(add_tag_act, dict) else str(add_tag_act)
        if new_tag:
            try:
                row = await db.fetchone("SELECT tags FROM tasks WHERE task_id = $1", int(task_id))
                curr_tags = row.get("tags") if row else ""
                updated_tags = f"{curr_tags},{new_tag}".strip(",") if curr_tags else new_tag
                await db.execute("UPDATE tasks SET tags = $1, updated_at = NOW() WHERE task_id = $2", updated_tags, int(task_id))
                results.append(f"Added tag '{new_tag}' to task #{task_id}")
            except Exception as e:
                log.warning("Automation add_tag failed: %s", e)

    # 3. Move to Sprint
    move_sprint_act = action_json.get("move_to_sprint")
    if move_sprint_act and task_id:
        sprint_id = move_sprint_act.get("sprint_id") if isinstance(move_sprint_act, dict) else move_sprint_act
        try:
            await db.execute("UPDATE tasks SET sprint_id = $1, updated_at = NOW() WHERE task_id = $2", int(sprint_id), int(task_id))
            results.append(f"Moved task #{task_id} to sprint #{sprint_id}")
        except Exception as e:
            log.warning("Automation move_to_sprint failed: %s", e)

    # 4. Assign Role
    role_act = action_json.get("assign_role")
    if role_act and guild and isinstance(role_act, dict):
        role_id = role_act.get("role_id")
        user_id = role_act.get("target_user_id") or context.get("owner_id")
        if role_id and user_id:
            try:
                role = guild.get_role(int(role_id))
                member = guild.get_member(int(user_id))
                if role and member:
                    await member.add_roles(role, reason="Automation rule trigger")
                    results.append(f"Assigned role {role.name} to {member.display_name}")
            except Exception as e:
                log.warning("Automation assign_role failed: %s", e)

    # 5. Create Discord Thread
    thread_act = action_json.get("create_thread")
    if thread_act and isinstance(thread_act, dict):
        ch_id = thread_act.get("channel_id")
        thread_name = thread_act.get("thread_name") or f"Task-{task_id}-discussion"
        try:
            channel = bot.get_channel(int(ch_id)) if bot else None
            if channel and hasattr(channel, "create_thread"):
                th = await channel.create_thread(name=thread_name, auto_archive_duration=1440)
                results.append(f"Created thread '{th.name}' in channel {ch_id}")
        except Exception as e:
            log.warning("Automation create_thread failed: %s", e)

    return results


async def dispatch_event(
    bot: Any,
    trigger_event: str,
    context: dict[str, Any],
    guild_id: str,
) -> list[str]:
    """
    Dispatches an event through the ECA rules engine.
    Finds active rules matching guild_id and trigger_event,
    evaluates conditions, and executes actions.
    """
    rows = await db.fetchall(
        """SELECT * FROM automation_rules
           WHERE guild_id = $1 AND trigger_event = $2 AND is_active = TRUE
           ORDER BY rule_id ASC""",
        str(guild_id),
        str(trigger_event),
    )

    all_results: list[str] = []
    guild = bot.get_guild(int(guild_id)) if bot and hasattr(bot, "get_guild") else None

    for row in rows:
        rule = ECARule.from_row(row)
        if eval_conditions(rule.condition_json, context):
            actions_res = await execute_actions(bot, rule.action_json, context, guild=guild)
            all_results.extend(actions_res)

    return all_results


async def create_rule(
    guild_id: str,
    name: str,
    trigger_event: str,
    condition_json: dict[str, Any],
    action_json: dict[str, Any],
    created_by: Optional[str] = None,
) -> int:
    """Inserts a new ECA automation rule."""
    row = await db.fetchone(
        """INSERT INTO automation_rules
           (guild_id, name, trigger_event, condition_json, action_json, is_active, created_by, created_at)
           VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, TRUE, $6, NOW())
           RETURNING rule_id""",
        str(guild_id),
        str(name),
        str(trigger_event),
        json.dumps(condition_json),
        json.dumps(action_json),
        str(created_by) if created_by else None,
    )
    return int(row["rule_id"])


async def delete_rule(rule_id: int, guild_id: str) -> bool:
    """Deletes an ECA automation rule."""
    row = await db.fetchone(
        "DELETE FROM automation_rules WHERE rule_id = $1 AND guild_id = $2 RETURNING rule_id",
        int(rule_id),
        str(guild_id),
    )
    return row is not None


async def toggle_rule(rule_id: int, guild_id: str) -> Optional[bool]:
    """Toggles active status of an ECA rule. Returns new is_active boolean, or None if not found."""
    row = await db.fetchone(
        """UPDATE automation_rules
           SET is_active = NOT is_active
           WHERE rule_id = $1 AND guild_id = $2
           RETURNING is_active""",
        int(rule_id),
        str(guild_id),
    )
    return bool(row["is_active"]) if row else None


async def list_rules(guild_id: str) -> list[ECARule]:
    """Lists all ECA automation rules for a guild."""
    rows = await db.fetchall(
        "SELECT * FROM automation_rules WHERE guild_id = $1 ORDER BY rule_id ASC",
        str(guild_id),
    )
    return [ECARule.from_row(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# 2. Automated Escalation Policies (Feature 21)
# ─────────────────────────────────────────────────────────────────────────────

async def check_and_escalate_tasks(bot: Any) -> list[dict[str, Any]]:
    """
    Checks critical tasks (Priority >= 6) stuck in 'Pending' status:
    - Over 12 hours: Level 1 escalation (Ping in project channel).
    - Over 18 hours: Level 2 escalation (Mention project lead/admin).
    """
    now_utc = datetime.now(timezone.utc)
    eighteen_hours_ago = now_utc - timedelta(hours=18)

    # Find candidate critical tasks in Pending status (pending > 12h)
    query = """
        SELECT t.task_id, t.task, t.priority, t.guild_id, t.project_id, t.created_at,
               p.name AS project_name, p.channel_id, p.lead_id, p.owner_id,
               e.escalation_level, e.level1_escalated_at, e.level2_escalated_at
        FROM tasks t
        LEFT JOIN projects p ON t.project_id = p.project_id
        LEFT JOIN task_escalations e ON t.task_id = e.task_id
        WHERE t.status = 'Pending'
          AND t.priority >= 6
          AND t.created_at <= NOW() - INTERVAL '12 hours'
        ORDER BY t.priority DESC, t.created_at ASC
    """
    try:
        rows = await db.fetchall(query)
    except Exception as exc:
        if "lead_id" in str(exc).lower():
            # Graceful fallback if lead_id column has not been added to projects yet
            fallback_query = """
                SELECT t.task_id, t.task, t.priority, t.guild_id, t.project_id, t.created_at,
                       p.name AS project_name, p.channel_id, p.owner_id AS lead_id, p.owner_id,
                       e.escalation_level, e.level1_escalated_at, e.level2_escalated_at
                FROM tasks t
                LEFT JOIN projects p ON t.project_id = p.project_id
                LEFT JOIN task_escalations e ON t.task_id = e.task_id
                WHERE t.status = 'Pending'
                  AND t.priority >= 6
                  AND t.created_at <= NOW() - INTERVAL '12 hours'
                ORDER BY t.priority DESC, t.created_at ASC
            """
            rows = await db.fetchall(fallback_query)
        else:
            raise

    escalations: list[dict[str, Any]] = []

    for r in rows:
        task_id = int(r["task_id"])
        created_at = r.get("created_at")
        if created_at is not None and getattr(created_at, "tzinfo", None) is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        current_level = int(r.get("escalation_level") or 0)
        channel_id = r.get("channel_id")
        lead_id = r.get("lead_id") or r.get("owner_id")
        project_name = r.get("project_name") or "Project"
        task_title = r.get("task") or "Untitled Task"
        priority = int(r.get("priority", 6))

        # Level 1 Escalation: > 12 hours and level == 0
        if current_level == 0:
            await db.execute(
                """INSERT INTO task_escalations (task_id, escalation_level, level1_escalated_at)
                   VALUES ($1, 1, NOW())
                   ON CONFLICT (task_id) DO UPDATE SET escalation_level = 1, level1_escalated_at = NOW()""",
                task_id,
            )
            # Dispatch Level 1 notification
            if bot and channel_id:
                try:
                    ch = bot.get_channel(int(channel_id))
                    if ch:
                        embed = discord.Embed(
                            title="⚠️ [Escalation Level 1] Critical Task Pending > 12h",
                            description=(
                                f"**Task #{task_id}:** {task_title}\n"
                                f"**Priority:** P{priority} (Critical)\n"
                                f"**Project:** {project_name}\n\n"
                                f"งานระดับวิกฤตนี้ยังคงค้างอยู่ในสถานะ Pending เกิน 12 ชั่วโมง "
                                f"กรุณากดรับงานเพื่อเริ่มดำเนินการ!"
                            ),
                            color=discord.Color.gold(),
                        )
                        await ch.send(embed=embed)
                except Exception as e:
                    log.warning("Failed sending escalation L1 alert: %s", e)

            escalations.append({"task_id": task_id, "level": 1, "task": task_title})

        # Level 2 Escalation: > 18 hours and level == 1
        elif current_level == 1 and created_at and created_at <= eighteen_hours_ago:
            await db.execute(
                """UPDATE task_escalations
                   SET escalation_level = 2, level2_escalated_at = NOW()
                   WHERE task_id = $1""",
                task_id,
            )
            # Dispatch Level 2 notification to Project Lead / Admin
            if bot and channel_id:
                try:
                    ch = bot.get_channel(int(channel_id))
                    if ch:
                        lead_mention = f"<@{lead_id}>" if lead_id else "@here"
                        embed = discord.Embed(
                            title="🚨 [Escalation Level 2] Critical Task Pending > 18h!",
                            description=(
                                f"**Task #{task_id}:** {task_title}\n"
                                f"**Priority:** P{priority} (Urgent Critical)\n"
                                f"**Project:** {project_name}\n"
                                f"**Escalated to:** {lead_mention}\n\n"
                                f"งานระดับวิกฤตยังไม่มีการเคลื่อนไหวเกิน 18 ชั่วโมง "
                                f"ต้องการการตัดสินใจหรือกระจายงานด่วนจากทีมลีด!"
                            ),
                            color=discord.Color.red(),
                        )
                        await ch.send(content=lead_mention, embed=embed)
                except Exception as e:
                    log.warning("Failed sending escalation L2 alert: %s", e)

            escalations.append({"task_id": task_id, "level": 2, "task": task_title})

    return escalations


async def get_escalation_status(guild_id: Optional[str] = None) -> list[dict[str, Any]]:
    """Retrieves active escalated tasks with their details."""
    query = """
        SELECT e.task_id, e.escalation_level, e.level1_escalated_at, e.level2_escalated_at,
               t.task, t.priority, t.status, t.owner_id, t.created_at,
               p.project_id, p.name AS project_name
        FROM task_escalations e
        JOIN tasks t ON e.task_id = t.task_id
        LEFT JOIN projects p ON t.project_id = p.project_id
        WHERE t.status != 'Completed'
    """
    params: list[Any] = []
    if guild_id:
        query += " AND t.guild_id = $1"
        params.append(str(guild_id))

    query += " ORDER BY e.escalation_level DESC, t.priority DESC"
    return await db.fetchall(query, *params)


# ─────────────────────────────────────────────────────────────────────────────
# 3. SLA Monitoring & Breach Warning Engine (Feature 23)
# ─────────────────────────────────────────────────────────────────────────────

def render_sla_progress_bar(pct: float, width: int = 10) -> str:
    """Renders an ASCII/Emoji progress bar representing SLA timeline consumption."""
    clamped = max(0.0, min(100.0, pct))
    filled_len = int(round((clamped / 100.0) * width))
    empty_len = width - filled_len
    bar = "█" * filled_len + "░" * empty_len
    return f"[{bar}] {clamped:.1f}%"


async def get_project_sla_policy(project_id: int) -> Optional[SLAPolicy]:
    """Fetches SLA policy for a project."""
    row = await db.fetchone(
        "SELECT * FROM project_sla_policies WHERE project_id = $1",
        int(project_id),
    )
    return SLAPolicy.from_row(row) if row else None


async def upsert_project_sla_policy(
    project_id: int,
    guild_id: str,
    p7_hours: float = 2.0,
    p6_hours: float = 8.0,
    p5_hours: float = 24.0,
    p4_hours: float = 48.0,
    is_active: bool = True,
) -> SLAPolicy:
    """Configures or updates SLA policy for a project."""
    row = await db.fetchone(
        """INSERT INTO project_sla_policies
           (project_id, guild_id, p7_hours, p6_hours, p5_hours, p4_hours, is_active, created_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
           ON CONFLICT (project_id) DO UPDATE SET
               p7_hours = EXCLUDED.p7_hours,
               p6_hours = EXCLUDED.p6_hours,
               p5_hours = EXCLUDED.p5_hours,
               p4_hours = EXCLUDED.p4_hours,
               is_active = EXCLUDED.is_active
           RETURNING *""",
        int(project_id),
        str(guild_id),
        float(p7_hours),
        float(p6_hours),
        float(p5_hours),
        float(p4_hours),
        bool(is_active),
    )
    return SLAPolicy.from_row(row)


async def register_task_sla(task_id: int, project_id: int, priority: int) -> Optional[TaskSLATracking]:
    """Registers SLA tracking when a task is created or attached to a project."""
    policy = await get_project_sla_policy(project_id)
    if not policy or not policy.is_active:
        return None

    hours = policy.get_hours_for_priority(priority)
    target_deadline = datetime.now(timezone.utc) + timedelta(hours=hours)

    row = await db.fetchone(
        """INSERT INTO task_sla_tracking
           (task_id, project_id, target_deadline, early_warning_sent, breached, resolved_at)
           VALUES ($1, $2, $3, FALSE, FALSE, NULL)
           ON CONFLICT (task_id) DO UPDATE SET
               project_id = EXCLUDED.project_id,
               target_deadline = EXCLUDED.target_deadline
           RETURNING *""",
        int(task_id),
        int(project_id),
        target_deadline,
    )
    return TaskSLATracking.from_row(row) if row else None


async def resolve_task_sla(task_id: int) -> None:
    """Marks task SLA tracking as resolved when task is completed."""
    await db.execute(
        """UPDATE task_sla_tracking
           SET resolved_at = NOW()
           WHERE task_id = $1 AND resolved_at IS NULL""",
        int(task_id),
    )


async def check_sla_deadlines(bot: Any) -> list[dict[str, Any]]:
    """
    Checks active task SLA tracking:
    - 75% elapsed SLA: Early Warning alert.
    - 100% elapsed (deadline passed): Breach alert and breached flag.
    """
    now_utc = datetime.now(timezone.utc)
    query = """
        SELECT s.task_id, s.project_id, s.target_deadline, s.early_warning_sent, s.breached,
               t.task, t.priority, t.status, t.created_at, t.guild_id,
               p.name AS project_name, p.channel_id
        FROM task_sla_tracking s
        JOIN tasks t ON s.task_id = t.task_id
        LEFT JOIN projects p ON s.project_id = p.project_id
        WHERE s.resolved_at IS NULL AND t.status != 'Completed'
    """
    rows = await db.fetchall(query)
    alerts: list[dict[str, Any]] = []

    for r in rows:
        task_id = int(r["task_id"])
        target_dl = r["target_deadline"]
        if target_dl.tzinfo is None:
            target_dl = target_dl.replace(tzinfo=timezone.utc)

        created_at = r["created_at"]
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        total_sec = max(1.0, (target_dl - created_at).total_seconds())
        elapsed_sec = (now_utc - created_at).total_seconds()
        pct = max(0.0, min(100.0, (elapsed_sec / total_sec) * 100.0))
        remaining_sec = (target_dl - now_utc).total_seconds()

        channel_id = r.get("channel_id")
        task_title = r.get("task") or "Untitled"
        prio = int(r.get("priority", 0))
        proj_name = r.get("project_name") or "Project"
        early_sent = bool(r.get("early_warning_sent", False))
        is_breached = bool(r.get("breached", False))

        # 1. Breach check
        if remaining_sec <= 0 and not is_breached:
            await db.execute(
                "UPDATE task_sla_tracking SET breached = TRUE WHERE task_id = $1",
                task_id,
            )
            if bot and channel_id:
                try:
                    ch = bot.get_channel(int(channel_id))
                    if ch:
                        embed = discord.Embed(
                            title="🚨 [SLA BREACH ALERT] Target Deadline Missed!",
                            description=(
                                f"**Task #{task_id}:** {task_title}\n"
                                f"**Project:** {proj_name} | **Priority:** P{prio}\n"
                                f"**Target SLA:** {target_dl.strftime('%Y-%m-%d %H:%M UTC')}\n"
                                f"**Status:** 💥 ผิดข้อตกลง SLA (Breached)\n\n"
                                f"{render_sla_progress_bar(100.0)}\n"
                                f"กรุณาตรวจสอบและเร่งดำเนินการส่งมอบโดยด่วนที่สุด!"
                            ),
                            color=discord.Color.red(),
                        )
                        await ch.send(embed=embed)
                except Exception as e:
                    log.warning("Failed sending SLA breach alert: %s", e)

            alerts.append({"task_id": task_id, "type": "breach", "pct": 100.0})

        # 2. 75% Early Warning check
        elif pct >= 75.0 and not early_sent and not is_breached:
            await db.execute(
                "UPDATE task_sla_tracking SET early_warning_sent = TRUE WHERE task_id = $1",
                task_id,
            )
            if bot and channel_id:
                try:
                    ch = bot.get_channel(int(channel_id))
                    if ch:
                        embed = discord.Embed(
                            title="⏳ [SLA Early Warning] 75% of Allowed Time Consumed",
                            description=(
                                f"**Task #{task_id}:** {task_title}\n"
                                f"**Project:** {proj_name} | **Priority:** P{prio}\n"
                                f"**Target SLA:** {target_dl.strftime('%Y-%m-%d %H:%M UTC')}\n"
                                f"**Timeline:** {render_sla_progress_bar(pct)}\n\n"
                                f"เหลือเวลาอีกประมาณ {max(0, int(remaining_sec // 60))} นาที ก่อนผิดข้อตกลง SLA!"
                            ),
                            color=discord.Color.orange(),
                        )
                        await ch.send(embed=embed)
                except Exception as e:
                    log.warning("Failed sending SLA warning alert: %s", e)

            alerts.append({"task_id": task_id, "type": "warning", "pct": pct})

    return alerts


async def get_sla_status(project_id: int) -> dict[str, Any]:
    """Retrieves SLA compliance overview and active tracked tasks for a project."""
    policy = await get_project_sla_policy(project_id)
    query = """
        SELECT s.task_id, s.target_deadline, s.early_warning_sent, s.breached, s.resolved_at,
               t.task, t.priority, t.status, t.created_at, t.owner_id
        FROM task_sla_tracking s
        JOIN tasks t ON s.task_id = t.task_id
        WHERE s.project_id = $1
        ORDER BY s.breached DESC, s.target_deadline ASC
    """
    rows = await db.fetchall(query, int(project_id))
    total = len(rows)
    breached_count = sum(1 for r in rows if r.get("breached"))
    resolved_count = sum(1 for r in rows if r.get("resolved_at"))
    active_count = sum(1 for r in rows if not r.get("resolved_at"))

    return {
        "policy": policy,
        "total_tasks": total,
        "active_tasks": active_count,
        "resolved_tasks": resolved_count,
        "breached_tasks": breached_count,
        "compliance_rate": ((total - breached_count) / total * 100.0) if total > 0 else 100.0,
        "tasks": rows,
    }


async def get_sla_breaches(guild_id: str, project_id: Optional[int] = None) -> list[dict[str, Any]]:
    """Retrieves all breached SLA tasks for a guild or specific project."""
    query = """
        SELECT s.task_id, s.target_deadline, s.breached, s.resolved_at,
               t.task, t.priority, t.status, t.owner_id, t.created_at,
               p.project_id, p.name AS project_name
        FROM task_sla_tracking s
        JOIN tasks t ON s.task_id = t.task_id
        JOIN projects p ON s.project_id = p.project_id
        WHERE s.breached = TRUE AND p.guild_id = $1
    """
    params: list[Any] = [str(guild_id)]
    if project_id:
        query += " AND s.project_id = $2"
        params.append(int(project_id))

    query += " ORDER BY s.target_deadline DESC"
    return await db.fetchall(query, *params)


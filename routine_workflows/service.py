"""Service layer for Task Templates, Definition of Done checklists, and Routine workflows."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pytz

from core.database import db
from routine_workflows.models import (
    ChecklistItem,
    RoutineEventRule,
    TaskTemplate,
)

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Built-in Standard Templates
# ─────────────────────────────────────────────────────────────────────────────

BUILT_IN_TEMPLATES: dict[str, dict[str, Any]] = {
    "onboarding": {
        "name": "onboarding",
        "description": "Onboarding สมาชิกใหม่พร้อมชุดข้อปฏิบัติและงานเริ่มต้น",
        "category": "Onboarding",
        "priority": 3,
        "items": {
            "task": "Onboarding สมาชิกใหม่",
            "category": "Onboarding",
            "priority": 3,
            "description": "ขั้นตอนต้อนรับและปฐมนิเทศสมาชิกใหม่",
            "relative_days": 3,
            "checklists": [
                "แนะนำตัวในห้องแชท",
                "อ่านกฎระเบียบเซิร์ฟเวอร์",
                "ยืนยันตัวตนกับทีมงาน",
            ],
            "subtasks": [
                {
                    "task": "แนะนำตัวในห้องแชท",
                    "priority": 2,
                    "relative_days": 1,
                    "description": "ส่งข้อความแนะนำตัวและทักทายเพื่อนสมาชิก",
                    "checklists": ["แจ้งชื่อเล่น", "แจ้งความสนใจ"],
                },
                {
                    "task": "อ่านกฎระเบียบเซิร์ฟเวอร์",
                    "priority": 3,
                    "relative_days": 1,
                    "description": "ทำความเข้าใจกฎกติกาการใช้งานเซิร์ฟเวอร์",
                },
                {
                    "task": "ตั้งค่าโปรไฟล์และแจ้งข้อมูลติดต่อ",
                    "priority": 2,
                    "relative_days": 2,
                    "description": "ใส่รูปโปรไฟล์และตั้งค่า Discord ให้พร้อมใช้งาน",
                },
                {
                    "task": "นัดหมายปฐมนิเทศ",
                    "priority": 4,
                    "relative_days": 3,
                    "description": "เข้าร่วม Voice Channel เพื่อรับฟังการปฐมนิเทศ",
                },
            ],
        },
    },
    "monthly_event": {
        "name": "monthly_event",
        "description": "เตรียมจัดกิจกรรมประจำเดือนและอีเวนต์สำคัญ",
        "category": "Event",
        "priority": 3,
        "items": {
            "task": "เตรียมจัดกิจกรรมประจำเดือน",
            "category": "Event",
            "priority": 3,
            "description": "แผนการเตรียมกิจกรรมและประชาสัมพันธ์ประจำเดือน",
            "relative_days": 10,
            "checklists": [
                "ประชุมทีมงานสรุปธีมและกติกา",
                "โปสเตอร์และโพสต์โปรโมตพร้อม",
                "งบประมาณและของรางวัลได้รับการอนุมัติ",
            ],
            "subtasks": [
                {
                    "task": "ประชุมวางธีมงานและกิจกรรม",
                    "priority": 3,
                    "relative_days": 2,
                    "description": "สรุปรูปแบบกิจกรรม วันเวลา และผู้รับผิดชอบ",
                },
                {
                    "task": "ออกแบบโปสเตอร์และประชาสัมพันธ์",
                    "priority": 2,
                    "relative_days": 5,
                    "description": "จัดทำภาพและข้อความโปรโมตลงห้องประกาศ",
                },
                {
                    "task": "เตรียมงบประมาณและของรางวัล",
                    "priority": 4,
                    "relative_days": 7,
                    "description": "ตรวจสอบของรางวัลและยอดงบที่ต้องใช้",
                },
                {
                    "task": "ซ้อมรันคิวและทดสอบระบบ Discord",
                    "priority": 3,
                    "relative_days": 10,
                    "description": "ทดสอบบอท สิทธิ์ห้อง และลำดับการดำเนินงาน",
                },
            ],
        },
    },
    "client_delivery": {
        "name": "client_delivery",
        "description": "Checklist ส่งมอบงานลูกค้าและการตรวจรับ",
        "category": "Delivery",
        "priority": 4,
        "items": {
            "task": "Checklist ส่งมอบงานลูกค้า",
            "category": "Delivery",
            "priority": 4,
            "description": "กระบวนการตรวจสอบคุณภาพก่อนส่งมอบงานให้ลูกค้า",
            "relative_days": 4,
            "checklists": [
                "QA & Unit Test ผ่าน 100%",
                "คู่มือการใช้งานและเอกสารครบถ้วน",
                "ลูกค้าทดสอบและ Sign-off เรียบร้อย",
            ],
            "subtasks": [
                {
                    "task": "QA & Unit Test ตรวจสอบระบบ",
                    "priority": 4,
                    "relative_days": 1,
                    "description": "รันชุดทดสอบอัตโนมัติและตรวจเช็คฟังก์ชันหลัก",
                },
                {
                    "task": "จัดทำเอกสารคู่มือส่งมอบ",
                    "priority": 2,
                    "relative_days": 2,
                    "description": "รวบรวม Release Note และขั้นตอนการติดตั้ง",
                },
                {
                    "task": "Deploy ขึ้น Production Server",
                    "priority": 5,
                    "relative_days": 3,
                    "description": "ขึ้นระบบและตรวจสอบความเสถียรบนสภาพแวดล้อมจริง",
                },
                {
                    "task": "นัดประชุม Demo งานและส่งมอบ",
                    "priority": 3,
                    "relative_days": 4,
                    "description": "สาธิตการใช้งานและตอบข้อซักถามลูกค้า",
                },
            ],
        },
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# 1. Template Queries & Management
# ─────────────────────────────────────────────────────────────────────────────

def _row_to_template(row: Any) -> TaskTemplate:
    raw_items = row["items"]
    if isinstance(raw_items, str):
        try:
            items_dict = json.loads(raw_items)
        except Exception:
            items_dict = {}
    elif isinstance(raw_items, dict):
        items_dict = raw_items
    else:
        items_dict = {}

    return TaskTemplate(
        template_id=row.get("template_id"),
        name=row["name"],
        description=row.get("description"),
        category=row.get("category"),
        priority=int(row.get("priority") or 0),
        owner_id=row.get("owner_id"),
        guild_id=row.get("guild_id"),
        items=items_dict,
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


async def get_template(
    name: str,
    owner_id: Optional[str] = None,
    guild_id: Optional[str] = None,
) -> Optional[TaskTemplate]:
    """Retrieve template by name, matching personal, guild-level, or built-in standard."""
    cleaned_name = name.strip().lower()

    # 1. Query database for user's personal template or server's template
    if owner_id and guild_id:
        row = await db.afetchone(
            """SELECT * FROM task_templates
               WHERE LOWER(name)=$1 AND (owner_id=$2 OR guild_id=$3)
               ORDER BY (owner_id=$2) DESC LIMIT 1""",
            (cleaned_name, owner_id, guild_id),
        )
    elif owner_id:
        row = await db.afetchone(
            """SELECT * FROM task_templates
               WHERE LOWER(name)=$1 AND owner_id=$2 LIMIT 1""",
            (cleaned_name, owner_id),
        )
    elif guild_id:
        row = await db.afetchone(
            """SELECT * FROM task_templates
               WHERE LOWER(name)=$1 AND guild_id=$2 LIMIT 1""",
            (cleaned_name, guild_id),
        )
    else:
        row = None

    if row:
        return _row_to_template(row)

    # 2. Check built-in templates
    if cleaned_name in BUILT_IN_TEMPLATES:
        b = BUILT_IN_TEMPLATES[cleaned_name]
        return TaskTemplate(
            template_id=None,
            name=b["name"],
            description=b["description"],
            category=b["category"],
            priority=b["priority"],
            owner_id=None,
            guild_id=None,
            items=b["items"],
        )

    return None


async def list_templates(
    owner_id: Optional[str] = None,
    guild_id: Optional[str] = None,
) -> list[TaskTemplate]:
    """Return all templates accessible to the user (built-in + personal + server)."""
    templates: list[TaskTemplate] = []

    # 1. Add built-in templates
    for b in BUILT_IN_TEMPLATES.values():
        templates.append(
            TaskTemplate(
                template_id=None,
                name=b["name"],
                description=b["description"],
                category=b["category"],
                priority=b["priority"],
                owner_id=None,
                guild_id=None,
                items=b["items"],
            )
        )

    # 2. Add custom templates from DB
    if owner_id and guild_id:
        rows = await db.afetchall(
            """SELECT * FROM task_templates
               WHERE owner_id=$1 OR guild_id=$2
               ORDER BY name ASC""",
            (owner_id, guild_id),
        )
    elif owner_id:
        rows = await db.afetchall(
            "SELECT * FROM task_templates WHERE owner_id=$1 ORDER BY name ASC",
            (owner_id,),
        )
    elif guild_id:
        rows = await db.afetchall(
            "SELECT * FROM task_templates WHERE guild_id=$1 ORDER BY name ASC",
            (guild_id,),
        )
    else:
        rows = []

    for r in rows:
        templates.append(_row_to_template(r))

    return templates


async def create_custom_template(
    name: str,
    items: dict[str, Any],
    owner_id: str,
    guild_id: Optional[str] = None,
    description: Optional[str] = None,
    category: Optional[str] = None,
    priority: int = 0,
) -> TaskTemplate:
    """Create a new custom template in database."""
    cleaned_name = name.strip()
    priority = max(0, min(7, int(priority)))
    json_str = json.dumps(items, ensure_ascii=False)

    row = await db.afetchone(
        """INSERT INTO task_templates
           (name, description, category, priority, owner_id, guild_id, items, updated_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, NOW())
           ON CONFLICT (COALESCE(owner_id, ''), COALESCE(guild_id, ''), LOWER(name))
           DO UPDATE SET
               description=EXCLUDED.description,
               category=EXCLUDED.category,
               priority=EXCLUDED.priority,
               items=EXCLUDED.items,
               updated_at=NOW()
           RETURNING *""",
        (cleaned_name, description, category, priority, owner_id, guild_id, json_str),
    )
    db.query_cache.invalidate_tables(["task_templates"])
    return _row_to_template(row)


async def delete_custom_template(
    name: str,
    owner_id: str,
    is_admin: bool = False,
    guild_id: Optional[str] = None,
) -> bool:
    """Delete a custom template if user is the owner or server admin."""
    cleaned_name = name.strip().lower()
    if is_admin and guild_id:
        res = await db.aexecute(
            """DELETE FROM task_templates
               WHERE LOWER(name)=$1 AND (owner_id=$2 OR guild_id=$3)""",
            (cleaned_name, owner_id, guild_id),
        )
    else:
        res = await db.aexecute(
            "DELETE FROM task_templates WHERE LOWER(name)=$1 AND owner_id=$2",
            (cleaned_name, owner_id),
        )
    db.query_cache.invalidate_tables(["task_templates"])
    return not res.endswith(" 0")


async def create_template_from_task(
    task_id: int,
    name: str,
    owner_id: str,
    guild_id: Optional[str] = None,
) -> Optional[TaskTemplate]:
    """Generate a template from an existing task (including its subtasks and checklists)."""
    parent = await db.afetchone("SELECT * FROM tasks WHERE task_id=$1", (task_id,))
    if not parent:
        return None

    # Fetch DoD checklists of parent
    parent_checklists = await get_checklists(task_id)
    checklist_titles = [c.title for c in parent_checklists]

    # Fetch subtasks
    sub_rows = await db.afetchall(
        "SELECT * FROM tasks WHERE parent_task_id=$1 ORDER BY task_id ASC",
        (task_id,),
    )
    subtasks_data: list[dict[str, Any]] = []
    base_time = parent["created_at"] or datetime.now(timezone.utc)

    for s in sub_rows:
        s_checklists = await get_checklists(s["task_id"])
        # compute relative days offset if subtask has a deadline
        rel_days = 1
        if s.get("deadline") and parent.get("deadline"):
            try:
                s_dl = s["deadline"] if isinstance(s["deadline"], datetime) else datetime.fromisoformat(s["deadline"])
                p_dl = parent["deadline"] if isinstance(parent["deadline"], datetime) else datetime.fromisoformat(parent["deadline"])
                diff = (s_dl - p_dl).days
                rel_days = max(1, diff) if diff > 0 else 1
            except Exception:
                rel_days = 1

        subtasks_data.append({
            "task": s["task"],
            "priority": int(s.get("priority") or 0),
            "relative_days": rel_days,
            "description": s.get("description"),
            "checklists": [c.title for c in s_checklists],
        })

    items = {
        "task": parent["task"],
        "category": parent.get("tags"),
        "priority": int(parent.get("priority") or 0),
        "description": parent.get("description"),
        "relative_days": 3,
        "checklists": checklist_titles,
        "subtasks": subtasks_data,
    }

    return await create_custom_template(
        name=name,
        items=items,
        owner_id=owner_id,
        guild_id=guild_id,
        description=f"Template created from Task #{task_id}",
        category=parent.get("tags"),
        priority=int(parent.get("priority") or 0),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Applying Templates (Creating Task + Subtasks + DoD Checklists)
# ─────────────────────────────────────────────────────────────────────────────

async def apply_template(
    template_name: str,
    user_id: str,
    guild_id: Optional[str] = None,
    project_id: Optional[int] = None,
    tz_name: str = "UTC",
) -> dict[str, Any]:
    """
    Instantiate a template for a user:
    - Calculates relative deadlines according to tz_name.
    - Inserts parent task, subtasks, and checklists in a single atomic transaction.
    - Returns summary dict with parent task ID and counts.
    """
    tmpl = await get_template(template_name, owner_id=user_id, guild_id=guild_id)
    if not tmpl:
        raise ValueError(f"Template '{template_name}' not found.")

    try:
        user_tz = pytz.timezone(tz_name)
    except Exception:
        user_tz = pytz.utc
    now_local = datetime.now(user_tz)

    items = tmpl.items or {}
    parent_title = items.get("task") or tmpl.name
    parent_priority = max(0, min(7, int(items.get("priority", tmpl.priority or 0))))
    parent_desc = items.get("description") or tmpl.description
    parent_tags = items.get("category") or tmpl.category
    parent_rel_days = int(items.get("relative_days", 3))

    parent_deadline_dt = now_local + timedelta(days=parent_rel_days)
    parent_deadline_iso = parent_deadline_dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    parent_checklists: list[str] = items.get("checklists") or []
    subtasks: list[dict[str, Any]] = items.get("subtasks") or []

    created_subtasks_count = 0
    created_checklists_count = 0

    async with db.acquire() as conn:
        async with conn.transaction():
            # 1. Insert parent task
            p_row = await conn.fetchrow(
                """INSERT INTO tasks
                   (task, deadline, priority, status, description, tags,
                    owner_id, guild_id, project_id, created_at, updated_at)
                   VALUES ($1, $2::timestamp, $3, 'Pending', $4, $5, $6, $7, $8, NOW(), NOW())
                   RETURNING task_id""",
                parent_title,
                parent_deadline_iso,
                parent_priority,
                parent_desc,
                parent_tags,
                user_id,
                guild_id,
                project_id,
            )
            parent_task_id = p_row["task_id"]

            # 2. Insert parent DoD checklists
            for pos, chk_title in enumerate(parent_checklists):
                chk_clean = str(chk_title).strip()
                if chk_clean:
                    await conn.execute(
                        """INSERT INTO task_checklists (task_id, title, is_done, position)
                           VALUES ($1, $2, FALSE, $3)""",
                        parent_task_id,
                        chk_clean,
                        pos,
                    )
                    created_checklists_count += 1

            # 3. Insert subtasks
            for s in subtasks:
                s_title = s.get("task", "Subtask").strip()
                s_prio = max(0, min(7, int(s.get("priority", parent_priority))))
                s_desc = s.get("description")
                s_rel_days = int(s.get("relative_days", 1))
                s_dl_dt = now_local + timedelta(days=s_rel_days)
                s_dl_iso = s_dl_dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

                s_row = await conn.fetchrow(
                    """INSERT INTO tasks
                       (task, deadline, priority, status, description, tags,
                        owner_id, guild_id, project_id, parent_task_id, created_at, updated_at)
                       VALUES ($1, $2::timestamp, $3, 'Pending', $4, $5, $6, $7, $8, $9, NOW(), NOW())
                       RETURNING task_id""",
                    s_title,
                    s_dl_iso,
                    s_prio,
                    s_desc,
                    parent_tags,
                    user_id,
                    guild_id,
                    project_id,
                    parent_task_id,
                )
                sub_task_id = s_row["task_id"]
                created_subtasks_count += 1

                # Subtask DoD checklists
                s_chks: list[str] = s.get("checklists") or []
                for s_pos, s_chk_title in enumerate(s_chks):
                    s_chk_clean = str(s_chk_title).strip()
                    if s_chk_clean:
                        await conn.execute(
                            """INSERT INTO task_checklists (task_id, title, is_done, position)
                               VALUES ($1, $2, FALSE, $3)""",
                            sub_task_id,
                            s_chk_clean,
                            s_pos,
                        )
                        created_checklists_count += 1

    db.invalidate_stats(user_id)
    db.query_cache.invalidate_tables(["tasks", "task_checklists"])
    await db.alog_action(user_id, "template_used", str(parent_task_id), f"template={tmpl.name}")

    return {
        "parent_task_id": parent_task_id,
        "task_name": parent_title,
        "subtask_count": created_subtasks_count,
        "checklist_count": created_checklists_count,
        "deadline_iso": parent_deadline_iso,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. Definition of Done (Task Checklist) Management
# ─────────────────────────────────────────────────────────────────────────────

async def get_checklists(task_id: int) -> list[ChecklistItem]:
    """Fetch all checklist items for a given task, ordered by position."""
    rows = await db.afetchall(
        """SELECT checklist_id, task_id, title, is_done, position, created_at, completed_at
           FROM task_checklists
           WHERE task_id=$1
           ORDER BY position ASC, checklist_id ASC""",
        (task_id,),
    )
    return [
        ChecklistItem(
            checklist_id=r["checklist_id"],
            task_id=r["task_id"],
            title=r["title"],
            is_done=bool(r["is_done"]),
            position=r["position"],
            created_at=r.get("created_at"),
            completed_at=r.get("completed_at"),
        )
        for r in rows
    ]


async def get_pending_checklists(task_id: int) -> list[ChecklistItem]:
    """Fetch all uncompleted (pending) checklist items for a given task."""
    rows = await db.afetchall(
        """SELECT checklist_id, task_id, title, is_done, position, created_at, completed_at
           FROM task_checklists
           WHERE task_id=$1 AND is_done=FALSE
           ORDER BY position ASC, checklist_id ASC""",
        (task_id,),
    )
    return [
        ChecklistItem(
            checklist_id=r["checklist_id"],
            task_id=r["task_id"],
            title=r["title"],
            is_done=False,
            position=r["position"],
            created_at=r.get("created_at"),
            completed_at=r.get("completed_at"),
        )
        for r in rows
    ]


async def get_pending_checklist_count(task_id: int) -> int:
    """Return count of uncompleted checklist items for a given task."""
    row = await db.afetchone(
        "SELECT COUNT(*) AS c FROM task_checklists WHERE task_id=$1 AND is_done=FALSE",
        (task_id,),
    )
    return int(row["c"] or 0) if row else 0


async def add_checklist_item(task_id: int, title: str) -> Optional[ChecklistItem]:
    """Add a new checklist item to a task."""
    cleaned = title.strip()
    if not cleaned:
        return None

    # Get max position
    pos_row = await db.afetchone(
        "SELECT COALESCE(MAX(position), -1) AS max_pos FROM task_checklists WHERE task_id=$1",
        (task_id,),
    )
    new_pos = int(pos_row["max_pos"] or -1) + 1 if pos_row else 0

    row = await db.afetchone(
        """INSERT INTO task_checklists (task_id, title, is_done, position)
           VALUES ($1, $2, FALSE, $3)
           RETURNING checklist_id, task_id, title, is_done, position, created_at, completed_at""",
        (task_id, cleaned, new_pos),
    )
    db.query_cache.invalidate_tables(["task_checklists"])
    return ChecklistItem(
        checklist_id=row["checklist_id"],
        task_id=row["task_id"],
        title=row["title"],
        is_done=False,
        position=row["position"],
        created_at=row.get("created_at"),
        completed_at=row.get("completed_at"),
    )


async def toggle_checklist_item(checklist_id: int, user_id: str) -> Optional[tuple[ChecklistItem, int]]:
    """Toggle a checklist item between done and undone. Returns (item, pending_count)."""
    curr = await db.afetchone(
        "SELECT task_id, is_done FROM task_checklists WHERE checklist_id=$1",
        (checklist_id,),
    )
    if not curr:
        return None

    new_done = not bool(curr["is_done"])
    task_id = curr["task_id"]

    row = await db.afetchone(
        """UPDATE task_checklists
           SET is_done=$1, completed_at=(CASE WHEN $1 THEN NOW() ELSE NULL END)
           WHERE checklist_id=$2
           RETURNING checklist_id, task_id, title, is_done, position, created_at, completed_at""",
        (new_done, checklist_id),
    )
    db.query_cache.invalidate_tables(["task_checklists"])
    await db.alog_action(
        user_id,
        "checklist_toggled",
        str(task_id),
        f"checklist_id={checklist_id},is_done={new_done}",
    )
    pending_count = await get_pending_checklist_count(task_id)
    item = ChecklistItem(
        checklist_id=row["checklist_id"],
        task_id=row["task_id"],
        title=row["title"],
        is_done=bool(row["is_done"]),
        position=row["position"],
        created_at=row.get("created_at"),
        completed_at=row.get("completed_at"),
    )
    return item, pending_count


async def delete_checklist_item(checklist_id: int) -> bool:
    """Delete a checklist item."""
    res = await db.aexecute("DELETE FROM task_checklists WHERE checklist_id=$1", (checklist_id,))
    db.query_cache.invalidate_tables(["task_checklists"])
    return not res.endswith(" 0")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Event-Driven Auto-Tasks (Routine Rules)
# ─────────────────────────────────────────────────────────────────────────────

async def add_routine_rule(
    guild_id: str,
    event_type: str,
    template_name: str,
    created_by: str,
    trigger_role_id: Optional[int] = None,
) -> RoutineEventRule:
    """Register an event-driven automation rule for a guild."""
    if event_type not in ("role_added", "member_join"):
        raise ValueError("Invalid event_type. Must be 'role_added' or 'member_join'.")

    row = await db.afetchone(
        """INSERT INTO routine_event_rules
           (guild_id, event_type, trigger_role_id, template_name, is_active, created_by)
           VALUES ($1, $2, $3, $4, TRUE, $5)
           RETURNING *""",
        (str(guild_id), event_type, trigger_role_id, template_name.strip().lower(), str(created_by)),
    )
    db.query_cache.invalidate_tables(["routine_event_rules"])
    return RoutineEventRule(
        rule_id=row["rule_id"],
        guild_id=row["guild_id"],
        event_type=row["event_type"],
        trigger_role_id=row.get("trigger_role_id"),
        template_name=row["template_name"],
        is_active=bool(row["is_active"]),
        created_by=row["created_by"],
        created_at=row.get("created_at"),
    )


async def get_routine_rules(guild_id: str) -> list[RoutineEventRule]:
    """Fetch all routine event rules configured for a guild."""
    rows = await db.afetchall(
        "SELECT * FROM routine_event_rules WHERE guild_id=$1 ORDER BY rule_id ASC",
        (str(guild_id),),
    )
    return [
        RoutineEventRule(
            rule_id=r["rule_id"],
            guild_id=r["guild_id"],
            event_type=r["event_type"],
            trigger_role_id=r.get("trigger_role_id"),
            template_name=r["template_name"],
            is_active=bool(r["is_active"]),
            created_by=r["created_by"],
            created_at=r.get("created_at"),
        )
        for r in rows
    ]


async def get_matching_rules(
    guild_id: str,
    event_type: str,
    role_id: Optional[int] = None,
) -> list[RoutineEventRule]:
    """Find active routine rules that match an event trigger."""
    if event_type == "role_added" and role_id:
        rows = await db.afetchall(
            """SELECT * FROM routine_event_rules
               WHERE guild_id=$1 AND event_type='role_added'
                 AND trigger_role_id=$2 AND is_active=TRUE""",
            (str(guild_id), role_id),
        )
    elif event_type == "member_join":
        rows = await db.afetchall(
            """SELECT * FROM routine_event_rules
               WHERE guild_id=$1 AND event_type='member_join' AND is_active=TRUE""",
            (str(guild_id),),
        )
    else:
        rows = []

    return [
        RoutineEventRule(
            rule_id=r["rule_id"],
            guild_id=r["guild_id"],
            event_type=r["event_type"],
            trigger_role_id=r.get("trigger_role_id"),
            template_name=r["template_name"],
            is_active=bool(r["is_active"]),
            created_by=r["created_by"],
            created_at=r.get("created_at"),
        )
        for r in rows
    ]


async def delete_routine_rule(rule_id: int, guild_id: str) -> bool:
    """Delete a routine rule."""
    res = await db.aexecute(
        "DELETE FROM routine_event_rules WHERE rule_id=$1 AND guild_id=$2",
        (rule_id, str(guild_id)),
    )
    db.query_cache.invalidate_tables(["routine_event_rules"])
    return not res.endswith(" 0")

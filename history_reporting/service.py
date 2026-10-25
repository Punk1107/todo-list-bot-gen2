"""
history_reporting/service.py — Core logic for Audit History, Offline HTML Export & Weekly Retrospective
"""
from __future__ import annotations

import html
import io
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import pytz
import discord
from discord.ext import commands

from core.database import db
from history_reporting.models import TaskAuditEvent, TaskAuditHistory, WeeklyRetrospectiveData
from locales.i18n import t
from utils.helpers import (
    format_deadline,
    get_user_lang,
    get_user_theme,
    get_user_timezone,
    progress_bar,
    time_left_str,
)

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Task Audit Trail & Activity History
# ─────────────────────────────────────────────────────────────────────────────

async def get_task_audit_history(
    task_id: int,
    user_id: str,
    is_guild_admin: bool = False,
) -> Optional[TaskAuditHistory]:
    """
    Retrieve full audit history for a task.
    Enforces privacy: only owner, authorized project member, or guild admin can view.
    """
    row = await db.afetchone(
        """SELECT t.task_id, t.task, t.owner_id, t.status, t.priority, t.deadline,
                  t.is_deleted, t.created_at, t.project_id, t.guild_id,
                  c.name AS category_name
           FROM tasks t
           LEFT JOIN categories c ON t.category_id = c.category_id
           WHERE t.task_id = $1""",
        (task_id,),
    )
    if not row:
        return None

    task_owner = str(row["owner_id"])
    t_proj_id = row.get("project_id")
    t_guild_id = row.get("guild_id")

    # Permission verification
    if t_proj_id and t_guild_id:
        if not is_guild_admin and task_owner != user_id:
            try:
                from collaboration import service as collab_service
                can_view = await collab_service.check_project_permission(
                    int(t_proj_id), user_id, "can_view_tasks", is_guild_admin=is_guild_admin
                )
                if not can_view:
                    proj = await collab_service.get_project(int(t_proj_id), str(t_guild_id))
                    if proj.owner_id != user_id:
                        role = await collab_service.get_member_role(int(t_proj_id), user_id)
                        if not role:
                            return None
            except Exception as exc:
                log.warning("Project permission check failed for task history %d: %s", task_id, exc)
                return None
    else:
        if task_owner != user_id and not is_guild_admin:
            return None

    # Fetch audit log records for this task (using migration 26 index idx_audit_target_created)
    audit_rows = await db.afetchall(
        """SELECT log_id, user_id, action, target_id, detail, created_at
           FROM audit_log
           WHERE target_id = $1
           ORDER BY created_at DESC""",
        (str(task_id),),
    )

    events: List[TaskAuditEvent] = []
    for r in (audit_rows or []):
        created_dt = r["created_at"]
        if isinstance(created_dt, str):
            try:
                created_dt = datetime.fromisoformat(created_dt)
            except Exception:
                created_dt = datetime.now(timezone.utc)
        events.append(
            TaskAuditEvent(
                log_id=r["log_id"],
                user_id=str(r["user_id"]),
                action=r["action"],
                target_id=r.get("target_id"),
                detail=r.get("detail"),
                created_at=created_dt,
            )
        )

    snooze_count = sum(1 for e in events if e.action == "task_snoozed")

    # Creator lookup from creation event, falling back to owner_id
    creator_id = task_owner
    created_at_dt = row.get("created_at")
    for e in reversed(events):
        if e.action == "task_created":
            creator_id = e.user_id
            created_at_dt = e.created_at
            break

    if isinstance(created_at_dt, str):
        try:
            created_at_dt = datetime.fromisoformat(created_at_dt)
        except Exception:
            created_at_dt = None

    deadline_dt = row.get("deadline")
    if isinstance(deadline_dt, str):
        try:
            deadline_dt = datetime.fromisoformat(deadline_dt)
        except Exception:
            deadline_dt = None

    return TaskAuditHistory(
        task_id=row["task_id"],
        task_name=row["task"],
        owner_id=task_owner,
        created_at=created_at_dt,
        snooze_count=snooze_count,
        events=events,
        current_status=row.get("status", "pending"),
        current_priority=row.get("priority", 1),
        current_deadline=deadline_dt,
        category_name=row.get("category_name"),
        creator_id=creator_id,
        is_deleted=bool(row.get("is_deleted", False)),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Standalone Interactive HTML Export
# ─────────────────────────────────────────────────────────────────────────────

def generate_interactive_html(
    tasks: List[Dict[str, Any]],
    categories: List[Dict[str, Any]],
    user_id: str,
    tz_name: str = "UTC",
    lang: str = "th",
    theme: str = "dark",
) -> str:
    """
    Generate a 100% self-contained, offline-ready interactive HTML file.
    No CDN links, no external fonts or scripts. Complete with glassmorphism,
    interactive task checkboxes, live search & filtering, dynamic stats, and print stylesheet.
    """
    cat_map = {c["category_id"]: c for c in categories if "category_id" in c}

    total_count = len(tasks)
    completed_count = 0
    overdue_count = 0
    pending_count = 0

    now_utc = datetime.now(timezone.utc)
    try:
        user_tz = pytz.timezone(tz_name)
    except Exception:
        user_tz = pytz.utc

    tasks_data: List[Dict[str, Any]] = []
    for r in tasks:
        tid = r["task_id"]
        tname = str(r["task"] or "")
        tstatus = str(r.get("status") or "pending").lower()
        tpriority = 0 if r.get("priority") == 0 else int(r.get("priority") or 1)
        tdl_raw = r.get("deadline")
        tdesc = str(r.get("description") or "")
        ttags = str(r.get("tags") or "")
        tcat_id = r.get("category_id")
        tpinned = bool(r.get("is_pinned", False))

        is_completed = (tstatus == "completed")
        is_cancelled = (tstatus == "cancelled")
        if is_completed:
            completed_count += 1
        elif not is_cancelled:
            pending_count += 1

        is_overdue = False
        dl_display = "-"
        if tdl_raw:
            dt_obj = tdl_raw
            if isinstance(dt_obj, str):
                try:
                    dt_obj = datetime.fromisoformat(dt_obj)
                except Exception:
                    dt_obj = None
            if dt_obj:
                if dt_obj.tzinfo is None:
                    dt_obj = pytz.utc.localize(dt_obj)
                if not is_completed and dt_obj < now_utc:
                    is_overdue = True
                    overdue_count += 1
                dl_display = dt_obj.astimezone(user_tz).strftime("%d/%m/%Y %H:%M")

        cat_info = cat_map.get(tcat_id)
        cat_name = cat_info.get("name", "General") if cat_info else "General"
        cat_emoji = cat_info.get("emoji", "📝") if cat_info else "📝"
        cat_color = cat_info.get("color", "#6366f1") if cat_info else "#6366f1"

        tasks_data.append({
            "id": tid,
            "name": tname,
            "status": "completed" if is_completed else ("overdue" if is_overdue else "pending"),
            "priority": tpriority,
            "deadline": dl_display,
            "is_overdue": is_overdue,
            "category": cat_name,
            "cat_emoji": cat_emoji,
            "cat_color": cat_color,
            "description": tdesc,
            "tags": ttags,
            "pinned": tpinned,
        })

    completion_rate = round((completed_count / total_count * 100), 1) if total_count > 0 else 0.0

    # HTML Templates with pure Vanilla JS and CSS
    return f"""<!DOCTYPE html>
<html lang="{html.escape(lang)}" data-theme="{html.escape(theme)}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>To-Do List Bot &mdash; Interactive Task Report</title>
  <style>
    :root {{
      --bg: #0f172a;
      --card-bg: rgba(30, 41, 59, 0.75);
      --card-border: rgba(255, 255, 255, 0.1);
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --primary: #6366f1;
      --primary-hover: #4f46e5;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --accent: #8b5cf6;
      --shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3), 0 8px 10px -6px rgba(0, 0, 0, 0.2);
    }}
    [data-theme="light"] {{
      --bg: #f8fafc;
      --card-bg: rgba(255, 255, 255, 0.85);
      --card-border: rgba(0, 0, 0, 0.08);
      --text: #0f172a;
      --text-muted: #64748b;
      --primary: #4f46e5;
      --primary-hover: #4338ca;
      --success: #059669;
      --warning: #d97706;
      --danger: #dc2626;
      --accent: #7c3aed;
      --shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05), 0 8px 10px -6px rgba(0, 0, 0, 0.03);
    }}
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }}
    body {{
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      padding: 2rem 1rem;
      transition: background 0.3s ease, color 0.3s ease;
    }}
    .container {{
      max-width: 1024px;
      margin: 0 auto;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 2rem;
      padding-bottom: 1.5rem;
      border-bottom: 1px solid var(--card-border);
    }}
    .logo-group {{
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }}
    .logo-icon {{
      font-size: 2rem;
      background: linear-gradient(135deg, var(--primary), var(--accent));
      width: 48px;
      height: 48px;
      display: flex;
      align-items: center;
      justify-content: center;
      border-radius: 12px;
      box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
    }}
    h1 {{
      font-size: 1.6rem;
      font-weight: 700;
      letter-spacing: -0.02em;
    }}
    .header-sub {{
      font-size: 0.875rem;
      color: var(--text-muted);
    }}
    .theme-toggle {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      color: var(--text);
      padding: 0.5rem 1rem;
      border-radius: 20px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.875rem;
      box-shadow: var(--shadow);
      transition: all 0.2s;
    }}
    .theme-toggle:hover {{
      transform: translateY(-2px);
    }}
    /* Stats Bar */
    .stats-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 1rem;
      margin-bottom: 2rem;
    }}
    .stat-card {{
      background: var(--card-bg);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 1.25rem;
      box-shadow: var(--shadow);
      position: relative;
      overflow: hidden;
    }}
    .stat-label {{
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      margin-bottom: 0.25rem;
    }}
    .stat-value {{
      font-size: 1.75rem;
      font-weight: 700;
    }}
    .stat-card.primary .stat-value {{ color: var(--primary); }}
    .stat-card.success .stat-value {{ color: var(--success); }}
    .stat-card.warning .stat-value {{ color: var(--warning); }}
    .stat-card.danger .stat-value {{ color: var(--danger); }}
    /* Progress Bar */
    .progress-box {{
      background: var(--card-bg);
      backdrop-filter: blur(12px);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 1.25rem;
      margin-bottom: 2rem;
      box-shadow: var(--shadow);
    }}
    .progress-header {{
      display: flex;
      justify-content: space-between;
      margin-bottom: 0.5rem;
      font-size: 0.9rem;
      font-weight: 600;
    }}
    .progress-track {{
      background: rgba(148, 163, 184, 0.2);
      height: 10px;
      border-radius: 5px;
      overflow: hidden;
    }}
    .progress-fill {{
      height: 100%;
      background: linear-gradient(90deg, var(--primary), var(--success));
      width: {completion_rate}%;
      transition: width 0.4s ease;
      border-radius: 5px;
    }}
    /* Filters */
    .filter-panel {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem;
      align-items: center;
      margin-bottom: 1.5rem;
    }}
    .search-input {{
      flex: 1;
      min-width: 220px;
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      color: var(--text);
      padding: 0.6rem 1rem;
      border-radius: 12px;
      outline: none;
      font-size: 0.9rem;
      transition: border-color 0.2s;
    }}
    .search-input:focus {{
      border-color: var(--primary);
    }}
    .filter-chips {{
      display: flex;
      gap: 0.5rem;
      flex-wrap: wrap;
    }}
    .chip {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      color: var(--text-muted);
      padding: 0.45rem 0.9rem;
      border-radius: 20px;
      font-size: 0.8rem;
      cursor: pointer;
      user-select: none;
      transition: all 0.2s;
    }}
    .chip.active, .chip:hover {{
      background: var(--primary);
      color: #fff;
      border-color: var(--primary);
    }}
    .select-dropdown {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      color: var(--text);
      padding: 0.55rem 0.9rem;
      border-radius: 12px;
      font-size: 0.85rem;
      outline: none;
      cursor: pointer;
    }}
    /* Task List */
    .task-list {{
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
    }}
    .task-item {{
      background: var(--card-bg);
      backdrop-filter: blur(12px);
      border: 1px solid var(--card-border);
      border-radius: 14px;
      padding: 1rem 1.25rem;
      box-shadow: var(--shadow);
      display: flex;
      align-items: flex-start;
      gap: 1rem;
      transition: transform 0.2s, border-color 0.2s, opacity 0.2s;
    }}
    .task-item:hover {{
      transform: translateY(-2px);
      border-color: rgba(99, 102, 241, 0.4);
    }}
    .task-item.completed {{
      opacity: 0.65;
    }}
    .task-checkbox {{
      margin-top: 0.25rem;
      width: 20px;
      height: 20px;
      accent-color: var(--success);
      cursor: pointer;
      flex-shrink: 0;
    }}
    .task-content {{
      flex: 1;
    }}
    .task-title-line {{
      display: flex;
      align-items: center;
      gap: 0.5rem;
      margin-bottom: 0.35rem;
      flex-wrap: wrap;
    }}
    .task-title {{
      font-size: 1rem;
      font-weight: 600;
      transition: text-decoration 0.2s;
    }}
    .task-item.completed .task-title {{
      text-decoration: line-through;
      color: var(--text-muted);
    }}
    .badge {{
      font-size: 0.7rem;
      padding: 0.2rem 0.5rem;
      border-radius: 6px;
      font-weight: 600;
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
    }}
    .badge.prio-high {{ background: rgba(239, 68, 68, 0.15); color: #ef4444; }}
    .badge.prio-med {{ background: rgba(245, 158, 11, 0.15); color: #f59e0b; }}
    .badge.prio-low {{ background: rgba(59, 130, 246, 0.15); color: #3b82f6; }}
    .badge.overdue {{ background: rgba(239, 68, 68, 0.2); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.4); }}
    .badge.category {{ background: rgba(139, 92, 246, 0.15); color: var(--accent); }}
    .badge.pinned {{ background: rgba(245, 158, 11, 0.2); color: #f59e0b; }}
    .task-meta {{
      font-size: 0.8rem;
      color: var(--text-muted);
      display: flex;
      gap: 1rem;
      flex-wrap: wrap;
      margin-top: 0.25rem;
    }}
    .task-desc {{
      margin-top: 0.5rem;
      font-size: 0.85rem;
      color: var(--text-muted);
      line-height: 1.4;
      background: rgba(0, 0, 0, 0.1);
      padding: 0.5rem 0.75rem;
      border-radius: 8px;
    }}
    .empty-state {{
      text-align: center;
      padding: 3rem;
      color: var(--text-muted);
      font-size: 1rem;
    }}
    /* Print Styles */
    @media print {{
      body {{ background: #fff !important; color: #000 !important; padding: 0 !important; }}
      .theme-toggle, .filter-panel, .task-checkbox {{ display: none !important; }}
      .stat-card, .progress-box, .task-item {{ border: 1px solid #ddd !important; box-shadow: none !important; }}
      .task-title {{ color: #000 !important; }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="logo-group">
        <div class="logo-icon">📋</div>
        <div>
          <h1>To-Do List Bot &mdash; Task Report</h1>
          <div class="header-sub">User: {html.escape(user_id)} &bull; Timezone: {html.escape(tz_name)} &bull; {datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M")} UTC</div>
        </div>
      </div>
      <button class="theme-toggle" id="themeBtn" onclick="toggleTheme()">
        <span id="themeIcon">🌓</span> <span id="themeText">Toggle Theme</span>
      </button>
    </header>

    <!-- Stats Bar -->
    <div class="stats-grid">
      <div class="stat-card primary">
        <div class="stat-label">Total Tasks</div>
        <div class="stat-value" id="valTotal">{total_count}</div>
      </div>
      <div class="stat-card success">
        <div class="stat-label">Completed</div>
        <div class="stat-value" id="valCompleted">{completed_count}</div>
      </div>
      <div class="stat-card warning">
        <div class="stat-label">Pending</div>
        <div class="stat-value" id="valPending">{pending_count}</div>
      </div>
      <div class="stat-card danger">
        <div class="stat-label">Overdue</div>
        <div class="stat-value" id="valOverdue">{overdue_count}</div>
      </div>
    </div>

    <!-- Progress Track -->
    <div class="progress-box">
      <div class="progress-header">
        <span>Completion Progress</span>
        <span id="progressText">{completion_rate}%</span>
      </div>
      <div class="progress-track">
        <div class="progress-fill" id="progressFill" style="width: {completion_rate}%"></div>
      </div>
    </div>

    <!-- Filter Bar -->
    <div class="filter-panel">
      <input type="text" class="search-input" id="searchBox" placeholder="🔍 Search tasks by title, category, tags..." oninput="applyFilters()">
      <div class="filter-chips">
        <div class="chip active" data-status="all" onclick="setStatusFilter(this, 'all')">All</div>
        <div class="chip" data-status="pending" onclick="setStatusFilter(this, 'pending')">Pending</div>
        <div class="chip" data-status="completed" onclick="setStatusFilter(this, 'completed')">Completed</div>
        <div class="chip" data-status="overdue" onclick="setStatusFilter(this, 'overdue')">Overdue</div>
      </div>
      <select class="select-dropdown" id="prioSelect" onchange="applyFilters()">
        <option value="all">All Priorities</option>
        <option value="high">High Priority (P4-P7)</option>
        <option value="med">Medium Priority (P2-P3)</option>
        <option value="low">Low Priority (P0-P1)</option>
      </select>
    </div>

    <!-- Task List Container -->
    <div class="task-list" id="taskList">
""" + ("\n".join([
        f"""      <div class="task-item {'completed' if t['status'] == 'completed' else ''}"
           data-id="{t['id']}"
           data-status="{t['status']}"
           data-prio="{'high' if t['priority'] >= 4 else ('med' if t['priority'] >= 2 else 'low')}"
           data-overdue="{str(t['is_overdue']).lower()}"
           data-search="{html.escape((t['name'] + ' ' + t['category'] + ' ' + t['tags'] + ' ' + t['description']).lower())}">
        <input type="checkbox" class="task-checkbox" {'checked' if t['status'] == 'completed' else ''} onchange="toggleTask({t['id']}, this.checked)">
        <div class="task-content">
          <div class="task-title-line">
            {'<span class="badge pinned">📌 Pinned</span>' if t['pinned'] else ''}
            <span class="task-title">#{t['id']} {html.escape(t['name'])}</span>
            <span class="badge prio-{'high' if t['priority'] >= 4 else ('med' if t['priority'] >= 2 else 'low')}">P{t['priority']}</span>
            <span class="badge category">{html.escape(t['cat_emoji'])} {html.escape(t['category'])}</span>
            {'<span class="badge overdue">⚠️ Overdue</span>' if t['is_overdue'] and t['status'] != 'completed' else ''}
          </div>
          <div class="task-meta">
            <span>📅 Deadline: {html.escape(t['deadline'])}</span>
            {f'<span>🏷️ Tags: {html.escape(t["tags"])}</span>' if t['tags'] else ''}
          </div>
          {f'<div class="task-desc">{html.escape(t["description"])}</div>' if t['description'] else ''}
        </div>
      </div>""" for t in tasks_data
    ]) if tasks_data else """      <div class="empty-state">No tasks found.</div>""") + f"""
    </div>
  </div>

  <script>
    let currentStatus = 'all';

    function toggleTheme() {{
      const html = document.documentElement;
      const cur = html.getAttribute('data-theme');
      const next = cur === 'light' ? 'dark' : 'light';
      html.setAttribute('data-theme', next);
      localStorage.setItem('todo_theme', next);
    }}

    function setStatusFilter(chip, status) {{
      document.querySelectorAll('.filter-chips .chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      currentStatus = status;
      applyFilters();
    }}

    function applyFilters() {{
      const query = (document.getElementById('searchBox').value || '').trim().toLowerCase();
      const prio = document.getElementById('prioSelect').value;
      const items = document.querySelectorAll('.task-item');

      items.forEach(item => {{
        const searchTxt = item.getAttribute('data-search') || '';
        const status = item.getAttribute('data-status');
        const itemPrio = item.getAttribute('data-prio');
        const isOverdue = item.getAttribute('data-overdue') === 'true';

        let matchesSearch = !query || searchTxt.includes(query);
        let matchesStatus = true;
        if (currentStatus === 'completed') matchesStatus = (status === 'completed');
        else if (currentStatus === 'pending') matchesStatus = (status !== 'completed');
        else if (currentStatus === 'overdue') matchesStatus = (isOverdue && status !== 'completed');

        let matchesPrio = (prio === 'all' || itemPrio === prio);

        if (matchesSearch && matchesStatus && matchesPrio) {{
          item.style.display = 'flex';
        }} else {{
          item.style.display = 'none';
        }}
      }});
    }}

    function toggleTask(taskId, isChecked) {{
      const item = document.querySelector(`.task-item[data-id="${{taskId}}"]`);
      if (!item) return;

      if (isChecked) {{
        item.classList.add('completed');
        item.setAttribute('data-status', 'completed');
      }} else {{
        item.classList.remove('completed');
        const isOverdue = item.getAttribute('data-overdue') === 'true';
        item.setAttribute('data-status', isOverdue ? 'overdue' : 'pending');
      }}

      recalculateStats();
      applyFilters();
    }}

    function recalculateStats() {{
      const items = Array.from(document.querySelectorAll('.task-item'));
      const total = items.length;
      let completed = 0;
      let pending = 0;
      let overdue = 0;

      items.forEach(i => {{
        const isDone = i.classList.contains('completed');
        const isOd = i.getAttribute('data-overdue') === 'true';
        if (isDone) completed++;
        else {{
          pending++;
          if (isOd) overdue++;
        }}
      }});

      document.getElementById('valTotal').innerText = total;
      document.getElementById('valCompleted').innerText = completed;
      document.getElementById('valPending').innerText = pending;
      document.getElementById('valOverdue').innerText = overdue;

      const rate = total > 0 ? Math.round((completed / total) * 1000) / 10 : 0;
      document.getElementById('progressText').innerText = rate + '%';
      document.getElementById('progressFill').style.width = rate + '%';
    }}

    // Init theme from storage
    (function() {{
      const saved = localStorage.getItem('todo_theme');
      if (saved) document.documentElement.setAttribute('data-theme', saved);
    }})();
  </script>
</body>
</html>"""


def build_html_export_bytes(
    tasks: List[Dict[str, Any]],
    categories: List[Dict[str, Any]],
    user_id: str,
    tz_name: str = "UTC",
    lang: str = "th",
    theme: str = "dark",
) -> io.BytesIO:
    """Generate self-contained HTML export as BytesIO ready for Discord upload."""
    content = generate_interactive_html(
        tasks=tasks,
        categories=categories,
        user_id=user_id,
        tz_name=tz_name,
        lang=lang,
        theme=theme,
    )
    return io.BytesIO(content.encode("utf-8"))


# ─────────────────────────────────────────────────────────────────────────────
# 3. Weekly Retrospective Self-Digest
# ─────────────────────────────────────────────────────────────────────────────

async def get_weekly_retrospective_data(
    user_id: str,
    ref_time: Optional[datetime] = None,
) -> WeeklyRetrospectiveData:
    """
    Calculate 7-day retrospective data for user:
    - Weekly completion rate %
    - Snooze bottleneck analysis (top 3 snoozed tasks)
    - Category distribution
    - Overdue carryover tasks
    - Personalized coaching tip
    """
    tz_name = await get_user_timezone(user_id)
    try:
        user_tz = pytz.timezone(tz_name)
    except Exception:
        user_tz = pytz.utc

    now_local = (
        ref_time.astimezone(user_tz)
        if (ref_time and ref_time.tzinfo)
        else (user_tz.localize(ref_time) if ref_time else datetime.now(user_tz))
    )

    # Calculate Monday 00:00 to Sunday 23:59
    start_of_week = (now_local - timedelta(days=now_local.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end_of_week = (start_of_week + timedelta(days=6)).replace(
        hour=23, minute=59, second=59, microsecond=999999
    )
    week_str = start_of_week.strftime("%Y-W%W")

    start_utc = start_of_week.astimezone(pytz.utc)
    end_utc = end_of_week.astimezone(pytz.utc)
    start_utc_naive = start_utc.replace(tzinfo=None)
    end_utc_naive = end_utc.replace(tzinfo=None)
    now_utc = datetime.now(timezone.utc)

    # 1. Query completed tasks this week (from task_completion_events or audit_log)
    comp_events = await db.afetchall(
        """SELECT task_id, task_title, priority, completed_at
           FROM task_completion_events
           WHERE user_id = $1 AND completed_at >= $2 AND completed_at <= $3""",
        (user_id, start_utc, end_utc),
    )
    completed_tasks_count = len(comp_events or [])

    # If task_completion_events is empty, fallback to audit_log
    if completed_tasks_count == 0:
        audit_comps = await db.afetchall(
            """SELECT target_id FROM audit_log
               WHERE user_id = $1 AND action = 'task_completed'
                 AND created_at >= $2 AND created_at <= $3""",
            (user_id, start_utc_naive, end_utc_naive),
        )
        completed_tasks_count = len(audit_comps or [])

    # 2. Query user tasks (active + carried over)
    user_tasks = await db.afetchall(
        """SELECT t.task_id, t.task, t.status, t.priority, t.deadline, t.created_at,
                  c.name AS category_name
           FROM tasks t
           LEFT JOIN categories c ON t.category_id = c.category_id
           WHERE t.owner_id = $1 AND t.is_deleted = FALSE""",
        (user_id,),
    )
    user_tasks = user_tasks or []

    pending_tasks = [
        t for t in user_tasks
        if str(t.get("status", "")).lower() in ("pending", "in_progress")
    ]
    total_active_week = completed_tasks_count + len(pending_tasks)

    completion_rate = (
        round((completed_tasks_count / total_active_week * 100), 1)
        if total_active_week > 0 else 0.0
    )

    # 3. Overdue carryover tasks
    overdue_carryovers: List[Dict[str, Any]] = []
    for t_row in pending_tasks:
        dl = t_row.get("deadline")
        if dl:
            dt = dl if isinstance(dl, datetime) else datetime.fromisoformat(str(dl))
            if dt.tzinfo is None:
                dt = pytz.utc.localize(dt)
            if dt < now_utc:
                overdue_carryovers.append({
                    "task_id": t_row["task_id"],
                    "task": t_row["task"],
                    "priority": t_row.get("priority", 1),
                    "deadline": dt.astimezone(user_tz).strftime("%d/%m %H:%M"),
                })

    # 4. Snooze bottleneck analysis from audit_log
    snooze_rows = await db.afetchall(
        """SELECT target_id, COUNT(*) AS snooze_cnt
           FROM audit_log
           WHERE user_id = $1 AND action = 'task_snoozed'
             AND created_at >= $2 AND created_at <= $3
           GROUP BY target_id
           ORDER BY snooze_cnt DESC
           LIMIT 3""",
        (user_id, start_utc_naive, end_utc_naive),
    )
    snooze_total = 0
    top_snoozed: List[Dict[str, Any]] = []
    for sr in (snooze_rows or []):
        cnt = int(sr["snooze_cnt"])
        snooze_total += cnt
        target_tid = sr["target_id"]
        # Find task title
        t_match = next((x for x in user_tasks if str(x["task_id"]) == str(target_tid)), None)
        title = t_match["task"] if t_match else f"Task #{target_tid}"
        top_snoozed.append({
            "task_id": target_tid,
            "name": title,
            "snooze_count": cnt,
        })

    # 5. Category distribution
    cat_dist: Dict[str, int] = {}
    for t_row in user_tasks:
        cname = t_row.get("category_name") or "General"
        cat_dist[cname] = cat_dist.get(cname, 0) + 1

    # 6. Dynamic coaching tip
    lang = await get_user_lang(user_id)
    if completion_rate >= 80:
        tip = t("retro_tip_excellent", lang)
    elif snooze_total >= 4:
        tip = t("retro_tip_snooze", lang)
    elif len(overdue_carryovers) >= 3:
        tip = t("retro_tip_overdue", lang)
    else:
        tip = t("retro_tip_standard", lang)

    return WeeklyRetrospectiveData(
        user_id=user_id,
        start_date=start_of_week,
        end_date=end_of_week,
        week_str=week_str,
        total_tasks=total_active_week,
        completed_tasks=completed_tasks_count,
        completion_rate=completion_rate,
        snooze_count_total=snooze_total,
        top_snoozed_tasks=top_snoozed,
        category_distribution=cat_dist,
        overdue_carryover_tasks=overdue_carryovers,
        coaching_tip=tip,
    )


async def send_weekly_retrospective_dm(
    bot: commands.Bot,
    user_id: str,
    retro_data: Optional[WeeklyRetrospectiveData] = None,
) -> bool:
    """
    Send the Sunday evening Weekly Retrospective DM to a user.
    Enforces user preference (weekly_retrospective == 1) and idempotency.
    """
    user_row = await db.afetchone(
        "SELECT weekly_retrospective, last_retrospective_date, lang FROM users WHERE user_id = $1",
        (user_id,),
    )
    if not user_row or not user_row.get("weekly_retrospective", 1):
        return False

    if not retro_data:
        retro_data = await get_weekly_retrospective_data(user_id)

    if user_row.get("last_retrospective_date") == retro_data.week_str:
        log.info("Weekly retrospective for user %s already sent for week %s", user_id, retro_data.week_str)
        return False

    lang = user_row.get("lang") or "th"

    # Build Embed
    embed = discord.Embed(
        title=f"🌅 {t('retro_title', lang, week=retro_data.week_str)}",
        description=f"> {retro_data.coaching_tip}",
        color=0x6366f1,
    )

    # Progress Bar
    pbar = progress_bar(retro_data.completed_tasks, retro_data.total_tasks)
    embed.add_field(
        name=t("retro_completion_rate", lang),
        value=f"**{retro_data.completion_rate}%** ({retro_data.completed_tasks}/{retro_data.total_tasks})\n{pbar}",
        inline=False,
    )

    # Snooze Bottleneck Analysis
    if retro_data.top_snoozed_tasks:
        snooze_lines = [
            f"• **{t_info['name']}** — {t('retro_snoozed_times', lang, count=t_info['snooze_count'])}"
            for t_info in retro_data.top_snoozed_tasks
        ]
        embed.add_field(
            name=f"⏰ {t('retro_snooze_bottlenecks', lang)} ({retro_data.snooze_count_total} {t('retro_total_label', lang)})",
            value="\n".join(snooze_lines),
            inline=False,
        )
    else:
        embed.add_field(
            name=f"⏰ {t('retro_snooze_bottlenecks', lang)}",
            value=f"*{t('retro_no_snoozes', lang)}*",
            inline=False,
        )

    # Overdue Carryovers
    if retro_data.overdue_carryover_tasks:
        carry_lines = [
            f"• [P{t_info['priority']}] **#{t_info['task_id']}** {t_info['task']} *({t('retro_due_label', lang, deadline=t_info['deadline'])})*"
            for t_info in retro_data.overdue_carryover_tasks[:5]
        ]
        if len(retro_data.overdue_carryover_tasks) > 5:
            carry_lines.append(f"... {t('and_more_tasks', lang, count=len(retro_data.overdue_carryover_tasks) - 5)}")
        embed.add_field(
            name=f"⚠️ {t('retro_overdue_carryovers', lang)} ({len(retro_data.overdue_carryover_tasks)})",
            value="\n".join(carry_lines),
            inline=False,
        )

    # Category Distribution
    if retro_data.category_distribution:
        cat_lines = [
            f"`{cname}`: {cnt}"
            for cname, cnt in sorted(retro_data.category_distribution.items(), key=lambda x: -x[1])[:5]
        ]
        embed.add_field(
            name=f"🏷️ {t('retro_category_breakdown', lang)}",
            value=" • ".join(cat_lines),
            inline=False,
        )

    embed.set_footer(text=t("retro_footer", lang))

    # Import view
    from history_reporting.views import WeeklyRetrospectiveView
    view = WeeklyRetrospectiveView(user_id=user_id, lang=lang)

    try:
        try:
            uid_val: Any = int(user_id)
        except (ValueError, TypeError):
            uid_val = user_id
        user_obj = await bot.fetch_user(uid_val)
        if not user_obj:
            return False
        await user_obj.send(embed=embed, view=view)
    except discord.Forbidden:
        log.warning("Cannot send weekly retrospective DM to user %s: DMs closed", user_id)
        return False
    except Exception as exc:
        log.error("Failed to send weekly retrospective DM to user %s: %s", user_id, exc)
        return False

    # Persist last_retrospective_date
    await db.aexecute(
        "UPDATE users SET last_retrospective_date = $1 WHERE user_id = $2",
        (retro_data.week_str, user_id),
    )
    log.info("Sent weekly retrospective to user %s for week %s", user_id, retro_data.week_str)
    return True

"""
Unit tests for Gen 5.0 Pillar 5: Advanced Native Workflow Engine & Automations.
Covers:
  - Feature 20: Event-Condition-Action (ECA) Automation Builder & Dispatcher
  - Feature 21: Automated Escalation Policies (12h L1 ping, 18h L2 lead alert)
  - Feature 22: Smart Dynamic Template Variables Engine ({{today}}, {{week_number}}, etc.)
  - Feature 23: Service Level Agreement (SLA) Monitoring, Progress Bars & Breach Warning
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from automation import engine
from automation.engine import (
    eval_conditions,
    execute_actions,
    render_sla_progress_bar,
)
from automation.models import ECARule, SLAPolicy, TaskEscalation, TaskSLATracking
from routine_workflows.dynamic_variables import resolve_template_variables


# ─────────────────────────────────────────────────────────────────────────────
# Feature 22: Smart Dynamic Template Variables Engine Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_resolve_template_variables_datetime():
    dt = datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc)
    ctx = {
        "now_local": dt,
        "user_id": "1001",
        "assignee_id": "2002",
        "project_name": "Antigravity Alpha",
        "sprint_name": "Sprint 42",
    }
    raw = (
        "Project: {{project_name}} ({{sprint_name}})\n"
        "Date: {{today}} to {{tomorrow}}\n"
        "Month: {{month_name}} {{year}} (Week {{week_number}})\n"
        "Assigned: {{assignee}} | Created by: {{creator}}\n"
        "Unknown: {{unknown_variable}}"
    )
    res = resolve_template_variables(raw, ctx)

    assert "Project: Antigravity Alpha (Sprint 42)" in res
    assert "Date: 2026-11-09 to 2026-11-10" in res
    assert "Month: November 2026 (Week 46)" in res
    assert "Assigned: <@2002> | Created by: <@1001>" in res
    assert "Unknown: {{unknown_variable}}" in res


def test_resolve_template_variables_case_insensitive():
    dt = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    ctx = {"now_local": dt, "project_name": "Apollo"}
    raw = "YEAR: {{YEAR}}, Today: {{Today}}, Proj: {{PROJECT_NAME}}"
    res = resolve_template_variables(raw, ctx)

    assert "YEAR: 2026" in res
    assert "Today: 2026-01-15" in res
    assert "Proj: Apollo" in res


def test_resolve_template_variables_empty_or_none():
    assert resolve_template_variables("") == ""
    assert resolve_template_variables(None) == ""


# ─────────────────────────────────────────────────────────────────────────────
# Feature 20: ECA Automation Builder & Dispatcher Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_eval_conditions_priority():
    ctx = {"priority": 6, "tags": "frontend,bug", "project_id": 10}

    # Should match
    assert eval_conditions({"priority_gte": 5}, ctx) is True
    assert eval_conditions({"priority_lte": 7}, ctx) is True
    assert eval_conditions({"priority_gte": 6, "priority_lte": 6}, ctx) is True

    # Should fail
    assert eval_conditions({"priority_gte": 7}, ctx) is False
    assert eval_conditions({"priority_lte": 4}, ctx) is False


def test_eval_conditions_tags_and_project():
    ctx = {"priority": 3, "tags": "security,critical-fix", "project_id": 42}

    assert eval_conditions({"has_tag": "security"}, ctx) is True
    assert eval_conditions({"has_tag": "SECURITY"}, ctx) is True
    assert eval_conditions({"project_id": 42}, ctx) is True
    assert eval_conditions({"has_tag": "marketing"}, ctx) is False
    assert eval_conditions({"project_id": 99}, ctx) is False


def test_eval_conditions_due_within_hours():
    now_utc = datetime.now(timezone.utc)
    due_in_3h = (now_utc + timedelta(hours=3)).isoformat()
    due_in_10h = (now_utc + timedelta(hours=10)).isoformat()

    assert eval_conditions({"due_within_hours": 5}, {"deadline": due_in_3h}) is True
    assert eval_conditions({"due_within_hours": 5}, {"deadline": due_in_10h}) is False
    assert eval_conditions({"due_within_hours": 5}, {}) is False


@pytest.mark.asyncio
async def test_execute_actions():
    bot = MagicMock()
    mock_channel = AsyncMock()
    bot.get_channel.return_value = mock_channel

    guild = MagicMock()
    mock_role = MagicMock(name="Role")
    mock_role.name = "Reviewer"
    mock_member = AsyncMock()
    guild.get_role.return_value = mock_role
    guild.get_member.return_value = mock_member

    actions = {
        "notify_channel": {"channel_id": "12345", "message": "Alert!"},
        "assign_role": {"role_id": "999", "target_user_id": "888"},
    }
    context = {"task_id": 50, "task": "Critical patch", "owner_id": "888"}

    results = await execute_actions(bot, actions, context, guild=guild)
    assert len(results) == 2
    mock_channel.send.assert_awaited_once_with("Alert!")
    mock_member.add_roles.assert_awaited_once()


# ─────────────────────────────────────────────────────────────────────────────
# Feature 21: Automated Escalation Policies Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_check_and_escalate_tasks_level1_and_level2():
    now_utc = datetime.now(timezone.utc)
    created_14h_ago = now_utc - timedelta(hours=14)
    created_20h_ago = now_utc - timedelta(hours=20)

    # Mock task rows returned from db.fetchall
    fake_tasks = [
        # Task 1: 14h ago, currently level 0 -> should escalate to level 1
        {
            "task_id": 101,
            "task": "Payment Gateway Timeout",
            "priority": 7,
            "guild_id": "G1",
            "project_id": 1,
            "created_at": created_14h_ago,
            "project_name": "Fintech Core",
            "channel_id": "9001",
            "lead_id": "501",
            "escalation_level": 0,
            "level1_escalated_at": None,
            "level2_escalated_at": None,
        },
        # Task 2: 20h ago, currently level 1 -> should escalate to level 2
        {
            "task_id": 102,
            "task": "Database Lock Detected",
            "priority": 6,
            "guild_id": "G1",
            "project_id": 1,
            "created_at": created_20h_ago,
            "project_name": "Fintech Core",
            "channel_id": "9001",
            "lead_id": "501",
            "escalation_level": 1,
            "level1_escalated_at": created_14h_ago,
            "level2_escalated_at": None,
        },
    ]

    bot = MagicMock()
    mock_channel = AsyncMock()
    bot.get_channel.return_value = mock_channel

    with patch("core.database.db.fetchall", new_callable=AsyncMock) as mock_fetch, \
         patch("core.database.db.execute", new_callable=AsyncMock) as mock_exec:
        mock_fetch.return_value = fake_tasks

        escalated = await engine.check_and_escalate_tasks(bot)
        assert len(escalated) == 2
        assert escalated[0]["task_id"] == 101
        assert escalated[0]["level"] == 1
        assert escalated[1]["task_id"] == 102
        assert escalated[1]["level"] == 2

        # Verify db.execute called for level 1 insert/update and level 2 update
        assert mock_exec.await_count == 2
        # Verify notification messages sent
        assert mock_channel.send.await_count == 2


@pytest.mark.asyncio
async def test_check_and_escalate_tasks_fallback_without_lead_id_column():
    """Verify fallback query runs seamlessly if column p.lead_id does not exist."""
    now_utc = datetime.now(timezone.utc)
    created_14h_ago = now_utc - timedelta(hours=14)

    fake_tasks = [
        {
            "task_id": 201,
            "task": "Database Slow Query",
            "priority": 6,
            "guild_id": "G1",
            "project_id": 2,
            "created_at": created_14h_ago,
            "project_name": "Core Backend",
            "channel_id": "999",
            "owner_id": "701",
            "lead_id": "701",
            "escalation_level": 0,
            "level1_escalated_at": None,
            "level2_escalated_at": None,
        }
    ]

    bot = MagicMock()
    mock_channel = AsyncMock()
    bot.get_channel.return_value = mock_channel

    side_effects = [
        Exception("column p.lead_id does not exist"),
        fake_tasks,
    ]

    with patch("core.database.db.fetchall", side_effect=side_effects) as mock_fetch, \
         patch("core.database.db.execute", new_callable=AsyncMock) as mock_exec:
        escalated = await engine.check_and_escalate_tasks(bot)
        assert len(escalated) == 1
        assert escalated[0]["task_id"] == 201
        assert mock_fetch.call_count == 2



# ─────────────────────────────────────────────────────────────────────────────
# Feature 23: SLA Monitoring & Breach Warning Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_sla_policy_get_hours():
    policy = SLAPolicy(
        project_id=1,
        guild_id="G1",
        p7_hours=1.5,
        p6_hours=6.0,
        p5_hours=12.0,
        p4_hours=24.0,
    )
    assert policy.get_hours_for_priority(7) == 1.5
    assert policy.get_hours_for_priority(6) == 6.0
    assert policy.get_hours_for_priority(5) == 12.0
    assert policy.get_hours_for_priority(4) == 24.0
    assert policy.get_hours_for_priority(2) == 24.0  # Fallback


def test_render_sla_progress_bar():
    bar_0 = render_sla_progress_bar(0.0)
    assert bar_0 == "[░░░░░░░░░░] 0.0%"

    bar_50 = render_sla_progress_bar(50.0)
    assert bar_50 == "[█████░░░░░] 50.0%"

    bar_80 = render_sla_progress_bar(80.0)
    assert bar_80 == "[████████░░] 80.0%"

    bar_100 = render_sla_progress_bar(100.0)
    assert bar_100 == "[██████████] 100.0%"


@pytest.mark.asyncio
async def test_check_sla_deadlines_warning_and_breach():
    now_utc = datetime.now(timezone.utc)
    t_start = now_utc - timedelta(hours=8)

    # Task 1: 8h elapsed out of 10h total (80% -> Early Warning alert)
    target_dl_1 = now_utc + timedelta(hours=2)

    # Task 2: 8h elapsed out of 6h total (-2h remaining -> Breach alert)
    target_dl_2 = now_utc - timedelta(hours=2)

    fake_sla_rows = [
        {
            "task_id": 201,
            "project_id": 1,
            "target_deadline": target_dl_1,
            "early_warning_sent": False,
            "breached": False,
            "task": "Optimize queries",
            "priority": 6,
            "status": "In Progress",
            "created_at": t_start,
            "guild_id": "G1",
            "project_name": "API Service",
            "channel_id": "7001",
        },
        {
            "task_id": 202,
            "project_id": 1,
            "target_deadline": target_dl_2,
            "early_warning_sent": True,
            "breached": False,
            "task": "Security Audit Report",
            "priority": 7,
            "status": "Pending",
            "created_at": t_start,
            "guild_id": "G1",
            "project_name": "API Service",
            "channel_id": "7001",
        },
    ]

    bot = MagicMock()
    mock_channel = AsyncMock()
    bot.get_channel.return_value = mock_channel

    with patch("core.database.db.fetchall", new_callable=AsyncMock) as mock_fetch, \
         patch("core.database.db.execute", new_callable=AsyncMock) as mock_exec:
        mock_fetch.return_value = fake_sla_rows

        alerts = await engine.check_sla_deadlines(bot)
        assert len(alerts) == 2

        # 202 is breached (remaining <= 0)
        breach_alert = next(a for a in alerts if a["task_id"] == 202)
        assert breach_alert["type"] == "breach"

        # 201 is early warning (pct >= 75%)
        warning_alert = next(a for a in alerts if a["task_id"] == 201)
        assert warning_alert["type"] == "warning"

        # Verify DB updates and channel notifications
        assert mock_exec.await_count == 2
        assert mock_channel.send.await_count == 2


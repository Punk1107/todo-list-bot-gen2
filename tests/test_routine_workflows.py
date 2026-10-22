"""Unit & Integration tests for Category 7: Task Templates, Definition of Done, and Routine Workflows."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import discord

from routine_workflows import service
from routine_workflows.cog import RoutineWorkflowsCog
from routine_workflows.models import (
    ChecklistItem,
    RoutineEventRule,
    TaskTemplate,
)
from routine_workflows.views import (
    DoDForceConfirmView,
    TaskChecklistView,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Template Service Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_builtin_templates_exist():
    assert "onboarding" in service.BUILT_IN_TEMPLATES
    assert "monthly_event" in service.BUILT_IN_TEMPLATES
    assert "client_delivery" in service.BUILT_IN_TEMPLATES

    tmpl = await service.get_template("onboarding")
    assert tmpl is not None
    assert tmpl.name == "onboarding"
    assert tmpl.is_built_in is True
    assert "subtasks" in tmpl.items
    assert len(tmpl.items["subtasks"]) >= 3
    assert len(tmpl.items["checklists"]) >= 2


@pytest.mark.asyncio
async def test_list_templates_merges_builtin_and_custom():
    custom_rows = [
        {
            "template_id": 10,
            "name": "custom_deploy",
            "description": "Deploy pipeline",
            "category": "DevOps",
            "priority": 2,
            "owner_id": "user123",
            "guild_id": None,
            "items": {"task": "Deploy", "subtasks": []},
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    ]
    with patch.object(service.db, "afetchall", new=AsyncMock(return_value=custom_rows)):
        templates = await service.list_templates(owner_id="user123")
        names = [t.name for t in templates]
        assert "onboarding" in names
        assert "monthly_event" in names
        assert "client_delivery" in names
        assert "custom_deploy" in names


@pytest.mark.asyncio
async def test_create_custom_template():
    items = {
        "task": "Bug Bash",
        "relative_days": 2,
        "subtasks": [{"task": "Triage", "relative_days": 1}],
        "checklists": ["All verified"],
    }
    fake_row = {
        "template_id": 1,
        "name": "bug_bash",
        "description": "Weekly bug bash",
        "category": "QA",
        "priority": 3,
        "owner_id": "u1",
        "guild_id": "g1",
        "items": items,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    with patch.object(service.db, "afetchone", new=AsyncMock(return_value=fake_row)):
        tmpl = await service.create_custom_template(
            name="bug_bash",
            items=items,
            owner_id="u1",
            guild_id="g1",
            description="Weekly bug bash",
            category="QA",
            priority=3,
        )
        assert tmpl.name == "bug_bash"
        assert tmpl.owner_id == "u1"
        assert tmpl.items["task"] == "Bug Bash"


@pytest.mark.asyncio
async def test_cannot_delete_builtin_template():
    # In service, delete_custom_template only deletes matching owner_id
    with patch.object(service.db, "aexecute", new=AsyncMock(return_value="DELETE 0")):
        res = await service.delete_custom_template("onboarding", owner_id="u1")
        assert res is False


@pytest.mark.asyncio
async def test_create_template_from_task():
    parent_row = {
        "task_id": 42,
        "task": "Sprint Planning",
        "priority": 4,
        "description": "Bi-weekly sprint planning",
        "tags": "Agile",
        "deadline": datetime.now(timezone.utc),
        "created_at": datetime.now(timezone.utc),
    }
    sub_rows = [
        {
            "task_id": 43,
            "task": "Review Backlog",
            "priority": 3,
            "description": "Groom items",
            "deadline": datetime.now(timezone.utc),
        }
    ]
    checklists = [
        ChecklistItem(checklist_id=1, task_id=42, title="Story points assigned", is_done=True, position=0)
    ]

    with (
        patch.object(service.db, "afetchone", new=AsyncMock(return_value=parent_row)),
        patch.object(service.db, "afetchall", new=AsyncMock(return_value=sub_rows)),
        patch.object(service, "get_checklists", new=AsyncMock(return_value=checklists)),
        patch.object(service, "create_custom_template", new=AsyncMock()) as mock_create,
    ):
        await service.create_template_from_task(42, "sprint_template", owner_id="u1", guild_id="g1")
        assert mock_create.called
        kwargs = mock_create.call_args.kwargs
        assert kwargs["name"] == "sprint_template"
        assert kwargs["items"]["task"] == "Sprint Planning"
        assert "Story points assigned" in kwargs["items"]["checklists"]


@pytest.mark.asyncio
async def test_apply_template_creates_parent_subtasks_and_checklists():
    mock_conn = AsyncMock()
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=tx)
    tx.__aexit__ = AsyncMock(return_value=None)
    mock_conn.transaction = MagicMock(return_value=tx)
    mock_conn.fetchrow.side_effect = [
        {"task_id": 100},  # parent task
        {"task_id": 101},  # subtask 1
        {"task_id": 102},  # subtask 2
        {"task_id": 103},  # subtask 3
        {"task_id": 104},  # subtask 4
    ]

    class FakeAcquire:
        async def __aenter__(self):
            return mock_conn
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    with (
        patch.object(service.db, "afetchone", new=AsyncMock(return_value=None)),
        patch.object(service.db, "acquire", return_value=FakeAcquire()),
        patch.object(service.db, "invalidate_stats"),
        patch.object(service.db, "alog_action", new=AsyncMock()),
    ):
        result = await service.apply_template(
            template_name="onboarding",
            user_id="u123",
            guild_id="g456",
            tz_name="Asia/Bangkok",
        )
        assert result["parent_task_id"] == 100
        assert result["subtask_count"] == 4
        assert result["checklist_count"] >= 3
        assert mock_conn.fetchrow.call_count == 5


# ─────────────────────────────────────────────────────────────────────────────
# 2. Definition of Done (Checklist) Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_checklist_crud_and_toggle():
    # 1. Add item
    add_row = {
        "checklist_id": 1,
        "task_id": 50,
        "title": "Check typo",
        "is_done": False,
        "position": 0,
        "created_at": datetime.now(timezone.utc),
        "completed_at": None,
    }
    with (
        patch.object(service.db, "afetchone", new=AsyncMock(side_effect=[{"max_pos": -1}, add_row])),
    ):
        item = await service.add_checklist_item(50, "Check typo")
        assert item is not None
        assert item.title == "Check typo"
        assert item.is_done is False

    # 2. Get pending count
    with patch.object(service.db, "afetchone", new=AsyncMock(return_value={"c": 2})):
        cnt = await service.get_pending_checklist_count(50)
        assert cnt == 2

    # 3. Toggle item
    toggle_curr = {"task_id": 50, "is_done": False}
    toggle_row = {
        "checklist_id": 1,
        "task_id": 50,
        "title": "Check typo",
        "is_done": True,
        "position": 0,
        "created_at": datetime.now(timezone.utc),
        "completed_at": datetime.now(timezone.utc),
    }
    with (
        patch.object(service.db, "afetchone", new=AsyncMock(side_effect=[toggle_curr, toggle_row])),
        patch.object(service, "get_pending_checklist_count", new=AsyncMock(return_value=1)),
        patch.object(service.db, "alog_action", new=AsyncMock()),
    ):
        res = await service.toggle_checklist_item(1, "u1")
        assert res is not None
        toggled_item, pending = res
        assert toggled_item.is_done is True
        assert pending == 1

    # 4. Delete item
    with patch.object(service.db, "aexecute", new=AsyncMock(return_value="DELETE 1")):
        assert await service.delete_checklist_item(1) is True


# ─────────────────────────────────────────────────────────────────────────────
# 3. Routine Rules Service Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_routine_rules_management():
    fake_rule_row = {
        "rule_id": 1,
        "guild_id": "guild_1",
        "event_type": "role_added",
        "trigger_role_id": 999,
        "template_name": "onboarding",
        "is_active": True,
        "created_by": "admin_1",
        "created_at": datetime.now(timezone.utc),
    }

    # Add rule
    with patch.object(service.db, "afetchone", new=AsyncMock(return_value=fake_rule_row)):
        rule = await service.add_routine_rule(
            guild_id="guild_1",
            event_type="role_added",
            template_name="onboarding",
            created_by="admin_1",
            trigger_role_id=999,
        )
        assert rule.rule_id == 1
        assert rule.event_type == "role_added"
        assert rule.trigger_role_id == 999

    # Match rule
    with patch.object(service.db, "afetchall", new=AsyncMock(return_value=[fake_rule_row])):
        matched = await service.get_matching_rules("guild_1", "role_added", role_id=999)
        assert len(matched) == 1
        assert matched[0].template_name == "onboarding"


# ─────────────────────────────────────────────────────────────────────────────
# 4. DoD Force Complete Dialog & Guard Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dod_force_confirm_view_interaction():
    pending_items = [
        ChecklistItem(checklist_id=1, task_id=10, title="Proofread document", is_done=False, position=0),
        ChecklistItem(checklist_id=2, task_id=10, title="Attach receipt", is_done=False, position=1),
    ]

    view = DoDForceConfirmView(
        task_id=10,
        task_name="Client Deliverable",
        user_id="user_test",
        lang="en",
        pending_items=pending_items,
    )
    embed = view.make_embed()
    assert "Proofread document" in embed.description
    assert "Attach receipt" in embed.description

    # Test force_complete callback
    mock_interaction = AsyncMock()
    mock_interaction.user.id = "user_test"
    mock_interaction.response.is_done.return_value = True

    with (
        patch("routine_workflows.views.gamification_service.complete_personal_task", new=AsyncMock(return_value=["badge_done"])),
        patch.object(service.db, "alog_action", new=AsyncMock()),
    ):
        await view.force_complete.callback(mock_interaction)
        assert mock_interaction.edit_original_response.called


# ─────────────────────────────────────────────────────────────────────────────
# 5. RoutineWorkflowsCog Listener Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_on_member_update_triggers_routine():
    bot = MagicMock()
    cog = RoutineWorkflowsCog(bot)

    mock_role = MagicMock(spec=discord.Role)
    mock_role.id = 888
    mock_role.name = "Verified"

    before_member = MagicMock(spec=discord.Member)
    before_member.bot = False
    before_member.roles = []

    after_member = MagicMock(spec=discord.Member)
    after_member.bot = False
    after_member.id = 12345
    after_member.roles = [mock_role]
    after_member.guild.id = 777
    after_member.guild.name = "Test Guild"
    after_member.send = AsyncMock()

    rule = RoutineEventRule(
        rule_id=1,
        guild_id="777",
        event_type="role_added",
        trigger_role_id=888,
        template_name="onboarding",
        is_active=True,
        created_by="admin",
    )

    with (
        patch.object(service, "get_matching_rules", new=AsyncMock(return_value=[rule])),
        patch("routine_workflows.cog.get_user_lang", new=AsyncMock(return_value="en")),
        patch("routine_workflows.cog.get_user_timezone", new=AsyncMock(return_value="UTC")),
        patch("routine_workflows.cog.ensure_user", new=AsyncMock()),
        patch.object(
            service,
            "apply_template",
            new=AsyncMock(
                return_value={
                    "parent_task_id": 99,
                    "task_name": "Onboarding",
                    "subtask_count": 3,
                    "checklist_count": 2,
                }
            ),
        ),
    ):
        await cog.on_member_update(before_member, after_member)
        assert after_member.send.called
        call_kwargs = after_member.send.call_args.kwargs
        assert "embed" in call_kwargs
        embed = call_kwargs["embed"]
        assert "Verified" in embed.title


# ─────────────────────────────────────────────────────────────────────────────
# 6. Task Embed & TaskActionView DoD Guard Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_build_task_embed_shows_dod_progress():
    from utils.helpers import build_task_embed

    row = {
        "task_id": 1,
        "task": "Test Task",
        "status": "Pending",
        "deadline": None,
        "priority": 2,
        "is_pinned": 0,
        "description": "Some description",
        "tags": None,
        "recurring": None,
        "progress_pct": 20,
    }
    checklists = [
        {"title": "Check A", "is_done": True},
        {"title": "Check B", "is_done": False},
        {"title": "Check C", "is_done": False},
    ]

    embed = build_task_embed(row, lang="en", tz_name="UTC", checklists=checklists)
    field_names = [f.name for f in embed.fields]
    assert any("Definition of Done" in name for name in field_names)
    dod_field = next(f for f in embed.fields if "Definition of Done" in f.name)
    assert "(1/3)" in dod_field.name
    assert "Check A" in dod_field.value
    assert "Check B" in dod_field.value


@pytest.mark.asyncio
async def test_task_action_view_mark_done_intercepted_by_pending_dod():
    from handlers.task_views import TaskActionView

    view = TaskActionView(task_id=77, uid="user_1", lang="en")
    mock_interaction = AsyncMock()
    mock_interaction.user.id = "user_1"
    mock_interaction.response.is_done.return_value = True

    pending = [
        ChecklistItem(checklist_id=1, task_id=77, title="Do QA", is_done=False, position=0)
    ]

    with (
        patch("handlers.task_views.get_user_lang", new=AsyncMock(return_value="en")),
        patch.object(service.db, "afetchone", new=AsyncMock(return_value={"task": "My Task", "status": "Pending"})),
        patch("routine_workflows.service.get_pending_checklists", new=AsyncMock(return_value=pending)),
    ):
        await view.mark_done.callback(mock_interaction)
        assert mock_interaction.followup.send.called
        kwargs = mock_interaction.followup.send.call_args.kwargs
        assert "embed" in kwargs
        assert "view" in kwargs
        from routine_workflows.views import DoDForceConfirmView
        assert isinstance(kwargs["view"], DoDForceConfirmView)


@pytest.mark.asyncio
async def test_task_action_view_mark_done_completes_when_no_pending_dod():
    from handlers.task_views import TaskActionView

    view = TaskActionView(task_id=88, uid="user_1", lang="en")
    mock_interaction = AsyncMock()
    mock_interaction.user.id = "user_1"
    mock_interaction.response.is_done.return_value = True

    with (
        patch("handlers.task_views.get_user_lang", new=AsyncMock(return_value="en")),
        patch.object(service.db, "afetchone", new=AsyncMock(return_value={"task": "Completed Task", "status": "Pending"})),
        patch("routine_workflows.service.get_pending_checklists", new=AsyncMock(return_value=[])),
        patch("handlers.task_views.gamification_service.complete_personal_task", new=AsyncMock(return_value=["badge_done"])),
        patch.object(service.db, "alog_action", new=AsyncMock()),
        patch("handlers.task_views._send_dm", new=AsyncMock()),
    ):
        await view.mark_done.callback(mock_interaction)
        assert mock_interaction.followup.send.called
        args, kwargs = mock_interaction.followup.send.call_args
        # Should complete directly
        assert "Completed" in args[0] or "task_done" in args[0] or "Completed Task" in args[0]


@pytest.mark.asyncio
async def test_tasks_cog_done_command_checks_dod_and_respects_force():
    from handlers.tasks_cog import TasksCog

    bot = MagicMock()
    cog = TasksCog(bot)

    mock_interaction = AsyncMock()
    mock_interaction.user.id = "user_1"
    mock_interaction.response.is_done.return_value = True

    pending = [
        ChecklistItem(checklist_id=1, task_id=99, title="Sign document", is_done=False, position=0)
    ]

    # 1. force=False with pending checklists -> prompts DoD confirmation
    with (
        patch("handlers.tasks_cog.get_user_lang", new=AsyncMock(return_value="en")),
        patch.object(service.db, "afetchone", new=AsyncMock(return_value={"task": "Doc Task", "status": "Pending", "owner_id": "user_1"})),
        patch("routine_workflows.service.get_pending_checklists", new=AsyncMock(return_value=pending)),
    ):
        await cog.done.callback(cog, mock_interaction, task_id=99, force=False)
        assert mock_interaction.followup.send.called
        kwargs = mock_interaction.followup.send.call_args.kwargs
        assert isinstance(kwargs["view"], DoDForceConfirmView)

    # 2. force=True with pending checklists -> completes task directly!
    mock_interaction.reset_mock()
    with (
        patch("handlers.tasks_cog.get_user_lang", new=AsyncMock(return_value="en")),
        patch.object(service.db, "afetchone", new=AsyncMock(return_value={"task": "Doc Task", "status": "Pending", "owner_id": "user_1"})),
        patch("handlers.tasks_cog.gamification_service.complete_personal_task", new=AsyncMock(return_value=["badge"])),
        patch.object(service.db, "alog_action", new=AsyncMock()),
        patch("handlers.tasks_cog._send_dm", new=AsyncMock()),
    ):
        await cog.done.callback(cog, mock_interaction, task_id=99, force=True)
        assert mock_interaction.followup.send.called
        kwargs = mock_interaction.followup.send.call_args.kwargs
        assert "embed" in kwargs


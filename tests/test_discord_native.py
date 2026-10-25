from __future__ import annotations

from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

import pytest

from collaboration import service
from core.database import MIGRATIONS, SCHEMA_VERSION, _split_sql_statements
from collaboration.models import ProjectTask
from collaboration.views import TaskDiscussionView
from discord_native.bulk_cog import BulkActionsCog, BulkTaskView
from handlers.tasks_cog import TasksCog
from locales.i18n import SUPPORTED_LANGS, t
from utils.helpers import build_task_embed


def _task_rows(count: int) -> list[dict]:
    return [
        {
            "task_id": index + 1,
            "task": f"Task {index + 1}",
            "deadline": "2099-12-31T23:59:00+00:00",
            "status": "Pending",
        }
        for index in range(count)
    ]


def test_bulk_task_view_paginates_and_retains_selections() -> None:
    view = BulkTaskView("42", "en", "done", _task_rows(26), 26)
    view.selected_ids.add(1)
    view.page = 1
    view._build_items()

    select = next(item for item in view.children if item.__class__.__name__ == "BulkTaskSelect")
    assert len(select.options) == 1
    assert select.options[0].value == "26"
    assert view.selected_ids == {1}
    assert view.previous.disabled is False
    assert view.next.disabled is True


def test_context_message_task_link_is_rendered_in_task_embed() -> None:
    embed = build_task_embed(
        {
            "task_id": 12,
            "task": "Review proposal",
            "status": "Pending",
            "deadline": "2099-12-31T23:59:00+00:00",
            "priority": 0,
            "is_pinned": False,
            "description": None,
            "source_message_url": "https://discord.com/channels/1/2/3",
            "tags": None,
            "recurring": None,
        },
        "en",
        "UTC",
    )
    assert any(field.value == "[Jump to source message](https://discord.com/channels/1/2/3)"
               for field in embed.fields)


def test_project_task_thread_view_offers_public_and_private_modes() -> None:
    task = ProjectTask(
        task_id=8,
        project_id=3,
        guild_id="4",
        task="Prepare release",
        status="Pending",
        priority=1,
        deadline="2099-12-31T23:59:00+00:00",
        owner_id="5",
        description=None,
        tags=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    view = TaskDiscussionView(3, "4", "en", "5", [task])
    labels = {item.label for item in view.children if hasattr(item, "label")}
    assert "🌐 Public Thread" in labels
    assert "🔒 Private Thread" in labels
    select = next(item for item in view.children if hasattr(item, "options"))
    assert select.options[0].value == "8"


def test_message_context_menu_is_created_for_task_cog() -> None:
    from unittest.mock import MagicMock

    cog = TasksCog(MagicMock())
    assert cog.message_to_task.name == "Add to To-Do"
    assert cog.message_to_task.type.name == "message"


def test_bulk_slash_group_exposes_all_three_actions() -> None:
    assert {command.name for command in BulkActionsCog.bulk.commands} == {
        "done", "snooze", "delete",
    }


@pytest.mark.asyncio
async def test_context_menu_registers_and_unregisters_with_task_cog() -> None:
    from unittest.mock import MagicMock

    bot = MagicMock()
    cog = TasksCog(bot)
    await cog.cog_load()
    bot.tree.add_command.assert_called_once_with(cog.message_to_task)
    await cog.cog_unload()
    bot.tree.remove_command.assert_called_once_with(
        "Add to To-Do", type=cog.message_to_task.type
    )


def test_discord_native_translations_have_safe_fallback_for_all_languages() -> None:
    for lang in SUPPORTED_LANGS:
        res = t("bulk_result", lang, succeeded=2, failed=1)
        assert "2" in res and "1" in res
        thread_msg = t("proj_thread_created", lang, url="https://discord.com/channels/1/2")
        assert "https://discord.com/channels/1/2" in thread_msg

    # Verify fallback for unknown/unsupported locale
    assert t("bulk_result", "xx", succeeded=2, failed=1) == (
        "✅ Completed: **2** · Failed or no longer available: **1**"
    )
    assert t("proj_thread_created", "xx", url="https://discord.com/channels/1/2") == (
        "✅ Discussion thread created: https://discord.com/channels/1/2"
    )


def test_collaboration_feature_translations_render_in_every_language() -> None:
    for lang in SUPPORTED_LANGS:
        blocked = t("proj_task_blocked", lang, blockers="#12 API task")
        workload = t("proj_workload_title", lang, project="Project X")
        assignment = t(
            "proj_role_assigned", lang,
            task_id=7, role="Designers", sent=3, failed=1,
        )
        assert "#12 API task" in blocked
        assert "Project X" in workload
        assert "Designers" in assignment
        assert "{blockers}" not in blocked
        assert "{project}" not in workload
        assert "{sent}" not in assignment and "{failed}" not in assignment


def test_schema_v20_contains_context_menu_and_thread_mapping() -> None:
    migration = dict(MIGRATIONS)[20]
    statements = _split_sql_statements(migration)
    assert SCHEMA_VERSION == 28
    assert any("source_message_url" in statement for statement in statements)
    assert any("CREATE TABLE IF NOT EXISTS project_task_threads" in statement for statement in statements)
    assert any("thread_type IN ('public', 'private')" in statement for statement in statements)


def test_schema_v21_contains_scoped_dependencies_and_role_assignments() -> None:
    migration = dict(MIGRATIONS)[21]
    statements = _split_sql_statements(migration)
    assert SCHEMA_VERSION == 28
    assert any("CREATE TABLE IF NOT EXISTS project_task_dependencies" in statement for statement in statements)
    assert any("CREATE TABLE IF NOT EXISTS project_task_role_assignments" in statement for statement in statements)
    assert any("CHECK (task_id <> blocked_by_task_id)" in statement for statement in statements)


@pytest.mark.asyncio
async def test_thread_reservation_is_scoped_and_conflicts_are_reported() -> None:
    with (
        patch.object(service, "get_project_task", new=AsyncMock()),
        patch.object(service.db, "fetchone", new=AsyncMock(return_value=None)) as fetchone,
        patch.object(service.db.query_cache, "invalidate_tables") as invalidate,
        patch.object(
            service,
            "get_project_task_thread",
            new=AsyncMock(return_value={"thread_id": 987654321}),
        ),
    ):
        with pytest.raises(service.TaskThreadExists):
            await service.reserve_project_task_thread(
                7, 11, "guild-13", "public", 17, "user-19"
            )

    query, params = fetchone.await_args.args
    assert "ON CONFLICT (task_id) DO UPDATE" in query
    assert params == (7, 11, "guild-13", "public", 17, "user-19")
    invalidate.assert_called_once_with(["project_task_threads"])

"""Comprehensive unit & integration tests for Gen 5.0 Pillar 10 (Features 38–45)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import io
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import zipfile

import pytest

from assignments import service as assign_service
from core import theme as theme_mod
from core.database import db
from federation import service as fed_service
from history_reporting import backup as backup_mod
from privacy import service as privacy_service
from recovery import janitor as janitor_mod
from routine_workflows import service as routine_service
from utils.helpers import build_task_list_embed, format_user_display


# ── Feature 38: Cross-Guild Project Federation ─────────────────────────────────

@pytest.mark.asyncio
async def test_federation_invite_and_accept_flow():
    exp = datetime.now(timezone.utc) + timedelta(hours=24)
    with patch.object(
        db,
        "fetchone",
        side_effect=[
            {"project_id": 7, "guild_id": "100", "owner_id": "u1"},  # home check
            {
                "invite_code": "ABCD1234",
                "project_id": 7,
                "home_guild_id": "100",
                "target_guild_id": "200",
                "created_by": "u1",
                "default_role": "member",
                "expires_at": exp,
            },
        ],
    ):
        invite = await fed_service.create_federation_invite(
            project_id=7,
            home_guild_id="100",
            target_guild_id="200",
            actor_id="u1",
            default_role="member",
        )
        assert invite.invite_code == "ABCD1234"
        assert invite.target_guild_id == "200"

    with patch.object(
        db,
        "fetchone",
        side_effect=[
            {
                "invite_code": "ABCD1234",
                "project_id": 7,
                "home_guild_id": "100",
                "target_guild_id": "200",
                "created_by": "u1",
                "default_role": "member",
                "expires_at": exp,
                "accepted_at": None,
            },
            {
                "project_id": 7,
                "guild_id": "200",
                "role_scope": "member",
                "status": "active",
                "sync_channel_id": 999,
                "linked_by": "u2",
            },
        ],
    ), patch.object(db, "execute", new=AsyncMock()), patch(
        "utils.helpers.ensure_user", new=AsyncMock()
    ), patch("collaboration.service.log_activity", new=AsyncMock()):
        link = await fed_service.accept_federation_invite(
            "ABCD1234", target_guild_id="200", actor_id="u2", sync_channel_id=999, is_guild_admin=True
        )
        assert link.project_id == 7
        assert link.guild_id == "200"
        assert link.status == "active"


@pytest.mark.asyncio
async def test_federation_same_guild_rejected():
    with pytest.raises(ValueError, match="own home server"):
        await fed_service.create_federation_invite(1, "100", "100", "u1")


# ── Feature 39: Multi-Assignees & Collective Sign-off ──────────────────────────

def test_parse_user_ids():
    parsed = assign_service.parse_user_ids("<@123456789012345678> <@!987654321098765432> 123456789012345678")
    assert parsed == ["123456789012345678", "987654321098765432"]


@pytest.mark.asyncio
async def test_all_signoff_blocks_until_everyone_signs():
    summary_initial = assign_service.AssignmentSummary(
        task_id=42,
        assignment_mode="all_signoff",
        user_ids=["u1", "u2"],
        role_ids=[],
        signed_user_ids=[],
        pending_user_ids=["u1", "u2"],
    )
    summary_after_one = assign_service.AssignmentSummary(
        task_id=42,
        assignment_mode="all_signoff",
        user_ids=["u1", "u2"],
        role_ids=[],
        signed_user_ids=["u1"],
        pending_user_ids=["u2"],
    )
    summary_all_done = assign_service.AssignmentSummary(
        task_id=42,
        assignment_mode="all_signoff",
        user_ids=["u1", "u2"],
        role_ids=[],
        signed_user_ids=["u1", "u2"],
        pending_user_ids=[],
    )

    with patch("assignments.service.ensure_user", new=AsyncMock()), patch.object(
        db, "aexecute", new=AsyncMock()
    ):
        with patch.object(
            assign_service, "get_assignment_summary", side_effect=[summary_initial, summary_after_one]
        ):
            r1 = await assign_service.handle_task_completion_attempt(42, "u1")
            assert r1.completed is False
            assert r1.pending_users == ["u2"]

        with patch.object(
            assign_service, "get_assignment_summary", side_effect=[summary_after_one, summary_all_done]
        ):
            r2 = await assign_service.handle_task_completion_attempt(42, "u2")
            assert r2.completed is True
            assert r2.pending_users == []


# ── Feature 40: Complete Data Portability & Archive Bundle (.zip) ──────────────

@pytest.mark.asyncio
async def test_backup_bundle_contains_required_artifacts():
    now = datetime.now(timezone.utc)
    fake_tasks = [
        {
            "task_id": 10,
            "task": "Ship Pillar 10",
            "status": "Pending",
            "priority": 5,
            "deadline": now.isoformat(),
            "owner_id": "u1",
            "category_id": None,
            "description": "Finalize tests",
            "tags": "#release",
            "recurring": None,
            "created_at": now,
            "updated_at": now,
            "is_pinned": 0,
            "progress_pct": 50,
            "project_id": None,
            "guild_id": None,
        }
    ]
    fake_docs = [
        {
            "doc_id": 3,
            "project_id": 1,
            "title": "Architecture Guide",
            "slug": "architecture-guide",
            "doc_type": "sop",
            "content_markdown": "# Architecture\nDetails here.",
            "updated_at": now,
        }
    ]

    with patch.object(
        db,
        "afetchall",
        side_effect=[
            fake_tasks,  # tasks
            [],          # categories
            fake_docs,   # project_documents
            [{"checklist_id": 1, "task_id": 10, "title": "Tests green", "is_done": True, "position": 0}],
            [],          # comments
            [{"task_id": 10, "user_id": "u1"}],
            [],          # attachments
        ],
    ):
        res = await backup_mod.build_backup_bundle("u1", scope="me", tz_name="UTC", lang="en")

    assert res.task_count == 1
    assert res.doc_count == 1
    assert res.filename.endswith(".zip")

    with zipfile.ZipFile(io.BytesIO(res.zip_bytes.getvalue()), "r") as zf:
        names = set(zf.namelist())
        assert "tasks.json" in names
        assert "tasks.csv" in names
        assert "dashboard.html" in names
        assert "attachments/MANIFEST.txt" in names
        assert "wiki_docs/3_architecture-guide.md" in names
        parsed_json = json.loads(zf.read("tasks.json").decode("utf-8"))
        assert parsed_json["task_count"] == 1
        assert parsed_json["tasks"][0]["checklists"][0]["title"] == "Tests green"


# ── Feature 41: Smart Janitor Engine ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_janitor_cycle_archives_purges_and_compacts():
    with patch.object(
        db,
        "afetchall",
        side_effect=[
            [{"task_id": 101}, {"task_id": 102}],  # archive candidates
            [{"task_id": 101, "cnt": 2, "done_cnt": 2}],  # checklist meta
            [{"task_id": 101, "hours": 4.5}],             # time logs meta
            [{"task_id": 101, "cnt": 3}],                 # comments meta
            [{"column_name": "task_id"}, {"column_name": "task"}],  # schema cols
            [{"task_id": 101}, {"task_id": 102}],         # DELETE RETURNING
            [{"period_month": "2026-01", "action": "task_completed", "event_count": 15, "unique_users": 4}],
        ],
    ), patch.object(db, "aexecute", new=AsyncMock()), patch(
        "recovery.service.purge_expired_trash", new=AsyncMock(return_value=3)
    ):
        report = await janitor_mod.run_janitor_cycle(archive_days=90, trash_days=30, audit_days=180)
        assert report.archived_tasks == 2
        assert report.purged_trash == 3
        assert report.compacted_audit_logs == 15


# ── Feature 42: GDPR Right to be Forgotten ─────────────────────────────────────

@pytest.mark.asyncio
async def test_gdpr_erasure_anonymizes_shared_and_deletes_personal():
    assert format_user_display("deleted_user") == "[Deleted User]"
    assert format_user_display("12345") == "<@12345>"

    with patch.object(
        db,
        "afetchall",
        side_effect=[
            [{"project_id": 9}],         # owned projects
            [{"task_id": 50}],           # shared tasks anonymized
            [{"task_id": 11}, {"task_id": 12}],  # personal tasks deleted
        ],
    ), patch.object(
        db,
        "afetchone",
        side_effect=[
            {"user_id": "u_lead2"},      # project successor
            {"user_id": "u_victim"},     # deleted user row
        ],
    ), patch.object(db, "aexecute", new=AsyncMock()), patch.object(
        db, "alog_action", new=AsyncMock()
    ):
        report = await privacy_service.execute_gdpr_deletion("u_victim")
        assert report.projects_transferred == 1
        assert report.shared_tasks_anonymized == 1
        assert report.personal_tasks_deleted == 2
        assert report.user_deleted is True


# ── Feature 43: Custom Theme & Color Palette Creator ───────────────────────────

def test_hex_validation_and_progress_styles():
    assert theme_mod.normalize_hex_color("5865f2") == "#5865F2"
    with pytest.raises(ValueError):
        theme_mod.normalize_hex_color("not-a-hex")

    assert "[" in theme_mod.render_progress_bar(50, "retro", width=10)
    assert "●" in theme_mod.render_progress_bar(50, "minimal", width=10)
    assert "🟩" in theme_mod.render_progress_bar(50, "blocks", width=10)
    assert "▰" in theme_mod.render_progress_bar(50, "neon", width=10)


@pytest.mark.asyncio
async def test_palette_resolution_hierarchy():
    with patch.object(
        db,
        "afetchone",
        side_effect=[
            None,  # no active user custom theme
            {"guild_id": "g1", "name": "Guild Neon", "primary_color": "#FF00AA", "progress_style": "blocks"},
        ],
    ), patch("utils.helpers.get_user_theme", new=AsyncMock(return_value="default")):
        pal = await theme_mod.resolve_user_palette("u1", guild_id="g1")
        assert pal.source == "guild_custom"
        assert pal.primary_color == "#FF00AA"
        assert pal.progress_style == "blocks"


# ── Feature 44: Mobile-Optimized Compact View Mode ─────────────────────────────

def test_compact_view_mode_cuts_embed_bloat_by_over_45_percent():
    now = datetime.now(timezone.utc) + timedelta(hours=5)
    tasks = [
        {
            "task_id": i,
            "task": f"Implement mobile compact view test task #{i}",
            "status": "Pending",
            "priority": i % 7,
            "deadline": now.isoformat(),
            "is_pinned": 1 if i == 1 else 0,
        }
        for i in range(1, 9)
    ]
    std = build_task_list_embed(tasks, 1, 2, "en", "UTC", "Pending", 8, 0, display_mode="standard")
    cmp = build_task_list_embed(tasks, 1, 2, "en", "UTC", "Pending", 8, 0, display_mode="compact")

    assert len(cmp.description or "") < len(std.description or "") * 0.55
    assert "╰" not in (cmp.description or "")


# ── Feature 45: Reusable DoD Checklist Templates ───────────────────────────────

@pytest.mark.asyncio
async def test_dod_checklist_template_save_and_apply():
    existing_tpl_row = {
        "template_id": 5,
        "name": "Code Review DoD",
        "owner_id": "u1",
        "guild_id": None,
        "description": "Saved",
        "items": ["Run pytest", "Check flake8"],
        "is_shared": False,
        "usage_count": 1,
    }
    fake_item = SimpleNamespace(checklist_id=9, task_id=20, title="Check flake8", is_done=False, position=1)
    with patch.object(
        db,
        "afetchone",
        side_effect=[
            {"task_id": 20, "owner_id": "u1", "project_id": None, "guild_id": None},  # task owner check
            existing_tpl_row,  # get_checklist_template
        ],
    ), patch.object(
        routine_service,
        "get_checklists",
        new=AsyncMock(return_value=[SimpleNamespace(title="Run pytest")]),
    ), patch.object(
        routine_service, "add_checklist_item", new=AsyncMock(return_value=fake_item)
    ) as mock_add, patch.object(db, "aexecute", new=AsyncMock()):
        tpl, added = await routine_service.apply_checklist_template(20, "Code Review DoD", "u1")
        assert tpl.name == "Code Review DoD"
        assert added == 1
        mock_add.assert_awaited_once_with(20, "Check flake8")


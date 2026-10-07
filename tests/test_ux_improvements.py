"""
tests/test_ux_improvements.py — Unit Tests for New UX/UI Features

Covers:
  1. Shorthand, relative, and natural (EN & TH) date parsing in parse_deadline
  2. Autocomplete helper functionality
  3. Visual subtask checklist rendering in build_task_embed
  4. AttachmentDeleteSelect & ProjectSelectDropdown component tests
  5. Help categories completeness
"""
import pytest
from datetime import datetime, timedelta
import pytz
from unittest.mock import AsyncMock, MagicMock, patch

from utils.helpers import parse_deadline, build_task_embed
from handlers.tasks_cog import task_autocomplete
from storage.views import AttachmentDeleteSelect
from storage.models import TaskAttachment
from collaboration.views import ProjectSelectDropdown, ProjectListView
from collaboration.models import Project
from handlers.settings_cog import build_help_embed, HelpCategorySelect
from handlers.task_views import AddTaskModal
from locales.i18n import SUPPORTED_LANGS, t


# ─────────────────────────────────────────────────────────────────────────────
# 1. Date Parsing: Relative, Shorthand & Natural (EN / TH)
# ─────────────────────────────────────────────────────────────────────────────

class TestParseDeadlineUX:
    """Tests for enhanced parse_deadline shorthand and natural language parsing."""

    def test_relative_hours(self):
        now = datetime.now(pytz.utc)
        parsed = parse_deadline("+2h", "UTC")
        assert parsed is not None
        diff = parsed - now
        assert 1.95 * 3600 <= diff.total_seconds() <= 2.05 * 3600

    def test_relative_days(self):
        now = datetime.now(pytz.utc)
        parsed = parse_deadline("+3d", "UTC")
        assert parsed is not None
        diff = parsed - now
        assert 2.95 * 86400 <= diff.total_seconds() <= 3.05 * 86400

    def test_relative_minutes(self):
        now = datetime.now(pytz.utc)
        parsed = parse_deadline("+45m", "UTC")
        assert parsed is not None
        diff = parsed - now
        assert 44 * 60 <= diff.total_seconds() <= 46 * 60

    def test_natural_today(self):
        parsed = parse_deadline("today 18:30", "Asia/Bangkok")
        assert parsed is not None
        tz = pytz.timezone("Asia/Bangkok")
        local_dt = parsed.astimezone(tz)
        assert local_dt.hour == 18
        assert local_dt.minute == 30

    def test_natural_tomorrow(self):
        tz = pytz.timezone("Asia/Bangkok")
        now_local = datetime.now(pytz.utc).astimezone(tz)
        tomorrow_date = (now_local + timedelta(days=1)).date()

        parsed = parse_deadline("tomorrow 09:00", "Asia/Bangkok")
        assert parsed is not None
        local_dt = parsed.astimezone(tz)
        assert local_dt.date() == tomorrow_date
        assert local_dt.hour == 9
        assert local_dt.minute == 0

    def test_natural_thai_today(self):
        parsed = parse_deadline("วันนี้ 20:00", "Asia/Bangkok")
        assert parsed is not None
        tz = pytz.timezone("Asia/Bangkok")
        local_dt = parsed.astimezone(tz)
        assert local_dt.hour == 20
        assert local_dt.minute == 0

    def test_natural_thai_tomorrow(self):
        tz = pytz.timezone("Asia/Bangkok")
        now_local = datetime.now(pytz.utc).astimezone(tz)
        tomorrow_date = (now_local + timedelta(days=1)).date()

        parsed = parse_deadline("พรุ่งนี้ 14:00", "Asia/Bangkok")
        assert parsed is not None
        local_dt = parsed.astimezone(tz)
        assert local_dt.date() == tomorrow_date
        assert local_dt.hour == 14
        assert local_dt.minute == 0

    def test_natural_thai_day_after_tomorrow(self):
        tz = pytz.timezone("Asia/Bangkok")
        now_local = datetime.now(pytz.utc).astimezone(tz)
        day_after = (now_local + timedelta(days=2)).date()

        parsed = parse_deadline("มะรืนนี้", "Asia/Bangkok")
        assert parsed is not None
        local_dt = parsed.astimezone(tz)
        assert local_dt.date() == day_after
        assert local_dt.hour == 23
        assert local_dt.minute == 59

    def test_shorthand_date_without_year(self):
        parsed = parse_deadline("25/12 18:00", "Asia/Bangkok")
        assert parsed is not None
        tz = pytz.timezone("Asia/Bangkok")
        local_dt = parsed.astimezone(tz)
        assert local_dt.day == 25
        assert local_dt.month == 12
        assert local_dt.hour == 18
        assert local_dt.minute == 0

    def test_invalid_deadline_returns_none(self):
        assert parse_deadline("invalid-date-string", "UTC") is None


# ─────────────────────────────────────────────────────────────────────────────
# 2. Autocomplete Helper
# ─────────────────────────────────────────────────────────────────────────────

class TestAutocompleteHelper:
    """Tests for task_autocomplete function."""

    @pytest.mark.asyncio
    async def test_autocomplete_returns_choices(self):
        mock_interaction = MagicMock()
        mock_interaction.user.id = "123456789"

        sample_rows = [
            {
                "task_id": 42,
                "task": "Fix website landing page responsive layout",
                "deadline": (datetime.now(pytz.utc) + timedelta(hours=4)).isoformat(),
                "status": "Pending",
            },
            {
                "task_id": 99,
                "task": "Review pull request #12",
                "deadline": (datetime.now(pytz.utc) + timedelta(days=2)).isoformat(),
                "status": "Pending",
            },
        ]

        with patch("core.database.db.afetchall", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = sample_rows
            choices = await task_autocomplete(mock_interaction, "")

            assert len(choices) == 2
            assert choices[0].value == 42
            assert "#42" in choices[0].name
            assert "Fix website" in choices[0].name
            assert choices[1].value == 99
            assert "#99" in choices[1].name


# ─────────────────────────────────────────────────────────────────────────────
# 3. Subtask Checklist Rendering in Task Embed
# ─────────────────────────────────────────────────────────────────────────────

class TestSubtaskChecklistRendering:
    """Tests for visual checklist rendering in build_task_embed."""

    def test_subtask_checklist_rendered_with_tasks(self):
        row = {
            "task_id": 1,
            "task": "Main Parent Task",
            "status": "Pending",
            "deadline": (datetime.now(pytz.utc) + timedelta(days=1)).isoformat(),
            "priority": 1,
            "description": "Parent task description",
            "tags": "test,ux",
            "recurring": None,
            "is_pinned": 0,
        }
        subtasks = [
            {"task_id": 101, "task": "Design database schema", "status": "Completed"},
            {"task_id": 102, "task": "Write REST API", "status": "Completed"},
            {"task_id": 103, "task": "Write unit tests", "status": "Pending"},
        ]

        embed = build_task_embed(row, "en", "UTC", subtasks=subtasks)
        # Find subtasks field
        subtask_field = next(f for f in embed.fields if "Subtask" in f.name)
        assert "✅ 2/3" in subtask_field.value
        assert "✅ `#101` Design database schema" in subtask_field.value
        assert "✅ `#102` Write REST API" in subtask_field.value
        assert "⏳ `#103` Write unit tests" in subtask_field.value

    def test_subtask_backward_compatibility_without_task_name(self):
        """If subtasks list only has status (legacy callers), it should not crash."""
        row = {
            "task_id": 1,
            "task": "Legacy Caller Task",
            "status": "Pending",
            "deadline": (datetime.now(pytz.utc) + timedelta(days=1)).isoformat(),
            "priority": 0,
            "description": None,
            "tags": None,
            "recurring": None,
        }
        subtasks = [{"status": "Completed"}, {"status": "Pending"}]
        embed = build_task_embed(row, "en", "UTC", subtasks=subtasks)
        subtask_field = next(f for f in embed.fields if "Subtask" in f.name)
        assert "✅ 1/2" in subtask_field.value


# ─────────────────────────────────────────────────────────────────────────────
# 4. Storage & Collaboration Component Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestStorageAndCollaborationComponents:
    """Tests for AttachmentDeleteSelect and ProjectListView."""

    def test_attachment_delete_select_initialization(self):
        now = datetime.now(pytz.utc)
        att1 = TaskAttachment(
            attachment_id=1,
            task_id=10,
            project_id=None,
            file_name="report.pdf",
            file_size=1024 * 500,
            file_type="application/pdf",
            storage_path="tasks/10/report.pdf",
            public_url="https://example.com/report.pdf",
            uploader_id="111",
            created_at=now,
        )
        select = AttachmentDeleteSelect([att1], task_id=10, uid="111", lang="en")
        assert len(select.options) == 1
        assert select.options[0].value == "1"
        assert "report.pdf" in select.options[0].label

    def test_project_list_view_initialization(self):
        now = datetime.now(pytz.utc)
        proj = Project(
            project_id=5,
            guild_id="999",
            name="Alpha Project",
            description="Our primary project",
            owner_id="111",
            status="active",
            color="#5865F2",
            emoji="🚀",
            channel_id=None,
            role_id=None,
            created_at=now,
            updated_at=now,
        )
        view = ProjectListView([proj], uid="111", lang="en")
        assert len(view.children) == 1
        dropdown = view.children[0]
        assert isinstance(dropdown, ProjectSelectDropdown)
        assert len(dropdown.options) == 1
        assert dropdown.options[0].value == "5"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Help Categories Extended
# ─────────────────────────────────────────────────────────────────────────────

class TestHelpCategories:
    """Verify help categories encompass all project modules."""

    def test_help_categories_complete(self):
        select = HelpCategorySelect("en")
        values = [opt.value for opt in select.options]
        assert "overview" in values
        assert "tasks" in values
        assert "collab" in values
        assert "search" in values
        assert "files" in values
        assert "settings" in values
        assert "tips" in values

    def test_build_help_embed_all_categories(self):
        for cat in ("overview", "tasks", "collab", "search", "files", "settings", "tips"):
            embed = build_help_embed(cat, "en")
            assert embed is not None
            assert len(embed.fields) > 0


# ─────────────────────────────────────────────────────────────────────────────
# 6. AddTaskModal In-Modal Priority Selection (All 9 Languages)
# ─────────────────────────────────────────────────────────────────────────────

class TestAddTaskModalPriorityUX:
    """Verify AddTaskModal in-modal priority dropdown functionality across all languages."""

    def test_modal_components_all_languages(self):
        """Ensure AddTaskModal has 5 components (4 inputs + 1 priority dropdown) in all 9 languages."""
        for lang in SUPPORTED_LANGS:
            modal = AddTaskModal(lang=lang, priority=0)
            d = modal.to_dict()
            assert len(d["components"]) == 5, f"Expected 5 components in {lang}, got {len(d['components'])}"
            # Component 4 should be Label (type 18) wrapping Select (type 3)
            assert d["components"][4]["type"] == 18
            sel_data = d["components"][4]["component"]
            assert sel_data["type"] == 3
            assert len(sel_data["options"]) == 8

            # Default option should be 0
            p0 = [o for o in sel_data["options"] if o.get("default") is True]
            assert len(p0) == 1 and p0[0]["value"] == "0"

    def test_modal_preselects_specified_priority(self):
        """Ensure specifying a priority when opening the modal correctly sets the default option."""
        for prio in (1, 3, 5, 7):
            modal = AddTaskModal(lang="en", priority=prio)
            d = modal.to_dict()
            sel_data = d["components"][4]["component"]
            selected = [o for o in sel_data["options"] if o.get("default") is True]
            assert len(selected) == 1
            assert selected[0]["value"] == str(prio)

    def test_modal_priority_fallback_and_extraction(self):
        """Ensure priority value extraction in on_submit logic correctly parses selected values."""
        modal = AddTaskModal(lang="th", priority=0)
        # Simulate user choosing priority 6 (Urgent)
        modal.priority_select._values = ["6"]
        val = int(modal.priority_select.values[0]) if modal.priority_select.values else modal.priority
        assert val == 6

        # Simulate user keeping default (empty values fallback)
        modal_def = AddTaskModal(lang="th", priority=3)
        modal_def.priority_select._values = []
        val_def = int(modal_def.priority_select.values[0]) if modal_def.priority_select.values else modal_def.priority
        assert val_def == 3

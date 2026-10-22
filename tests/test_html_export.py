"""
tests/test_html_export.py — Unit tests for Category 10: Standalone Interactive HTML Export
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from history_reporting import service as history_service


# ─────────────────────────────────────────────────────────────────────────────
# 1. HTML Generator & Offline Compliance Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_generate_interactive_html_zero_external_cdns():
    sample_tasks = [
        {
            "task_id": 1,
            "task": "Review Q4 budget",
            "status": "pending",
            "priority": 4,
            "deadline": "2026-10-25T18:00:00",
            "description": "Cross-check with accounting team",
            "tags": "finance,urgent",
            "category_id": 1,
            "is_pinned": True,
        },
        {
            "task_id": 2,
            "task": "Clean desk",
            "status": "completed",
            "priority": 1,
            "deadline": None,
            "description": "",
            "tags": "personal",
            "category_id": 2,
            "is_pinned": False,
        },
    ]
    sample_cats = [
        {"category_id": 1, "name": "Finance", "emoji": "💰", "color": "#10b981"},
        {"category_id": 2, "name": "General", "emoji": "📝", "color": "#6366f1"},
    ]

    html = history_service.generate_interactive_html(
        tasks=sample_tasks,
        categories=sample_cats,
        user_id="123456789",
        tz_name="Asia/Bangkok",
        lang="en",
        theme="dark",
    )

    # 1. Must be completely offline — zero CDN or external script/font links
    assert "https://" not in html.lower()
    assert "http://" not in html.lower()
    assert "<script src=" not in html.lower()
    assert "<link rel=\"stylesheet\"" not in html.lower()

    # 2. Must contain system font stack
    assert "-apple-system" in html
    assert "BlinkMacSystemFont" in html

    # 3. Must contain dark/light CSS variables & print media query
    assert "data-theme=\"dark\"" in html
    assert "@media print" in html
    assert "--card-bg:" in html

    # 4. Header & user metadata
    assert "User: 123456789" in html
    assert "Asia/Bangkok" in html

    # 5. Stats counters
    assert 'id="valTotal">2<' in html
    assert 'id="valCompleted">1<' in html
    assert 'id="valPending">1<' in html

    # 6. Interactive controls & elements
    assert 'id="searchBox"' in html
    assert 'id="themeBtn"' in html
    assert 'onclick="toggleTheme()"' in html
    assert 'class="task-checkbox"' in html
    assert 'onchange="toggleTask(' in html

    # 7. Vanilla JS logic
    assert "function toggleTask" in html
    assert "function applyFilters" in html
    assert "function recalculateStats" in html


def test_generate_interactive_html_empty_tasks():
    html = history_service.generate_interactive_html(
        tasks=[],
        categories=[],
        user_id="999",
        tz_name="UTC",
        lang="th",
    )
    assert 'id="valTotal">0<' in html
    assert 'id="valCompleted">0<' in html
    assert "No tasks found." in html


def test_build_html_export_bytes():
    sample_tasks = [{"task_id": 5, "task": "Test Task", "status": "pending", "priority": 2}]
    byte_stream = history_service.build_html_export_bytes(
        tasks=sample_tasks,
        categories=[],
        user_id="user_test",
        tz_name="UTC",
    )
    assert isinstance(byte_stream, io.BytesIO)
    content = byte_stream.getvalue().decode("utf-8")
    assert "<!DOCTYPE html>" in content
    assert "Test Task" in content


# ─────────────────────────────────────────────────────────────────────────────
# 2. /export Command Routing Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_export_slash_command_html_and_csv():
    from handlers.tasks_cog import TasksCog

    bot = MagicMock()
    cog = TasksCog(bot)

    interaction = MagicMock()
    interaction.user.id = 12345
    interaction.response.send_message = AsyncMock()

    sample_tasks = [{"task_id": 1, "task": "Task A", "status": "Pending", "priority": 1, "deadline": None, "recurring": None, "category_id": None, "tags": None, "description": None, "created_at": None}]
    sample_cats = [{"category_id": 1, "name": "General", "emoji": "📝", "color": "#6366f1"}]

    with patch("handlers.tasks_cog.get_user_lang", new=AsyncMock(return_value="en")), \
         patch("handlers.tasks_cog.get_user_timezone", new=AsyncMock(return_value="UTC")), \
         patch("handlers.tasks_cog.db.afetchall", new=AsyncMock(side_effect=[sample_tasks, sample_cats, sample_tasks])), \
         patch("handlers.tasks_cog.db.alog_action", new=AsyncMock()):

        # 1. Default format (HTML)
        await cog.export.callback(cog, interaction, format=None)
        assert interaction.response.send_message.called
        call_args = interaction.response.send_message.call_args[1]
        assert "html" in call_args["file"].filename

        # 2. Explicit CSV format
        csv_choice = MagicMock()
        csv_choice.value = "csv"
        interaction.response.send_message.reset_mock()
        await cog.export.callback(cog, interaction, format=csv_choice)
        assert interaction.response.send_message.called
        call_args_csv = interaction.response.send_message.call_args[1]
        assert "csv" in call_args_csv["file"].filename

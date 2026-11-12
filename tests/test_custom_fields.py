"""
tests/test_custom_fields.py — Unit tests for Feature 36: Dynamic JSONB Meta-Fields Engine (/field).
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from custom_fields import service as field_service
from custom_fields.models import (
    CustomFieldType,
    ProjectCustomField,
    normalize_field_key,
    parse_custom_fields_json,
)
from custom_fields.views import TaskCustomFieldsView
from utils.helpers import build_task_embed


def test_normalize_key_and_json_helpers():
    assert normalize_field_key("Environment Name") == "environment_name"
    thai_key = normalize_field_key("สภาพแวดล้อม")
    assert thai_key.startswith("cf_")
    assert parse_custom_fields_json('{"env": "Staging", "sev": 3}') == {"env": "Staging", "sev": 3}


def test_validate_and_coerce_all_4_field_types():
    f_select = ProjectCustomField(1, 1, "g1", "env", "Environment", "select", ["Staging", "Production"])
    f_text   = ProjectCustomField(2, 1, "g1", "pr_link", "PR Link", "text", is_required=False)
    f_num    = ProjectCustomField(3, 1, "g1", "severity", "Severity", "number", is_required=True)
    f_date   = ProjectCustomField(4, 1, "g1", "qa_date", "QA Date", "date")

    assert field_service.validate_and_coerce_value(f_select, "staging") == "Staging"
    with pytest.raises(field_service.CustomFieldValidationError):
        field_service.validate_and_coerce_value(f_select, "Unknown")

    assert field_service.validate_and_coerce_value(f_text, "https://github.com/org/repo/pull/12") == "https://github.com/org/repo/pull/12"
    assert field_service.validate_and_coerce_value(f_text, "   ") is None

    assert field_service.validate_and_coerce_value(f_num, "1,500") == 1500
    assert field_service.validate_and_coerce_value(f_num, "4.5") == 4.5
    with pytest.raises(field_service.CustomFieldValidationError):
        field_service.validate_and_coerce_value(f_num, "")  # required!
    with pytest.raises(field_service.CustomFieldValidationError):
        field_service.validate_and_coerce_value(f_num, "not_a_number")

    assert field_service.validate_and_coerce_value(f_date, "25/12/2026") == "2026-12-25"
    with pytest.raises(field_service.CustomFieldValidationError):
        field_service.validate_and_coerce_value(f_date, "31/02/2026")


@pytest.mark.asyncio
async def test_filter_tasks_uses_gin_containment_and_text_jsonb_operators():
    fake_proj = SimpleNamespace(project_id=2, guild_id="g1", owner_id="u1", name="WebApp")
    defs = [
        ProjectCustomField(1, 2, "g1", "env", "Environment", CustomFieldType.SELECT.value, ["Staging", "Production"]),
        ProjectCustomField(2, 2, "g1", "pr_link", "PR Link", CustomFieldType.TEXT.value),
    ]
    queries: list[str] = []

    async def fake_fetchall(sql, params):
        queries.append(sql)
        return [{"task_id": 101, "task": "Deploy API", "status": "Pending", "priority": 4, "deadline": "", "custom_fields": {"env": "Production"}}]

    with patch("collaboration.service.get_project", new=AsyncMock(return_value=fake_proj)), \
         patch("custom_fields.service.list_field_definitions", new=AsyncMock(return_value=defs)), \
         patch.object(field_service.db, "afetchall", new=AsyncMock(side_effect=fake_fetchall)):
        _, rows_sel = await field_service.filter_tasks_by_custom_field(
            project_id=2, guild_id="g1", field_key="env", raw_value="production", actor_id="u1"
        )
        _, rows_txt = await field_service.filter_tasks_by_custom_field(
            project_id=2, guild_id="g1", field_key="pr_link", raw_value="github.com", actor_id="u1"
        )

    assert len(rows_sel) == 1
    assert "custom_fields @>" in queries[0]
    assert "custom_fields ?" in queries[1] and "->>" in queries[1]


@pytest.mark.asyncio
async def test_custom_fields_panel_and_task_embed_integration():
    defs = [
        ProjectCustomField(1, 2, "g1", "env", "Environment", "select", ["Staging", "Production"]),
        ProjectCustomField(2, 2, "g1", "severity", "Severity", "number"),
    ]
    panel = TaskCustomFieldsView(
        task_id=88,
        task_title="Fix login bug",
        project_id=2,
        guild_id="g1",
        field_defs=defs,
        current_values={"env": "Production", "severity": 5},
        lang="en",
    )
    embed = panel.make_embed()
    assert "#88" in embed.title
    assert len(embed.fields) == 2
    assert panel.edit_inputs_btn.disabled is False

    task_row = {
        "task_id": 88,
        "task": "Fix login bug",
        "deadline": "2026-12-01T10:00:00+00:00",
        "priority": 5,
        "status": "Pending",
        "description": "Login redirect issue",
        "tags": "fix",
        "recurring": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    task_embed = build_task_embed(
        task_row,
        lang="en",
        tz_name="UTC",
        custom_fields=[("🔽 Environment", "Production"), ("🔢 Severity", "5")],
    )
    assert any("Custom Fields" in f.name and "Production" in f.value for f in task_embed.fields)


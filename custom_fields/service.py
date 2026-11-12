"""
custom_fields/service.py — Schema registry, JSONB coercion, GIN filtering & task field CRUD.
"""
from __future__ import annotations

import json
import logging
import math
import re
from datetime import datetime
from typing import Any, Optional

from core.database import db
from core.security import validator
from custom_fields.models import (
    MAX_FIELDS_PER_PROJECT,
    MAX_SELECT_OPTIONS,
    CustomFieldType,
    ProjectCustomField,
    normalize_field_key,
    parse_custom_fields_json,
    parse_options_list,
)
from utils.helpers import ensure_user

log = logging.getLogger(__name__)

_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)


class CustomFieldError(Exception):
    """Base error carrying an i18n key for custom fields operations."""


class CustomFieldValidationError(CustomFieldError):
    """Raised when a custom field schema or value fails type validation."""


class CustomFieldAccessDenied(CustomFieldError):
    """Raised when caller lacks permission for the target project or task."""


def _parse_iso_date(raw: str) -> Optional[str]:
    text = raw.strip()
    if not text:
        return None
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        try:
            datetime.strptime(text[:10], "%Y-%m-%d")
            return text[:10]
        except ValueError:
            pass
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def validate_and_coerce_value(
    field_def: ProjectCustomField,
    raw_value: Optional[str],
) -> Any:
    """Validate and convert user string input into the exact JSONB value for ``field_def.field_type``."""
    if raw_value is None or not str(raw_value).strip():
        if field_def.is_required:
            raise CustomFieldValidationError("field_value_required")
        return None

    text = str(raw_value).strip()
    ftype = field_def.field_type

    if ftype == CustomFieldType.SELECT.value:
        lower_map = {opt.lower(): opt for opt in field_def.options}
        matched = lower_map.get(text.lower())
        if matched is None:
            raise CustomFieldValidationError("field_invalid_select_option")
        return matched

    if ftype == CustomFieldType.NUMBER.value:
        cleaned_num = text.replace(",", "").strip()
        try:
            if "." not in cleaned_num and "e" not in cleaned_num.lower():
                return int(cleaned_num)
            num_val = float(cleaned_num)
            if not math.isfinite(num_val):
                raise ValueError("non-finite")
            return int(num_val) if num_val.is_integer() else num_val
        except ValueError:
            raise CustomFieldValidationError("field_invalid_number")

    if ftype == CustomFieldType.DATE.value:
        iso_date = _parse_iso_date(text)
        if not iso_date:
            raise CustomFieldValidationError("field_invalid_date")
        return iso_date

    # Default: TEXT
    cleaned_text = validator.sanitize(text, 500)
    if not cleaned_text:
        if field_def.is_required:
            raise CustomFieldValidationError("field_value_required")
        return None
    if cleaned_text.lower().startswith(("http://", "https://")) and not _URL_RE.match(cleaned_text):
        raise CustomFieldValidationError("field_invalid_text")
    return cleaned_text


async def create_field_definition(
    project_id: int,
    guild_id: str,
    actor_id: str,
    label: str,
    field_type: str,
    options_csv: Optional[str] = None,
    field_key: Optional[str] = None,
    is_required: bool = False,
    is_guild_admin: bool = False,
) -> ProjectCustomField:
    """Define a new dynamic custom meta-field for ``project_id`` (Lead / Owner / Admin)."""
    from collaboration import service as collab_service

    project = await collab_service.get_project(project_id, guild_id)
    try:
        await collab_service.require_role(project, actor_id, "lead", is_guild_admin=is_guild_admin)
    except collab_service.ProjectPermissionError:
        raise CustomFieldAccessDenied("proj_no_permission")

    clean_label = validator.sanitize(label, 60)
    if not clean_label:
        raise CustomFieldValidationError("field_invalid_label")

    norm_type = (field_type or "").strip().lower()
    if norm_type not in {t.value for t in CustomFieldType}:
        raise CustomFieldValidationError("field_invalid_type")

    options: list[str] = []
    if norm_type == CustomFieldType.SELECT.value:
        raw_opts = parse_options_list(options_csv)
        deduped: list[str] = []
        seen: set[str] = set()
        for opt in raw_opts:
            clean_opt = validator.sanitize(opt, 60)
            if clean_opt and clean_opt.lower() not in seen:
                seen.add(clean_opt.lower())
                deduped.append(clean_opt)
        if not deduped or len(deduped) > MAX_SELECT_OPTIONS:
            raise CustomFieldValidationError("field_invalid_options_count")
        options = deduped

    existing = await list_field_definitions(project_id, guild_id)
    if len(existing) >= MAX_FIELDS_PER_PROJECT:
        raise CustomFieldValidationError("field_limit_reached")

    key = normalize_field_key(field_key or clean_label)
    if any(f.field_key == key for f in existing):
        raise CustomFieldValidationError("field_duplicate_key")

    await ensure_user(actor_id)
    row = await db.afetchone(
        """INSERT INTO project_custom_fields
               (project_id, guild_id, field_key, field_label, field_type, options_json, is_required, created_by)
           VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8)
           RETURNING *""",
        (
            project_id,
            guild_id,
            key,
            clean_label,
            norm_type,
            json.dumps(options),
            bool(is_required),
            actor_id,
        ),
    )
    db.query_cache.invalidate_table("project_custom_fields")
    await collab_service.log_activity(
        project_id, guild_id, actor_id, "field_created", f"{key} ({norm_type})"
    )
    return ProjectCustomField.from_row(row)


async def list_field_definitions(project_id: int, guild_id: str) -> list[ProjectCustomField]:
    """Return all custom meta-field schemas defined on ``project_id`` in creation order."""
    rows = await db.afetchall(
        """SELECT * FROM project_custom_fields
           WHERE project_id = $1 AND guild_id = $2
           ORDER BY field_id ASC""",
        (project_id, guild_id),
    )
    return [ProjectCustomField.from_row(r) for r in (rows or [])]


async def delete_field_definition(
    project_id: int,
    guild_id: str,
    field_key: str,
    actor_id: str,
    is_guild_admin: bool = False,
) -> bool:
    """Delete a custom field definition and strip its key from tasks JSONB payloads."""
    from collaboration import service as collab_service

    project = await collab_service.get_project(project_id, guild_id)
    try:
        await collab_service.require_role(project, actor_id, "lead", is_guild_admin=is_guild_admin)
    except collab_service.ProjectPermissionError:
        raise CustomFieldAccessDenied("proj_no_permission")

    norm_key = normalize_field_key(field_key)
    row = await db.afetchone(
        """DELETE FROM project_custom_fields
           WHERE project_id = $1 AND guild_id = $2 AND (field_key = $3 OR field_key = $4)
           RETURNING field_key""",
        (project_id, guild_id, field_key.strip().lower(), norm_key),
    )
    if not row:
        raise CustomFieldValidationError("field_not_found")

    removed_key = str(row["field_key"])
    await db.aexecute(
        """UPDATE tasks
              SET custom_fields = COALESCE(custom_fields, '{}'::jsonb) - $1,
                  updated_at = NOW()
            WHERE project_id = $2 AND guild_id = $3 AND custom_fields ? $1""",
        (removed_key, project_id, guild_id),
    )
    db.query_cache.invalidate_tables(["project_custom_fields", "tasks"])
    await collab_service.log_activity(project_id, guild_id, actor_id, "field_deleted", removed_key)
    return True


async def _fetch_task_for_field_write(
    task_id: int,
    guild_id: str,
    actor_id: str,
    is_guild_admin: bool = False,
) -> dict[str, Any]:
    row = await db.afetchone(
        """SELECT task_id, task, owner_id, project_id, guild_id, custom_fields, is_deleted
           FROM tasks WHERE task_id = $1 AND is_deleted = FALSE""",
        (task_id,),
    )
    if not row:
        raise CustomFieldValidationError("field_task_not_found")
    if not row.get("project_id") or str(row.get("guild_id") or "") != guild_id:
        raise CustomFieldValidationError("field_project_task_required")

    if not is_guild_admin and str(row["owner_id"]) != actor_id:
        from collaboration import service as collab_service
        proj_id = int(row["project_id"])
        can_edit = await collab_service.check_project_permission(
            proj_id, actor_id, "can_edit_tasks", is_guild_admin=is_guild_admin
        )
        if not can_edit:
            role = await collab_service.get_member_role(proj_id, actor_id)
            if role not in ("lead", "member"):
                raise CustomFieldAccessDenied("proj_no_permission")
    return dict(row)


async def set_task_custom_fields_batch(
    task_id: int,
    guild_id: str,
    updates: dict[str, Optional[str]],
    actor_id: str,
    is_guild_admin: bool = False,
) -> dict[str, Any]:
    """Validate and atomically patch/unset custom field keys inside ``tasks.custom_fields`` JSONB."""
    task_row = await _fetch_task_for_field_write(task_id, guild_id, actor_id, is_guild_admin=is_guild_admin)
    proj_id = int(task_row["project_id"])
    defs = await list_field_definitions(proj_id, guild_id)
    def_map = {d.field_key: d for d in defs}
    label_map = {d.field_label.lower(): d for d in defs}

    patch: dict[str, Any] = {}
    clear_keys: list[str] = []

    for raw_k, raw_v in updates.items():
        k_lower = raw_k.strip().lower()
        field_def = def_map.get(k_lower) or label_map.get(k_lower) or def_map.get(normalize_field_key(raw_k))
        if not field_def:
            raise CustomFieldValidationError("field_not_found")
        coerced = validate_and_coerce_value(field_def, raw_v)
        if coerced is None:
            clear_keys.append(field_def.field_key)
        else:
            patch[field_def.field_key] = coerced

    if clear_keys and patch:
        row = await db.afetchone(
            """UPDATE tasks
                  SET custom_fields = (COALESCE(custom_fields, '{}'::jsonb) - $1::text[]) || $2::jsonb,
                      updated_at = NOW()
                WHERE task_id = $3 AND project_id = $4 AND is_deleted = FALSE
               RETURNING custom_fields""",
            (clear_keys, json.dumps(patch), task_id, proj_id),
        )
    elif clear_keys:
        row = await db.afetchone(
            """UPDATE tasks
                  SET custom_fields = COALESCE(custom_fields, '{}'::jsonb) - $1::text[],
                      updated_at = NOW()
                WHERE task_id = $2 AND project_id = $3 AND is_deleted = FALSE
               RETURNING custom_fields""",
            (clear_keys, task_id, proj_id),
        )
    elif patch:
        row = await db.afetchone(
            """UPDATE tasks
                  SET custom_fields = COALESCE(custom_fields, '{}'::jsonb) || $1::jsonb,
                      updated_at = NOW()
                WHERE task_id = $2 AND project_id = $3 AND is_deleted = FALSE
               RETURNING custom_fields""",
            (json.dumps(patch), task_id, proj_id),
        )
    else:
        return parse_custom_fields_json(task_row.get("custom_fields"))

    db.query_cache.invalidate_table("tasks")
    from collaboration import service as collab_service
    changed_keys = list(patch.keys()) + clear_keys
    await collab_service.log_activity(
        proj_id, guild_id, actor_id, "field_updated", f"#{task_id}: {', '.join(changed_keys)}"
    )
    return parse_custom_fields_json(row["custom_fields"] if row else {})


async def filter_tasks_by_custom_field(
    project_id: int,
    guild_id: str,
    field_key: str,
    raw_value: str,
    actor_id: str,
    is_guild_admin: bool = False,
) -> tuple[ProjectCustomField, list[dict[str, Any]]]:
    """Query tasks matching a custom field filter leveraging PostgreSQL JSONB GIN index."""
    from collaboration import service as collab_service

    project = await collab_service.get_project(project_id, guild_id)
    if not is_guild_admin and project.owner_id != actor_id:
        role = await collab_service.get_member_role(project_id, actor_id)
        if not role:
            raise CustomFieldAccessDenied("proj_no_permission")

    defs = await list_field_definitions(project_id, guild_id)
    def_map = {d.field_key: d for d in defs}
    field_def = def_map.get(field_key.strip().lower()) or def_map.get(normalize_field_key(field_key))
    if not field_def:
        raise CustomFieldValidationError("field_not_found")

    if field_def.field_type in (
        CustomFieldType.SELECT.value,
        CustomFieldType.NUMBER.value,
        CustomFieldType.DATE.value,
    ):
        coerced = validate_and_coerce_value(field_def, raw_value)
        containment = json.dumps({field_def.field_key: coerced})
        rows = await db.afetchall(
            """SELECT task_id, task, status, priority, deadline, custom_fields
               FROM tasks
               WHERE project_id = $1 AND guild_id = $2 AND is_deleted = FALSE
                 AND custom_fields @> $3::jsonb
               ORDER BY priority DESC, task_id DESC
               LIMIT 25""",
            (project_id, guild_id, containment),
        )
    else:
        rows = await db.afetchall(
            """SELECT task_id, task, status, priority, deadline, custom_fields
               FROM tasks
               WHERE project_id = $1 AND guild_id = $2 AND is_deleted = FALSE
                 AND custom_fields ? $3
                 AND (custom_fields ->> $3) ILIKE $4
               ORDER BY priority DESC, task_id DESC
               LIMIT 25""",
            (project_id, guild_id, field_def.field_key, f"%{raw_value.strip()}%"),
        )

    return field_def, [dict(r) for r in (rows or [])]


async def get_task_custom_fields_for_embed(
    project_id: Optional[int],
    guild_id: Optional[str],
    raw_custom_fields: Any,
) -> list[tuple[str, str]]:
    """Format stored JSONB custom fields alongside their project labels for Discord Embeds."""
    values = parse_custom_fields_json(raw_custom_fields)
    if not values:
        return []
    if not project_id or not guild_id:
        return [(f"🧩 `{k}`", str(v)) for k, v in list(values.items())[:10]]

    defs = await list_field_definitions(int(project_id), str(guild_id))
    def_by_key = {d.field_key: d for d in defs}
    result: list[tuple[str, str]] = []
    seen: set[str] = set()

    for d in defs:
        if d.field_key in values:
            result.append((f"{d.type_emoji} {d.field_label}", str(values[d.field_key])))
            seen.add(d.field_key)
    for k, v in values.items():
        if k not in seen:
            meta = def_by_key.get(k)
            lbl = f"{meta.type_emoji} {meta.field_label}" if meta else f"🧩 `{k}`"
            result.append((lbl, str(v)))
    return result

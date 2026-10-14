from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pytz

from core.security import validator
from utils.helpers import parse_deadline

MAX_IMPORT_BYTES = 1_000_000
MAX_IMPORT_TASKS = 500
_STATUSES = {"Pending", "In_Progress", "Completed", "Cancelled"}
_RECURRING = {"", "daily", "weekly", "monthly"}


class ImportValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ImportedTask:
    task: str
    deadline: str | None
    priority: int
    status: str
    recurring: str | None
    tags: str | None
    description: str | None
    is_pinned: bool


def _normalise_key(value: Any) -> str:
    return str(value or "").strip().casefold().replace(" ", "_")


def _get(record: dict[str, Any], *keys: str, default: Any = "") -> Any:
    normalised = {_normalise_key(key): value for key, value in record.items()}
    for key in keys:
        value = normalised.get(_normalise_key(key))
        if value is not None:
            return value
    return default


def _parse_records(data: bytes, filename: str) -> list[dict[str, Any]]:
    if len(data) > MAX_IMPORT_BYTES:
        raise ImportValidationError("The attached file exceeds the 1 MB limit.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportValidationError("The file must use UTF-8 encoding.") from exc
    if filename.lower().endswith(".json"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ImportValidationError(f"Invalid JSON: {exc.msg}.") from exc
        if isinstance(parsed, dict):
            parsed = parsed.get("tasks")
        if not isinstance(parsed, list) or any(not isinstance(row, dict) for row in parsed):
            raise ImportValidationError("JSON must be an array of task objects or an object with a tasks array.")
        records = parsed
    elif filename.lower().endswith(".csv"):
        try:
            records = list(csv.DictReader(io.StringIO(text, newline="")))
        except csv.Error as exc:
            raise ImportValidationError("Invalid CSV file.") from exc
        if not records:
            raise ImportValidationError("The CSV file contains no task rows.")
    else:
        raise ImportValidationError("Only .csv and .json files are supported.")
    if not records:
        raise ImportValidationError("The file contains no tasks.")
    if len(records) > MAX_IMPORT_TASKS:
        raise ImportValidationError(f"A file may contain at most {MAX_IMPORT_TASKS} tasks.")
    return records


def _parse_boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    normal = str(value or "").strip().casefold()
    if normal in {"", "false", "0", "no", "off"}:
        return False
    if normal in {"true", "1", "yes", "on"}:
        return True
    raise ValueError("Pinned must be true or false.")


def _parse_deadline(raw: Any, tz_name: str, deadline_policy: str) -> str | None:
    value = str(raw or "").strip()
    if not value:
        if deadline_policy == "no_deadline":
            return None
        if deadline_policy != "default_1_day":
            raise ValueError("Unknown missing-deadline policy.")
        return (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    parsed = parse_deadline(value, tz_name)
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = pytz.timezone(tz_name).localize(parsed)
            parsed = parsed.astimezone(timezone.utc)
        except (ValueError, pytz.exceptions.UnknownTimeZoneError) as exc:
            raise ValueError("Deadline could not be parsed.") from exc
    if parsed.year < 2000 or parsed.year > datetime.now(timezone.utc).year + 10:
        raise ValueError("Deadline year must be between 2000 and ten years from now.")
    return parsed.isoformat()


def parse_import_file(
    data: bytes,
    filename: str,
    tz_name: str,
    deadline_policy: str,
) -> list[ImportedTask]:
    records = _parse_records(data, filename)
    imported: list[ImportedTask] = []
    errors: list[str] = []
    for index, record in enumerate(records, start=2 if filename.lower().endswith(".csv") else 1):
        try:
            raw_name = _get(record, "task", "task_name", "name")
            ok, name_or_error = validator.validate_task_name(str(raw_name or ""))
            if not ok:
                raise ValueError("Task name is required or invalid.")
            priority_raw = str(_get(record, "priority", default="0")).strip()
            if not priority_raw.isdigit() or int(priority_raw) not in range(8):
                raise ValueError("Priority must be an integer from 0 to 7.")
            status = str(_get(record, "status", default="Pending") or "Pending").strip()
            if status not in _STATUSES:
                raise ValueError("Status must be Pending, In_Progress, Completed, or Cancelled.")
            recurring = str(_get(record, "recurring")).strip().lower()
            if recurring not in _RECURRING:
                raise ValueError("Recurring must be daily, weekly, monthly, or empty.")
            deadline = _parse_deadline(_get(record, "deadline"), tz_name, deadline_policy)
            if recurring and deadline is None:
                raise ValueError("Recurring tasks must have a deadline.")
            description_raw = str(_get(record, "description") or "").strip()
            description = None
            if description_raw:
                ok_description, description_or_error = validator.validate_description(description_raw)
                if not ok_description:
                    raise ValueError("Description is invalid.")
                description = description_or_error
            tags_raw = str(_get(record, "tags") or "").strip()
            tags = validator.sanitize(tags_raw, 200) if tags_raw else None
            if tags and validator.is_suspicious(tags):
                raise ValueError("Tags contain invalid content.")
            imported.append(ImportedTask(
                task=name_or_error,
                deadline=deadline,
                priority=int(priority_raw),
                status=status,
                recurring=recurring or None,
                tags=tags,
                description=description,
                is_pinned=_parse_boolean(_get(record, "pinned", "is_pinned")),
            ))
        except (TypeError, ValueError) as exc:
            errors.append(f"Row {index}: {exc}")
    if errors:
        preview = "; ".join(errors[:10])
        extra = f" ({len(errors) - 10} more errors)" if len(errors) > 10 else ""
        raise ImportValidationError(preview + extra)
    return imported

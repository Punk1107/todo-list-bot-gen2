"""
custom_fields/models.py — Data models & key normalization helpers for Dynamic Meta-Fields.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Optional

MAX_FIELDS_PER_PROJECT = 15
MAX_SELECT_OPTIONS = 25


class CustomFieldType(str, Enum):
    SELECT = "select"
    TEXT   = "text"
    NUMBER = "number"
    DATE   = "date"


FIELD_TYPE_EMOJI: dict[str, str] = {
    CustomFieldType.SELECT.value: "🔽",
    CustomFieldType.TEXT.value:   "📝",
    CustomFieldType.NUMBER.value: "🔢",
    CustomFieldType.DATE.value:   "📅",
}

_KEY_CLEAN_RE = re.compile(r"[^a-z0-9_]+")


def normalize_field_key(raw: str, max_len: int = 32) -> str:
    """Normalize a label/key into a safe lowercase snake_case JSONB key."""
    base = _KEY_CLEAN_RE.sub("_", (raw or "").strip().lower()).strip("_")
    if not base:
        digest = hashlib.md5((raw or "field").encode("utf-8")).hexdigest()[:6]
        return f"cf_{digest}"
    return base[:max_len].strip("_") or "cf_field"


def parse_options_list(raw_options: Any) -> list[str]:
    """Decode ``options_json`` from DB JSONB (list, JSON string, or CSV string)."""
    if raw_options is None:
        return []
    if isinstance(raw_options, list):
        return [str(x).strip() for x in raw_options if str(x).strip()]
    if isinstance(raw_options, str):
        text = raw_options.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                loaded = json.loads(text)
                if isinstance(loaded, list):
                    return [str(x).strip() for x in loaded if str(x).strip()]
            except Exception:
                pass
        return [part.strip() for part in text.replace("|", ",").split(",") if part.strip()]
    return []


def parse_custom_fields_json(raw: Any) -> dict[str, Any]:
    """Safely coerce ``tasks.custom_fields`` (dict or JSON string) into a Python dict."""
    if not raw:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return dict(parsed) if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


@dataclass
class ProjectCustomField:
    """Schema definition for one dynamic JSONB meta-field belonging to a project."""
    field_id: int
    project_id: int
    guild_id: str
    field_key: str
    field_label: str
    field_type: str
    options: list[str] = field(default_factory=list)
    is_required: bool = False
    created_by: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def type_emoji(self) -> str:
        return FIELD_TYPE_EMOJI.get(self.field_type, "🧩")

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "ProjectCustomField":
        created = row.get("created_at") or datetime.now(timezone.utc)
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        return cls(
            field_id=int(row["field_id"]),
            project_id=int(row["project_id"]),
            guild_id=str(row["guild_id"]),
            field_key=str(row["field_key"]),
            field_label=str(row["field_label"]),
            field_type=str(row["field_type"]),
            options=parse_options_list(row.get("options_json")),
            is_required=bool(row.get("is_required") or False),
            created_by=str(row["created_by"]) if row.get("created_by") is not None else None,
            created_at=created,
        )


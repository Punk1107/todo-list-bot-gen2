"""
knowledge_base/models.py — Data models and Markdown pagination/slug helpers for Wiki Docs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Optional


class DocType(str, Enum):
    REQUIREMENT = "requirement"
    DESIGN      = "design"
    SOP         = "sop"
    GENERAL     = "general"


DOC_TYPE_EMOJI: dict[str, str] = {
    DocType.REQUIREMENT.value: "📋",
    DocType.DESIGN.value:      "🎨",
    DocType.SOP.value:         "📘",
    DocType.GENERAL.value:     "📄",
}

_SLUG_CLEAN_RE = re.compile(r"[^\w\s-]", re.UNICODE)
_SLUG_DASH_RE = re.compile(r"[-\s]+")


def slugify_title(text: str, max_len: int = 60) -> str:
    """Convert an arbitrary document title into a clean URL/command-friendly slug."""
    cleaned = _SLUG_CLEAN_RE.sub("", (text or "").strip().lower())
    slug = _SLUG_DASH_RE.sub("-", cleaned).strip("-_")
    if not slug:
        slug = "doc"
    return slug[:max_len].strip("-_") or "doc"


def split_markdown_pages(content: str, max_chars: int = 3400) -> list[str]:
    """Split Markdown content into pages <= ``max_chars`` respecting paragraph boundaries."""
    text = (content or "").strip()
    if not text:
        return ["*(empty document)*"]
    if len(text) <= max_chars:
        return [text]

    pages: list[str] = []
    paragraphs = text.split("\n\n")
    buf: list[str] = []
    cur_len = 0

    for para in paragraphs:
        # Handle single huge paragraph > max_chars line by line
        if len(para) > max_chars:
            if buf:
                pages.append("\n\n".join(buf))
                buf, cur_len = [], 0
            for line in para.splitlines():
                while len(line) > max_chars:
                    pages.append(line[:max_chars])
                    line = line[max_chars:]
                extra = len(line) + (1 if buf else 0)
                if cur_len + extra > max_chars and buf:
                    pages.append("\n".join(buf))
                    buf, cur_len = [line], len(line)
                else:
                    buf.append(line)
                    cur_len += extra
            if buf:
                pages.append("\n".join(buf))
                buf, cur_len = [], 0
            continue

        sep = 2 if buf else 0
        if cur_len + sep + len(para) > max_chars and buf:
            pages.append("\n\n".join(buf))
            buf = [para]
            cur_len = len(para)
        else:
            buf.append(para)
            cur_len += sep + len(para)

    if buf:
        pages.append("\n\n".join(buf))
    return pages or [text[:max_chars]]


def extract_snippet(content: str, query: str, window: int = 120) -> str:
    """Extract a short search-result snippet highlighting the matched region."""
    plain = " ".join((content or "").split())
    if not plain:
        return "*(empty)*"
    q = (query or "").strip()
    if not q:
        return plain[:window] + ("..." if len(plain) > window else "")
    idx = plain.lower().find(q.lower())
    if idx < 0:
        first_word = q.split()[0] if q.split() else ""
        idx = plain.lower().find(first_word.lower()) if first_word else -1
    if idx < 0:
        return plain[:window] + ("..." if len(plain) > window else "")
    start = max(0, idx - 40)
    end = min(len(plain), start + window)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(plain) else ""
    return f"{prefix}{plain[start:end]}{suffix}"


@dataclass
class ProjectDocument:
    """A Markdown wiki document scoped to a Discord guild (and optionally project/task)."""
    doc_id: int
    guild_id: Optional[str]
    project_id: Optional[int]
    task_id: Optional[int]
    title: str
    slug: Optional[str]
    doc_type: str
    content_markdown: str
    author_id: Optional[str]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    project_name: Optional[str] = None
    rank: float = 0.0

    @property
    def type_emoji(self) -> str:
        return DOC_TYPE_EMOJI.get(self.doc_type, "📄")

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "ProjectDocument":
        created = row.get("created_at") or datetime.now(timezone.utc)
        updated = row.get("updated_at") or datetime.now(timezone.utc)
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        if isinstance(updated, str):
            updated = datetime.fromisoformat(updated)
        return cls(
            doc_id=int(row["doc_id"]),
            guild_id=str(row["guild_id"]) if row.get("guild_id") is not None else None,
            project_id=int(row["project_id"]) if row.get("project_id") is not None else None,
            task_id=int(row["task_id"]) if row.get("task_id") is not None else None,
            title=str(row["title"]),
            slug=row.get("slug"),
            doc_type=str(row.get("doc_type") or DocType.GENERAL.value),
            content_markdown=str(row.get("content_markdown") or ""),
            author_id=str(row["author_id"]) if row.get("author_id") is not None else None,
            created_at=created,
            updated_at=updated,
            project_name=row.get("project_name"),
            rank=float(row.get("rank") or 0.0),
        )


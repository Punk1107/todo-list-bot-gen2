"""
storage/models.py — Task Attachment Data Model

Lightweight dataclass that maps 1-to-1 with the task_attachments database table.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


# ── File type groupings ────────────────────────────────────────────────────────

_IMAGE_EXTS    = frozenset({"png", "jpg", "jpeg", "gif", "webp", "svg", "bmp"})
_DOC_EXTS      = frozenset({"pdf", "docx", "xlsx", "pptx", "odt", "ods", "odp"})
_TEXT_EXTS     = frozenset({"txt", "csv", "md", "rst", "log", "yaml", "yml", "json", "xml", "toml"})
_ARCHIVE_EXTS  = frozenset({"zip", "tar", "gz", "bz2", "7z", "rar"})


@dataclass
class TaskAttachment:
    attachment_id: int
    task_id:       int
    project_id:    Optional[int]
    file_name:     str
    file_size:     int          # bytes
    file_type:     str          # MIME type  e.g. "image/png"
    storage_path:  str          # Supabase Storage object path
    public_url:    str          # CDN URL for direct access
    uploader_id:   str          # Discord user ID
    created_at:    datetime

    @classmethod
    def from_record(cls, row) -> "TaskAttachment":
        return cls(
            attachment_id = row["attachment_id"],
            task_id       = row["task_id"],
            project_id    = row.get("project_id"),
            file_name     = row["file_name"],
            file_size     = row["file_size"],
            file_type     = row["file_type"],
            storage_path  = row["storage_path"],
            public_url    = row["public_url"],
            uploader_id   = row["uploader_id"],
            created_at    = row["created_at"],
        )

    # ── Computed properties ────────────────────────────────────────────────────

    @property
    def extension(self) -> str:
        """Lower-case file extension without the leading dot."""
        parts = self.file_name.rsplit(".", 1)
        return parts[1].lower() if len(parts) == 2 else ""

    @property
    def is_image(self) -> bool:
        return self.extension in _IMAGE_EXTS

    @property
    def is_document(self) -> bool:
        return self.extension in _DOC_EXTS

    @property
    def is_text(self) -> bool:
        return self.extension in _TEXT_EXTS

    @property
    def is_archive(self) -> bool:
        return self.extension in _ARCHIVE_EXTS

    @property
    def icon_emoji(self) -> str:
        if self.is_image:    return "🖼️"
        if self.is_document: return "📄"
        if self.is_text:     return "📝"
        if self.is_archive:  return "📦"
        return "📎"

    @property
    def size_human(self) -> str:
        """Return human-readable file size: bytes, KB, or MB."""
        if self.file_size < 1024:
            return f"{self.file_size} B"
        if self.file_size < 1024 * 1024:
            return f"{self.file_size / 1024:.1f} KB"
        return f"{self.file_size / (1024 * 1024):.2f} MB"

    @property
    def display_name(self) -> str:
        """Truncated display name for embeds."""
        return self.file_name if len(self.file_name) <= 50 else self.file_name[:47] + "…"

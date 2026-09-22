"""
storage/service.py — Task Attachment Business Logic

Validates, uploads, retrieves, and deletes task file attachments.
Streams files directly from Discord's CDN into Supabase Storage
(no intermediate disk writes).

Object path convention inside the bucket:
    tasks/<task_id>/<timestamp>_<sanitised_filename>
    projects/<project_id>/tasks/<task_id>/<timestamp>_<sanitised_filename>
"""
from __future__ import annotations

import logging
import re
import time
from typing import Optional, TYPE_CHECKING

import aiohttp

if TYPE_CHECKING:
    import discord

from core.config import config
from core.database import db
from storage.client import SupabaseStorageClient
from storage.models import TaskAttachment

log = logging.getLogger(__name__)

# Module-level singleton REST client & aiohttp session (created on first use)
_storage_client: Optional[SupabaseStorageClient] = None
_http_session: Optional[aiohttp.ClientSession] = None


def _get_client() -> SupabaseStorageClient:
    global _storage_client
    if _storage_client is None:
        cfg = config.storage
        _storage_client = SupabaseStorageClient(cfg.url, cfg.key, cfg.bucket)
    return _storage_client


def _get_http_session() -> aiohttp.ClientSession:
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession()
    return _http_session


# ── Custom exceptions ──────────────────────────────────────────────────────────

class StorageDisabledError(Exception):
    """Raised when the storage feature is not enabled."""


class FileTooLargeError(Exception):
    """Raised when a file exceeds the configured size limit."""
    def __init__(self, size_mb: float, max_mb: int) -> None:
        self.size_mb = size_mb
        self.max_mb  = max_mb
        super().__init__(f"File size {size_mb:.2f} MB exceeds limit {max_mb} MB")


class InvalidFileTypeError(Exception):
    """Raised when a file extension is not on the allow-list."""
    def __init__(self, extension: str, allowed: tuple) -> None:
        self.extension = extension
        self.allowed   = allowed
        super().__init__(f"Extension '{extension}' not allowed; allowed: {', '.join(allowed)}")


class AttachmentNotFoundError(Exception):
    """Raised when the requested attachment does not exist."""


class AttachmentPermissionError(Exception):
    """Raised when the actor lacks permission to delete this attachment."""


# ── Initialisation ─────────────────────────────────────────────────────────────

async def initialize() -> None:
    """Ensure the Supabase Storage bucket exists. Called from main.py setup_hook()."""
    if not config.storage.enabled:
        log.info("Supabase Storage disabled — skipping bucket provisioning.")
        return
    try:
        await _get_client().ensure_bucket()
        log.info("Supabase Storage ready (bucket='%s').", config.storage.bucket)
    except Exception as exc:
        log.error("Storage initialisation failed: %s", exc)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _sanitise_filename(name: str) -> str:
    """Strip unsafe characters from a filename."""
    name = re.sub(r"[^\w.\-]", "_", name)
    return name[:120]  # limit path component length


def _build_object_path(task_id: int, file_name: str, project_id: Optional[int] = None) -> str:
    ts = int(time.time())
    safe = _sanitise_filename(file_name)
    if project_id:
        return f"projects/{project_id}/tasks/{task_id}/{ts}_{safe}"
    return f"tasks/{task_id}/{ts}_{safe}"


def _guess_content_type(file_name: str) -> str:
    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    mapping = {
        "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "gif": "image/gif", "webp": "image/webp", "svg": "image/svg+xml",
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "txt": "text/plain", "csv": "text/csv", "md": "text/markdown",
        "zip": "application/zip",
    }
    return mapping.get(ext, "application/octet-stream")


# ── Core operations ────────────────────────────────────────────────────────────

async def upload_attachment(
    *,
    task_id: int,
    discord_attachment: "discord.Attachment",
    uploader_id: str,
    project_id: Optional[int] = None,
) -> TaskAttachment:
    """
    Validate, stream, and persist a Discord attachment as a task file.

    Pipeline:
      1. Validate enabled, file size, and extension.
      2. Stream bytes from Discord CDN (no disk I/O).
      3. Upload to Supabase Storage.
      4. Insert record into task_attachments table.
      5. Return TaskAttachment dataclass.

    Raises:
        StorageDisabledError, FileTooLargeError, InvalidFileTypeError, RuntimeError
    """
    cfg = config.storage
    if not cfg.enabled:
        raise StorageDisabledError("File storage is disabled on this bot instance.")

    # ── Validate size ──────────────────────────────────────────────────────────
    max_bytes = cfg.max_file_size_mb * 1024 * 1024
    if discord_attachment.size > max_bytes:
        raise FileTooLargeError(
            size_mb=discord_attachment.size / (1024 * 1024),
            max_mb=cfg.max_file_size_mb,
        )

    # ── Validate extension ─────────────────────────────────────────────────────
    file_name = discord_attachment.filename
    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    if ext not in cfg.allowed_extensions:
        raise InvalidFileTypeError(ext, cfg.allowed_extensions)

    # ── Stream bytes from Discord (reusing shared ClientSession) ───────────────
    session = _get_http_session()
    async with session.get(discord_attachment.url) as resp:
        if resp.status != 200:
            raise RuntimeError(
                f"Could not download attachment from Discord CDN: HTTP {resp.status}"
            )
        data = await resp.read()

    content_type = _guess_content_type(file_name)
    object_path  = _build_object_path(task_id, file_name, project_id)

    # ── Upload to Supabase ─────────────────────────────────────────────────────
    client = _get_client()
    public_url = await client.upload_file(object_path, data, content_type)
    log.info(
        "Uploaded attachment: task=%d  file=%s  size=%d  path=%s",
        task_id, file_name, len(data), object_path,
    )

    # ── Persist to DB ──────────────────────────────────────────────────────────
    row = await db.fetchone(
        """INSERT INTO task_attachments
               (task_id, project_id, file_name, file_size, file_type,
                storage_path, public_url, uploader_id)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
           RETURNING *""",
        (
            task_id, project_id, file_name, len(data),
            content_type, object_path, public_url, uploader_id,
        ),
    )
    db.query_cache.invalidate_table("task_attachments")
    return TaskAttachment.from_record(row)


async def get_attachments(task_id: int) -> list[TaskAttachment]:
    """Return all attachments for a task, newest first."""
    rows = await db.fetchall(
        """SELECT * FROM task_attachments
            WHERE task_id=$1
            ORDER BY created_at DESC""",
        (task_id,),
    )
    return [TaskAttachment.from_record(r) for r in rows] if rows else []


async def delete_attachment(
    attachment_id: int,
    actor_id: str,
    is_guild_admin: bool = False,
) -> None:
    """
    Delete an attachment from Supabase Storage and the DB.

    Permission: uploader OR guild admin.

    Raises:
        AttachmentNotFoundError, AttachmentPermissionError, RuntimeError
    """
    row = await db.fetchone(
        "SELECT * FROM task_attachments WHERE attachment_id=$1",
        (attachment_id,),
    )
    if not row:
        raise AttachmentNotFoundError(f"Attachment {attachment_id} not found.")

    if row["uploader_id"] != actor_id and not is_guild_admin:
        raise AttachmentPermissionError("Only the uploader or a guild admin can delete this file.")

    storage_path = row["storage_path"]

    # Remove from Supabase Storage
    try:
        await _get_client().delete_file(storage_path)
    except Exception as exc:
        # Log but still remove DB record — storage object may have been manually deleted
        log.warning("Storage delete error (continuing with DB cleanup): %s", exc)

    # Remove DB record
    await db.execute(
        "DELETE FROM task_attachments WHERE attachment_id=$1",
        (attachment_id,),
    )
    db.query_cache.invalidate_all()
    log.info(
        "Attachment deleted: attachment_id=%d  path=%s  by=%s",
        attachment_id, storage_path, actor_id,
    )


async def close_client() -> None:
    """Close the underlying aiohttp session gracefully."""
    global _storage_client
    if _storage_client:
        await _storage_client.close()
        _storage_client = None

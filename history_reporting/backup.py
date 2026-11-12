"""
history_reporting/backup.py — Complete Data Portability & Archive Bundle (Feature 40)

Assembles an in-memory `.zip` archive containing:
  - tasks.json      Full task records + subtasks, checklists, assignees, comments, revisions
  - tasks.csv       Spreadsheet-compatible UTF-8 BOM CSV
  - wiki_docs/*.md  Markdown wiki documents with YAML frontmatter
  - attachments/*   Binary file attachments fetched via Supabase Storage (size-guarded)
  - dashboard.html  Standalone offline Interactive HTML dashboard
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
import io
import json
import logging
import re
from typing import Any, Optional
import zipfile

import aiohttp

from core.config import config
from core.database import db
from history_reporting import service as history_service
from utils.helpers import build_csv_export

log = logging.getLogger(__name__)

_SAFE_NAME_RE = re.compile(r"[^\w.\-]+")


def _safe_filename(name: str, fallback: str = "file") -> str:
    cleaned = _SAFE_NAME_RE.sub("_", (name or "").strip()).strip("._")
    return (cleaned or fallback)[:100]


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (set, tuple)):
        return list(obj)
    return str(obj)


@dataclass
class BackupBundleResult:
    """Result metadata and `.zip` byte stream for `/export format:backup`."""
    filename: str
    zip_bytes: io.BytesIO
    task_count: int = 0
    doc_count: int = 0
    attachment_files_included: int = 0
    attachment_manifest_only: int = 0
    scope: str = "me"
    warnings: list[str] = field(default_factory=list)


async def _fetch_attachment_bytes(
    storage_path: str,
    public_url: Optional[str],
    session: aiohttp.ClientSession,
) -> Optional[bytes]:
    """Download one attachment from Supabase Storage (signed URL first, public fallback)."""
    target_url: Optional[str] = None
    if config.storage.enabled and storage_path:
        try:
            from storage import service as storage_service
            target_url = await storage_service._get_client().get_signed_url(storage_path, expires_in=300)
        except Exception as exc:
            log.debug("Signed URL fallback for %s: %s", storage_path, exc)
    if not target_url and public_url:
        target_url = public_url
    if not target_url:
        return None

    try:
        async with session.get(target_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                return await resp.read()
    except Exception as exc:
        log.warning("Could not download attachment %s: %s", storage_path, exc)
    return None


async def build_backup_bundle(
    user_id: str,
    *,
    guild_id: Optional[str] = None,
    scope: str = "me",
    tz_name: str = "UTC",
    lang: str = "en",
    max_zip_bytes: int = 23 * 1024 * 1024,
) -> BackupBundleResult:
    """Build a complete portable `.zip` archive for either a user (`me`) or a guild (`server`)."""
    clean_scope = "server" if (scope == "server" and guild_id) else "me"

    if clean_scope == "server":
        tasks_rows = await db.afetchall(
            """SELECT * FROM tasks
               WHERE guild_id=$1 AND is_deleted=FALSE
               ORDER BY created_at DESC""",
            (str(guild_id),),
        )
        cats_rows = await db.afetchall(
            "SELECT * FROM categories WHERE owner_id='system' OR owner_id=$1 ORDER BY name",
            (str(user_id),),
        )
        docs_rows = await db.afetchall(
            """SELECT * FROM project_documents
               WHERE guild_id=$1
               ORDER BY updated_at DESC""",
            (str(guild_id),),
        )
    else:
        tasks_rows = await db.afetchall(
            """SELECT * FROM tasks
               WHERE owner_id=$1 AND is_deleted=FALSE
               ORDER BY created_at DESC""",
            (str(user_id),),
        )
        cats_rows = await db.afetchall(
            "SELECT * FROM categories WHERE owner_id IN ($1, 'system') ORDER BY name",
            (str(user_id),),
        )
        docs_rows = await db.afetchall(
            """SELECT * FROM project_documents
               WHERE author_id=$1
                  OR project_id IN (SELECT project_id FROM project_members WHERE user_id=$1)
               ORDER BY updated_at DESC""",
            (str(user_id),),
        )

    tasks_list = [dict(r) for r in (tasks_rows or [])]
    cats_list = [dict(r) for r in (cats_rows or [])]
    docs_list = [dict(r) for r in (docs_rows or [])]
    task_ids = [int(t_row["task_id"]) for t_row in tasks_list if t_row.get("task_id")]

    checklists_map: dict[int, list[dict[str, Any]]] = {}
    comments_map: dict[int, list[dict[str, Any]]] = {}
    assignees_map: dict[int, list[str]] = {}
    attachments_list: list[dict[str, Any]] = []

    if task_ids:
        placeholders = ",".join(f"${i + 1}" for i in range(len(task_ids)))
        cl_rows = await db.afetchall(
            f"SELECT * FROM task_checklists WHERE task_id IN ({placeholders}) ORDER BY position ASC",
            tuple(task_ids),
        )
        for cr in (cl_rows or []):
            checklists_map.setdefault(int(cr["task_id"]), []).append(dict(cr))

        cm_rows = await db.afetchall(
            f"SELECT * FROM task_comments WHERE task_id IN ({placeholders}) ORDER BY created_at ASC",
            tuple(task_ids),
        )
        for mr in (cm_rows or []):
            comments_map.setdefault(int(mr["task_id"]), []).append(dict(mr))

        as_rows = await db.afetchall(
            f"""SELECT task_id, user_id FROM task_assignees WHERE task_id IN ({placeholders})
                UNION
                SELECT task_id, user_id FROM task_assignments WHERE task_id IN ({placeholders})""",
            tuple(task_ids),
        )
        for ar in (as_rows or []):
            assignees_map.setdefault(int(ar["task_id"]), []).append(str(ar["user_id"]))

        att_rows = await db.afetchall(
            f"SELECT * FROM task_attachments WHERE task_id IN ({placeholders}) ORDER BY created_at ASC",
            tuple(task_ids),
        )
        attachments_list = [dict(a) for a in (att_rows or [])]

    enriched_tasks: list[dict[str, Any]] = []
    for tr in tasks_list:
        tid = int(tr["task_id"])
        item = dict(tr)
        item["checklists"] = checklists_map.get(tid, [])
        item["comments"] = comments_map.get(tid, [])
        item["assignees"] = sorted(set(assignees_map.get(tid, [])))
        enriched_tasks.append(item)

    payload_json = json.dumps(
        {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "scope": clean_scope,
            "scope_id": str(guild_id if clean_scope == "server" else user_id),
            "timezone": tz_name,
            "task_count": len(enriched_tasks),
            "doc_count": len(docs_list),
            "categories": cats_list,
            "tasks": enriched_tasks,
            "wiki_docs": docs_list,
        },
        ensure_ascii=False,
        indent=2,
        default=_json_default,
    ).encode("utf-8")

    csv_stream = build_csv_export(tasks_list, tz_name)
    html_stream = history_service.build_html_export_bytes(
        tasks=tasks_list,
        categories=cats_list,
        user_id=str(user_id),
        tz_name=tz_name,
        lang=lang,
    )

    zip_buf = io.BytesIO()
    att_included = 0
    att_manifest_only = 0
    warnings: list[str] = []
    manifest_lines: list[str] = [
        "# Attachments Export Manifest",
        f"# Exported at {datetime.now(timezone.utc).isoformat()}",
        "",
    ]

    with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("tasks.json", payload_json)
        zf.writestr("tasks.csv", csv_stream.getvalue())
        zf.writestr("dashboard.html", html_stream.getvalue())

        # Write Markdown wiki docs
        used_doc_paths: set[str] = set()
        for doc in docs_list:
            did = doc.get("doc_id", "0")
            title = str(doc.get("title") or f"doc_{did}")
            slug = _safe_filename(doc.get("slug") or title, fallback=f"doc_{did}")
            rel_path = f"wiki_docs/{did}_{slug}.md"
            while rel_path in used_doc_paths:
                rel_path = f"wiki_docs/{did}_{slug}_{len(used_doc_paths)}.md"
            used_doc_paths.add(rel_path)

            md_text = (
                f"---\n"
                f"doc_id: {did}\n"
                f"title: {title}\n"
                f"doc_type: {doc.get('doc_type', 'general')}\n"
                f"project_id: {doc.get('project_id', '')}\n"
                f"updated_at: {doc.get('updated_at', '')}\n"
                f"---\n\n"
                f"{doc.get('content_markdown') or ''}\n"
            )
            zf.writestr(rel_path, md_text.encode("utf-8"))

        # Stream attachments within Discord's upload ceiling
        approx_budget = max(0, max_zip_bytes - zip_buf.tell() - 512 * 1024)
        if attachments_list:
            sem = asyncio.Semaphore(5)

            async def _download_with_sem(sess: aiohttp.ClientSession, att: dict[str, Any]):
                async with sem:
                    content = await _fetch_attachment_bytes(
                        str(att.get("storage_path") or ""),
                        att.get("public_url"),
                        sess,
                    )
                    return att, content

            async with aiohttp.ClientSession() as session:
                downloaded = await asyncio.gather(
                    *[_download_with_sem(session, att) for att in attachments_list],
                    return_exceptions=False,
                )

            for att, content in downloaded:
                tid = att.get("task_id", 0)
                fname = _safe_filename(str(att.get("file_name") or "attachment.bin"))
                arc_name = f"attachments/{tid}_{fname}"
                if content is not None and len(content) <= approx_budget:
                    zf.writestr(arc_name, content)
                    approx_budget -= len(content)
                    att_included += 1
                    manifest_lines.append(f"[INCLUDED] {arc_name} ({len(content)} bytes)")
                else:
                    att_manifest_only += 1
                    reason = "size limit" if content is not None else "storage unavailable"
                    url = att.get("public_url") or att.get("storage_path") or "N/A"
                    manifest_lines.append(f"[LINK ONLY - {reason}] {arc_name} -> {url}")

            if att_manifest_only > 0:
                warnings.append(f"{att_manifest_only} attachment(s) referenced in attachments/MANIFEST.txt")

        zf.writestr("attachments/MANIFEST.txt", "\n".join(manifest_lines).encode("utf-8"))
        readme = (
            f"Gen 5.0 Portable Archive Bundle\n"
            f"Scope: {clean_scope}\n"
            f"Tasks: {len(enriched_tasks)}\n"
            f"Wiki Docs: {len(docs_list)}\n"
            f"Attachments Embedded: {att_included} | Manifest Links: {att_manifest_only}\n"
            f"Open dashboard.html in any browser for interactive offline viewing.\n"
        )
        zf.writestr("README.txt", readme.encode("utf-8"))

    zip_buf.seek(0)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    scope_tag = f"guild_{guild_id}" if clean_scope == "server" else f"user_{user_id}"
    return BackupBundleResult(
        filename=f"backup_{scope_tag}_{stamp}.zip",
        zip_bytes=zip_buf,
        task_count=len(enriched_tasks),
        doc_count=len(docs_list),
        attachment_files_included=att_included,
        attachment_manifest_only=att_manifest_only,
        scope=clean_scope,
        warnings=warnings,
    )


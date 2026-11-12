"""
knowledge_base/service.py — CRUD, access control, and PostgreSQL tsvector Hybrid FTS for /doc.
"""
from __future__ import annotations

import logging
from typing import Optional

from core.database import db
from core.security import validator
from knowledge_base.models import DocType, ProjectDocument, slugify_title
from utils.helpers import ensure_user

log = logging.getLogger(__name__)

MAX_DOC_TITLE_LEN = 150
MAX_DOC_CONTENT_LEN = 12000


class DocumentNotFound(Exception):
    """Raised when a document does not exist in the requested guild."""


class DocumentAccessDenied(Exception):
    """Raised when the user lacks permission to read, edit, or delete a document."""


class DocumentValidationError(Exception):
    """Raised when document title, slug, or content fails validation."""


async def _verify_scope_access(
    guild_id: str,
    user_id: str,
    project_id: Optional[int] = None,
    task_id: Optional[int] = None,
    require_write: bool = False,
    is_guild_admin: bool = False,
) -> Optional[int]:
    """Validate linked project_id / task_id permissions and infer project_id from task if omitted."""
    resolved_project_id = project_id

    if task_id is not None:
        t_row = await db.afetchone(
            """SELECT task_id, owner_id, project_id, guild_id, is_private, is_deleted
               FROM tasks WHERE task_id = $1""",
            (task_id,),
        )
        if not t_row or t_row.get("is_deleted"):
            raise DocumentValidationError("doc_task_not_found")
        t_guild = t_row.get("guild_id")
        t_proj = t_row.get("project_id")
        if t_guild and str(t_guild) != guild_id:
            raise DocumentAccessDenied("permission_denied")
        if t_proj is not None:
            if resolved_project_id is not None and int(t_proj) != resolved_project_id:
                raise DocumentValidationError("doc_task_project_mismatch")
            resolved_project_id = int(t_proj)
        elif str(t_row["owner_id"]) != user_id and not is_guild_admin:
            raise DocumentAccessDenied("permission_denied")

    if resolved_project_id is not None:
        from collaboration import service as collab_service
        try:
            proj = await collab_service.get_project(resolved_project_id, guild_id)
        except collab_service.ProjectNotFound:
            raise DocumentValidationError("doc_project_not_found")
        if not is_guild_admin and proj.owner_id != user_id:
            role = await collab_service.get_member_role(resolved_project_id, user_id)
            if role is None:
                raise DocumentAccessDenied("proj_no_permission")
            if require_write and role not in ("member", "lead"):
                raise DocumentAccessDenied("proj_no_permission")

    return resolved_project_id


async def _ensure_unique_slug(
    guild_id: str,
    project_id: Optional[int],
    raw_slug: str,
    exclude_doc_id: Optional[int] = None,
) -> str:
    """Guarantee a collision-free slug within ``(guild_id, COALESCE(project_id, 0))``."""
    base = slugify_title(raw_slug)
    rows = await db.afetchall(
        """SELECT doc_id, LOWER(slug) AS slug
           FROM project_documents
           WHERE COALESCE(guild_id, '') = $1
             AND COALESCE(project_id, 0) = $2
             AND slug IS NOT NULL
             AND LOWER(slug) LIKE $3""",
        (guild_id, project_id or 0, f"{base}%"),
    )
    existing = {
        str(r["slug"])
        for r in (rows or [])
        if exclude_doc_id is None or int(r["doc_id"]) != exclude_doc_id
    }
    if base not in existing:
        return base
    idx = 2
    while f"{base}-{idx}" in existing:
        idx += 1
    return f"{base}-{idx}"[:60]


def _normalize_doc_type(doc_type: Optional[str]) -> str:
    val = (doc_type or DocType.GENERAL.value).strip().lower()
    valid = {d.value for d in DocType}
    return val if val in valid else DocType.GENERAL.value


async def create_document(
    guild_id: str,
    author_id: str,
    title: str,
    content_markdown: str,
    doc_type: str = DocType.GENERAL.value,
    project_id: Optional[int] = None,
    task_id: Optional[int] = None,
    slug: Optional[str] = None,
    is_guild_admin: bool = False,
) -> ProjectDocument:
    """Create a new Markdown wiki page inside a guild (project-scoped, task-linked, or SOP)."""
    clean_title = validator.sanitize(title, MAX_DOC_TITLE_LEN)
    # Note: sanitize strips control chars while keeping valid Markdown syntax like `---`.
    clean_body = validator.sanitize(content_markdown, MAX_DOC_CONTENT_LEN)
    if not clean_title:
        raise DocumentValidationError("doc_invalid_title")
    if not clean_body:
        raise DocumentValidationError("doc_empty_content")

    resolved_project_id = await _verify_scope_access(
        guild_id=guild_id,
        user_id=author_id,
        project_id=project_id,
        task_id=task_id,
        require_write=True,
        is_guild_admin=is_guild_admin,
    )
    await ensure_user(author_id)

    unique_slug = await _ensure_unique_slug(
        guild_id=guild_id,
        project_id=resolved_project_id,
        raw_slug=slug or clean_title,
    )
    norm_type = _normalize_doc_type(doc_type)

    row = await db.afetchone(
        """INSERT INTO project_documents
               (guild_id, project_id, task_id, title, slug, doc_type, content_markdown, author_id)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
           RETURNING doc_id, guild_id, project_id, task_id, title, slug, doc_type,
                     content_markdown, author_id, created_at, updated_at""",
        (guild_id, resolved_project_id, task_id, clean_title, unique_slug, norm_type, clean_body, author_id),
    )
    db.query_cache.invalidate_table("project_documents")
    await db.alog_action(author_id, "doc_created", str(row["doc_id"]), clean_title)
    if resolved_project_id:
        from collaboration import service as collab_service
        await collab_service.log_activity(
            resolved_project_id, guild_id, author_id, "doc_created", f"#{row['doc_id']} {clean_title}"
        )
    return ProjectDocument.from_row(row)


async def get_document(
    guild_id: str,
    doc_ref: str | int,
    user_id: str,
    is_guild_admin: bool = False,
) -> ProjectDocument:
    """Fetch a single document by numeric ``doc_id`` or ``slug`` (case-insensitive) within ``guild_id``."""
    ref_str = str(doc_ref).strip()
    if ref_str.isdigit():
        row = await db.afetchone(
            """SELECT pd.doc_id, pd.guild_id, pd.project_id, pd.task_id, pd.title, pd.slug,
                      pd.doc_type, pd.content_markdown, pd.author_id, pd.created_at, pd.updated_at,
                      p.name AS project_name
               FROM project_documents pd
               LEFT JOIN projects p ON p.project_id = pd.project_id
               WHERE pd.doc_id = $1 AND (pd.guild_id = $2 OR p.guild_id = $2)""",
            (int(ref_str), guild_id),
        )
    else:
        row = await db.afetchone(
            """SELECT pd.doc_id, pd.guild_id, pd.project_id, pd.task_id, pd.title, pd.slug,
                      pd.doc_type, pd.content_markdown, pd.author_id, pd.created_at, pd.updated_at,
                      p.name AS project_name
               FROM project_documents pd
               LEFT JOIN projects p ON p.project_id = pd.project_id
               WHERE (pd.guild_id = $1 OR p.guild_id = $1)
                 AND LOWER(pd.slug) = LOWER($2)
               ORDER BY pd.updated_at DESC
               LIMIT 1""",
            (guild_id, ref_str),
        )
    if not row:
        raise DocumentNotFound("doc_not_found")

    doc = ProjectDocument.from_row(row)
    await _verify_scope_access(
        guild_id=guild_id,
        user_id=user_id,
        project_id=doc.project_id,
        task_id=doc.task_id,
        require_write=False,
        is_guild_admin=is_guild_admin,
    )
    return doc


async def update_document(
    guild_id: str,
    doc_id: int,
    actor_id: str,
    title: Optional[str] = None,
    content_markdown: Optional[str] = None,
    doc_type: Optional[str] = None,
    is_guild_admin: bool = False,
) -> ProjectDocument:
    """Update a wiki document's title, body, or type."""
    doc = await get_document(guild_id, doc_id, actor_id, is_guild_admin=is_guild_admin)

    if doc.project_id is not None:
        await _verify_scope_access(
            guild_id=guild_id,
            user_id=actor_id,
            project_id=doc.project_id,
            require_write=True,
            is_guild_admin=is_guild_admin,
        )
    elif doc.author_id != actor_id and not is_guild_admin:
        raise DocumentAccessDenied("permission_denied")

    new_title = validator.sanitize(title, MAX_DOC_TITLE_LEN) if title is not None else doc.title
    new_body = (
        validator.sanitize(content_markdown, MAX_DOC_CONTENT_LEN)
        if content_markdown is not None
        else doc.content_markdown
    )
    if not new_title:
        raise DocumentValidationError("doc_invalid_title")
    if not new_body:
        raise DocumentValidationError("doc_empty_content")

    new_type = _normalize_doc_type(doc_type) if doc_type is not None else doc.doc_type

    row = await db.afetchone(
        """UPDATE project_documents
              SET title = $1,
                  content_markdown = $2,
                  doc_type = $3,
                  updated_at = NOW()
            WHERE doc_id = $4
           RETURNING doc_id, guild_id, project_id, task_id, title, slug, doc_type,
                     content_markdown, author_id, created_at, updated_at""",
        (new_title, new_body, new_type, doc_id),
    )
    db.query_cache.invalidate_table("project_documents")
    await db.alog_action(actor_id, "doc_updated", str(doc_id), new_title)
    if doc.project_id:
        from collaboration import service as collab_service
        await collab_service.log_activity(
            doc.project_id, guild_id, actor_id, "doc_updated", f"#{doc_id} {new_title}"
        )
    return ProjectDocument.from_row(row)


async def delete_document(
    guild_id: str,
    doc_id: int,
    actor_id: str,
    is_guild_admin: bool = False,
) -> bool:
    """Delete a wiki document (author, project lead/owner, or guild admin only)."""
    doc = await get_document(guild_id, doc_id, actor_id, is_guild_admin=is_guild_admin)

    can_delete = is_guild_admin or (doc.author_id == actor_id)
    if not can_delete and doc.project_id is not None:
        from collaboration import service as collab_service
        proj = await collab_service.get_project(doc.project_id, guild_id)
        if proj.owner_id == actor_id:
            can_delete = True
        else:
            role = await collab_service.get_member_role(doc.project_id, actor_id)
            can_delete = (role == "lead")

    if not can_delete:
        raise DocumentAccessDenied("permission_denied")

    await db.aexecute("DELETE FROM project_documents WHERE doc_id = $1", (doc_id,))
    db.query_cache.invalidate_table("project_documents")
    await db.alog_action(actor_id, "doc_deleted", str(doc_id), doc.title)
    return True


async def list_or_search_documents(
    guild_id: str,
    user_id: str,
    project_id: Optional[int] = None,
    task_id: Optional[int] = None,
    doc_type: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 25,
    is_guild_admin: bool = False,
) -> list[ProjectDocument]:
    """List wiki documents or search with PostgreSQL ``tsvector`` + ``ILIKE`` hybrid matching."""
    if project_id is not None:
        await _verify_scope_access(
            guild_id=guild_id,
            user_id=user_id,
            project_id=project_id,
            require_write=False,
            is_guild_admin=is_guild_admin,
        )

    where = ["(pd.guild_id = $1 OR p.guild_id = $1)"]
    params: list[object] = [guild_id]
    idx = 2

    if project_id is not None:
        where.append(f"pd.project_id = ${idx}")
        params.append(project_id)
        idx += 1
    elif not is_guild_admin:
        # Restrict project-scoped docs to projects where caller is owner or member; server-wide docs remain visible
        where.append(
            f"(pd.project_id IS NULL OR p.owner_id = ${idx} OR EXISTS ("
            f"SELECT 1 FROM project_members pm WHERE pm.project_id = pd.project_id AND pm.user_id = ${idx}))"
        )
        params.append(user_id)
        idx += 1

    if task_id is not None:
        where.append(f"pd.task_id = ${idx}")
        params.append(task_id)
        idx += 1

    if doc_type:
        where.append(f"pd.doc_type = ${idx}")
        params.append(_normalize_doc_type(doc_type))
        idx += 1

    q_clean = (query or "").strip()
    if q_clean:
        q_idx = idx
        like_idx = idx + 1
        params.append(q_clean)
        params.append(f"%{q_clean}%")
        idx += 2
        where.append(
            f"(pd.search_vector @@ websearch_to_tsquery('simple', ${q_idx}) "
            f"OR pd.title ILIKE ${like_idx} "
            f"OR pd.content_markdown ILIKE ${like_idx} "
            f"OR COALESCE(pd.slug, '') ILIKE ${like_idx})"
        )
        rank_expr = f"ts_rank(pd.search_vector, websearch_to_tsquery('simple', ${q_idx}))"
        order_by = "rank DESC, pd.updated_at DESC"
    else:
        rank_expr = "0.0"
        order_by = "pd.updated_at DESC"

    params.append(max(1, min(limit, 50)))
    lim_idx = idx

    sql = f"""
        SELECT pd.doc_id, pd.guild_id, pd.project_id, pd.task_id, pd.title, pd.slug,
               pd.doc_type, pd.content_markdown, pd.author_id, pd.created_at, pd.updated_at,
               p.name AS project_name,
               {rank_expr} AS rank
          FROM project_documents pd
          LEFT JOIN projects p ON p.project_id = pd.project_id
         WHERE {' AND '.join(where)}
         ORDER BY {order_by}
         LIMIT ${lim_idx}
    """
    rows = await db.afetchall(sql, tuple(params))
    return [ProjectDocument.from_row(r) for r in (rows or [])]

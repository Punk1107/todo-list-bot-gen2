"""
tests/test_knowledge_base.py — Unit tests for Feature 34: Task & Project Markdown Wiki Docs (/doc).
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from knowledge_base import service as doc_service
from knowledge_base.models import (
    DocType,
    ProjectDocument,
    extract_snippet,
    slugify_title,
    split_markdown_pages,
)
from knowledge_base.views import DocListView, DocViewerView


def test_slugify_and_markdown_pagination():
    assert slugify_title("API Auth Spec v2!") == "api-auth-spec-v2"
    assert slugify_title("   ") == "doc"

    long_md = "\n\n".join([f"Paragraph {i}: " + ("word " * 120) for i in range(12)])
    pages = split_markdown_pages(long_md, max_chars=1200)
    assert len(pages) > 1
    assert all(len(p) <= 1200 for p in pages)

    snip = extract_snippet("Authentication uses OAuth2 PKCE tokens with short expiry.", "PKCE")
    assert "PKCE" in snip


@pytest.mark.asyncio
async def test_create_document_allows_markdown_dividers_and_deduplicates_slug():
    now = datetime.now(timezone.utc)
    fake_proj = SimpleNamespace(project_id=5, guild_id="g1", owner_id="u1", name="Alpha")

    with patch("collaboration.service.get_project", new=AsyncMock(return_value=fake_proj)), \
         patch("collaboration.service.get_member_role", new=AsyncMock(return_value="member")), \
         patch("collaboration.service.log_activity", new=AsyncMock()), \
         patch("knowledge_base.service.ensure_user", new=AsyncMock()), \
         patch.object(doc_service.db, "afetchall", new=AsyncMock(return_value=[{"doc_id": 1, "slug": "api-spec"}])), \
         patch.object(doc_service.db, "afetchone", new=AsyncMock(return_value={
             "doc_id": 2,
             "guild_id": "g1",
             "project_id": 5,
             "task_id": None,
             "title": "API Spec",
             "slug": "api-spec-2",
             "doc_type": "requirement",
             "content_markdown": "# Title\n\n---\n\n-- note --",
             "author_id": "u1",
             "created_at": now,
             "updated_at": now,
         })), \
         patch.object(doc_service.db, "alog_action", new=AsyncMock()):
        doc = await doc_service.create_document(
            guild_id="g1",
            author_id="u1",
            title="API Spec",
            content_markdown="# Title\n\n---\n\n-- note --",
            doc_type=DocType.REQUIREMENT.value,
            project_id=5,
        )

    assert doc.doc_id == 2
    assert doc.slug == "api-spec-2"
    assert "---" in doc.content_markdown


@pytest.mark.asyncio
async def test_search_documents_uses_tsvector_and_ilike_hybrid():
    now = datetime.now(timezone.utc)
    captured_sql: list[str] = []

    async def fake_fetchall(sql, params):
        captured_sql.append(sql)
        return [{
            "doc_id": 7,
            "guild_id": "g1",
            "project_id": None,
            "task_id": None,
            "title": "คู่มือ Deploy",
            "slug": "deploy-sop",
            "doc_type": "sop",
            "content_markdown": "ขั้นตอนการ Deploy บน Render",
            "author_id": "u1",
            "created_at": now,
            "updated_at": now,
            "project_name": None,
            "rank": 0.42,
        }]

    with patch.object(doc_service.db, "afetchall", new=AsyncMock(side_effect=fake_fetchall)):
        docs = await doc_service.list_or_search_documents(
            guild_id="g1",
            user_id="u1",
            query="Deploy",
        )

    assert len(docs) == 1
    assert docs[0].doc_id == 7
    assert "websearch_to_tsquery('simple'" in captured_sql[0]
    assert "ILIKE" in captured_sql[0]


@pytest.mark.asyncio
async def test_doc_viewer_and_list_views_embed():
    now = datetime.now(timezone.utc)
    doc = ProjectDocument(
        doc_id=10,
        guild_id="g1",
        project_id=3,
        task_id=None,
        title="System Architecture",
        slug="system-architecture",
        doc_type="design",
        content_markdown="# Intro\nSection A\n\n" + ("Line " * 900),
        author_id="u1",
        created_at=now,
        updated_at=now,
        project_name="Core",
    )
    viewer = DocViewerView(doc=doc, guild_id="g1", user_id="u1", lang="en")
    assert len(viewer.pages) >= 2
    assert viewer.prev_btn.disabled is True
    assert viewer.next_btn.disabled is False

    embed = viewer.make_embed()
    assert "System Architecture" in embed.title

    list_view = DocListView(docs=[doc], guild_id="g1", lang="en", query="Architecture")
    list_embed = list_view.make_embed()
    assert "Architecture" in list_embed.title
    assert "System Architecture" in list_embed.description


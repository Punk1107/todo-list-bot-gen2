"""
knowledge_base/cog.py — Slash commands /doc create, /doc view, /doc edit, /doc list, /doc delete.
"""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from core.security import rate_limit_check
from knowledge_base import service as doc_service
from knowledge_base.views import DocCreateModal, DocEditModal, DocListView, DocViewerView
from locales.i18n import t
from utils.helpers import ensure_user, get_user_lang

log = logging.getLogger(__name__)

_DOC_TYPE_CHOICES = [
    app_commands.Choice(name="📄 General / ทั่วไป", value="general"),
    app_commands.Choice(name="📋 Requirements / ข้อกำหนดระบบ", value="requirement"),
    app_commands.Choice(name="🎨 Design Guidelines / แนวทางการออกแบบ", value="design"),
    app_commands.Choice(name="📘 SOP / คู่มือปฏิบัติงาน", value="sop"),
]

_MAX_ATTACHMENT_BYTES = 256 * 1024


async def _doc_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    if not interaction.guild:
        return []
    uid = str(interaction.user.id)
    gid = str(interaction.guild.id)
    is_admin = bool(
        hasattr(interaction.user, "guild_permissions")
        and interaction.user.guild_permissions.administrator
    )
    try:
        docs = await doc_service.list_or_search_documents(
            guild_id=gid,
            user_id=uid,
            query=current.strip() or None,
            limit=25,
            is_guild_admin=is_admin,
        )
        return [
            app_commands.Choice(
                name=f"{d.type_emoji} #{d.doc_id} {d.title}"[:100],
                value=str(d.doc_id),
            )
            for d in docs
        ]
    except Exception:
        return []


class KnowledgeBaseCog(commands.Cog, name="KnowledgeBase"):
    """Task & Project Markdown Wiki Docs (/doc) with PostgreSQL Full-Text Search."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    doc = app_commands.Group(
        name="doc",
        description="📚 ระบบวิกิเอกสาร Markdown ของโปรเจกต์และเซิร์ฟเวอร์ / Markdown Wiki Docs",
        guild_only=True,
    )

    async def _read_markdown_attachment(
        self, attachment: discord.Attachment, lang: str
    ) -> tuple[bool, str]:
        if attachment.size > _MAX_ATTACHMENT_BYTES:
            return False, t("doc_attachment_too_large", lang)
        fname = (attachment.filename or "").lower()
        if not (fname.endswith(".md") or fname.endswith(".txt") or fname.endswith(".markdown")):
            return False, t("doc_attachment_invalid_ext", lang)
        raw = await attachment.read()
        try:
            return True, raw.decode("utf-8")
        except UnicodeDecodeError:
            return False, t("doc_attachment_encoding_err", lang)

    @doc.command(name="create", description="📝 สร้างหน้าวิกิ Markdown ใหม่ / Create a Markdown wiki doc")
    @app_commands.describe(
        doc_type="ประเภทเอกสาร / Document type",
        project_id="รหัสโปรเจกต์ (ไม่ระบุ = วิกิระดับเซิร์ฟเวอร์) / Project ID (optional)",
        task_id="รหัสงานที่ต้องการแนบเอกสาร / Linked Task ID (optional)",
        title="ชื่อเอกสาร (ใช้ร่วมกับไฟล์ .md) / Document title (when uploading a file)",
        file="อัปโหลดไฟล์ .md/.txt แทนการกรอกในฟอร์ม / Optional .md file upload",
    )
    @app_commands.choices(doc_type=_DOC_TYPE_CHOICES)
    @rate_limit_check("command")
    async def doc_create(
        self,
        interaction: discord.Interaction,
        doc_type: Optional[str] = "general",
        project_id: Optional[int] = None,
        task_id: Optional[int] = None,
        title: Optional[str] = None,
        file: Optional[discord.Attachment] = None,
    ) -> None:
        uid = str(interaction.user.id)
        gid = str(interaction.guild.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)
        is_admin = bool(
            hasattr(interaction.user, "guild_permissions")
            and interaction.user.guild_permissions.administrator
        )

        if file is None:
            modal = DocCreateModal(
                guild_id=gid,
                lang=lang,
                doc_type=doc_type or "general",
                project_id=project_id,
                task_id=task_id,
                is_guild_admin=is_admin,
            )
            await interaction.response.send_modal(modal)
            return

        await interaction.response.defer(ephemeral=False)
        ok, content_or_err = await self._read_markdown_attachment(file, lang)
        if not ok:
            await interaction.followup.send(content_or_err, ephemeral=True)
            return

        doc_title = (title or "").strip() or file.filename.rsplit(".", 1)[0]
        try:
            created = await doc_service.create_document(
                guild_id=gid,
                author_id=uid,
                title=doc_title,
                content_markdown=content_or_err,
                doc_type=doc_type or "general",
                project_id=project_id,
                task_id=task_id,
                is_guild_admin=is_admin,
            )
        except (doc_service.DocumentAccessDenied, doc_service.DocumentValidationError) as exc:
            await interaction.followup.send(t(str(exc), lang), ephemeral=True)
            return

        viewer = DocViewerView(doc=created, guild_id=gid, user_id=uid, lang=lang)
        await interaction.followup.send(
            content=t("doc_created_msg", lang, doc_id=created.doc_id, slug=created.slug or created.doc_id),
            embed=viewer.make_embed(),
            view=viewer,
        )

    @doc.command(name="view", description="📖 เปิดอ่านเอกสารวิกิ / View a Markdown wiki document")
    @app_commands.describe(document="รหัส Doc ID หรือ Slug / Document ID or slug")
    @app_commands.autocomplete(document=_doc_autocomplete)
    @rate_limit_check("command")
    async def doc_view(self, interaction: discord.Interaction, document: str) -> None:
        uid = str(interaction.user.id)
        gid = str(interaction.guild.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)
        await interaction.response.defer(ephemeral=True)
        is_admin = bool(
            hasattr(interaction.user, "guild_permissions")
            and interaction.user.guild_permissions.administrator
        )
        try:
            doc = await doc_service.get_document(gid, document, uid, is_guild_admin=is_admin)
        except (doc_service.DocumentNotFound, doc_service.DocumentAccessDenied) as exc:
            await interaction.followup.send(t(str(exc), lang), ephemeral=True)
            return

        viewer = DocViewerView(doc=doc, guild_id=gid, user_id=uid, lang=lang)
        await interaction.followup.send(embed=viewer.make_embed(), view=viewer, ephemeral=True)

    @doc.command(name="edit", description="✏️ แก้ไขเอกสารวิกิ / Edit an existing Markdown wiki document")
    @app_commands.describe(
        document="รหัส Doc ID หรือ Slug / Document ID or slug",
        file="อัปโหลดไฟล์ .md/.txt เพื่อแทนที่เนื้อหา / Optional .md file to replace content",
    )
    @app_commands.autocomplete(document=_doc_autocomplete)
    @rate_limit_check("command")
    async def doc_edit(
        self,
        interaction: discord.Interaction,
        document: str,
        file: Optional[discord.Attachment] = None,
    ) -> None:
        uid = str(interaction.user.id)
        gid = str(interaction.guild.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)
        is_admin = bool(
            hasattr(interaction.user, "guild_permissions")
            and interaction.user.guild_permissions.administrator
        )
        try:
            doc = await doc_service.get_document(gid, document, uid, is_guild_admin=is_admin)
        except (doc_service.DocumentNotFound, doc_service.DocumentAccessDenied) as exc:
            await interaction.response.send_message(t(str(exc), lang), ephemeral=True)
            return

        if file is not None:
            await interaction.response.defer(ephemeral=True)
            ok, content_or_err = await self._read_markdown_attachment(file, lang)
            if not ok:
                await interaction.followup.send(content_or_err, ephemeral=True)
                return
            try:
                updated = await doc_service.update_document(
                    guild_id=gid,
                    doc_id=doc.doc_id,
                    actor_id=uid,
                    content_markdown=content_or_err,
                    is_guild_admin=is_admin,
                )
            except (doc_service.DocumentNotFound, doc_service.DocumentAccessDenied, doc_service.DocumentValidationError) as exc:
                await interaction.followup.send(t(str(exc), lang), ephemeral=True)
                return
            viewer = DocViewerView(doc=updated, guild_id=gid, user_id=uid, lang=lang)
            await interaction.followup.send(
                content=t("doc_updated_msg", lang, doc_id=updated.doc_id),
                embed=viewer.make_embed(),
                view=viewer,
                ephemeral=True,
            )
            return

        if len(doc.content_markdown) > 4000:
            await interaction.response.send_message(t("doc_too_long_use_file", lang), ephemeral=True)
            return

        modal = DocEditModal(doc, gid, lang, is_guild_admin=is_admin)
        await interaction.response.send_modal(modal)

    @doc.command(name="list", description="🔍 ค้นหาและแสดงรายการวิกิเอกสาร (Full-Text Search) / List or search docs")
    @app_commands.describe(
        project_id="กรองตามรหัสโปรเจกต์ / Filter by Project ID",
        task_id="กรองตามรหัสงาน / Filter by Task ID",
        doc_type="กรองตามประเภทเอกสาร / Filter by doc type",
        query="คำค้นหา Full-Text Search ในหัวข้อและเนื้อหา / Search keywords",
    )
    @app_commands.choices(doc_type=_DOC_TYPE_CHOICES)
    @rate_limit_check("search")
    async def doc_list(
        self,
        interaction: discord.Interaction,
        project_id: Optional[int] = None,
        task_id: Optional[int] = None,
        doc_type: Optional[str] = None,
        query: Optional[str] = None,
    ) -> None:
        uid = str(interaction.user.id)
        gid = str(interaction.guild.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)
        await interaction.response.defer(ephemeral=True)
        is_admin = bool(
            hasattr(interaction.user, "guild_permissions")
            and interaction.user.guild_permissions.administrator
        )
        try:
            docs = await doc_service.list_or_search_documents(
                guild_id=gid,
                user_id=uid,
                project_id=project_id,
                task_id=task_id,
                doc_type=doc_type,
                query=query,
                is_guild_admin=is_admin,
            )
        except (doc_service.DocumentAccessDenied, doc_service.DocumentValidationError) as exc:
            await interaction.followup.send(t(str(exc), lang), ephemeral=True)
            return

        view = DocListView(docs=docs, guild_id=gid, lang=lang, query=query, project_id=project_id)
        await interaction.followup.send(embed=view.make_embed(), view=view, ephemeral=True)

    @doc.command(name="delete", description="🗑️ ลบเอกสารวิกิ / Delete a Markdown wiki document")
    @app_commands.describe(document="รหัส Doc ID หรือ Slug / Document ID or slug")
    @app_commands.autocomplete(document=_doc_autocomplete)
    @rate_limit_check("command")
    async def doc_delete(self, interaction: discord.Interaction, document: str) -> None:
        uid = str(interaction.user.id)
        gid = str(interaction.guild.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)
        await interaction.response.defer(ephemeral=True)
        is_admin = bool(
            hasattr(interaction.user, "guild_permissions")
            and interaction.user.guild_permissions.administrator
        )
        try:
            doc = await doc_service.get_document(gid, document, uid, is_guild_admin=is_admin)
            await doc_service.delete_document(gid, doc.doc_id, uid, is_guild_admin=is_admin)
        except (doc_service.DocumentNotFound, doc_service.DocumentAccessDenied) as exc:
            await interaction.followup.send(t(str(exc), lang), ephemeral=True)
            return

        await interaction.followup.send(
            t("doc_deleted_msg", lang, doc_id=doc.doc_id, title=doc.title),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(KnowledgeBaseCog(bot))


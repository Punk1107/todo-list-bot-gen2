"""
knowledge_base/views.py — Interactive Discord UI Modals & Paginated Wiki Viewer for /doc.
"""
from __future__ import annotations

import io
import logging
from datetime import datetime
from typing import Optional

import discord
from discord import ui

from knowledge_base import service as doc_service
from knowledge_base.models import ProjectDocument, extract_snippet, split_markdown_pages
from locales.i18n import t
from utils.helpers import get_user_lang

log = logging.getLogger(__name__)


def _is_admin(user: discord.User | discord.Member, guild: Optional[discord.Guild]) -> bool:
    return bool(
        guild and hasattr(user, "guild_permissions") and user.guild_permissions.administrator
    )


class DocCreateModal(ui.Modal):
    """Modal form to author a new Markdown wiki page."""

    def __init__(
        self,
        guild_id: str,
        lang: str,
        doc_type: str = "general",
        project_id: Optional[int] = None,
        task_id: Optional[int] = None,
        is_guild_admin: bool = False,
    ) -> None:
        super().__init__(title=t("doc_modal_create_title", lang)[:45])
        self.guild_id = guild_id
        self.lang = lang
        self.doc_type = doc_type
        self.project_id = project_id
        self.task_id = task_id
        self.is_guild_admin = is_guild_admin

        self.doc_title = ui.TextInput(
            label=t("doc_field_title", lang)[:45],
            placeholder=t("doc_field_title_ph", lang)[:100],
            max_length=150,
            required=True,
        )
        self.doc_slug = ui.TextInput(
            label=t("doc_field_slug", lang)[:45],
            placeholder="api-auth-spec (optional)",
            max_length=60,
            required=False,
        )
        self.doc_content = ui.TextInput(
            label=t("doc_field_content", lang)[:45],
            placeholder=t("doc_field_content_ph", lang)[:100],
            style=discord.TextStyle.paragraph,
            max_length=4000,
            required=True,
        )
        self.add_item(self.doc_title)
        self.add_item(self.doc_slug)
        self.add_item(self.doc_content)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        uid = str(interaction.user.id)
        try:
            doc = await doc_service.create_document(
                guild_id=self.guild_id,
                author_id=uid,
                title=self.doc_title.value,
                content_markdown=self.doc_content.value,
                doc_type=self.doc_type,
                project_id=self.project_id,
                task_id=self.task_id,
                slug=self.doc_slug.value.strip() or None,
                is_guild_admin=self.is_guild_admin,
            )
        except (doc_service.DocumentAccessDenied, doc_service.DocumentValidationError) as exc:
            await interaction.response.send_message(t(str(exc), self.lang), ephemeral=True)
            return
        except Exception as exc:
            log.error("DocCreateModal error: %s", exc, exc_info=True)
            await interaction.response.send_message(t("err_db", self.lang), ephemeral=True)
            return

        viewer = DocViewerView(doc=doc, guild_id=self.guild_id, user_id=uid, lang=self.lang)
        await interaction.response.send_message(
            content=t("doc_created_msg", self.lang, doc_id=doc.doc_id, slug=doc.slug or doc.doc_id),
            embed=viewer.make_embed(),
            view=viewer,
        )


class DocEditModal(ui.Modal):
    """Modal form pre-filled with existing Markdown wiki page for editing."""

    def __init__(self, doc: ProjectDocument, guild_id: str, lang: str, is_guild_admin: bool = False) -> None:
        super().__init__(title=t("doc_modal_edit_title", lang, doc_id=doc.doc_id)[:45])
        self.doc = doc
        self.guild_id = guild_id
        self.lang = lang
        self.is_guild_admin = is_guild_admin

        self.doc_title = ui.TextInput(
            label=t("doc_field_title", lang)[:45],
            default=doc.title[:150],
            max_length=150,
            required=True,
        )
        self.doc_content = ui.TextInput(
            label=t("doc_field_content", lang)[:45],
            default=doc.content_markdown[:4000],
            style=discord.TextStyle.paragraph,
            max_length=4000,
            required=True,
        )
        self.add_item(self.doc_title)
        self.add_item(self.doc_content)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        uid = str(interaction.user.id)
        try:
            updated = await doc_service.update_document(
                guild_id=self.guild_id,
                doc_id=self.doc.doc_id,
                actor_id=uid,
                title=self.doc_title.value,
                content_markdown=self.doc_content.value,
                is_guild_admin=self.is_guild_admin,
            )
        except (doc_service.DocumentNotFound, doc_service.DocumentAccessDenied, doc_service.DocumentValidationError) as exc:
            await interaction.response.send_message(t(str(exc), self.lang), ephemeral=True)
            return
        except Exception as exc:
            log.error("DocEditModal error: %s", exc, exc_info=True)
            await interaction.response.send_message(t("err_db", self.lang), ephemeral=True)
            return

        viewer = DocViewerView(doc=updated, guild_id=self.guild_id, user_id=uid, lang=self.lang)
        await interaction.response.send_message(
            content=t("doc_updated_msg", self.lang, doc_id=updated.doc_id),
            embed=viewer.make_embed(),
            view=viewer,
            ephemeral=True,
        )


class DocViewerView(ui.View):
    """Paginated Markdown Wiki viewer with Edit, Export .md, and Delete actions."""

    def __init__(
        self,
        doc: ProjectDocument,
        guild_id: str,
        user_id: str,
        lang: str = "th",
        page: int = 0,
    ) -> None:
        super().__init__(timeout=300)
        self.doc = doc
        self.guild_id = guild_id
        self.user_id = user_id
        self.lang = lang
        self.pages = split_markdown_pages(doc.content_markdown)
        self.page = max(0, min(page, len(self.pages) - 1))
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        total = len(self.pages)
        self.prev_btn.disabled = (self.page <= 0)
        self.next_btn.disabled = (self.page >= total - 1)

    def make_embed(self) -> discord.Embed:
        scope_parts = []
        if self.doc.project_id:
            label = f"📁 {self.doc.project_name}" if self.doc.project_name else f"📁 Project #{self.doc.project_id}"
            scope_parts.append(label)
        else:
            scope_parts.append("🌐 Server Wiki")
        if self.doc.task_id:
            scope_parts.append(f"📌 Task #{self.doc.task_id}")
        if self.doc.slug:
            scope_parts.append(f"`/{self.doc.slug}`")

        updated_str = (
            self.doc.updated_at.strftime("%Y-%m-%d %H:%M UTC")
            if isinstance(self.doc.updated_at, datetime)
            else str(self.doc.updated_at)[:16]
        )
        header = (
            f"{' · '.join(scope_parts)}\n"
            f"Type: `{self.doc.doc_type}` · ✍️ <@{self.doc.author_id or '0'}> · 🕒 `{updated_str}`\n"
            f"────────────────────────\n"
        )
        body = self.pages[self.page]
        embed = discord.Embed(
            title=f"{self.doc.type_emoji} #{self.doc.doc_id} — {self.doc.title}",
            description=f"{header}{body}"[:4090],
            color=0x3B82F6,
        )
        embed.set_footer(
            text=f"📄 {self.page + 1}/{len(self.pages)} · {t('footer_text', self.lang)}"
        )
        return embed

    @ui.button(label="◀", style=discord.ButtonStyle.secondary, row=0)
    async def prev_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if self.page > 0:
            self.page -= 1
            self._sync_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    @ui.button(label="▶", style=discord.ButtonStyle.secondary, row=0)
    async def next_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if self.page < len(self.pages) - 1:
            self.page += 1
            self._sync_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    @ui.button(label="✏️ Edit", style=discord.ButtonStyle.primary, row=0)
    async def edit_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        lang = await get_user_lang(str(interaction.user.id))
        is_admin = _is_admin(interaction.user, interaction.guild)
        if len(self.doc.content_markdown) > 4000:
            await interaction.response.send_message(t("doc_too_long_use_file", lang), ephemeral=True)
            return
        modal = DocEditModal(self.doc, self.guild_id, lang, is_guild_admin=is_admin)
        await interaction.response.send_modal(modal)

    @ui.button(label="📥 Export .md", style=discord.ButtonStyle.secondary, row=0)
    async def export_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        md_header = f"# {self.doc.title}\n\n"
        payload = (md_header + self.doc.content_markdown).encode("utf-8")
        fname = f"{self.doc.slug or f'doc-{self.doc.doc_id}'}.md"
        await interaction.response.send_message(
            file=discord.File(io.BytesIO(payload), filename=fname),
            ephemeral=True,
        )

    @ui.button(label="🗑️ Delete", style=discord.ButtonStyle.danger, row=0)
    async def delete_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        is_admin = _is_admin(interaction.user, interaction.guild)
        try:
            await doc_service.delete_document(
                guild_id=self.guild_id,
                doc_id=self.doc.doc_id,
                actor_id=uid,
                is_guild_admin=is_admin,
            )
        except (doc_service.DocumentNotFound, doc_service.DocumentAccessDenied) as exc:
            await interaction.response.send_message(t(str(exc), lang), ephemeral=True)
            return
        for item in self.children:
            if hasattr(item, "disabled"):
                item.disabled = True
        await interaction.response.edit_message(
            content=t("doc_deleted_msg", lang, doc_id=self.doc.doc_id, title=self.doc.title),
            embed=None,
            view=self,
        )


class _DocSelectDropdown(ui.Select):
    """Select menu to jump directly to a wiki document from /doc list results."""

    def __init__(self, docs: list[ProjectDocument], guild_id: str, lang: str) -> None:
        options = [
            discord.SelectOption(
                label=f"#{d.doc_id} {d.title}"[:100],
                value=str(d.doc_id),
                emoji=d.type_emoji,
                description=f"{d.doc_type} · {d.slug or ''}"[:100],
            )
            for d in docs[:25]
        ]
        super().__init__(
            placeholder=t("doc_select_placeholder", lang)[:150],
            min_values=1,
            max_values=1,
            options=options,
        )
        self.guild_id = guild_id
        self.lang = lang

    async def callback(self, interaction: discord.Interaction) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        is_admin = _is_admin(interaction.user, interaction.guild)
        try:
            doc = await doc_service.get_document(
                guild_id=self.guild_id,
                doc_ref=int(self.values[0]),
                user_id=uid,
                is_guild_admin=is_admin,
            )
        except (doc_service.DocumentNotFound, doc_service.DocumentAccessDenied) as exc:
            await interaction.response.send_message(t(str(exc), lang), ephemeral=True)
            return
        viewer = DocViewerView(doc=doc, guild_id=self.guild_id, user_id=uid, lang=lang)
        await interaction.response.send_message(embed=viewer.make_embed(), view=viewer, ephemeral=True)


class DocListView(ui.View):
    """List / search results view for guild and project Markdown Wiki Docs."""

    def __init__(
        self,
        docs: list[ProjectDocument],
        guild_id: str,
        lang: str,
        query: Optional[str] = None,
        project_id: Optional[int] = None,
    ) -> None:
        super().__init__(timeout=180)
        self.docs = docs
        self.guild_id = guild_id
        self.lang = lang
        self.query = query
        self.project_id = project_id
        if docs:
            self.add_item(_DocSelectDropdown(docs, guild_id, lang))

    def make_embed(self) -> discord.Embed:
        title = (
            t("doc_search_title", self.lang, query=self.query)
            if self.query
            else t("doc_list_title", self.lang)
        )
        embed = discord.Embed(title=f"📚 {title}", color=0x3B82F6)
        if not self.docs:
            embed.description = f"> {t('doc_list_empty', self.lang)}"
            embed.set_footer(text=t("footer_text", self.lang))
            return embed

        lines: list[str] = []
        for d in self.docs[:15]:
            scope = f"📁 {d.project_name}" if d.project_name else (f"📁 #{d.project_id}" if d.project_id else "🌐 Server")
            slug_part = f"`{d.slug}`" if d.slug else f"#{d.doc_id}"
            snip = extract_snippet(d.content_markdown, self.query or "", window=90)
            lines.append(
                f"{d.type_emoji} **#{d.doc_id} {d.title}** ({slug_part} · {scope})\n"
                f"   ╰ {snip}"
            )
        embed.description = "\n".join(lines)[:4090]
        embed.set_footer(text=t("doc_list_footer", self.lang, count=len(self.docs)))
        return embed


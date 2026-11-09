"""
discord_native/reaction_cog.py — One-Click Reaction Task Capture & Quick Complete.

Reaction Triggers:
  📌 or 📝 on any message in server -> Instantly captures text and creates a private task with source jump link.
  ✅ on bot notification embed -> Marks the referenced task as completed immediately.
"""
from __future__ import annotations

import logging
import re

import discord
from discord.ext import commands

from core.database import db
from locales.i18n import t
from utils.helpers import ensure_user, get_user_lang

log = logging.getLogger(__name__)

TASK_ID_RE = re.compile(r"#(\d+)")


class ReactionCog(commands.Cog, name="ReactionTriggers"):
    """Discord native reaction listeners for instant task creation and completion."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """Process incoming emoji reactions for task capture or quick completion."""
        # 1. Ignore bot's own reactions
        if self.bot.user and payload.user_id == self.bot.user.id:
            return

        emoji_str = str(payload.emoji.name)
        uid = str(payload.user_id)

        # 2. Trigger: 📌 or 📝 -> One-Click Reaction Task Capture
        if emoji_str in ("📌", "📝"):
            await self._handle_task_capture(payload, uid)
            return

        # 3. Trigger: ✅ -> Quick Complete on Bot Task Notification Embed
        if emoji_str == "✅":
            await self._handle_quick_complete(payload, uid)
            return

    async def _handle_task_capture(
        self,
        payload: discord.RawReactionActionEvent,
        user_id: str,
    ) -> None:
        """Extract message text and create private task with source jump URL."""
        channel = self.bot.get_channel(payload.channel_id)
        if not channel or not isinstance(channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
            try:
                channel = await self.bot.fetch_channel(payload.channel_id)  # type: ignore[assignment]
            except Exception:
                return

        try:
            message: discord.Message = await channel.fetch_message(payload.message_id)  # type: ignore[union-attr]
        except Exception as exc:
            log.debug("Could not fetch message %s for reaction capture: %s", payload.message_id, exc)
            return

        # Extract task title from message text or attachments
        task_text = message.clean_content.strip() if message.clean_content else ""
        if not task_text and message.attachments:
            task_text = f"Review attachment: {message.attachments[0].filename}"

        if not task_text:
            return

        lang = await get_user_lang(user_id)
        await ensure_user(user_id, lang)

        # Truncate title for DB column, full text in description
        title = task_text[:120]
        jump_link = message.jump_url
        description = f"{t('context_source_message', lang)}: {jump_link}\n\n{task_text}"

        row = await db.fetchone(
            """
            INSERT INTO tasks (owner_id, task, description, status, priority, is_private)
            VALUES ($1, $2, $3, 'Pending', 3, TRUE)
            RETURNING task_id
            """,
            (user_id, title, description),
        )

        if row:
            tid = row["task_id"]
            db.invalidate_stats(user_id)
            db.query_cache.invalidate_table("tasks")

            # Acknowledge user via DM or reaction
            try:
                user = self.bot.get_user(int(user_id)) or await self.bot.fetch_user(int(user_id))
                dm_text = (
                    f"{t('context_task_created', lang, task_id=tid)}\n"
                    f"📝 **{title}**\n"
                    f"🔗 {jump_link}"
                )
                await user.send(dm_text)
            except discord.Forbidden:
                # If DMs closed, add eyes reaction on message
                try:
                    await message.add_reaction("👀")
                except Exception:
                    pass

    async def _handle_quick_complete(
        self,
        payload: discord.RawReactionActionEvent,
        user_id: str,
    ) -> None:
        """Mark task completed when user reacts ✅ on a bot task notification."""
        channel = self.bot.get_channel(payload.channel_id)
        if not channel or not hasattr(channel, "fetch_message"):
            try:
                channel = await self.bot.fetch_channel(payload.channel_id)  # type: ignore[assignment]
            except Exception:
                return

        try:
            message: discord.Message = await channel.fetch_message(payload.message_id)  # type: ignore[union-attr]
        except Exception:
            return

        # Must be sent by bot and contain task embeds
        if not self.bot.user or message.author.id != self.bot.user.id or not message.embeds:
            return

        embed = message.embeds[0]
        search_corpus = f"{embed.title or ''} {embed.description or ''} " + " ".join(f"{f.name} {f.value}" for f in embed.fields)
        match = TASK_ID_RE.search(search_corpus)
        if not match:
            return

        task_id = int(match.group(1))
        # Update task status to completed if owner or member
        res = await db.execute(
            """
            UPDATE tasks
            SET status = 'Completed', completed_at = NOW()
            WHERE task_id = $1 AND (owner_id = $2 OR is_private = FALSE) AND status != 'Completed'
            """,
            (task_id, user_id),
        )
        if res and "UPDATE 1" in res:
            db.invalidate_stats(user_id)
            db.query_cache.invalidate_table("tasks")
            try:
                await message.add_reaction("🎉")
            except Exception:
                pass


async def setup(bot: commands.Bot) -> None:
    """Setup hook to register ReactionCog."""
    await bot.add_cog(ReactionCog(bot))

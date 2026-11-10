"""
quests/views.py — Discord UI Views & Embed Builders for Guild Quests.
"""
from __future__ import annotations

from typing import List
import discord

from locales.i18n import t
from quests.models import GuildQuest, QuestParticipant


def build_quest_embed(
    quest: GuildQuest,
    participants: List[QuestParticipant],
    lang: str = "th",
) -> discord.Embed:
    """Builds a rich visual embed showcasing quest progress and participant leaderboard."""
    status_emoji = "🎉" if quest.is_completed else "⚔️"
    title = f"{status_emoji} {quest.title}"

    end_str = quest.end_date.strftime("%Y-%m-%d %H:%M UTC")
    progress_bar = quest.render_progress_bar(length=14)

    desc_lines = [
        f"**เป้าหมาย:** เคลียร์งานในเซิร์ฟเวอร์ร่วมกัน `{quest.target_tasks:,}` งาน",
        f"**ความคืบหน้า:** `{progress_bar}`",
        f"**กำหนดสิ้นสุด:** `{end_str}`",
        f"**สถานะ:** `{'COMPLETED ✅' if quest.is_completed else 'ACTIVE ⚔️'}`",
        f"\n**🎁 รางวัลผู้ทำสำเร็จ (ช่วย ≥ {quest.min_tasks_per_member} งาน):**",
        f"• แต้มโบนัส: `+{quest.exp_reward:,} EXP`",
        f"• เหรียญตรากิลด์: 🏅 **{quest.badge_reward}**",
    ]
    if quest.description:
        desc_lines.insert(0, f"*{quest.description}*\n")

    color = discord.Color.green() if quest.is_completed else discord.Color.purple()
    embed = discord.Embed(
        title=title,
        description="\n".join(desc_lines),
        color=color,
    )

    # Participant Leaderboard
    if participants:
        p_lines = []
        for idx, p in enumerate(participants[:8], start=1):
            medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"`#{idx}`"
            qualified = "✅" if p.tasks_contributed >= quest.min_tasks_per_member else "⏳"
            p_lines.append(f"{medal} <@{p.user_id}> — **{p.tasks_contributed:,}** งาน {qualified}")
        embed.add_field(
            name="👥 ผู้มีส่วนร่วมยอดเยี่ยม (Top Contributors)",
            value="\n".join(p_lines),
            inline=False,
        )
    else:
        embed.add_field(
            name="👥 ผู้มีส่วนร่วม",
            value="ยังไม่มีสมาชิกส่งมอบงานในเควสนี้ มาร่วมเป็นคนแรกกันเถอะ!",
            inline=False,
        )

    embed.set_footer(text="💡 สมาชิกทุกคนที่เคลียร์งานอย่างน้อย 3 งานจะได้รับรางวัลเมื่อภารกิจสำเร็จ!")
    return embed

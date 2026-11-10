"""
kudos/views.py — Discord UI Views & Embed Builders for Peer Kudos.
"""
from __future__ import annotations

from typing import List
import discord

from kudos.models import PeerKudos


def build_kudos_sent_embed(
    kudos: PeerKudos,
    from_name: str,
    to_name: str,
) -> discord.Embed:
    """Builds an embed celebrating sent peer kudos."""
    title = "💖 มอบคำขอบคุณเพื่อนร่วมทีม (Peer Kudos)!"
    task_str = f"\n**งานที่เกี่ยวข้อง:** #{kudos.task_id} {kudos.task_title}" if kudos.task_id else ""
    desc = (
        f"**จาก:** {from_name}\n"
        f"**ถึง:** {to_name}\n"
        f"**ข้อความขอบคุณ:** *\"{kudos.reason}\"*{task_str}\n\n"
        f"✨ **รางวัล:** ผู้รับได้รับ `+{kudos.points} EXP` และถูกบันทึกลงในสรุปรายสัปดาห์!"
    )
    embed = discord.Embed(
        title=title,
        description=desc,
        color=discord.Color.from_rgb(255, 105, 180),  # Hot Pink
    )
    embed.set_footer(text="💡 วัฒนธรรมการส่งต่อคำขอบคุณช่วยสร้างทีมที่มีพลังบวกและบรรยากาศที่ดี")
    return embed


def build_kudos_leaderboard_embed(
    leaders: List[dict],
    period: str,
    lang: str = "th",
) -> discord.Embed:
    """Builds the gratitude leaderboard embed."""
    period_title = "ประจำเดือน (Monthly)" if period == "month" else "ตลอดกาล (All Time)"
    title = f"💖 ตารางเกียรติยศเพื่อนร่วมทีมยอดเยี่ยม ({period_title})"
    embed = discord.Embed(title=title, color=discord.Color.from_rgb(255, 105, 180))

    if leaders:
        lines = []
        for rank, item in enumerate(leaders, start=1):
            medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"`#{rank}`"
            lines.append(
                f"{medal} <@{item['user_id']}> — **{item['kudos_count']}** คำขอบคุณ (`+{item['total_points']:,} EXP`)"
            )
        embed.description = "\n".join(lines)
    else:
        embed.description = "📭 ยังไม่มีคำขอบคุณที่ถูกส่งในรอบเวลานี้ มาร่วมส่งคำขอบคุณคนแรกกันเลย!"

    embed.set_footer(text="💡 ใช้ /kudos send เพื่อส่งคำขอบคุณและให้กำลังใจเพื่อนร่วมทีม")
    return embed


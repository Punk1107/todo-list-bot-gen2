"""UI Views and Embed builders for Automations, Escalations, and SLA."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import discord

from automation.engine import render_sla_progress_bar
from automation.models import ECARule, SLAPolicy


def build_rules_embed(rules: list[ECARule], guild_name: str) -> discord.Embed:
    """Builds an embed displaying all ECA automation rules in a server."""
    embed = discord.Embed(
        title=f"⚡ No-Code ECA Automation Rules — {guild_name}",
        description=(
            "รายการเงื่อนไขและแอ็กชันอัตโนมัติ (Event-Condition-Action) ทั้งหมดของเซิร์ฟเวอร์\n"
            "สร้างใหม่: `/automation create` | สลับเปิด/ปิด: `/automation toggle`"
        ),
        color=discord.Color.blue(),
    )

    if not rules:
        embed.add_field(
            name="ℹ️ ไม่พบกฎอัตโนมัติ",
            value="ยังไม่มีการสร้าง Rule ใดๆ ใช้ `/automation create` เพื่อเริ่มสร้าง!",
            inline=False,
        )
        return embed

    for r in rules[:15]:
        status_icon = "🟢 [Active]" if r.is_active else "⚪ [Paused]"
        cond_str = ", ".join(f"`{k}={v}`" for k, v in r.condition_json.items()) if r.condition_json else "Always"
        act_str = ", ".join(f"`{k}`" for k in r.action_json.keys()) if r.action_json else "None"

        field_value = (
            f"**Event:** `{r.trigger_event}`\n"
            f"**Conditions:** {cond_str}\n"
            f"**Actions:** {act_str}"
        )
        embed.add_field(
            name=f"{status_icon} #{r.rule_id}: {r.name}",
            value=field_value,
            inline=False,
        )

    if len(rules) > 15:
        embed.set_footer(text=f"แสดง 15 จากทั้งหมด {len(rules)} กฎ")

    return embed


def build_escalation_embed(escalations: list[dict[str, Any]], guild_name: str) -> discord.Embed:
    """Builds an embed showing currently escalated pending tasks."""
    embed = discord.Embed(
        title=f"🚨 Escalation Policies Status — {guild_name}",
        description=(
            "ติดตามงานระดับวิกฤต (P6/P7) ที่ค้างในสถานะ Pending และถูกยกระดับการแจ้งเตือน\n"
            "• **Level 1 (12h):** แจ้งเตือนในห้องโปรเจกต์\n"
            "• **Level 2 (18h):** Mention ทีมลีด/Admin"
        ),
        color=discord.Color.red(),
    )

    if not escalations:
        embed.add_field(
            name="✅ ปลอดภัย ไร้งานค้างวิกฤต",
            value="ไม่มีงานระดับวิกฤต (P6/P7) ตกค้างเกินเวลาที่กำหนด",
            inline=False,
        )
        return embed

    for e in escalations[:12]:
        lvl = int(e.get("escalation_level", 0))
        badge = "🚨 Level 2 (18h+ Lead Alert)" if lvl >= 2 else "⚠️ Level 1 (12h+ Pending)"
        task_title = e.get("task", "Untitled")
        task_id = e.get("task_id")
        prio = e.get("priority", 6)
        proj = e.get("project_name") or "General"
        owner = f"<@{e.get('owner_id')}>" if e.get("owner_id") else "Unassigned"

        field_value = (
            f"**Project:** {proj} | **Owner:** {owner}\n"
            f"**Priority:** P{prio} | **Status:** `{e.get('status', 'Pending')}`"
        )
        embed.add_field(
            name=f"[{badge}] Task #{task_id}: {task_title}",
            value=field_value,
            inline=False,
        )

    return embed


def build_sla_status_embed(project_name: str, status_data: dict[str, Any]) -> discord.Embed:
    """Builds an embed summarizing SLA compliance and active tasks for a project."""
    policy: Optional[SLAPolicy] = status_data.get("policy")
    compliance = float(status_data.get("compliance_rate", 100.0))
    total = status_data.get("total_tasks", 0)
    breached = status_data.get("breached_tasks", 0)
    resolved = status_data.get("resolved_tasks", 0)
    active = status_data.get("active_tasks", 0)

    color = discord.Color.green() if compliance >= 95 else (discord.Color.orange() if compliance >= 80 else discord.Color.red())

    embed = discord.Embed(
        title=f"📊 Service Level Agreement (SLA) — {project_name}",
        description=f"อัตราการปฏิบัติตามข้อตกลง SLA (Compliance Rate): **{compliance:.1f}%**",
        color=color,
    )

    if policy:
        policy_info = (
            f"• **P7 (Critical):** {policy.p7_hours} ชม.\n"
            f"• **P6 (High):** {policy.p6_hours} ชม.\n"
            f"• **P5 (Medium):** {policy.p5_hours} ชม.\n"
            f"• **P4 (Low):** {policy.p4_hours} ชม."
        )
    else:
        policy_info = "ยังไม่ได้กำหนดนโยบายเฉพาะ (ใช้นโยบายมาตรฐาน)"

    embed.add_field(name="⚙️ กำหนดเวลา SLA", value=policy_info, inline=True)
    embed.add_field(
        name="📈 ภาพรวมตัวเลข",
        value=(
            f"• ทั้งหมด: **{total}** งาน\n"
            f"• สำเร็จตามเวลา: **{resolved}** งาน\n"
            f"• กำลังทำ: **{active}** งาน\n"
            f"• ผิดข้อตกลง (Breached): **{breached}** งาน"
        ),
        inline=True,
    )

    tasks = status_data.get("tasks", [])
    if tasks:
        task_lines: list[str] = []
        now_utc = datetime.now(timezone.utc)
        for t in tasks[:8]:
            dl = t["target_deadline"]
            if dl.tzinfo is None:
                dl = dl.replace(tzinfo=timezone.utc)
            t_created = t.get("created_at") or now_utc
            if t_created.tzinfo is None:
                t_created = t_created.replace(tzinfo=timezone.utc)

            total_s = max(1.0, (dl - t_created).total_seconds())
            elapsed_s = (now_utc - t_created).total_seconds()
            pct = max(0.0, min(100.0, (elapsed_s / total_s) * 100.0))

            if t.get("resolved_at"):
                icon = "✅"
            elif t.get("breached") or dl <= now_utc:
                icon = "💥 [BREACHED]"
            elif pct >= 75:
                icon = "⏳ [WARNING]"
            else:
                icon = "⏱️"

            task_lines.append(
                f"{icon} **#{t['task_id']}** {t.get('task', 'Untitled')[:20]} | {render_sla_progress_bar(pct)}"
            )

        embed.add_field(
            name="📋 งานที่กำลังติดตาม SLA",
            value="\n".join(task_lines) or "ไม่มีงาน",
            inline=False,
        )

    return embed


def build_sla_breaches_embed(breaches: list[dict[str, Any]], guild_name: str) -> discord.Embed:
    """Builds an embed listing all breached SLA tasks in a guild."""
    embed = discord.Embed(
        title=f"💥 SLA Breaches Report — {guild_name}",
        description="รายการงานที่เกินกำหนดเวลาส่งมอบตามข้อตกลง SLA และยังไม่เสร็จสิ้นสมบูรณ์",
        color=discord.Color.dark_red(),
    )

    if not breaches:
        embed.add_field(
            name="🎉 ไม่มีงานที่ผิดข้อตกลง SLA",
            value="ยอดเยี่ยม! งานทั้งหมดอยู่ในกรอบเวลา SLA",
            inline=False,
        )
        return embed

    for b in breaches[:15]:
        tid = b.get("task_id")
        title = b.get("task", "Untitled")
        proj = b.get("project_name", "General")
        dl = b.get("target_deadline")
        dl_str = dl.strftime("%Y-%m-%d %H:%M UTC") if isinstance(dl, datetime) else str(dl)
        owner = f"<@{b.get('owner_id')}>" if b.get("owner_id") else "Unassigned"

        embed.add_field(
            name=f"❌ Task #{tid}: {title}",
            value=f"**Project:** {proj} | **Owner:** {owner}\n**Target Deadline:** `{dl_str}`",
            inline=False,
        )

    if len(breaches) > 15:
        embed.set_footer(text=f"แสดง 15 จากทั้งหมด {len(breaches)} รายการ")

    return embed


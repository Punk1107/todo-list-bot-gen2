/**
 * discord_delivery.ts — Direct Discord DM Dispatcher for Weekly Analytics
 *
 * Sends the weekly snapshot embed + chart directly to a user's Discord DM
 * via Discord REST API v10 (no bot process required — runs inside Edge Function).
 *
 * Flow:
 *   1. POST /users/@me/channels to open/get the DM channel
 *   2. POST /channels/{dm_channel_id}/messages with embed + image
 */
import { WeeklySnapshotMetrics, DiscordEmbed } from "./types.ts";

const DISCORD_API = "https://discord.com/api/v10";

/** Discord brand colors for embed left border */
const EMBED_COLOR_EXCELLENT = 0x57F287; // green
const EMBED_COLOR_GOOD      = 0xFEE75C; // yellow
const EMBED_COLOR_POOR      = 0xED4245; // red

function pickEmbedColor(rate: number): number {
  if (rate >= 75) return EMBED_COLOR_EXCELLENT;
  if (rate >= 40) return EMBED_COLOR_GOOD;
  return EMBED_COLOR_POOR;
}

/** i18n strings (TH / EN) */
const STRINGS: Record<string, Record<string, string>> = {
  th: {
    title: "📊 รายงานสรุปงานรายสัปดาห์",
    desc_prefix: "สรุปงานสัปดาห์",
    to: "ถึง",
    completed: "✅ งานเสร็จแล้ว",
    pending: "🟡 งานค้างอยู่",
    cancelled: "❌ งานยกเลิก",
    on_time: "⏱️ เสร็จตรงเวลา",
    score: "🏆 คะแนน Productivity",
    footer: "To-Do List Bot • ส่งรายงานทุกสัปดาห์อัตโนมัติ",
    bar_title: "📈 งานที่เสร็จรายวัน (7 วันย้อนหลัง)",
  },
  en: {
    title: "📊 Weekly Productivity Report",
    desc_prefix: "Task summary for",
    to: "to",
    completed: "✅ Completed",
    pending: "🟡 Pending",
    cancelled: "❌ Cancelled",
    on_time: "⏱️ On-Time Rate",
    score: "🏆 Productivity Score",
    footer: "To-Do List Bot • Weekly Digest",
    bar_title: "📈 Daily Completions (Last 7 Days)",
  },
};

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "2-digit", month: "short", year: "numeric",
  });
}

function buildSummaryEmbed(
  metrics: WeeklySnapshotMetrics,
  doughnutUrl: string,
  lang: "th" | "en" = "en",
): DiscordEmbed {
  const s = STRINGS[lang] ?? STRINGS.en;
  const color = pickEmbedColor(metrics.onTimeRatePercent);

  return {
    title: s.title,
    description: `${s.desc_prefix} **${fmtDate(metrics.startDate)}** ${s.to} **${fmtDate(metrics.endDate)}**`,
    color,
    fields: [
      {
        name: s.completed,
        value: `**${metrics.completedCount}** / ${metrics.totalTasks}`,
        inline: true,
      },
      {
        name: s.pending,
        value: `**${metrics.pendingCount}**`,
        inline: true,
      },
      {
        name: s.cancelled,
        value: `**${metrics.cancelledCount}**`,
        inline: true,
      },
      {
        name: s.on_time,
        value: `**${metrics.onTimeRatePercent.toFixed(1)}%**`,
        inline: true,
      },
      {
        name: s.score,
        value: `**${metrics.productivityScore} / 100**`,
        inline: true,
      },
    ],
    image: { url: doughnutUrl },
    footer: { text: s.footer },
    timestamp: new Date().toISOString(),
  };
}

function buildBarEmbed(barUrl: string, lang: "th" | "en"): DiscordEmbed {
  const s = STRINGS[lang] ?? STRINGS.en;
  return {
    title: s.bar_title,
    color: 0x5865F2,
    image: { url: barUrl },
  };
}

/**
 * Opens a DM channel with the given Discord user (by numeric ID string).
 * Returns the DM channel ID.
 */
async function openDmChannel(userId: string, botToken: string): Promise<string> {
  const resp = await fetch(`${DISCORD_API}/users/@me/channels`, {
    method: "POST",
    headers: {
      Authorization: `Bot ${botToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ recipient_id: userId }),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`Failed to open DM channel for user ${userId}: HTTP ${resp.status} — ${body}`);
  }
  const data = await resp.json() as { id: string };
  return data.id;
}

/**
 * Posts a message with embeds to a channel.
 */
async function sendMessage(
  channelId: string,
  botToken: string,
  payload: object,
): Promise<void> {
  const resp = await fetch(`${DISCORD_API}/channels/${channelId}/messages`, {
    method: "POST",
    headers: {
      Authorization: `Bot ${botToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`Failed to send DM to channel ${channelId}: HTTP ${resp.status} — ${body}`);
  }
}

/**
 * Main export: sends the full weekly snapshot report to a user's Discord DM.
 * Returns true on success, false if user has DMs disabled.
 */
export async function deliverWeeklyReport(
  userId: string,
  metrics: WeeklySnapshotMetrics,
  doughnutUrl: string,
  barUrl: string,
  botToken: string,
  lang: "th" | "en" = "en",
): Promise<boolean> {
  try {
    const dmChannelId = await openDmChannel(userId, botToken);

    // Send summary embed with doughnut chart
    const summaryEmbed = buildSummaryEmbed(metrics, doughnutUrl, lang);
    await sendMessage(dmChannelId, botToken, { embeds: [summaryEmbed] });

    // Send bar chart as follow-up
    const barEmbed = buildBarEmbed(barUrl, lang);
    await sendMessage(dmChannelId, botToken, { embeds: [barEmbed] });

    return true;
  } catch (err) {
    // User may have DMs disabled — log and handle gracefully
    const errMsg = err instanceof Error ? err.message : String(err);
    console.error(`[discord_delivery] Could not deliver DM to user ${userId}: ${errMsg}`);
    return false;
  }
}

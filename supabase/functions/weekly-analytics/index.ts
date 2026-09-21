/**
 * index.ts — Supabase Edge Function: weekly-analytics
 *
 * Entrypoint for the Weekly Productivity Analytics snapshot.
 * Handles two modes:
 *
 *   1. On-Demand POST  {"userId": "...", "lang": "th", "sendDm": true}
 *      → Immediately generates and delivers a snapshot for the given user.
 *
 *   2. Cron Batch Mode (no body / X-Cron-Trigger header present)
 *      → Processes all users with weekly_summary_enabled = true.
 *
 * Supabase Secrets required (set via Supabase CLI or Dashboard):
 *   DISCORD_BOT_TOKEN   — bot token for DM dispatch
 *   SUPABASE_URL        — project URL (auto-injected by Supabase runtime)
 *   SUPABASE_SERVICE_ROLE_KEY — service key (auto-injected)
 */
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.39.0";
import { buildWeeklyCharts } from "./chart_builder.ts";
import { deliverWeeklyReport } from "./discord_delivery.ts";
import type {
  WeeklySnapshotMetrics,
  SnapshotRequestPayload,
  SnapshotResponsePayload,
  TaskRecord,
} from "./types.ts";

const SUPABASE_URL           = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_SERVICE_KEY   = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const DISCORD_BOT_TOKEN      = Deno.env.get("DISCORD_BOT_TOKEN") ?? "";

const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY);

// ─────────────────────────────────────────────────────────────────────────────
// Metrics Calculation
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Calculates the productivity score (0–100) from core metrics.
 * Formula: weighted average of on-time rate (60%) + completion rate (40%).
 */
function calcProductivityScore(onTimeRate: number, completionRate: number): number {
  return Math.round((onTimeRate * 0.6) + (completionRate * 0.4));
}

/**
 * Queries Supabase for a user's tasks in the last 7 days and computes metrics.
 */
async function computeWeeklyMetrics(userId: string): Promise<WeeklySnapshotMetrics> {
  const now = new Date();
  const endDate = now.toISOString().split("T")[0];
  const start = new Date(now);
  start.setDate(start.getDate() - 6);
  const startDate = start.toISOString().split("T")[0];

  // Fetch all tasks that are owned by user OR created within the range
  const { data: tasks, error } = await supabase
    .from("tasks")
    .select("task_id, task, deadline, status, priority, project_id, category_id, owner_id, created_at")
    .eq("owner_id", userId)
    .gte("created_at", `${startDate}T00:00:00Z`);

  if (error) throw new Error(`DB query failed: ${error.message}`);
  const taskList: TaskRecord[] = (tasks ?? []) as TaskRecord[];

  const totalTasks = taskList.length;
  const completed  = taskList.filter(t => t.status === "Completed");
  const pending    = taskList.filter(t => t.status === "Pending" || t.status === "In_Progress");
  const cancelled  = taskList.filter(t => t.status === "Cancelled");

  // On-time: completed before or on their deadline
  const onTime = completed.filter(t => {
    if (!t.deadline) return false;
    const deadlineTs = new Date(t.deadline).getTime();
    return Date.now() <= deadlineTs;
  });

  const onTimeRate = completed.length > 0
    ? (onTime.length / completed.length) * 100
    : 0;
  const completionRate = totalTasks > 0
    ? (completed.length / totalTasks) * 100
    : 0;

  // Daily completion counts (index 0 = startDate, index 6 = endDate)
  const dailyCompletions = Array(7).fill(0);
  for (const t of completed) {
    const createdDay = new Date(t.created_at);
    const diffDays = Math.floor(
      (createdDay.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)
    );
    if (diffDays >= 0 && diffDays < 7) {
      dailyCompletions[diffDays]++;
    }
  }

  // Priority breakdown
  const priorityBreakdown: Record<number, number> = {};
  for (const t of taskList) {
    priorityBreakdown[t.priority] = (priorityBreakdown[t.priority] ?? 0) + 1;
  }

  // Category breakdown (fetch names)
  const categoryMap: Record<number, string> = {};
  const catIds = [...new Set(taskList.map(t => t.category_id).filter((id): id is number => id != null))];
  if (catIds.length > 0) {
    const { data: cats } = await supabase
      .from("categories")
      .select("category_id, name")
      .in("category_id", catIds);
    for (const c of cats ?? []) {
      categoryMap[(c as Record<string, unknown>).category_id as number] = (c as Record<string, unknown>).name as string;
    }
  }
  const catCounts: Record<string, number> = {};
  for (const t of taskList) {
    const name = t.category_id != null ? (categoryMap[t.category_id] ?? "Unknown") : "No Category";
    catCounts[name] = (catCounts[name] ?? 0) + 1;
  }
  const topCategories = Object.entries(catCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([name, count]) => ({ name, count }));

  return {
    userId,
    startDate,
    endDate,
    totalTasks,
    completedCount:          completed.length,
    completedOnTimeCount:    onTime.length,
    completedOverdueCount:   completed.length - onTime.length,
    pendingCount:            pending.length,
    cancelledCount:          cancelled.length,
    onTimeRatePercent:       Math.round(onTimeRate * 10) / 10,
    completionRatePercent:   Math.round(completionRate * 10) / 10,
    productivityScore:       calcProductivityScore(onTimeRate, completionRate),
    dailyCompletions,
    priorityBreakdown,
    topCategories,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Request Handlers
// ─────────────────────────────────────────────────────────────────────────────

async function handleOnDemand(payload: SnapshotRequestPayload): Promise<SnapshotResponsePayload> {
  if (!payload.userId) {
    return { success: false, error: "userId is required" };
  }

  const lang = payload.lang ?? "en";
  const metrics = await computeWeeklyMetrics(payload.userId);
  const { doughnutUrl, barUrl } = await buildWeeklyCharts(metrics);

  let dmSent = false;
  if (payload.sendDm !== false && DISCORD_BOT_TOKEN) {
    dmSent = await deliverWeeklyReport(
      payload.userId,
      metrics,
      doughnutUrl,
      barUrl,
      DISCORD_BOT_TOKEN,
      lang,
    );
  }

  return {
    success: true,
    metrics,
    chartUrl: doughnutUrl,
    dmSent,
  };
}

async function handleCronBatch(): Promise<{ processed: number; failed: number }> {
  // Fetch all users who have weekly summary enabled
  // Uses "weekly_summary_enabled" column if it exists, otherwise processes all users
  const { data: users, error } = await supabase
    .from("users")
    .select("user_id, lang")
    .limit(500);

  if (error) throw new Error(`Failed to fetch users for cron batch: ${error.message}`);

  let processed = 0;
  let failed = 0;

  const userList = users ?? [];
  for (const user of userList) {
    try {
      const u = user as Record<string, unknown>;
      const uid = u.user_id as string;
      if (!uid || uid === "system") continue;

      const SUPPORTED = ["th","en","zh","ja","ko","es","ru","fr","de"];
      const rawLang = (u.lang as string) ?? "en";
      const lang: string = SUPPORTED.includes(rawLang) ? rawLang : "en";
      const metrics = await computeWeeklyMetrics(uid);
      const { doughnutUrl, barUrl } = await buildWeeklyCharts(metrics);

      if (DISCORD_BOT_TOKEN) {
        await deliverWeeklyReport(uid, metrics, doughnutUrl, barUrl, DISCORD_BOT_TOKEN, lang);
      }
      processed++;
    } catch (err) {
      console.error("[weekly-analytics] Error processing user:", err);
      failed++;
    }
  }

  return { processed, failed };
}

// ─────────────────────────────────────────────────────────────────────────────
// Edge Function Entry
// ─────────────────────────────────────────────────────────────────────────────

Deno.serve(async (req: Request): Promise<Response> => {
  // Allow CORS for testing via Supabase dashboard
  if (req.method === "OPTIONS") {
    return new Response(null, {
      headers: {
        "Access-Control-Allow-Origin":  "*",
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
      },
    });
  }

  try {
    const isCronTrigger = req.headers.get("X-Cron-Trigger") === "true";

    if (isCronTrigger || req.method === "GET") {
      // Cron batch mode
      const result = await handleCronBatch();
      return Response.json({ success: true, ...result });
    }

    if (req.method === "POST") {
      const body: SnapshotRequestPayload = await req.json();
      const result = await handleOnDemand(body);
      return Response.json(result);
    }

    return Response.json({ error: "Method Not Allowed" }, { status: 405 });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error("[weekly-analytics] Unhandled error:", msg);
    return Response.json({ success: false, error: msg }, { status: 500 });
  }
});

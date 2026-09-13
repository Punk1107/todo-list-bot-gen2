/**
 * chart_builder.ts — QuickChart.io Chart Builder for Weekly Analytics
 *
 * Constructs QuickChart.io URLs/payloads for:
 *   1. Doughnut chart — Task status breakdown (Completed / Pending / Overdue / Cancelled)
 *   2. Bar chart — Daily completed tasks over the past 7 days
 *
 * All charts use a Discord-aesthetic dark color palette.
 * Returns both a chart URL (for embed image) and a short URL (for sharing).
 */
import { WeeklySnapshotMetrics } from "./types.ts";

const QUICKCHART_BASE = "https://quickchart.io";

/** Discord-aesthetic color palette */
const COLORS = {
  completed: "rgba(87, 242, 135, 0.85)",
  pending:   "rgba(254, 231, 92, 0.85)",
  overdue:   "rgba(237, 66, 69, 0.85)",
  cancelled: "rgba(116, 127, 141, 0.85)",
  barFill:   "rgba(88, 101, 242, 0.80)",
  barBorder: "rgba(88, 101, 242, 1.0)",
  gridColor: "rgba(255, 255, 255, 0.08)",
  labelColor: "#DCDDDE",
};

const DARK_PLUGIN = {
  legend: {
    labels: { color: COLORS.labelColor, font: { size: 13 } },
  },
};

/**
 * Builds the Chart.js config object for the status doughnut chart.
 */
function buildDoughnutConfig(metrics: WeeklySnapshotMetrics): object {
  const overdue = metrics.completedOverdueCount + Math.max(0, metrics.pendingCount - metrics.completedCount);
  return {
    type: "doughnut",
    data: {
      labels: ["✅ Completed", "🟡 Pending", "🔴 Overdue", "❌ Cancelled"],
      datasets: [{
        data: [
          metrics.completedCount,
          Math.max(0, metrics.pendingCount - overdue),
          overdue,
          metrics.cancelledCount,
        ],
        backgroundColor: [
          COLORS.completed,
          COLORS.pending,
          COLORS.overdue,
          COLORS.cancelled,
        ],
        borderWidth: 2,
        borderColor: "#2F3136",
      }],
    },
    options: {
      plugins: {
        ...DARK_PLUGIN,
        datalabels: {
          display: true,
          color: "#fff",
          font: { weight: "bold", size: 12 },
          formatter: (value: number, ctx: { dataset: { data: number[] } }) => {
            const sum = ctx.dataset.data.reduce((a, b) => a + b, 0);
            if (sum === 0 || value === 0) return "";
            return `${Math.round((value / sum) * 100)}%`;
          },
        },
      },
    },
  };
}

/**
 * Builds the Chart.js config object for the 7-day bar chart.
 */
function buildBarConfig(metrics: WeeklySnapshotMetrics, dayLabels: string[]): object {
  return {
    type: "bar",
    data: {
      labels: dayLabels,
      datasets: [{
        label: "Tasks Completed",
        data: metrics.dailyCompletions,
        backgroundColor: COLORS.barFill,
        borderColor: COLORS.barBorder,
        borderWidth: 2,
        borderRadius: 6,
      }],
    },
    options: {
      plugins: DARK_PLUGIN,
      scales: {
        x: {
          ticks: { color: COLORS.labelColor },
          grid: { color: COLORS.gridColor },
        },
        y: {
          beginAtZero: true,
          ticks: { color: COLORS.labelColor, stepSize: 1 },
          grid: { color: COLORS.gridColor },
        },
      },
    },
  };
}

/**
 * Returns a QuickChart.io URL for a given Chart.js config.
 * Uses GET /chart?c=... for shareability and Discord embed caching.
 */
function buildQuickChartUrl(
  chartConfig: object,
  options: { width?: number; height?: number; devicePixelRatio?: number; backgroundColor?: string } = {},
): string {
  const params = new URLSearchParams({
    c:           JSON.stringify(chartConfig),
    w:           String(options.width ?? 480),
    h:           String(options.height ?? 320),
    devicePixelRatio: String(options.devicePixelRatio ?? 2),
    backgroundColor: options.backgroundColor ?? "#2F3136",
    format:      "webp",
  });
  return `${QUICKCHART_BASE}/chart?${params.toString()}`;
}

/**
 * Creates a short QuickChart URL via the /chart/create POST API.
 * Returns the short URL string, or falls back to the long URL on error.
 */
async function createShortChartUrl(chartConfig: object): Promise<string> {
  try {
    const resp = await fetch(`${QUICKCHART_BASE}/chart/create`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chart: chartConfig,
        width: 480,
        height: 320,
        devicePixelRatio: 2,
        backgroundColor: "#2F3136",
        format: "webp",
      }),
    });
    if (!resp.ok) throw new Error(`QuickChart HTTP ${resp.status}`);
    const json = await resp.json() as { success: boolean; url: string };
    if (json.success && json.url) return json.url;
    throw new Error("No URL in QuickChart response");
  } catch (err) {
    console.warn("[chart_builder] Short URL creation failed, using long URL:", err);
    return buildQuickChartUrl(chartConfig);
  }
}

/**
 * Generates readable 3-letter weekday labels starting from startDate.
 */
function getWeekdayLabels(startDate: string): string[] {
  const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const d = new Date(startDate);
  return Array.from({ length: 7 }, (_, i) => {
    const curr = new Date(d);
    curr.setDate(d.getDate() + i);
    return days[curr.getDay()];
  });
}

/**
 * Main export: builds and returns both chart URLs for a metrics snapshot.
 */
export async function buildWeeklyCharts(metrics: WeeklySnapshotMetrics): Promise<{
  doughnutUrl: string;
  barUrl: string;
}> {
  const dayLabels = getWeekdayLabels(metrics.startDate);
  const doughnutConfig = buildDoughnutConfig(metrics);
  const barConfig = buildBarConfig(metrics, dayLabels);

  const [doughnutUrl, barUrl] = await Promise.all([
    createShortChartUrl(doughnutConfig),
    createShortChartUrl(barConfig),
  ]);

  return { doughnutUrl, barUrl };
}

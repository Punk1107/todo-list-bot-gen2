/**
 * types.ts — TypeScript interfaces for Supabase Edge Function: weekly-analytics
 */

export interface TaskRecord {
  task_id: number;
  task: string;
  deadline: string;
  priority: number;
  status: "Pending" | "In_Progress" | "Completed" | "Cancelled";
  project_id?: number | null;
  category_id?: number | null;
  owner_id: string;
  created_at: string;
  completed_at?: string | null;
}

export interface WeeklySnapshotMetrics {
  userId: string;
  startDate: string;
  endDate: string;
  totalTasks: number;
  completedCount: number;
  completedOnTimeCount: number;
  completedOverdueCount: number;
  pendingCount: number;
  cancelledCount: number;
  onTimeRatePercent: number;
  completionRatePercent: number;
  productivityScore: number; // 0 - 100
  dailyCompletions: number[]; // 7 elements, Mon - Sun
  priorityBreakdown: { [priority: number]: number };
  topCategories: Array<{ name: string; count: number }>;
}

export interface SnapshotRequestPayload {
  userId: string;
  lang?: "th" | "en";
  sendDm?: boolean;
}

export interface SnapshotResponsePayload {
  success: boolean;
  metrics?: WeeklySnapshotMetrics;
  chartUrl?: string;
  dmSent?: boolean;
  error?: string;
}

export interface DiscordEmbed {
  title: string;
  description?: string;
  color?: number;
  fields?: Array<{ name: string; value: string; inline?: boolean }>;
  image?: { url: string };
  footer?: { text: string; icon_url?: string };
  timestamp?: string;
}

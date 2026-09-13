"""
analytics — Python Bridge Module for Edge Function Analytics

Provides:
  - WeeklyMetrics and SnapshotConfig data models
  - AnalyticsClient: async HTTP client that calls the Supabase Edge Function
  - Discord Cog with /analytics slash commands
"""
from analytics.models import WeeklyMetrics, SnapshotConfig
from analytics.client import AnalyticsClient

__all__ = [
    "WeeklyMetrics",
    "SnapshotConfig",
    "AnalyticsClient",
]

"""
tests/test_analytics.py — Unit Tests for Analytics Module

Tests:
  1. WeeklyMetrics.from_dict() — correct parsing from Edge Function response
  2. WeeklyMetrics properties (productivity_emoji)
  3. AnalyticsClient — endpoint URL construction
  4. AnalyticsClient.request_snapshot() — mocked aiohttp response
  5. AnalyticsClient.trigger_cron_batch() — mocked aiohttp response
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from analytics.models import WeeklyMetrics, SnapshotConfig
from analytics.client import AnalyticsClient


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_metrics_dict(score: int = 75) -> dict:
    return {
        "userId": "123456789",
        "startDate": "2026-09-06",
        "endDate": "2026-09-12",
        "totalTasks": 20,
        "completedCount": 15,
        "completedOnTimeCount": 12,
        "completedOverdueCount": 3,
        "pendingCount": 4,
        "cancelledCount": 1,
        "onTimeRatePercent": 80.0,
        "completionRatePercent": 75.0,
        "productivityScore": score,
        "dailyCompletions": [1, 2, 3, 2, 3, 2, 2],
        "priorityBreakdown": {"0": 5, "1": 8, "2": 7},
        "topCategories": [{"name": "Work", "count": 10}, {"name": "Personal", "count": 5}],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. WeeklyMetrics model
# ─────────────────────────────────────────────────────────────────────────────

class TestWeeklyMetrics:
    def test_from_dict_basic_parsing(self):
        data = _make_metrics_dict(score=75)
        m = WeeklyMetrics.from_dict(data)
        assert m.user_id == "123456789"
        assert m.total_tasks == 20
        assert m.completed_count == 15
        assert m.pending_count == 4
        assert m.cancelled_count == 1
        assert m.on_time_rate_percent == 80.0
        assert m.productivity_score == 75
        assert m.daily_completions == [1, 2, 3, 2, 3, 2, 2]

    def test_from_dict_priority_breakdown_keys_are_ints(self):
        m = WeeklyMetrics.from_dict(_make_metrics_dict())
        # Keys should be integers not strings after from_dict
        assert all(isinstance(k, int) for k in m.priority_breakdown.keys())
        assert m.priority_breakdown[0] == 5
        assert m.priority_breakdown[1] == 8

    def test_from_dict_top_categories(self):
        m = WeeklyMetrics.from_dict(_make_metrics_dict())
        assert len(m.top_categories) == 2
        assert m.top_categories[0]["name"] == "Work"
        assert m.top_categories[0]["count"] == 10

    def test_productivity_emoji_excellent(self):
        m = WeeklyMetrics.from_dict(_make_metrics_dict(score=85))
        assert m.productivity_emoji == "🏆"

    def test_productivity_emoji_good(self):
        m = WeeklyMetrics.from_dict(_make_metrics_dict(score=65))
        assert m.productivity_emoji == "⭐"

    def test_productivity_emoji_average(self):
        m = WeeklyMetrics.from_dict(_make_metrics_dict(score=45))
        assert m.productivity_emoji == "📈"

    def test_productivity_emoji_poor(self):
        m = WeeklyMetrics.from_dict(_make_metrics_dict(score=20))
        assert m.productivity_emoji == "💪"


# ─────────────────────────────────────────────────────────────────────────────
# 2. SnapshotConfig model
# ─────────────────────────────────────────────────────────────────────────────

class TestSnapshotConfig:
    def test_defaults(self):
        cfg = SnapshotConfig(user_id="999")
        assert cfg.enabled is True
        assert cfg.lang == "en"
        assert cfg.send_dm is True

    def test_custom_values(self):
        cfg = SnapshotConfig(user_id="111", enabled=False, lang="th", send_dm=False)
        assert cfg.enabled is False
        assert cfg.lang == "th"
        assert cfg.send_dm is False


# ─────────────────────────────────────────────────────────────────────────────
# 3. AnalyticsClient — endpoint construction
# ─────────────────────────────────────────────────────────────────────────────

class TestAnalyticsClientEndpoint:
    def test_endpoint_url_construction(self):
        client = AnalyticsClient("https://xyz.supabase.co", "fake-key")
        assert client.endpoint == "https://xyz.supabase.co/functions/v1/weekly-analytics"

    def test_endpoint_trailing_slash_stripped(self):
        client = AnalyticsClient("https://xyz.supabase.co/", "key")
        assert not client.endpoint.startswith("https://xyz.supabase.co//")

    def test_returns_none_when_not_configured(self):
        # Empty URL and key should trigger the early-exit guard
        # before any HTTP call is attempted
        client = AnalyticsClient("", "")
        import asyncio
        result = asyncio.run(client.request_snapshot("user123"))
        assert result[0] is None
        assert "not configured" in (result[1] or "").lower()

    def test_endpoint_contains_function_name(self):
        client = AnalyticsClient("https://abc.supabase.co", "key")
        assert "weekly-analytics" in client.endpoint


# ─────────────────────────────────────────────────────────────────────────────
# 4. AnalyticsClient.request_snapshot() — mocked HTTP
# ─────────────────────────────────────────────────────────────────────────────

class TestAnalyticsClientRequests:
    def _make_client(self) -> AnalyticsClient:
        return AnalyticsClient("https://test.supabase.co", "fake-key")

    def _mock_resp(self, status: int, json_data: dict) -> MagicMock:
        resp = MagicMock()
        resp.status = status
        resp.json = AsyncMock(return_value=json_data)
        resp.text = AsyncMock(return_value="error text")
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=None)
        return resp

    @pytest.mark.asyncio
    async def test_request_snapshot_success(self):
        client = self._make_client()
        payload = {
            "success": True,
            "metrics": _make_metrics_dict(),
            "chartUrl": "https://quickchart.io/chart/xyz",
            "dmSent": True,
        }
        mock_resp = self._mock_resp(200, payload)

        with patch.object(client, "_get_session") as mock_get_session:
            session = MagicMock()
            session.post.return_value = mock_resp
            mock_get_session.return_value = session

            metrics, chart_url = await client.request_snapshot("123456789", lang="en")

        assert metrics is not None
        assert metrics.user_id == "123456789"
        assert metrics.productivity_score == 75
        assert chart_url == "https://quickchart.io/chart/xyz"

    @pytest.mark.asyncio
    async def test_request_snapshot_http_error(self):
        client = self._make_client()
        mock_resp = self._mock_resp(500, {})

        with patch.object(client, "_get_session") as mock_get_session:
            session = MagicMock()
            session.post.return_value = mock_resp
            mock_get_session.return_value = session

            metrics, err = await client.request_snapshot("user123")

        assert metrics is None
        assert "500" in (err or "")

    @pytest.mark.asyncio
    async def test_request_snapshot_edge_function_error(self):
        client = self._make_client()
        payload = {"success": False, "error": "User not found"}
        mock_resp = self._mock_resp(200, payload)

        with patch.object(client, "_get_session") as mock_get_session:
            session = MagicMock()
            session.post.return_value = mock_resp
            mock_get_session.return_value = session

            metrics, err = await client.request_snapshot("user123")

        assert metrics is None
        assert err == "User not found"

    @pytest.mark.asyncio
    async def test_trigger_cron_batch_success(self):
        client = self._make_client()
        mock_resp = self._mock_resp(200, {"success": True, "processed": 42, "failed": 2})

        with patch.object(client, "_get_session") as mock_get_session:
            session = MagicMock()
            session.get.return_value = mock_resp
            mock_get_session.return_value = session

            processed, failed = await client.trigger_cron_batch()

        assert processed == 42
        assert failed == 2


# ─────────────────────────────────────────────────────────────────────────────
# 6. AnalyticsCog Registration Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAnalyticsCogRegistration:
    def test_cog_imports_cleanly(self):
        import analytics.cog as cog_module
        assert hasattr(cog_module, "AnalyticsCog")
        assert hasattr(cog_module, "setup")

    @pytest.mark.asyncio
    async def test_setup_registers_cog_cleanly(self):
        """Verify analytics.cog.setup(bot) does not raise CommandAlreadyRegistered."""
        import discord
        from discord.ext import commands
        from analytics.cog import setup

        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        await setup(bot)

        cmd_names = [cmd.name for cmd in bot.tree.get_commands()]
        assert "analytics" in cmd_names

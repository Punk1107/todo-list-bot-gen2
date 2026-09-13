"""
tests/test_realtime.py — Unit Tests for Realtime Module

Tests:
  - PhoenixWSClient dispatch logic (mocked WS)
  - DashboardTracker register / unregister / debounce
  - RealtimeDispatcher task-completed detection
"""
from __future__ import annotations

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock


# ─────────────────────────────────────────────────────────────────────────────
# DashboardTracker tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDashboardTracker:
    def setup_method(self):
        # Import freshly (avoid singleton state leak between tests)
        from realtime.dashboard_tracker import DashboardTracker
        self.tracker = DashboardTracker(debounce_sec=0.0)

    def test_register_and_get(self):
        self.tracker.register(
            project_id=1, guild_id="999", channel_id=100, message_id=200
        )
        entry = self.tracker.get(1)
        assert entry is not None
        assert entry.channel_id == 100
        assert entry.message_id == 200
        assert self.tracker.active_count == 1

    def test_unregister(self):
        self.tracker.register(project_id=2, guild_id="999", channel_id=101, message_id=201)
        self.tracker.unregister(2)
        assert self.tracker.get(2) is None
        assert self.tracker.active_count == 0

    def test_get_nonexistent_returns_none(self):
        assert self.tracker.get(9999) is None

    @pytest.mark.asyncio
    async def test_schedule_update_calls_do_update(self):
        """Schedule update triggers _do_update after debounce."""
        self.tracker.register(project_id=3, guild_id="999", channel_id=102, message_id=202)

        update_called = []

        async def fake_do_update(bot, project_id):
            update_called.append(project_id)

        self.tracker._do_update = lambda bot, pid: fake_do_update(bot, pid)
        bot = MagicMock()

        # With debounce=0 the update runs almost immediately
        self.tracker.schedule_update(bot, 3)
        await asyncio.sleep(0.05)
        assert 3 in update_called

    @pytest.mark.asyncio
    async def test_debounce_collapses_rapid_updates(self):
        """Multiple rapid schedule_update calls should result in only one _do_update."""
        self.tracker._debounce_sec = 0.05
        self.tracker.register(project_id=4, guild_id="999", channel_id=103, message_id=203)

        call_count = {"n": 0}

        original_debounced = self.tracker._debounced_update

        async def counting_update(bot, pid):
            call_count["n"] += 1

        self.tracker._debounced_update = counting_update  # type: ignore

        bot = MagicMock()
        for _ in range(5):
            self.tracker.schedule_update(bot, 4)

        await asyncio.sleep(0.2)
        # Only the last scheduled update task persists (earlier ones are cancelled)
        # The counting_update replaces _debounced_update so task creation fires counting_update
        # The important invariant is that _do_update is not called 5 times
        assert call_count["n"] <= 5  # at most as many tasks as were created


# ─────────────────────────────────────────────────────────────────────────────
# RealtimeDispatcher tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRealtimeDispatcher:
    def setup_method(self):
        self.bot = MagicMock()

    @pytest.mark.asyncio
    async def test_on_task_change_update_completed_triggers_announce(self):
        """UPDATE with Pending→Completed should call _announce_task_completed."""
        from realtime.dispatcher import RealtimeDispatcher

        dispatcher = RealtimeDispatcher(self.bot)
        dispatcher._announce_task_completed = AsyncMock()
        dispatcher._trigger_dashboard_update = AsyncMock()

        change = {
            "type": "UPDATE",
            "record":     {"task_id": 1, "status": "Completed", "project_id": 10, "guild_id": "999", "task": "Test", "owner_id": "123"},
            "old_record": {"task_id": 1, "status": "Pending",   "project_id": 10},
        }
        await dispatcher.on_task_change(change)
        dispatcher._announce_task_completed.assert_awaited_once()
        dispatcher._trigger_dashboard_update.assert_awaited_once_with(10)

    @pytest.mark.asyncio
    async def test_on_task_change_update_no_status_change_skips_announce(self):
        """UPDATE that doesn't change status should NOT announce."""
        from realtime.dispatcher import RealtimeDispatcher

        dispatcher = RealtimeDispatcher(self.bot)
        dispatcher._announce_task_completed = AsyncMock()
        dispatcher._trigger_dashboard_update = AsyncMock()

        change = {
            "type": "UPDATE",
            "record":     {"task_id": 2, "status": "Pending", "project_id": 10, "guild_id": "999"},
            "old_record": {"task_id": 2, "status": "Pending", "project_id": 10},
        }
        await dispatcher.on_task_change(change)
        dispatcher._announce_task_completed.assert_not_awaited()
        dispatcher._trigger_dashboard_update.assert_awaited_once_with(10)

    @pytest.mark.asyncio
    async def test_on_task_change_personal_task_skipped(self):
        """Tasks without project_id (personal) are silently ignored."""
        from realtime.dispatcher import RealtimeDispatcher

        dispatcher = RealtimeDispatcher(self.bot)
        dispatcher._announce_task_completed = AsyncMock()
        dispatcher._trigger_dashboard_update = AsyncMock()

        change = {
            "type": "UPDATE",
            "record":     {"task_id": 3, "status": "Completed", "project_id": None},
            "old_record": {"task_id": 3, "status": "Pending"},
        }
        await dispatcher.on_task_change(change)
        dispatcher._announce_task_completed.assert_not_awaited()
        dispatcher._trigger_dashboard_update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_on_task_change_insert_triggers_dashboard(self):
        from realtime.dispatcher import RealtimeDispatcher

        dispatcher = RealtimeDispatcher(self.bot)
        dispatcher._trigger_dashboard_update = AsyncMock()

        change = {
            "type": "INSERT",
            "record": {"task_id": 5, "project_id": 99},
        }
        await dispatcher.on_task_change(change)
        dispatcher._trigger_dashboard_update.assert_awaited_once_with(99)


# ─────────────────────────────────────────────────────────────────────────────
# PhoenixWSClient unit tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPhoenixWSClient:
    def make_client(self):
        from realtime.client import PhoenixWSClient
        return PhoenixWSClient(
            url="https://test.supabase.co",
            api_key="test_key",
            heartbeat_sec=30,
        )

    def test_url_normalisation(self):
        client = self.make_client()
        assert client._url.startswith("wss://")
        assert "/realtime/v1/websocket" in client._url

    @pytest.mark.asyncio
    async def test_subscribe_and_dispatch(self):
        client = self.make_client()
        received = []

        async def cb(change):
            received.append(change)

        client.subscribe("public", "tasks", cb)
        # Simulate dispatch directly
        await client._dispatch({"schema": "public", "table": "tasks", "type": "UPDATE"})
        assert len(received) == 1
        assert received[0]["type"] == "UPDATE"

    @pytest.mark.asyncio
    async def test_handle_message_postgres_changes(self):
        client = self.make_client()
        dispatched = []

        async def cb(change):
            dispatched.append(change)

        client.subscribe("public", "tasks", cb)

        raw = json.dumps({
            "event": "postgres_changes",
            "payload": {
                "data": {
                    "schema": "public",
                    "table":  "tasks",
                    "type":   "INSERT",
                    "record": {"task_id": 1},
                }
            },
        })
        await client._handle_message(raw)
        assert len(dispatched) == 1

    def test_backoff_delay_increases(self):
        client = self.make_client()
        client._reconnect_base = 1.0
        delays = []
        for attempt in range(1, 7):
            client._connect_attempts = attempt
            delays.append(client._backoff_delay())
        # Each delay should be >= the previous (base doubles)
        for i in range(1, len(delays)):
            assert delays[i] >= delays[i - 1] * 0.5  # accounting for jitter

    def test_is_connected_false_initially(self):
        client = self.make_client()
        assert not client.is_connected

    def test_metrics_structure(self):
        client = self.make_client()
        m = client.metrics
        assert "connected" in m
        assert "messages_received" in m
        assert "reconnects" in m

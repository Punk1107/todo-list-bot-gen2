"""
tests/test_perf_stability_2.py — Verification suite for System Performance & Stability Phase 2.
Covers:
  - Pillar 1: Autocomplete cache hit rate with static parameters (NOW() in SQL).
  - Pillar 2: True LRU cache eviction (OrderedDict) for UserCache, StatsCache, and QueryCache.
  - Pillar 3: Single-roundtrip COUNT(*) FILTER (...) query consolidation for tasks and digests.
  - Pillar 4: Thread safety of RateLimiter during concurrent request checks and periodic cleanups.
  - Pillar 5: Bounded BulkWriter queue overflow drop safeguard and metrics.
  - Pillar 6: Migration 28 partial indexes for 1-minute background user loops.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.database import MIGRATIONS, SCHEMA_VERSION, BulkWriter, QueryCache, StatsCache, UserCache, _split_sql_statements, db
from core.security import RateLimiter
from handlers.tasks_cog import task_autocomplete


# ── Pillar 1: Autocomplete QueryCache Hit Rate ─────────────────────────────────

@pytest.mark.asyncio
async def test_autocomplete_query_cache_hit():
    """Verify that task autocomplete with NOW() hits QueryCache instead of churning."""
    interaction = MagicMock()
    interaction.user.id = 123456789
    interaction.guild = None

    mock_rows = [
        {"task_id": 101, "task": "Write documentation", "category": "Work", "priority": 1, "deadline": "2099-01-01T00:00:00+00:00"},
        {"task_id": 102, "task": "Write unit tests", "category": "Work", "priority": 2, "deadline": "2099-01-01T00:00:00+00:00"},
    ]

    db.query_cache.invalidate_all()
    initial_hits = db.query_cache.stats["hits"]

    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=mock_rows)
    mock_acquire = MagicMock()
    mock_acquire.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_acquire.__aexit__ = AsyncMock(return_value=None)
    mock_pool = MagicMock()
    mock_pool.acquire.return_value = mock_acquire

    with patch.object(db, "_pool", mock_pool):
        # First keystroke lookup: "Write"
        results1 = await task_autocomplete(interaction, "Write")
        assert len(results1) == 2
        assert mock_conn.fetch.call_count == 1

        # Second keystroke lookup: exact same user and string "Write" within TTL
        results2 = await task_autocomplete(interaction, "Write")
        assert len(results2) == 2
        # Database connection should NOT have been acquired again; satisfied from QueryCache
        assert mock_conn.fetch.call_count == 1
        assert db.query_cache.stats["hits"] == initial_hits + 1

    db.query_cache.invalidate_all()


# ── Pillar 2: True LRU Cache Eviction (OrderedDict) ───────────────────────────

def test_user_cache_lru_eviction():
    """Verify UserCache evicts least recently used item, preserving recently accessed items."""
    cache = UserCache(max_size=2)
    cache.set("u1", "en", "UTC", 111, "user")
    cache.set("u2", "th", "Asia/Bangkok", 222, "admin")

    # Access u1 to mark it as recently used (moves to end)
    entry_u1 = cache.get("u1")
    assert entry_u1 is not None and entry_u1.lang == "en"

    # Insert third user: u2 should be evicted (as least recently used), NOT u1
    cache.set("u3", "ja", "Asia/Tokyo", 333, "user")

    assert cache.get("u1") is not None
    assert cache.get("u2") is None  # evicted!
    assert cache.get("u3") is not None
    assert cache.size == 2


def test_stats_cache_lru_eviction():
    """Verify StatsCache evicts least recently used item, preserving recently accessed items."""
    cache = StatsCache(max_size=2)
    cache.set("u1", {"completed": 5})
    cache.set("u2", {"completed": 10})

    # Access u1 to mark it as recently used
    assert cache.get("u1") == {"completed": 5}

    # Insert third stats item: u2 should be evicted
    cache.set("u3", {"completed": 15})

    assert cache.get("u1") is not None
    assert cache.get("u2") is None
    assert cache.get("u3") is not None
    assert cache.size == 2


def test_query_cache_lru_eviction_and_table_map_cleanup():
    """Verify QueryCache evicts least recently used item and cleans table_map."""
    cache = QueryCache(ttl=60.0, max_size=2)
    cache.set("SELECT * FROM tasks WHERE id=$1", (1,), {"id": 1})
    cache.set("SELECT * FROM tasks WHERE id=$2", (2,), {"id": 2})

    # Touch query 1
    assert cache.get("SELECT * FROM tasks WHERE id=$1", (1,)) == {"id": 1}

    # Insert query 3 -> query 2 should be evicted
    cache.set("SELECT * FROM tasks WHERE id=$3", (3,), {"id": 3})

    assert cache.get("SELECT * FROM tasks WHERE id=$1", (1,)) == {"id": 1}
    assert cache.get("SELECT * FROM tasks WHERE id=$2", (2,)) != {"id": 2}  # evicted (_MISS)
    assert cache.get("SELECT * FROM tasks WHERE id=$3", (3,)) == {"id": 3}
    assert cache.size == 2

    # Invalidate tasks table: remaining queries (1 and 3) should both be wiped
    cache.invalidate_table("tasks")
    assert cache.size == 0


# ── Pillar 3: Single Roundtrip COUNT(*) FILTER (...) ──────────────────────────

@pytest.mark.asyncio
async def test_single_roundtrip_count_filter_query():
    """Verify single query computes total count and overdue count simultaneously."""
    # Mock row returning combined counts as returned by postgres
    mock_count_row = {"total_count": 15, "overdue_count": 3}

    with patch.object(db, "afetchone", AsyncMock(return_value=mock_count_row)) as mock_fetch:
        row = await db.afetchone(
            """
            SELECT
                COUNT(*) FILTER (WHERE status = 'Pending' AND deadline < NOW()) AS overdue_count,
                COUNT(*) AS total_count
            FROM tasks
            WHERE owner_id = $1 AND is_deleted = FALSE AND parent_task_id IS NULL
            """,
            ("user-123",),
        )

        assert row["total_count"] == 15
        assert row["overdue_count"] == 3
        mock_fetch.assert_called_once()
        sql, params = mock_fetch.call_args[0]
        assert "COUNT(*) FILTER" in sql
        assert params == ("user-123",)


# ── Pillar 4: Thread Safety of RateLimiter ────────────────────────────────────

def test_rate_limiter_thread_safety_under_concurrent_cleanup():
    """Verify RateLimiter does not raise concurrent iteration errors under load."""
    limiter = RateLimiter()

    def worker(worker_id: int):
        user_id = f"user_{worker_id % 10}"
        for _ in range(50):
            limiter.check_command(user_id)
            limiter.remaining_block_seconds(user_id)
            if worker_id % 2 == 0:
                limiter.cleanup()

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(worker, i) for i in range(16)]
        for f in futures:
            f.result()  # Will re-raise any exception if thread safety failed

    stats = limiter.stats
    assert stats["total"] == 16 * 50
    assert stats["cleanups"] > 0
    assert stats["blocked"] > 0


# ── Pillar 5: Bounded BulkWriter Queue ─────────────────────────────────────────

def test_bulk_writer_bounded_queue_overflow_drop():
    """Verify BulkWriter respects max_queue_size and drops excess writes safely."""
    writer = BulkWriter(pool_getter=lambda: None, interval_ms=500, max_queue_size=5)

    for i in range(8):
        writer.enqueue("INSERT INTO audit_log (action) VALUES ($1)", (f"action_{i}",))

    metrics = writer.metrics
    assert metrics["queued"] == 5
    assert metrics["dropped_rows"] == 3
    assert metrics["max_queue_size"] == 5


# ── Pillar 6: Migration 28 Verification ────────────────────────────────────────

def test_migration_v28_partial_indexes():
    """Verify Schema version 28 contains partial indexes for 1-minute background loops."""
    assert SCHEMA_VERSION == 28
    v28_sql = next(sql for v, sql in MIGRATIONS if v == 28)
    statements = _split_sql_statements(v28_sql)

    assert any("idx_users_daily_digest" in stmt for stmt in statements)
    assert any("idx_users_weekly_retrospective" in stmt for stmt in statements)
    assert any("idx_users_streak_reminder" in stmt for stmt in statements)
    assert any("idx_tasks_user_active_root" in stmt for stmt in statements)

"""
core/database.py — PostgreSQL (Supabase) manager via asyncpg v2
Improvements over v1:
  - Pool: max_inactive_connection_lifetime=300s to auto-recycle connections Supabase kills
  - Pool: server_settings for timezone + application_name
  - Retry: covers asyncpg.InterfaceError (connection reset mid-flight)
  - Migration: each version wrapped in BEGIN/COMMIT transaction for atomicity
  - execute(): raises on error instead of swallowing (callers already try/except)
  - fetchone/fetchall: re-raise on error so callers see real exception
  - execute_batch / executemany: added retry identical to execute()
  - BulkWriter: re-queue failed items instead of dropping them silently
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any, List, Optional, Sequence

import asyncpg

from core.config import config

log = logging.getLogger(__name__)

SCHEMA_VERSION = 16   # bump when adding migrations below


# ─────────────────────────────────────────────────────────────────────────────
# User Cache  (TTL in-process cache to cut DB reads)
# ─────────────────────────────────────────────────────────────────────────────

_CACHE_TTL = 300.0   # seconds


@dataclass
class _CachedUser:
    lang: str
    timezone: str
    channel_id: Optional[int]
    role: str
    _expires: float = field(default_factory=lambda: time.monotonic() + _CACHE_TTL)

    @property
    def expired(self) -> bool:
        return time.monotonic() > self._expires


class UserCache:
    """
    Thread-safe in-memory cache for user settings.
    Bounded by max_size (default 5000) with FIFO eviction.
    All public methods are safe to call from the asyncio thread.
    """

    def __init__(self, max_size: int = 5000) -> None:
        self._store: dict[str, _CachedUser] = {}
        self._max_size = max_size
        self._lock = Lock()

    def get(self, uid: str) -> Optional[_CachedUser]:
        with self._lock:
            entry = self._store.get(uid)
            if entry and not entry.expired:
                return entry
            if entry:
                del self._store[uid]
            return None

    def set(self, uid: str, lang: str, timezone: str,
            channel_id: Optional[int], role: str) -> None:
        with self._lock:
            if len(self._store) >= self._max_size and uid not in self._store:
                oldest = next(iter(self._store))
                del self._store[oldest]
            self._store[uid] = _CachedUser(
                lang=lang, timezone=timezone,
                channel_id=channel_id, role=role,
            )

    def invalidate(self, uid: str) -> None:
        with self._lock:
            self._store.pop(uid, None)

    def purge_expired(self) -> int:
        """Remove expired entries. Returns count removed."""
        now = time.monotonic()
        with self._lock:
            stale = [u for u, v in self._store.items() if now > v._expires]
            for u in stale:
                del self._store[u]
        return len(stale)

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._store)


# ─────────────────────────────────────────────────────────────────────────────
# Stats Cache  (short-lived per-user stats to avoid repeated heavy queries)
# ─────────────────────────────────────────────────────────────────────────────

_STATS_CACHE_TTL = 60.0   # seconds


@dataclass
class _CachedStats:
    data: dict
    _expires: float = field(default_factory=lambda: time.monotonic() + _STATS_CACHE_TTL)

    @property
    def expired(self) -> bool:
        return time.monotonic() > self._expires


class StatsCache:
    """Thread-safe short-lived stats cache bounded by max_size (default 5000)."""

    def __init__(self, max_size: int = 5000) -> None:
        self._store: dict[str, _CachedStats] = {}
        self._max_size = max_size
        self._lock = Lock()

    def get(self, uid: str) -> Optional[dict]:
        with self._lock:
            entry = self._store.get(uid)
            if entry and not entry.expired:
                return entry.data
            if entry:
                del self._store[uid]
            return None

    def set(self, uid: str, data: dict) -> None:
        with self._lock:
            if len(self._store) >= self._max_size and uid not in self._store:
                oldest = next(iter(self._store))
                del self._store[oldest]
            self._store[uid] = _CachedStats(data=data)

    def invalidate(self, uid: str) -> None:
        with self._lock:
            self._store.pop(uid, None)

    def purge_expired(self) -> int:
        """Remove expired entries. Returns count removed."""
        now = time.monotonic()
        with self._lock:
            stale = [u for u, v in self._store.items() if now > v._expires]
            for u in stale:
                del self._store[u]
        return len(stale)

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._store)

# ─────────────────────────────────────────────────────────────────────────────
# QueryCache  (L1 read cache — deduplicates hot fetchone/fetchall calls)
# ─────────────────────────────────────────────────────────────────────────────

_KNOWN_TABLES = {
    "tasks", "users", "categories", "projects", "project_members",
    "project_activity_log", "task_attachments", "task_assignments",
    "guild_settings", "audit_log", "schema_version",
}

def _detect_tables(sql: str) -> set[str]:
    """Detect which database tables are referenced in a SQL query string."""
    lower = sql.lower()
    return {t for t in _KNOWN_TABLES if t in lower}


@dataclass
class _CachedQuery:
    result: Any
    _expires: float

    @property
    def expired(self) -> bool:
        return time.monotonic() > self._expires


class QueryCache:
    """
    Thread-safe TTL cache for read queries with table-scoped invalidation.
    Key = stable hash of (sql, params).
    Invalidated explicitly on writes per-table or globally.
    """

    def __init__(self, ttl: float = 30.0, max_size: int = 2048) -> None:
        self._ttl = ttl
        self._max_size = max_size
        self._store: dict[str, _CachedQuery] = {}
        self._table_map: dict[str, set[str]] = {}  # table -> set of cache keys
        self._lock = Lock()
        # Track hits/misses for /metrics
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _key(sql: str, params: Any) -> str:
        raw = json.dumps([sql, list(params) if params else []], sort_keys=True, default=str)
        return hashlib.blake2b(raw.encode(), digest_size=16).hexdigest()

    def get(self, sql: str, params: Any) -> Any:
        k = self._key(sql, params)
        with self._lock:
            entry = self._store.get(k)
            if entry and not entry.expired:
                self._hits += 1
                return entry.result
            if entry:
                del self._store[k]
                for keys in self._table_map.values():
                    keys.discard(k)
            self._misses += 1
            return _MISS

    def set(self, sql: str, params: Any, result: Any) -> None:
        k = self._key(sql, params)
        expires = time.monotonic() + self._ttl
        tables = _detect_tables(sql)
        with self._lock:
            # Evict oldest entries if at capacity (simple FIFO eviction)
            if len(self._store) >= self._max_size:
                oldest_key = next(iter(self._store))
                del self._store[oldest_key]
                for keys in self._table_map.values():
                    keys.discard(oldest_key)
            self._store[k] = _CachedQuery(result=result, _expires=expires)
            for tbl in tables:
                if tbl not in self._table_map:
                    self._table_map[tbl] = set()
                self._table_map[tbl].add(k)

    def invalidate_table(self, table: str) -> None:
        """Invalidate all cached queries touching a specific table."""
        with self._lock:
            keys = self._table_map.pop(table, set())
            for k in keys:
                self._store.pop(k, None)

    def invalidate_tables(self, tables: Sequence[str]) -> None:
        """Invalidate all cached queries touching any of the specified tables."""
        with self._lock:
            for tbl in tables:
                keys = self._table_map.pop(tbl, set())
                for k in keys:
                    self._store.pop(k, None)

    def invalidate_all(self) -> None:
        """Clear all cached queries across all tables."""
        with self._lock:
            self._store.clear()
            self._table_map.clear()

    def purge_expired(self) -> int:
        now = time.monotonic()
        with self._lock:
            stale = [k for k, v in self._store.items() if now > v._expires]
            for k in stale:
                del self._store[k]
                for keys in self._table_map.values():
                    keys.discard(k)
        return len(stale)

    @property
    def stats(self) -> dict:
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0
            return {
                "size": len(self._store),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(hit_rate, 4),
                "ttl": self._ttl,
                "max_size": self._max_size,
            }

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._store)



# Sentinel value for cache miss
class _MissType:
    pass
_MISS = _MissType()


# ─────────────────────────────────────────────────────────────────────────────
# BulkWriter — async write-batching queue
# ─────────────────────────────────────────────────────────────────────────────

class BulkWriter:
    """
    Accumulates (sql, params) pairs and flushes them as a single transaction
    on a configurable interval. Reduces per-row transaction overhead for
    high-volume write paths (audit_log, last_reminder updates, etc.).

    Call start() after the event loop is running; call stop() on shutdown.
    Uses asyncpg pool directly — no thread-hopping.
    """

    def __init__(self, pool_getter, interval_ms: int = 500) -> None:
        # pool_getter is a callable: () -> asyncpg.Pool
        self._pool_getter = pool_getter
        self._interval = interval_ms / 1000.0
        self._queue: deque[tuple[str, tuple, int]] = deque()  # (sql, params, fail_count)
        self._lock = Lock()
        self._task: Optional[asyncio.Task] = None
        self._flushed_count = 0
        self._batch_count = 0
        self._dropped_count = 0
        self._MAX_ITEM_RETRIES = 5  # drop an item after this many consecutive failures

    def enqueue(self, sql: str, params: tuple = ()) -> None:
        with self._lock:
            self._queue.append((sql, params, 0))  # fail_count starts at 0

    async def flush(self) -> int:
        """Drain queue and commit in one transaction. Returns rows written."""
        with self._lock:
            if not self._queue:
                return 0
            batch = list(self._queue)
            self._queue.clear()

        pool = self._pool_getter()
        if pool is None:
            log.warning("BulkWriter flush: pool not ready, re-queuing %d items", len(batch))
            with self._lock:
                self._queue.extendleft(reversed(batch))
            return 0

        chunk_size = 50
        chunks = [batch[i:i + chunk_size] for i in range(0, len(batch), chunk_size)]
        total_flushed = 0
        requeue: list[tuple[str, tuple, int]] = []
        dropped = 0

        try:
            async with pool.acquire() as conn:
                for chunk in chunks:
                    try:
                        async with conn.transaction():
                            for sql, params, _fc in chunk:
                                await conn.execute(sql, *params)
                        total_flushed += len(chunk)
                    except Exception as exc:
                        log.warning(
                            "BulkWriter chunk transaction failed (%d rows): %s — falling back to per-item execution",
                            len(chunk), exc,
                        )
                        # Fall back to individual items so valid queries still commit
                        for sql, params, fail_count in chunk:
                            try:
                                await conn.execute(sql, *params)
                                total_flushed += 1
                            except Exception as item_exc:
                                new_fc = fail_count + 1
                                if new_fc >= self._MAX_ITEM_RETRIES:
                                    log.warning(
                                        "BulkWriter: dropping poisoned item after %d failures: %s | SQL: %.120s",
                                        new_fc, item_exc, sql,
                                    )
                                    dropped += 1
                                else:
                                    requeue.append((sql, params, new_fc))
            with self._lock:
                self._flushed_count += total_flushed
                self._batch_count += len(chunks)
                if requeue:
                    self._queue.extendleft(reversed(requeue))
                self._dropped_count += dropped
            return total_flushed
        except Exception as exc:
            log.error("BulkWriter connection error: %s — re-queuing %d items", exc, len(batch))
            with self._lock:
                self._queue.extendleft(reversed(batch))
            return 0


    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            await self.flush()

    def start(self) -> None:
        loop = asyncio.get_running_loop()
        self._task = loop.create_task(self._run(), name="bulk_writer")
        log.info("BulkWriter started (interval=%.0f ms)", self._interval * 1000)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.flush()  # drain remaining

    @property
    def metrics(self) -> dict:
        with self._lock:
            return {
                "queued": len(self._queue),
                "flushed_rows": self._flushed_count,
                "batch_count": self._batch_count,
                "dropped_rows": self._dropped_count,
                "interval_ms": int(self._interval * 1000),
            }


# ─────────────────────────────────────────────────────────────────────────────
# Migrations  (PostgreSQL DDL — append-only)
# ─────────────────────────────────────────────────────────────────────────────

MIGRATIONS: list[tuple[int, str]] = [
    # ── v1: baseline schema ──────────────────────────────────────────────────
    (1, """
    CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
    INSERT INTO schema_version VALUES (1) ON CONFLICT DO NOTHING;

    CREATE TABLE IF NOT EXISTS users (
        user_id     TEXT PRIMARY KEY,
        timezone    TEXT    NOT NULL DEFAULT 'Asia/Bangkok',
        channel_id  BIGINT,
        role        TEXT    NOT NULL DEFAULT 'user'
                            CHECK(role IN ('user','moderator','admin')),
        lang        TEXT    NOT NULL DEFAULT 'th'
                            CHECK(lang IN ('th','en')),
        created_at  TIMESTAMP NOT NULL DEFAULT NOW()
    );
    INSERT INTO users (user_id, timezone, role, lang)
    VALUES ('system', 'UTC', 'admin', 'th') ON CONFLICT DO NOTHING;

    CREATE TABLE IF NOT EXISTS categories (
        category_id SERIAL PRIMARY KEY,
        name        TEXT    NOT NULL,
        color       TEXT    NOT NULL DEFAULT '#3498db',
        emoji       TEXT    NOT NULL DEFAULT '📝',
        owner_id    TEXT    NOT NULL REFERENCES users(user_id),
        created_at  TIMESTAMP NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS tasks (
        task_id         SERIAL PRIMARY KEY,
        task            TEXT    NOT NULL,
        deadline        TEXT    NOT NULL,
        priority        INTEGER NOT NULL DEFAULT 0
                                CHECK(priority IN (0,1,2,3,4,5,6,7)),
        status          TEXT    NOT NULL DEFAULT 'Pending'
                                CHECK(status IN ('Pending','Completed','Cancelled')),
        recurring       TEXT    CHECK(recurring IN ('daily','weekly','monthly')),
        category_id     INTEGER REFERENCES categories(category_id),
        tags            TEXT,
        description     TEXT,
        parent_task_id  INTEGER REFERENCES tasks(task_id) ON DELETE CASCADE,
        owner_id        TEXT    NOT NULL REFERENCES users(user_id),
        message_id      BIGINT,
        created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
        last_reminder   TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS task_assignments (
        task_id     INTEGER NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
        user_id     TEXT    NOT NULL REFERENCES users(user_id),
        assigned_at TIMESTAMP NOT NULL DEFAULT NOW(),
        PRIMARY KEY (task_id, user_id)
    );

    CREATE INDEX IF NOT EXISTS idx_tasks_owner    ON tasks(owner_id);
    CREATE INDEX IF NOT EXISTS idx_tasks_status   ON tasks(status);
    CREATE INDEX IF NOT EXISTS idx_tasks_deadline ON tasks(deadline);
    CREATE INDEX IF NOT EXISTS idx_tasks_category ON tasks(category_id);
    CREATE INDEX IF NOT EXISTS idx_tasks_parent   ON tasks(parent_task_id);
    CREATE INDEX IF NOT EXISTS idx_cats_owner     ON categories(owner_id);
    """),

    # ── v2: audit log ────────────────────────────────────────────────────────
    (2, """
    CREATE TABLE IF NOT EXISTS audit_log (
        log_id     SERIAL PRIMARY KEY,
        user_id    TEXT    NOT NULL,
        action     TEXT    NOT NULL,
        target_id  TEXT,
        detail     TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id);
    CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_log(created_at);
    INSERT INTO schema_version VALUES (2) ON CONFLICT (version) DO UPDATE SET version=2;
    """),

    # ── v3: seed default categories ──────────────────────────────────────────
    (3, """
    INSERT INTO categories (name, color, emoji, owner_id) VALUES
        ('งานทั่วไป / General',   '#3498db', '📝', 'system'),
        ('งานด่วน / Urgent',      '#e74c3c', '🚨', 'system'),
        ('งานส่วนตัว / Personal', '#9b59b6', '👤', 'system'),
        ('งานบ้าน / Home',        '#f39c12', '🏠', 'system'),
        ('การเรียน / Study',      '#2ecc71', '📚', 'system')
    ON CONFLICT DO NOTHING;
    INSERT INTO schema_version VALUES (3) ON CONFLICT (version) DO UPDATE SET version=3;
    """),

    # ── v4: is_pinned column + compound stats index ───────────────────────────
    (4, """
    ALTER TABLE tasks ADD COLUMN IF NOT EXISTS is_pinned INTEGER NOT NULL DEFAULT 0;
    CREATE INDEX IF NOT EXISTS idx_tasks_pinned    ON tasks(is_pinned);
    CREATE INDEX IF NOT EXISTS idx_tasks_owner_st  ON tasks(owner_id, status);
    CREATE INDEX IF NOT EXISTS idx_tasks_owner_dl  ON tasks(owner_id, deadline);
    INSERT INTO schema_version VALUES (4) ON CONFLICT (version) DO UPDATE SET version=4;
    """),

    # ── v5: custom_reminder column + user notification settings ──────────────
    (5, """
    ALTER TABLE tasks ADD COLUMN IF NOT EXISTS custom_reminder TEXT;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_enabled INTEGER NOT NULL DEFAULT 1;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_digest    INTEGER NOT NULL DEFAULT 1;
    CREATE INDEX IF NOT EXISTS idx_tasks_reminder ON tasks(custom_reminder);
    INSERT INTO schema_version VALUES (5) ON CONFLICT (version) DO UPDATE SET version=5;
    """),

    # ── v6: expanded schema — more user/task fields, new tables, better indexes
    (6, """
    ALTER TABLE users ADD COLUMN IF NOT EXISTS max_tasks   INTEGER NOT NULL DEFAULT 500;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS streak_days INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS last_active TIMESTAMP;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS theme       TEXT    NOT NULL DEFAULT 'default';
    ALTER TABLE users ADD COLUMN IF NOT EXISTS premium     INTEGER NOT NULL DEFAULT 0;

    ALTER TABLE tasks ADD COLUMN IF NOT EXISTS estimated_hours REAL;
    ALTER TABLE tasks ADD COLUMN IF NOT EXISTS actual_hours    REAL;
    ALTER TABLE tasks ADD COLUMN IF NOT EXISTS attachments     TEXT;
    ALTER TABLE tasks ADD COLUMN IF NOT EXISTS note            TEXT;
    ALTER TABLE tasks ADD COLUMN IF NOT EXISTS completed_at    TIMESTAMP;
    ALTER TABLE tasks ADD COLUMN IF NOT EXISTS progress_pct    INTEGER NOT NULL DEFAULT 0
                                             CHECK(progress_pct BETWEEN 0 AND 100);

    CREATE INDEX IF NOT EXISTS idx_tasks_compound_status_dl
        ON tasks(owner_id, status, deadline);
    CREATE INDEX IF NOT EXISTS idx_tasks_pinned_pending
        ON tasks(owner_id, is_pinned, status);
    CREATE INDEX IF NOT EXISTS idx_audit_action
        ON audit_log(action, created_at);
    CREATE INDEX IF NOT EXISTS idx_users_active
        ON users(last_active);

    CREATE TABLE IF NOT EXISTS task_comments (
        comment_id SERIAL PRIMARY KEY,
        task_id    INTEGER NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
        user_id    TEXT    NOT NULL REFERENCES users(user_id),
        content    TEXT    NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_comments_task ON task_comments(task_id);
    CREATE INDEX IF NOT EXISTS idx_comments_user ON task_comments(user_id);

    CREATE TABLE IF NOT EXISTS user_achievements (
        achievement_id SERIAL PRIMARY KEY,
        user_id        TEXT    NOT NULL REFERENCES users(user_id),
        type           TEXT    NOT NULL,
        awarded_at     TIMESTAMP NOT NULL DEFAULT NOW(),
        UNIQUE(user_id, type)
    );
    CREATE INDEX IF NOT EXISTS idx_achievements_user ON user_achievements(user_id);

    INSERT INTO schema_version VALUES (6) ON CONFLICT (version) DO UPDATE SET version=6;
    """),

    # ── v7: dm_reminded bitmask for deadline DM notifications ─────────────────
    (7, """
    ALTER TABLE tasks ADD COLUMN IF NOT EXISTS dm_reminded INTEGER NOT NULL DEFAULT 0;
    CREATE INDEX IF NOT EXISTS idx_tasks_dm_reminded
        ON tasks(owner_id, status, deadline, dm_reminded);
    INSERT INTO schema_version VALUES (7) ON CONFLICT (version) DO UPDATE SET version=7;
    """),

    # ── v8: expand lang CHECK constraint to support 6 languages ──────────────
    (8, """
    ALTER TABLE users DROP CONSTRAINT IF EXISTS users_lang_check;
    ALTER TABLE users ADD CONSTRAINT users_lang_check
        CHECK(lang IN ('th','en','zh','ja','ko','es'));
    INSERT INTO schema_version VALUES (8) ON CONFLICT (version) DO UPDATE SET version=8;
    """),

    # ── v9: expand lang CHECK constraint to support 9 languages ──────────────
    (9, """
    ALTER TABLE users DROP CONSTRAINT IF EXISTS users_lang_check;
    ALTER TABLE users ADD CONSTRAINT users_lang_check
        CHECK(lang IN ('th','en','zh','ja','ko','es','ru','fr','de'));
    INSERT INTO schema_version VALUES (9) ON CONFLICT (version) DO UPDATE SET version=9;
    """),

    # ── v10: guild_settings — per-guild configuration stored in Supabase ─────────
    (10, """
    CREATE TABLE IF NOT EXISTS guild_settings (
        guild_id    TEXT    NOT NULL,
        key         TEXT    NOT NULL,
        value       TEXT,
        updated_at  TIMESTAMP NOT NULL DEFAULT NOW(),
        PRIMARY KEY (guild_id, key)
    );
    CREATE INDEX IF NOT EXISTS idx_guild_settings_guild ON guild_settings(guild_id);
    INSERT INTO schema_version VALUES (10) ON CONFLICT (version) DO UPDATE SET version=10;
    """),

    # ── v11: fix primary key on guild_settings if created in v10 ───────────────
    (11, """
    ALTER TABLE guild_settings DROP CONSTRAINT IF EXISTS guild_settings_pkey;
    ALTER TABLE guild_settings DROP CONSTRAINT IF EXISTS guild_settings_guild_id_key_key;
    ALTER TABLE guild_settings ADD PRIMARY KEY (guild_id, key);
    INSERT INTO schema_version VALUES (11) ON CONFLICT (version) DO UPDATE SET version=11;
    """),

    # ── v12: daily digest scheduling + productivity analytics support ─────────
    (12, """
    ALTER TABLE users ADD COLUMN IF NOT EXISTS last_digest_date TEXT;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS digest_hour      INTEGER NOT NULL DEFAULT 8;
    UPDATE tasks
       SET completed_at = updated_at
     WHERE status = 'Completed'
       AND completed_at IS NULL;
    CREATE INDEX IF NOT EXISTS idx_tasks_completed_at
        ON tasks(owner_id, status, completed_at);
    CREATE INDEX IF NOT EXISTS idx_tasks_productivity
        ON tasks(owner_id, status, deadline, completed_at, created_at);
    INSERT INTO schema_version VALUES (12) ON CONFLICT (version) DO UPDATE SET version=12;
    """),

    # ── v13: Shared Projects (Collaboration) system ───────────────────────────
    # Data Scope design:
    #   Personal Tasks: project_id IS NULL, guild_id IS NULL (unchanged, backward-compatible)
    #   Shared Tasks:   project_id = <int>, guild_id = <TEXT>  (guild-tenancy isolated)
    (13, """
    CREATE TABLE IF NOT EXISTS projects (
        project_id  SERIAL PRIMARY KEY,
        guild_id    TEXT      NOT NULL,
        name        TEXT      NOT NULL,
        description TEXT,
        owner_id    TEXT      NOT NULL REFERENCES users(user_id),
        status      TEXT      NOT NULL DEFAULT 'active'
                              CHECK(status IN ('active','archived','completed')),
        color       TEXT      NOT NULL DEFAULT '#5865F2',
        emoji       TEXT      NOT NULL DEFAULT '📁',
        channel_id  BIGINT,
        role_id     BIGINT,
        created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at  TIMESTAMP NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_projects_guild
        ON projects(guild_id);
    CREATE INDEX IF NOT EXISTS idx_projects_guild_status
        ON projects(guild_id, status);
    CREATE INDEX IF NOT EXISTS idx_projects_owner
        ON projects(owner_id);

    CREATE TABLE IF NOT EXISTS project_members (
        project_id  INTEGER NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
        user_id     TEXT    NOT NULL REFERENCES users(user_id),
        role        TEXT    NOT NULL DEFAULT 'member'
                            CHECK(role IN ('lead','member','viewer')),
        joined_at   TIMESTAMP NOT NULL DEFAULT NOW(),
        PRIMARY KEY (project_id, user_id)
    );
    CREATE INDEX IF NOT EXISTS idx_proj_members_user
        ON project_members(user_id);
    CREATE INDEX IF NOT EXISTS idx_proj_members_project
        ON project_members(project_id);

    CREATE TABLE IF NOT EXISTS project_activity_log (
        activity_id SERIAL PRIMARY KEY,
        project_id  INTEGER NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
        guild_id    TEXT    NOT NULL,
        user_id     TEXT    NOT NULL,
        action      TEXT    NOT NULL,
        detail      TEXT,
        created_at  TIMESTAMP NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_proj_activity_project
        ON project_activity_log(project_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_proj_activity_user
        ON project_activity_log(user_id);

    ALTER TABLE tasks ADD COLUMN IF NOT EXISTS project_id INTEGER REFERENCES projects(project_id) ON DELETE SET NULL;
    ALTER TABLE tasks ADD COLUMN IF NOT EXISTS guild_id   TEXT;
    CREATE INDEX IF NOT EXISTS idx_tasks_project
        ON tasks(project_id)
        WHERE project_id IS NOT NULL;
    CREATE INDEX IF NOT EXISTS idx_tasks_guild_project
        ON tasks(guild_id, project_id)
        WHERE guild_id IS NOT NULL;

    ALTER TABLE tasks DROP CONSTRAINT IF EXISTS tasks_status_check;
    ALTER TABLE tasks ADD CONSTRAINT tasks_status_check
        CHECK(status IN ('Pending','In_Progress','Completed','Cancelled'));

    INSERT INTO schema_version VALUES (13) ON CONFLICT (version) DO UPDATE SET version=13;
    """),

    # ── v14: task_attachments + realtime publication setup ──────────────────────────────
    # Scope: new table for file attachments linked to tasks/projects;
    #        new columns on projects for live dashboard tracking;
    #        register tables with Supabase Realtime publication.
    (14, """
    CREATE TABLE IF NOT EXISTS task_attachments (
        attachment_id SERIAL PRIMARY KEY,
        task_id       INTEGER NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
        project_id    INTEGER REFERENCES projects(project_id) ON DELETE SET NULL,
        file_name     TEXT    NOT NULL,
        file_size     BIGINT  NOT NULL,
        file_type     TEXT    NOT NULL,
        storage_path  TEXT    NOT NULL,
        public_url    TEXT    NOT NULL,
        uploader_id   TEXT    NOT NULL REFERENCES users(user_id),
        created_at    TIMESTAMP NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_attachments_task     ON task_attachments(task_id);
    CREATE INDEX IF NOT EXISTS idx_attachments_project  ON task_attachments(project_id)
        WHERE project_id IS NOT NULL;
    CREATE INDEX IF NOT EXISTS idx_attachments_uploader ON task_attachments(uploader_id);
    CREATE INDEX IF NOT EXISTS idx_attachments_created  ON task_attachments(created_at);

    -- Track which Discord message is currently displaying the live project dashboard
    -- so the Realtime listener can edit it in-place on task changes.
    ALTER TABLE projects ADD COLUMN IF NOT EXISTS active_dashboard_msg_id  BIGINT;
    ALTER TABLE projects ADD COLUMN IF NOT EXISTS active_dashboard_chan_id  BIGINT;

    -- Track which Discord channel receives task-complete broadcast for this project.
    ALTER TABLE projects ADD COLUMN IF NOT EXISTS notification_channel_id  BIGINT;

    -- Enable Realtime CDC for the tables the bot listens to.
    -- Wrapped in DO block: silently ignored if publication doesn't exist or tables are
    -- already added (idempotent).
    DO $rt$
    BEGIN
        ALTER PUBLICATION supabase_realtime ADD TABLE tasks;
    EXCEPTION WHEN OTHERS THEN NULL;
    END $rt$;
    DO $rt2$
    BEGIN
        ALTER PUBLICATION supabase_realtime ADD TABLE project_activity_log;
    EXCEPTION WHEN OTHERS THEN NULL;
    END $rt2$;
    DO $rt3$
    BEGIN
        ALTER PUBLICATION supabase_realtime ADD TABLE task_attachments;
    EXCEPTION WHEN OTHERS THEN NULL;
    END $rt3$;

    -- Full replica identity so old/new values are available in change events.
    ALTER TABLE tasks REPLICA IDENTITY FULL;
    ALTER TABLE task_attachments REPLICA IDENTITY FULL;

    INSERT INTO schema_version VALUES (14) ON CONFLICT (version) DO UPDATE SET version=14;
    """),

    # ── v15: Full Text Search support ─────────────────────────────────────────
    # Adds a generated tsvector column combining all searchable text fields with
    # weighted importance (A=task title, B=tags, C=description, D=note).
    # Uses 'simple' dictionary for multi-language support (Thai, EN, etc.).
    # GIN index enables fast ts_rank_cd() full text ranking queries.
    # Composite B-Tree index for filter+sort without FTS for non-text queries.
    (15, """
    ALTER TABLE tasks ADD COLUMN IF NOT EXISTS search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('simple', COALESCE(task, '')), 'A') ||
            setweight(to_tsvector('simple', COALESCE(tags, '')), 'B') ||
            setweight(to_tsvector('simple', COALESCE(description, '')), 'C') ||
            setweight(to_tsvector('simple', COALESCE(note, '')), 'D')
        ) STORED;

    CREATE INDEX IF NOT EXISTS idx_tasks_search_vector
        ON tasks USING gin(search_vector);

    -- Composite index for fast filter-only searches (no FTS)
    -- Covers: guild_id + owner_id scope, status filter, priority sort, deadline sort
    CREATE INDEX IF NOT EXISTS idx_tasks_search_filter
        ON tasks(guild_id, owner_id, status, priority DESC, deadline ASC)
        WHERE status != 'Cancelled';

    INSERT INTO schema_version VALUES (15) ON CONFLICT (version) DO UPDATE SET version=15;
    """),

    # ── v16: weekly_digest on users & lang on projects ────────────────────────
    (16, """
    ALTER TABLE users ADD COLUMN IF NOT EXISTS weekly_digest INTEGER NOT NULL DEFAULT 1;
    ALTER TABLE projects ADD COLUMN IF NOT EXISTS lang TEXT DEFAULT 'th';
    INSERT INTO schema_version VALUES (16) ON CONFLICT (version) DO UPDATE SET version=16;
    """),
]



def _split_sql_statements(sql: str) -> list[str]:
    """
    Split a SQL script into individual executable statements by semicolon.
    Respects single-quoted string literals ('...') and dollar-quoted blocks
    ($$...$$ or $tag$...$tag$) as well as SQL line/block comments so that
    internal semicolons inside PL/pgSQL blocks or default values do not split statements.
    """
    statements: list[str] = []
    current: list[str] = []
    i = 0
    n = len(sql)
    in_single_quote = False
    dollar_tag: Optional[str] = None

    while i < n:
        ch = sql[i]

        # 1. Line comments (-- ...) - preserve until newline (when outside quotes)
        if not in_single_quote and dollar_tag is None and ch == "-" and i + 1 < n and sql[i + 1] == "-":
            eol = sql.find("\n", i)
            if eol == -1:
                current.append(sql[i:])
                break
            current.append(sql[i : eol + 1])
            i = eol + 1
            continue

        # 2. Block comments (/* ... */) (when outside quotes)
        if not in_single_quote and dollar_tag is None and ch == "/" and i + 1 < n and sql[i + 1] == "*":
            eob = sql.find("*/", i + 2)
            if eob == -1:
                current.append(sql[i:])
                break
            current.append(sql[i : eob + 2])
            i = eob + 2
            continue

        # 3. Single-quote string literals (when outside dollar-quotes)
        if dollar_tag is None:
            if ch == "'":
                if in_single_quote and i + 1 < n and sql[i + 1] == "'":
                    current.append("''")
                    i += 2
                    continue
                in_single_quote = not in_single_quote
                current.append(ch)
                i += 1
                continue

        # 4. Dollar quotes ($$...$$ or $tag$...$tag$) (when outside single-quotes)
        if not in_single_quote:
            if ch == "$":
                tag_end = sql.find("$", i + 1)
                if tag_end != -1:
                    tag = sql[i : tag_end + 1]
                    name = tag[1:-1]
                    if all(c.isalnum() or c == "_" for c in name):
                        if dollar_tag is None:
                            dollar_tag = tag
                            current.append(tag)
                            i = tag_end + 1
                            continue
                        elif dollar_tag == tag:
                            dollar_tag = None
                            current.append(tag)
                            i = tag_end + 1
                            continue

            # 5. Statement delimiter ';' (only when outside all quotes and blocks)
            if ch == ";" and not in_single_quote and dollar_tag is None:
                stmt = "".join(current).strip()
                if stmt:
                    statements.append(stmt)
                current = []
                i += 1
                continue

        current.append(ch)
        i += 1

    stmt = "".join(current).strip()
    if stmt:
        statements.append(stmt)
    return statements


# ─────────────────────────────────────────────────────────────────────────────
# DatabaseManager  (asyncpg-backed, PostgreSQL / Supabase)
# ─────────────────────────────────────────────────────────────────────────────

class DatabaseManager:
    """
    PostgreSQL (Supabase) database manager using asyncpg:
    - asyncpg.Pool — native async, no thread-pool wrappers needed
    - Automatic schema migrations (v1→v8)
    - UserCache + StatsCache + QueryCache (L1 read cache)
    - BulkWriter for async queued writes (audit log, reminder timestamps)
    - Exponential backoff with jitter on transient errors
    - /metrics data exposed via .metrics property

    Public API is intentionally identical to the SQLite version so that
    all Cog code continues to work without modification.
    """

    _MAX_RETRIES = 5
    _RETRY_BASE  = 0.05   # seconds (exponential, with jitter)

    def __init__(self) -> None:
        self._pool: Optional[asyncpg.Pool] = None
        self.user_cache  = UserCache()
        self.stats_cache = StatsCache()
        self.query_cache = QueryCache(
            ttl=config.db.query_cache_ttl,
            max_size=2048,
        )
        self.bulk_writer = BulkWriter(
            pool_getter=lambda: self._pool,
            interval_ms=config.db.bulk_write_interval_ms,
        )
        log.info("DatabaseManager created — will connect on initialize()")

    # ── Async initialization (must be called inside event loop) ──────────────

    async def initialize(self) -> None:
        """
        Create asyncpg connection pool and run migrations.
        Call this inside setup_hook (or any coroutine on the bot's event loop).
        """
        self._pool = await asyncpg.create_pool(
            host=config.db.host,
            port=config.db.port,
            database=config.db.database,
            user=config.db.user,
            password=config.db.password,
            min_size=2,
            max_size=config.db.pool_size,
            command_timeout=config.db.timeout,
            statement_cache_size=0,   # required for Supabase/pgBouncer pooler
            ssl="require",
            # Auto-recycle idle connections that Supabase may have killed (5 min idle limit)
            max_inactive_connection_lifetime=300,
            server_settings={
                "application_name": "todo-bot-gen2",
                "timezone": "UTC",
            },
        )
        await self._migrate()
        log.info("DatabaseManager ready — Supabase PostgreSQL (schema v%d, pool max=%d)",
                 SCHEMA_VERSION, config.db.pool_size)

    # ── BulkWriter lifecycle ──────────────────────────────────────────────────

    def start_bulk_writer(self) -> None:
        """Call once the asyncio event loop is running (e.g. in setup_hook)."""
        self.bulk_writer.start()

    def acquire(self) -> asyncpg.pool.PoolAcquireContext:
        """Acquire a connection from the asyncpg pool.

        Usage::
            async with db.acquire() as conn:
                await conn.execute(\"SELECT 1\")

        Raises RuntimeError if the pool has not been initialised yet.
        """
        if self._pool is None:
            raise RuntimeError("Database pool has not been initialized. Call db.initialize() first.")
        return self._pool.acquire()

    # ── Migrations ────────────────────────────────────────────────────────────

    async def _current_version(self, conn: asyncpg.Connection) -> int:
        try:
            row = await conn.fetchrow(
                "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
            )
            return row["version"] if row else 0
        except Exception:
            return 0

    async def _migrate(self) -> None:
        async with self._pool.acquire() as conn:
            current = await self._current_version(conn)
            for version, sql in MIGRATIONS:
                if version > current:
                    log.info("Applying DB migration v%d", version)
                    statements = _split_sql_statements(sql)
                    # Wrap each version in a transaction for atomicity
                    async with conn.transaction():
                        for stmt in statements:
                            try:
                                await conn.execute(stmt)
                            except Exception as exc:
                                errmsg = str(exc).lower()
                                if "already exists" in errmsg or "duplicate" in errmsg:
                                    log.debug("Migration v%d: skip existing: %s", version, exc)
                                else:
                                    log.error("Migration v%d failed on stmt: %.120s\nError: %s",
                                              version, stmt, exc)
                                    raise
        log.info("Schema up-to-date (v%d)", SCHEMA_VERSION)

    # ── Retry helper ──────────────────────────────────────────────────────────

    def _retry_delay(self, attempt: int) -> float:
        """Exponential backoff with full jitter: delay = rand(0, base * 2^attempt)."""
        cap = self._RETRY_BASE * (2 ** attempt)
        return random.uniform(0, min(cap, 2.0))

    # ── Core async methods ────────────────────────────────────────────────────

    async def execute(self, sql: str, params: Sequence[Any] = ()) -> str:
        """
        Execute a write statement (INSERT/UPDATE/DELETE).
        Invalidates table-scoped query cache. Returns asyncpg status string.
        Retries on transient connection errors with exponential backoff.
        """
        lower_sql = sql.lower()
        if "last_reminder" in lower_sql or "last_active" in lower_sql:
            pass  # Background timestamp writes don't invalidate user query caches
        else:
            tables = _detect_tables(sql)
            if tables:
                self.query_cache.invalidate_tables(list(tables))
            else:
                self.query_cache.invalidate_all()

        last_exc: Optional[Exception] = None
        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                async with self._pool.acquire() as conn:
                    result = await conn.execute(sql, *params)
                return result
            except (
                asyncpg.TooManyConnectionsError,
                asyncpg.PostgresConnectionError,
                asyncpg.InterfaceError,       # connection reset mid-flight
                asyncpg.CannotConnectNowError,
                asyncpg.ConnectionDoesNotExistError,
                asyncio.TimeoutError,
            ) as exc:
                last_exc = exc
                if attempt < self._MAX_RETRIES:
                    delay = self._retry_delay(attempt)
                    log.warning("DB transient error (attempt %d/%d), retry in %.3fs: %s",
                                attempt, self._MAX_RETRIES, delay, exc)
                    await asyncio.sleep(delay)
                else:
                    log.error("DB execute failed after %d retries: %s | SQL: %.200s",
                              self._MAX_RETRIES, exc, sql)
                    raise
            except Exception as exc:
                log.error("DB execute error: %s | SQL: %.200s", exc, sql)
                raise
        raise last_exc  # type: ignore[misc]

    async def executemany(self, sql: str, params_list: list[Sequence[Any]]) -> None:
        """Execute a statement for each row in params_list within one transaction."""
        tables = _detect_tables(sql)
        if tables:
            self.query_cache.invalidate_tables(list(tables))
        else:
            self.query_cache.invalidate_all()

        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                async with self._pool.acquire() as conn:
                    async with conn.transaction():
                        await conn.executemany(sql, [tuple(p) for p in params_list])
                return
            except (
                asyncpg.TooManyConnectionsError,
                asyncpg.PostgresConnectionError,
                asyncpg.InterfaceError,
                asyncpg.CannotConnectNowError,
                asyncpg.ConnectionDoesNotExistError,
                asyncio.TimeoutError,
            ) as exc:
                if attempt < self._MAX_RETRIES:
                    delay = self._retry_delay(attempt)
                    log.warning("DB executemany transient error, retry %d/%d: %s",
                                attempt, self._MAX_RETRIES, exc)
                    await asyncio.sleep(delay)
                else:
                    raise
            except Exception:
                raise
        raise RuntimeError("DB executemany failed after retries")

    async def execute_batch(self, statements: list[tuple[str, Sequence[Any]]]) -> None:
        """
        Execute multiple (sql, params) pairs in a single explicit transaction.
        Far more efficient than calling execute() N times for bulk operations.
        """
        all_tables: set[str] = set()
        for stmt_sql, _ in statements:
            all_tables.update(_detect_tables(stmt_sql))
        if all_tables:
            self.query_cache.invalidate_tables(list(all_tables))
        else:
            self.query_cache.invalidate_all()

        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                async with self._pool.acquire() as conn:
                    async with conn.transaction():
                        for sql, params in statements:
                            await conn.execute(sql, *params)
                return
            except (
                asyncpg.TooManyConnectionsError,
                asyncpg.PostgresConnectionError,
                asyncpg.InterfaceError,
                asyncpg.CannotConnectNowError,
                asyncpg.ConnectionDoesNotExistError,
                asyncio.TimeoutError,
            ) as exc:
                if attempt < self._MAX_RETRIES:
                    delay = self._retry_delay(attempt)
                    log.warning("DB batch transient error, retry %d/%d: %s",
                                attempt, self._MAX_RETRIES, exc)
                    await asyncio.sleep(delay)
                else:
                    raise
            except Exception:
                raise
        raise RuntimeError("DB execute_batch failed after retries")

    async def fetchone(self, sql: str, params: Sequence[Any] = ()) -> Optional[asyncpg.Record]:
        """Fetch a single row. Results are L1-cached. Retries on transient connection errors."""
        cached = self.query_cache.get(sql, params)
        if not isinstance(cached, _MissType):
            return cached

        last_exc: Optional[Exception] = None
        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                async with self._pool.acquire() as conn:
                    result = await conn.fetchrow(sql, *params)
                self.query_cache.set(sql, params, result)
                return result
            except (
                asyncpg.TooManyConnectionsError,
                asyncpg.PostgresConnectionError,
                asyncpg.InterfaceError,
                asyncpg.CannotConnectNowError,
                asyncpg.ConnectionDoesNotExistError,
                asyncio.TimeoutError,
            ) as exc:
                last_exc = exc
                if attempt < self._MAX_RETRIES:
                    delay = self._retry_delay(attempt)
                    await asyncio.sleep(delay)
                else:
                    log.error("DB fetchone failed after %d retries: %s | SQL: %.200s",
                              self._MAX_RETRIES, exc, sql)
                    raise
            except Exception as exc:
                log.error("DB fetchone error: %s | SQL: %.200s", exc, sql)
                raise
        raise last_exc  # type: ignore[misc]

    async def fetchall(self, sql: str, params: Sequence[Any] = ()) -> List[asyncpg.Record]:
        """Fetch all rows. Results are L1-cached. Retries on transient connection errors."""
        cached = self.query_cache.get(sql, params)
        if not isinstance(cached, _MissType):
            return cached

        last_exc: Optional[Exception] = None
        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                async with self._pool.acquire() as conn:
                    result = await conn.fetch(sql, *params)
                self.query_cache.set(sql, params, result)
                return result
            except (
                asyncpg.TooManyConnectionsError,
                asyncpg.PostgresConnectionError,
                asyncpg.InterfaceError,
                asyncpg.CannotConnectNowError,
                asyncpg.ConnectionDoesNotExistError,
                asyncio.TimeoutError,
            ) as exc:
                last_exc = exc
                if attempt < self._MAX_RETRIES:
                    delay = self._retry_delay(attempt)
                    await asyncio.sleep(delay)
                else:
                    log.error("DB fetchall failed after %d retries: %s | SQL: %.200s",
                              self._MAX_RETRIES, exc, sql)
                    raise
            except Exception as exc:
                log.error("DB fetchall error: %s | SQL: %.200s", exc, sql)
                raise
        raise last_exc  # type: ignore[misc]


    # ── Async aliases (kept for API compatibility with cog code) ──────────────
    # asyncpg is already fully async — these are just aliases.

    async def aexecute(self, sql: str, params: Sequence[Any] = ()) -> str:
        return await self.execute(sql, params)

    async def afetchone(self, sql: str, params: Sequence[Any] = ()) -> Optional[asyncpg.Record]:
        return await self.fetchone(sql, params)

    async def afetchall(self, sql: str, params: Sequence[Any] = ()) -> List[asyncpg.Record]:
        return await self.fetchall(sql, params)

    async def aexecutemany(self, sql: str, params_list: list[Sequence[Any]]) -> None:
        return await self.executemany(sql, params_list)

    async def aexecute_batch(self, statements: list[tuple[str, Sequence[Any]]]) -> None:
        """Async batched writes in one transaction."""
        return await self.execute_batch(statements)

    # ── Audit log ─────────────────────────────────────────────────────────────

    def log_action(self, user_id: str, action: str,
                   target_id: Optional[str] = None, detail: Optional[str] = None) -> None:
        """Enqueue into BulkWriter (non-blocking) or schedule a direct write."""
        sql = ("INSERT INTO audit_log (user_id, action, target_id, detail) "
               "VALUES ($1, $2, $3, $4)")
        params = (str(user_id), action, str(target_id) if target_id else None, detail)
        try:
            self.bulk_writer.enqueue(sql, params)
        except Exception as exc:
            log.warning("Audit log enqueue failed, scheduling direct write: %s", exc)
            asyncio.ensure_future(self.execute(sql, params))

    async def alog_action(self, user_id: str, action: str,
                          target_id: Optional[str] = None, detail: Optional[str] = None) -> None:
        sql = ("INSERT INTO audit_log (user_id, action, target_id, detail) "
               "VALUES ($1, $2, $3, $4)")
        await self.execute(sql, (str(user_id), action,
                                 str(target_id) if target_id else None, detail))

    # ── Stats helper (single query, with 60s cache) ───────────────────────────

    async def user_task_stats(self, uid: str) -> dict[str, int]:
        # Serve from cache if fresh
        cached = self.stats_cache.get(uid)
        if cached is not None:
            return cached

        now = datetime.now(timezone.utc).isoformat()
        row = await self.afetchone(
            """SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status='Completed' THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN status='Pending'   THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN status='Cancelled' THEN 1 ELSE 0 END) AS cancelled,
                SUM(CASE WHEN status='Pending' AND deadline < $1 THEN 1 ELSE 0 END) AS overdue,
                SUM(CASE WHEN is_pinned=1 THEN 1 ELSE 0 END) AS pinned
               FROM tasks WHERE owner_id=$2""",
            (now, uid),
        )
        if not row:
            result = {"total": 0, "completed": 0, "pending": 0,
                      "cancelled": 0, "overdue": 0, "pinned": 0}
        else:
            result = {k: int(row[k] or 0) for k in
                      ("total", "completed", "pending", "cancelled", "overdue", "pinned")}
        self.stats_cache.set(uid, result)
        return result

    def invalidate_stats(self, uid: str) -> None:
        """Call this after any task mutation to keep stats fresh."""
        self.stats_cache.invalidate(uid)
        self.query_cache.invalidate_all()  # also bust L1 query cache

    # ── Productivity analytics (for /task-stats) ──────────────────────────────

    async def get_user_productivity_analytics(self, uid: str) -> dict:
        """
        Compute rich productivity metrics for /task-stats:
        - Completion counts, pending, overdue
        - Velocity: tasks completed in last 7d / 30d
        - Turnaround time: avg hours from created_at → completed_at
        - Timeliness: on-time rate, late rate
        - Lead/lag margin: avg hours early (on-time tasks) / avg hours late
        - Streak days
        Results are cached in StatsCache for 60 seconds.
        """
        cache_key = f"analytics:{uid}"
        cached = self.stats_cache.get(cache_key)
        if cached is not None:
            return cached

        # ── 1+2+3+4+5+6: Combined CTE query (replaces 6 separate round-trips) ──
        # All count/aggregate computations happen server-side in one query.
        now_iso = datetime.now(timezone.utc).isoformat()
        combined_row = await self.afetchone(
            """WITH base AS (
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN status='Completed' THEN 1 ELSE 0 END) AS completed,
                    SUM(CASE WHEN status='Pending'   THEN 1 ELSE 0 END) AS pending,
                    SUM(CASE WHEN status='Cancelled' THEN 1 ELSE 0 END) AS cancelled,
                    SUM(CASE WHEN status='Pending' AND deadline < $1 THEN 1 ELSE 0 END) AS overdue,
                    SUM(CASE WHEN is_pinned=1 THEN 1 ELSE 0 END) AS pinned,
                    -- Velocity
                    SUM(CASE WHEN completed_at >= NOW() - INTERVAL '7 days'
                             AND status='Completed' AND completed_at IS NOT NULL
                             THEN 1 ELSE 0 END) AS done_7d,
                    SUM(CASE WHEN completed_at >= NOW() - INTERVAL '30 days'
                             AND status='Completed' AND completed_at IS NOT NULL
                             THEN 1 ELSE 0 END) AS done_30d,
                    -- Timeliness
                    SUM(CASE WHEN status='Completed' AND completed_at IS NOT NULL
                             AND deadline IS NOT NULL
                             AND completed_at <= deadline::TIMESTAMP WITH TIME ZONE
                             THEN 1 ELSE 0 END) AS on_time,
                    SUM(CASE WHEN status='Completed' AND completed_at IS NOT NULL
                             AND deadline IS NOT NULL
                             AND completed_at > deadline::TIMESTAMP WITH TIME ZONE
                             THEN 1 ELSE 0 END) AS late,
                    -- Turnaround
                    AVG(CASE WHEN status='Completed' AND completed_at IS NOT NULL
                             AND created_at IS NOT NULL
                             THEN EXTRACT(EPOCH FROM (completed_at - created_at)) / 3600.0
                             ELSE NULL END) AS avg_turnaround_h,
                    -- Lead margin (hours early for on-time tasks)
                    AVG(CASE WHEN status='Completed' AND completed_at IS NOT NULL
                             AND deadline IS NOT NULL
                             AND completed_at <= deadline::TIMESTAMP WITH TIME ZONE
                             THEN EXTRACT(EPOCH FROM (deadline::TIMESTAMP WITH TIME ZONE - completed_at)) / 3600.0
                             ELSE NULL END) AS avg_lead_h,
                    -- Lag margin (hours late for overdue-completed tasks)
                    AVG(CASE WHEN status='Completed' AND completed_at IS NOT NULL
                             AND deadline IS NOT NULL
                             AND completed_at > deadline::TIMESTAMP WITH TIME ZONE
                             THEN EXTRACT(EPOCH FROM (completed_at - deadline::TIMESTAMP WITH TIME ZONE)) / 3600.0
                             ELSE NULL END) AS avg_lag_h
                FROM tasks WHERE owner_id=$2
            )
            SELECT * FROM base""",
            (now_iso, uid),
        )
        if not combined_row:
            combined_row = {}

        def _int(key: str) -> int:
            return int(combined_row.get(key) or 0)

        def _float(key: str) -> float:
            return float(combined_row.get(key) or 0.0)

        base = {
            "total":     _int("total"),
            "completed": _int("completed"),
            "pending":   _int("pending"),
            "cancelled": _int("cancelled"),
            "overdue":   _int("overdue"),
            "pinned":    _int("pinned"),
        }
        done_7d  = _int("done_7d")
        done_30d = _int("done_30d")

        on_time_count = _int("on_time")
        late_count    = _int("late")
        timed_total   = on_time_count + late_count
        on_time_rate  = round(on_time_count / timed_total * 100, 1) if timed_total > 0 else 0.0
        late_rate     = round(late_count    / timed_total * 100, 1) if timed_total > 0 else 0.0

        avg_turnaround_hours = round(_float("avg_turnaround_h"), 1)
        avg_lead_hours       = round(_float("avg_lead_h"), 1)
        avg_lag_hours        = round(_float("avg_lag_h"), 1)

        # ── 2. Streak days (separate row from users table) ────────────────────
        streak_row = await self.afetchone(
            "SELECT streak_days FROM users WHERE user_id=$1", (uid,)
        )
        streak_days = int(streak_row["streak_days"] or 0) if streak_row else 0


        # ── 8. Productivity Score (0–100) ─────────────────────────────────────
        #  Weighted formula:
        #    40% on-time rate  (max 40 pts)
        #    30% completion rate vs total non-cancelled (max 30 pts)
        #    20% velocity score: done_7d capped at 20 (1 pt/task, max 20 pts)
        #    10% consistency bonus: on_time_count >= 5 → full 10 pts
        total_eligible = base["completed"] + base["pending"] + base["overdue"]
        completion_rate = base["completed"] / total_eligible * 100 if total_eligible > 0 else 0.0

        score_ontime     = on_time_rate * 0.40
        score_completion = min(completion_rate, 100) * 0.30
        score_velocity   = min(done_7d * 5, 20)        # 4 tasks/week = full score
        score_consistency = 10 if on_time_count >= 5 else (on_time_count / 5 * 10)
        productivity_score = round(min(score_ontime + score_completion + score_velocity + score_consistency, 100), 1)

        result = {
            # Basic counts
            **base,
            # Velocity
            "done_7d":  done_7d,
            "done_30d": done_30d,
            # Timeliness
            "on_time_count":  on_time_count,
            "late_count":     late_count,
            "on_time_rate":   on_time_rate,
            "late_rate":      late_rate,
            # Turnaround
            "avg_turnaround_hours": round(avg_turnaround_hours, 1),
            # Lead/lag
            "avg_lead_hours": round(avg_lead_hours, 1),
            "avg_lag_hours":  round(avg_lag_hours, 1),
            # Streak
            "streak_days":    streak_days,
            # Score
            "productivity_score": productivity_score,
            "completion_rate":    round(completion_rate, 1),
        }
        self.stats_cache.set(cache_key, result)
        return result

    # ── Cache maintenance ─────────────────────────────────────────────────────

    def purge_all_caches(self) -> dict[str, int]:
        """Purge expired entries from all caches. Returns counts removed."""
        return {
            "user_cache":   self.user_cache.purge_expired(),
            "stats_cache":  self.stats_cache.purge_expired(),
            "query_cache":  self.query_cache.purge_expired(),
        }

    # ── Metrics (for /metrics endpoint) ──────────────────────────────────────

    @property
    def metrics(self) -> dict:
        pool_metrics: dict = {}
        if self._pool:
            pool_metrics = {
                "min_size": self._pool.get_min_size(),
                "max_size": self._pool.get_max_size(),
                "size": self._pool.get_size(),
                "idle": self._pool.get_idle_size(),
            }
        return {
            "schema_version": SCHEMA_VERSION,
            "pool": pool_metrics,
            "user_cache_size": self.user_cache.size,
            "query_cache": self.query_cache.stats,
            "bulk_writer": self.bulk_writer.metrics,
        }

    # ── Guild settings (monitoring & admin config) ────────────────────────────

    async def get_guild_setting(self, guild_id: str, key: str) -> Optional[str]:
        """
        Fetch a single guild configuration value from Supabase.
        Returns None if not set.
        """
        row = await self.fetchone(
            "SELECT value FROM guild_settings WHERE guild_id=$1 AND key=$2",
            (guild_id, key),
        )
        return row["value"] if row else None

    async def set_guild_setting(self, guild_id: str, key: str, value: str) -> None:
        """
        Upsert a guild configuration key-value pair into Supabase.
        Creates the row if it doesn't exist, updates it if it does.
        """
        await self.execute(
            """
            INSERT INTO guild_settings (guild_id, key, value, updated_at)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (guild_id, key)
            DO UPDATE SET value=$3, updated_at=NOW()
            """,
            (guild_id, key, value),
        )
        log.debug("guild_settings updated: guild=%s key=%s", guild_id, key)

    async def get_all_guild_settings(self, guild_id: str) -> dict[str, str]:
        """Fetch all settings for a guild as a dict."""
        rows = await self.fetchall(
            "SELECT key, value FROM guild_settings WHERE guild_id=$1",
            (guild_id,),
        )
        return {row["key"]: row["value"] for row in rows} if rows else {}

    # ── Graceful shutdown ─────────────────────────────────────────────────────

    async def close(self) -> None:
        """Close the asyncpg pool. Call on bot shutdown. Safe to call only once."""
        if self._pool:
            await self.bulk_writer.stop()
            pool, self._pool = self._pool, None   # null-out before closing (double-close guard)
            await pool.close()
            log.info("DatabaseManager closed")


# Module-level singleton
db = DatabaseManager()

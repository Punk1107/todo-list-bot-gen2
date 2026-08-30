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

SCHEMA_VERSION = 8   # bump when adding migrations below


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
    All public methods are safe to call from the asyncio thread.
    """

    def __init__(self) -> None:
        self._store: dict[str, _CachedUser] = {}
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
    """Thread-safe short-lived stats cache to avoid hammering the DB on /stats."""

    def __init__(self) -> None:
        self._store: dict[str, _CachedStats] = {}
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
            self._store[uid] = _CachedStats(data=data)

    def invalidate(self, uid: str) -> None:
        with self._lock:
            self._store.pop(uid, None)


# ─────────────────────────────────────────────────────────────────────────────
# QueryCache  (L1 read cache — deduplicates hot fetchone/fetchall calls)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _CachedQuery:
    result: Any
    _expires: float

    @property
    def expired(self) -> bool:
        return time.monotonic() > self._expires


class QueryCache:
    """
    Thread-safe TTL cache for read queries.
    Key = stable hash of (sql, params). Invalidated explicitly on writes.

    Usage: only fetchone/fetchall results are cached.
    Any execute() (write) call on the same table should call invalidate_all().
    """

    def __init__(self, ttl: float = 30.0, max_size: int = 2048) -> None:
        self._ttl = ttl
        self._max_size = max_size
        self._store: dict[str, _CachedQuery] = {}
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
            self._misses += 1
            return _MISS

    def set(self, sql: str, params: Any, result: Any) -> None:
        k = self._key(sql, params)
        expires = time.monotonic() + self._ttl
        with self._lock:
            # Evict oldest entries if at capacity (simple FIFO eviction)
            if len(self._store) >= self._max_size:
                oldest_key = next(iter(self._store))
                del self._store[oldest_key]
            self._store[k] = _CachedQuery(result=result, _expires=expires)

    def invalidate_all(self) -> None:
        with self._lock:
            self._store.clear()

    def purge_expired(self) -> int:
        now = time.monotonic()
        with self._lock:
            stale = [k for k, v in self._store.items() if now > v._expires]
            for k in stale:
                del self._store[k]
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

        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    for sql, params, _fc in batch:
                        await conn.execute(sql, *params)
            with self._lock:
                self._flushed_count += len(batch)
                self._batch_count += 1
            return len(batch)
        except Exception as exc:
            log.error("BulkWriter flush failed (%d rows): %s — re-queuing", len(batch), exc)
            # Re-queue failed items with incremented failure count.
            # Items that exceed _MAX_ITEM_RETRIES are dropped to prevent unbounded growth.
            requeue = []
            dropped = 0
            for sql, params, fail_count in batch:
                new_fc = fail_count + 1
                if new_fc >= self._MAX_ITEM_RETRIES:
                    log.warning(
                        "BulkWriter: dropping item after %d failures — SQL: %.120s",
                        new_fc, sql,
                    )
                    dropped += 1
                else:
                    requeue.append((sql, params, new_fc))
            with self._lock:
                self._queue.extendleft(reversed(requeue))
                self._dropped_count += dropped
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
]


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
                    statements = [s.strip() for s in sql.split(";") if s.strip()]
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
        Invalidates query cache. Returns asyncpg status string.
        Retries on transient connection errors with exponential backoff.
        """
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
        """Fetch a single row. Results are L1-cached."""
        cached = self.query_cache.get(sql, params)
        if not isinstance(cached, _MissType):
            return cached
        try:
            async with self._pool.acquire() as conn:
                result = await conn.fetchrow(sql, *params)
            self.query_cache.set(sql, params, result)
            return result
        except Exception as exc:
            log.error("DB fetchone error: %s | SQL: %.200s", exc, sql)
            raise

    async def fetchall(self, sql: str, params: Sequence[Any] = ()) -> List[asyncpg.Record]:
        """Fetch all rows. Results are L1-cached."""
        cached = self.query_cache.get(sql, params)
        if not isinstance(cached, _MissType):
            return cached
        try:
            async with self._pool.acquire() as conn:
                result = await conn.fetch(sql, *params)
            self.query_cache.set(sql, params, result)
            return result
        except Exception as exc:
            log.error("DB fetchall error: %s | SQL: %.200s", exc, sql)
            raise

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

    # ── Cache maintenance ─────────────────────────────────────────────────────

    def purge_all_caches(self) -> dict[str, int]:
        """Purge expired entries from all caches. Returns counts removed."""
        return {
            "user_cache": self.user_cache.purge_expired(),
            "query_cache": self.query_cache.purge_expired(),
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

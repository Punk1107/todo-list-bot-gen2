"""
core/database.py — High-performance SQLite manager v3
Improvements over v2:
  - PRAGMA tuning: cache 64 MB, mmap 1 GB, busy_timeout 10 s
  - Connection pool default 10 (was 5), max retries 5 (was 3)
  - QueryCache (L1 read cache, TTL-based) — eliminates repeated read round-trips
  - execute_batch() / aexecute_batch() — true batched writes in one transaction
  - BulkWriter — async write queue that flushes on interval (reduces txn overhead)
  - Exponential backoff with jitter on DB locked retries
  - Migration v6: new columns for users/tasks, task_comments, user_achievements,
    compound indexes for high-traffic queries
  - WAL checkpoint helper for reminders_cog
  - Metrics property for webserver /metrics endpoint
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import sqlite3
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from threading import Lock, Thread
from typing import Any, Generator, List, Optional, Sequence

from core.config import config

log = logging.getLogger(__name__)

SCHEMA_VERSION = 7   # bump when adding migrations below


# ─────────────────────────────────────────────────────────────────────────────
# Connection helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False, timeout=config.db.timeout)
    conn.row_factory = sqlite3.Row
    # ── Performance PRAGMAs ──────────────────────────────────────────────────
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA cache_size = -65536")    # 64 MB page cache (was 16 MB)
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute("PRAGMA mmap_size = 1073741824")  # 1 GB memory-mapped I/O (was 256 MB)
    conn.execute("PRAGMA busy_timeout = 10000")    # 10 s wait on lock (was 5 s)
    conn.execute("PRAGMA page_size = 4096")        # optimal for most workloads
    conn.execute("PRAGMA auto_vacuum = INCREMENTAL")  # keep file size compact
    conn.execute("PRAGMA threads = 4")             # allow SQLite to use up to 4 OS threads
    return conn


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
    Any execute() (write) call on the same table should call invalidate_prefix().
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
# Connection Pool
# ─────────────────────────────────────────────────────────────────────────────

class ConnectionPool:
    def __init__(self, db_path: str, size: int = 10) -> None:
        self._db_path = db_path
        self._pool: Queue[sqlite3.Connection] = Queue(maxsize=size)
        self._size = size
        for _ in range(size):
            self._pool.put(_make_conn(db_path))
        # Track metrics
        self._total_acquired = 0
        self._overflow_count = 0
        self._lock = Lock()

    @contextmanager
    def get(self) -> Generator[sqlite3.Connection, None, None]:
        conn: Optional[sqlite3.Connection] = None
        _overflow = False
        try:
            try:
                conn = self._pool.get(timeout=config.db.timeout)
                # Health-check: ping with a cheap query
                conn.execute("SELECT 1")
            except (Empty, sqlite3.OperationalError):
                log.warning("Pool exhausted or conn dead — creating overflow connection")
                conn = _make_conn(self._db_path)
                _overflow = True
            with self._lock:
                self._total_acquired += 1
                if _overflow:
                    self._overflow_count += 1
            yield conn
        finally:
            if conn is not None:
                if _overflow:
                    conn.close()
                else:
                    try:
                        self._pool.put_nowait(conn)
                    except Exception:
                        conn.close()

    def close_all(self) -> None:
        while not self._pool.empty():
            try:
                self._pool.get_nowait().close()
            except Exception:
                pass

    @property
    def metrics(self) -> dict:
        with self._lock:
            return {
                "pool_size": self._size,
                "available": self._pool.qsize(),
                "total_acquired": self._total_acquired,
                "overflow_count": self._overflow_count,
            }


# ─────────────────────────────────────────────────────────────────────────────
# BulkWriter — async write-batching queue
# ─────────────────────────────────────────────────────────────────────────────

class BulkWriter:
    """
    Accumulates (sql, params) pairs and flushes them as a single transaction
    on a configurable interval. Reduces per-row transaction overhead for
    high-volume write paths (audit_log, last_reminder updates, etc.).

    Call start() after the event loop is running; call stop() on shutdown.
    """

    def __init__(self, pool: ConnectionPool, interval_ms: int = 500) -> None:
        self._pool = pool
        self._interval = interval_ms / 1000.0
        self._queue: deque[tuple[str, tuple]] = deque()
        self._lock = Lock()
        self._task: Optional[asyncio.Task] = None
        self._flushed_count = 0
        self._batch_count = 0

    def enqueue(self, sql: str, params: tuple = ()) -> None:
        with self._lock:
            self._queue.append((sql, params))

    async def flush(self) -> int:
        """Drain queue and commit in one transaction. Returns rows written."""
        with self._lock:
            if not self._queue:
                return 0
            batch = list(self._queue)
            self._queue.clear()

        def _commit(batch: list) -> int:
            with self._pool.get() as conn:
                conn.execute("BEGIN")
                for sql, params in batch:
                    conn.execute(sql, params)
                conn.execute("COMMIT")
            return len(batch)

        try:
            written = await asyncio.to_thread(_commit, batch)
            with self._lock:
                self._flushed_count += written
                self._batch_count += 1
            return written
        except Exception as exc:
            log.error("BulkWriter flush failed (%d rows lost): %s", len(batch), exc)
            return 0

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            await self.flush()

    def start(self) -> None:
        loop = asyncio.get_event_loop()
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
                "interval_ms": int(self._interval * 1000),
            }


# ─────────────────────────────────────────────────────────────────────────────
# Migrations  (append-only — never edit existing entries)
# ─────────────────────────────────────────────────────────────────────────────

MIGRATIONS: list[tuple[int, str]] = [
    # ── v1: baseline schema ──────────────────────────────────────────────────
    (1, """
    CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
    INSERT OR IGNORE INTO schema_version VALUES (1);

    CREATE TABLE IF NOT EXISTS users (
        user_id     TEXT PRIMARY KEY,
        timezone    TEXT    NOT NULL DEFAULT 'Asia/Bangkok',
        channel_id  INTEGER,
        role        TEXT    NOT NULL DEFAULT 'user'
                            CHECK(role IN ('user','moderator','admin')),
        lang        TEXT    NOT NULL DEFAULT 'th'
                            CHECK(lang IN ('th','en')),
        created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    INSERT OR IGNORE INTO users (user_id, timezone, role, lang)
    VALUES ('system', 'UTC', 'admin', 'th');

    CREATE TABLE IF NOT EXISTS categories (
        category_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT    NOT NULL,
        color       TEXT    NOT NULL DEFAULT '#3498db',
        emoji       TEXT    NOT NULL DEFAULT '📝',
        owner_id    TEXT    NOT NULL REFERENCES users(user_id),
        created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS tasks (
        task_id         INTEGER PRIMARY KEY AUTOINCREMENT,
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
        message_id      INTEGER,
        created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_reminder   TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS task_assignments (
        task_id     INTEGER NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
        user_id     TEXT    NOT NULL REFERENCES users(user_id),
        assigned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
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
        log_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    TEXT    NOT NULL,
        action     TEXT    NOT NULL,
        target_id  TEXT,
        detail     TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id);
    CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_log(created_at);
    INSERT OR REPLACE INTO schema_version VALUES (2);
    """),

    # ── v3: seed default categories ──────────────────────────────────────────
    (3, """
    INSERT OR IGNORE INTO categories (name, color, emoji, owner_id) VALUES
        ('งานทั่วไป / General',   '#3498db', '📝', 'system'),
        ('งานด่วน / Urgent',      '#e74c3c', '🚨', 'system'),
        ('งานส่วนตัว / Personal', '#9b59b6', '👤', 'system'),
        ('งานบ้าน / Home',        '#f39c12', '🏠', 'system'),
        ('การเรียน / Study',      '#2ecc71', '📚', 'system');
    INSERT OR REPLACE INTO schema_version VALUES (3);
    """),

    # ── v4: is_pinned column + compound stats index ───────────────────────────
    (4, """
    ALTER TABLE tasks ADD COLUMN is_pinned INTEGER NOT NULL DEFAULT 0;
    CREATE INDEX IF NOT EXISTS idx_tasks_pinned    ON tasks(is_pinned);
    CREATE INDEX IF NOT EXISTS idx_tasks_owner_st  ON tasks(owner_id, status);
    CREATE INDEX IF NOT EXISTS idx_tasks_owner_dl  ON tasks(owner_id, deadline);
    INSERT OR REPLACE INTO schema_version VALUES (4);
    """),

    # ── v5: custom_reminder column + user notification settings ──────────────
    (5, """
    ALTER TABLE tasks ADD COLUMN custom_reminder TEXT;
    ALTER TABLE users ADD COLUMN notify_enabled INTEGER NOT NULL DEFAULT 1;
    ALTER TABLE users ADD COLUMN daily_digest    INTEGER NOT NULL DEFAULT 1;
    CREATE INDEX IF NOT EXISTS idx_tasks_reminder ON tasks(custom_reminder);
    INSERT OR REPLACE INTO schema_version VALUES (5);
    """),

    # ── v6: expanded schema — more user/task fields, new tables, better indexes
    (6, """
    -- users: lifecycle + personalisation + gamification
    ALTER TABLE users ADD COLUMN max_tasks   INTEGER NOT NULL DEFAULT 500;
    ALTER TABLE users ADD COLUMN streak_days INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE users ADD COLUMN last_active TIMESTAMP;
    ALTER TABLE users ADD COLUMN theme       TEXT    NOT NULL DEFAULT 'default';
    ALTER TABLE users ADD COLUMN premium     INTEGER NOT NULL DEFAULT 0;

    -- tasks: time-tracking + progress + rich metadata
    ALTER TABLE tasks ADD COLUMN estimated_hours REAL;
    ALTER TABLE tasks ADD COLUMN actual_hours    REAL;
    ALTER TABLE tasks ADD COLUMN attachments     TEXT;
    ALTER TABLE tasks ADD COLUMN note            TEXT;
    ALTER TABLE tasks ADD COLUMN completed_at    TIMESTAMP;
    ALTER TABLE tasks ADD COLUMN progress_pct    INTEGER NOT NULL DEFAULT 0
                                                 CHECK(progress_pct BETWEEN 0 AND 100);

    -- Compound indexes for high-traffic query patterns
    CREATE INDEX IF NOT EXISTS idx_tasks_compound_status_dl
        ON tasks(owner_id, status, deadline);
    CREATE INDEX IF NOT EXISTS idx_tasks_pinned_pending
        ON tasks(owner_id, is_pinned, status);
    CREATE INDEX IF NOT EXISTS idx_audit_action
        ON audit_log(action, created_at);
    CREATE INDEX IF NOT EXISTS idx_users_active
        ON users(last_active);

    -- task_comments: per-task discussion / notes from collaborators
    CREATE TABLE IF NOT EXISTS task_comments (
        comment_id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id    INTEGER NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
        user_id    TEXT    NOT NULL REFERENCES users(user_id),
        content    TEXT    NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_comments_task ON task_comments(task_id);
    CREATE INDEX IF NOT EXISTS idx_comments_user ON task_comments(user_id);

    -- user_achievements: badge / milestone tracking
    CREATE TABLE IF NOT EXISTS user_achievements (
        achievement_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id        TEXT    NOT NULL REFERENCES users(user_id),
        type           TEXT    NOT NULL,
        awarded_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, type)
    );
    CREATE INDEX IF NOT EXISTS idx_achievements_user ON user_achievements(user_id);

    INSERT OR REPLACE INTO schema_version VALUES (6);
    """),

    # ── v7: dm_reminded bitmask for deadline DM notifications ─────────────────
    (7, """
    ALTER TABLE tasks ADD COLUMN dm_reminded INTEGER NOT NULL DEFAULT 0;
    CREATE INDEX IF NOT EXISTS idx_tasks_dm_reminded
        ON tasks(owner_id, status, deadline, dm_reminded);
    INSERT OR REPLACE INTO schema_version VALUES (7);
    """),
]


# ─────────────────────────────────────────────────────────────────────────────
# DatabaseManager
# ─────────────────────────────────────────────────────────────────────────────

class DatabaseManager:
    """
    High-performance SQLite manager v3:
    - Connection pool (default 10)
    - Automatic schema migrations (v1→v7)
    - Async wrappers (asyncio.to_thread) — never blocks the event loop
    - UserCache + StatsCache + QueryCache (L1 read cache)
    - execute_batch() for true multi-row batched writes
    - BulkWriter for async queued writes (audit log, reminder timestamps)
    - Exponential backoff with jitter on DB locked retries
    - Automatic WAL checkpointing
    - Automatic backups with rotation
    - /metrics data exposed via .metrics property
    """

    _MAX_RETRIES = 5
    _RETRY_BASE  = 0.05   # seconds (exponential, with jitter)

    def __init__(self) -> None:
        db_path = config.db.path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._pool = ConnectionPool(db_path, size=config.db.pool_size)
        self.user_cache  = UserCache()
        self.stats_cache = StatsCache()
        self.query_cache = QueryCache(
            ttl=config.db.query_cache_ttl,
            max_size=2048,
        )
        self.bulk_writer = BulkWriter(
            self._pool,
            interval_ms=config.db.bulk_write_interval_ms,
        )
        self._migrate()
        log.info("DatabaseManager ready — %s (schema v%d, pool=%d)",
                 db_path, SCHEMA_VERSION, config.db.pool_size)

    # ── BulkWriter lifecycle ──────────────────────────────────────────────────

    def start_bulk_writer(self) -> None:
        """Call once the asyncio event loop is running (e.g. in setup_hook)."""
        self.bulk_writer.start()

    # ── Migrations ────────────────────────────────────────────────────────────

    def _current_version(self, conn: sqlite3.Connection) -> int:
        try:
            row = conn.execute(
                "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
            ).fetchone()
            return row[0] if row else 0
        except sqlite3.OperationalError:
            return 0

    def _migrate(self) -> None:
        with self._pool.get() as conn:
            current = self._current_version(conn)
            for version, sql in MIGRATIONS:
                if version > current:
                    log.info("Applying DB migration v%d", version)
                    # Split multi-statement SQL and execute one-by-one so we can
                    # handle "duplicate column" gracefully without skipping the
                    # entire migration block.
                    statements = [s.strip() for s in sql.split(";") if s.strip()]
                    for stmt in statements:
                        try:
                            conn.execute(stmt)
                        except sqlite3.OperationalError as exc:
                            errmsg = str(exc).lower()
                            if "duplicate column" in errmsg or "already exists" in errmsg:
                                log.debug("Migration v%d: skip existing: %s", version, exc)
                            else:
                                conn.rollback()
                                raise
                    conn.execute(
                        "INSERT OR REPLACE INTO schema_version VALUES (?)", (version,)
                    )
                    conn.commit()
        log.info("Schema up-to-date (v%d)", SCHEMA_VERSION)

    # ── Retry helper ──────────────────────────────────────────────────────────

    def _retry_delay(self, attempt: int) -> float:
        """Exponential backoff with full jitter: delay = rand(0, base * 2^attempt)."""
        cap = self._RETRY_BASE * (2 ** attempt)
        return random.uniform(0, min(cap, 2.0))

    # ── Synchronous core ──────────────────────────────────────────────────────

    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        # Any write invalidates query cache
        self.query_cache.invalidate_all()
        for attempt in range(1, self._MAX_RETRIES + 1):
            with self._pool.get() as conn:
                try:
                    cur = conn.execute(sql, params)
                    conn.commit()
                    return cur
                except sqlite3.OperationalError as exc:
                    conn.rollback()
                    if "locked" in str(exc).lower() and attempt < self._MAX_RETRIES:
                        delay = self._retry_delay(attempt)
                        log.warning("DB locked, retry %d/%d in %.3fs",
                                    attempt, self._MAX_RETRIES, delay)
                        time.sleep(delay)
                        continue
                    log.error("DB execute error: %s | SQL: %.200s", exc, sql)
                    raise
                except sqlite3.Error as exc:
                    conn.rollback()
                    log.error("DB execute error: %s | SQL: %.200s", exc, sql)
                    raise
        raise sqlite3.OperationalError("DB execute failed after retries")

    def executemany(self, sql: str, params_list: list[Sequence[Any]]) -> None:
        self.query_cache.invalidate_all()
        for attempt in range(1, self._MAX_RETRIES + 1):
            with self._pool.get() as conn:
                try:
                    conn.executemany(sql, params_list)
                    conn.commit()
                    return
                except sqlite3.OperationalError as exc:
                    conn.rollback()
                    if "locked" in str(exc).lower() and attempt < self._MAX_RETRIES:
                        delay = self._retry_delay(attempt)
                        log.warning("DB locked (executemany), retry %d/%d in %.3fs",
                                    attempt, self._MAX_RETRIES, delay)
                        time.sleep(delay)
                        continue
                    log.error("DB executemany error: %s | SQL: %.200s", exc, sql)
                    raise
                except sqlite3.Error as exc:
                    conn.rollback()
                    log.error("DB executemany error: %s | SQL: %.200s", exc, sql)
                    raise
        raise sqlite3.OperationalError("DB executemany failed after retries")

    def execute_batch(self, statements: list[tuple[str, Sequence[Any]]]) -> None:
        """
        Execute multiple (sql, params) pairs in a single explicit transaction.
        Far more efficient than calling execute() N times for bulk operations.
        """
        self.query_cache.invalidate_all()
        for attempt in range(1, self._MAX_RETRIES + 1):
            with self._pool.get() as conn:
                try:
                    conn.execute("BEGIN")
                    for sql, params in statements:
                        conn.execute(sql, params)
                    conn.execute("COMMIT")
                    return
                except sqlite3.OperationalError as exc:
                    conn.execute("ROLLBACK")
                    if "locked" in str(exc).lower() and attempt < self._MAX_RETRIES:
                        delay = self._retry_delay(attempt)
                        log.warning("DB locked (batch), retry %d/%d in %.3fs",
                                    attempt, self._MAX_RETRIES, delay)
                        time.sleep(delay)
                        continue
                    log.error("DB execute_batch error: %s", exc)
                    raise
                except sqlite3.Error as exc:
                    try:
                        conn.execute("ROLLBACK")
                    except Exception:
                        pass
                    log.error("DB execute_batch error: %s", exc)
                    raise
        raise sqlite3.OperationalError("DB execute_batch failed after retries")

    def fetchone(self, sql: str, params: Sequence[Any] = ()) -> Optional[sqlite3.Row]:
        # Try L1 cache first
        cached = self.query_cache.get(sql, params)
        if not isinstance(cached, _MissType):
            return cached
        with self._pool.get() as conn:
            try:
                result = conn.execute(sql, params).fetchone()
                self.query_cache.set(sql, params, result)
                return result
            except sqlite3.Error as exc:
                log.error("DB fetchone error: %s | SQL: %.200s", exc, sql)
                return None

    def fetchall(self, sql: str, params: Sequence[Any] = ()) -> List[sqlite3.Row]:
        # Try L1 cache first
        cached = self.query_cache.get(sql, params)
        if not isinstance(cached, _MissType):
            return cached
        with self._pool.get() as conn:
            try:
                result = conn.execute(sql, params).fetchall()
                self.query_cache.set(sql, params, result)
                return result
            except sqlite3.Error as exc:
                log.error("DB fetchall error: %s | SQL: %.200s", exc, sql)
                return []

    # ── Async wrappers  (use these in Cogs — won't block event loop) ──────────

    async def aexecute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        return await asyncio.to_thread(self.execute, sql, params)

    async def afetchone(self, sql: str, params: Sequence[Any] = ()) -> Optional[sqlite3.Row]:
        return await asyncio.to_thread(self.fetchone, sql, params)

    async def afetchall(self, sql: str, params: Sequence[Any] = ()) -> List[sqlite3.Row]:
        return await asyncio.to_thread(self.fetchall, sql, params)

    async def aexecutemany(self, sql: str, params_list: list[Sequence[Any]]) -> None:
        return await asyncio.to_thread(self.executemany, sql, params_list)

    async def aexecute_batch(self, statements: list[tuple[str, Sequence[Any]]]) -> None:
        """Async version of execute_batch — runs in thread pool to avoid blocking."""
        return await asyncio.to_thread(self.execute_batch, statements)

    # ── Audit log ─────────────────────────────────────────────────────────────

    def log_action(self, user_id: str, action: str,
                   target_id: Optional[str] = None, detail: Optional[str] = None) -> None:
        """Enqueue into BulkWriter (non-blocking) or fall back to direct write."""
        sql = "INSERT INTO audit_log (user_id, action, target_id, detail) VALUES (?,?,?,?)"
        params = (str(user_id), action, str(target_id) if target_id else None, detail)
        try:
            self.bulk_writer.enqueue(sql, params)
        except Exception as exc:
            log.warning("Audit log enqueue failed, writing directly: %s", exc)
            try:
                self.execute(sql, params)
            except Exception as exc2:
                log.warning("Audit log write failed: %s", exc2)

    async def alog_action(self, user_id: str, action: str,
                          target_id: Optional[str] = None, detail: Optional[str] = None) -> None:
        await asyncio.to_thread(self.log_action, user_id, action, target_id, detail)

    # ── WAL checkpoint ────────────────────────────────────────────────────────

    def wal_checkpoint(self) -> None:
        """
        Run a TRUNCATE WAL checkpoint to keep the WAL file from growing unbounded.
        Should be called periodically (every few hours) via reminders_cog.
        """
        try:
            with self._pool.get() as conn:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            log.info("WAL checkpoint completed")
        except Exception as exc:
            log.warning("WAL checkpoint failed: %s", exc)

    async def awa_checkpoint(self) -> None:
        await asyncio.to_thread(self.wal_checkpoint)

    # ── Backup ────────────────────────────────────────────────────────────────

    def backup(self) -> Optional[str]:
        if not config.db.backup_enabled:
            return None
        backup_dir = Path(self._db_path).parent / "backups"
        backup_dir.mkdir(exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        dest = str(backup_dir / f"tasks_backup_{ts}.db")
        try:
            with self._pool.get() as conn:
                bak = sqlite3.connect(dest)
                conn.backup(bak)
                bak.close()
            self._purge_old_backups(backup_dir)
            log.info("DB backup created: %s", dest)
            return dest
        except Exception as exc:
            log.error("DB backup failed: %s", exc)
            return None

    def _purge_old_backups(self, backup_dir: Path) -> None:
        files = sorted(backup_dir.glob("tasks_backup_*.db"),
                       key=lambda p: p.stat().st_mtime)
        while len(files) > config.db.max_backups:
            oldest = files.pop(0)
            oldest.unlink(missing_ok=True)
            log.info("Purged old backup: %s", oldest)

    # ── Stats helper (single query, with 60s cache) ───────────────────────────

    async def user_task_stats(self, uid: str) -> dict[str, int]:
        # Serve from cache if fresh
        cached = self.stats_cache.get(uid)
        if cached is not None:
            return cached

        now = datetime.utcnow().isoformat()
        row = await self.afetchone(
            """SELECT
                COUNT(*) AS total,
                SUM(status='Completed') AS completed,
                SUM(status='Pending')   AS pending,
                SUM(status='Cancelled') AS cancelled,
                SUM(status='Pending' AND deadline < :now) AS overdue,
                SUM(is_pinned=1)        AS pinned
               FROM tasks WHERE owner_id=:uid""",
            {"now": now, "uid": uid},
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
        return {
            "schema_version": SCHEMA_VERSION,
            "pool": self._pool.metrics,
            "user_cache_size": self.user_cache.size,
            "query_cache": self.query_cache.stats,
            "bulk_writer": self.bulk_writer.metrics,
        }

    # ── Graceful shutdown ─────────────────────────────────────────────────────

    def close(self) -> None:
        self._pool.close_all()
        log.info("DatabaseManager closed")


# Module-level singleton
db = DatabaseManager()

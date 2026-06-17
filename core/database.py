"""
core/database.py — Thread-safe SQLite manager v2
Improvements:
  - async wrappers via asyncio.to_thread (non-blocking event loop)
  - LRU-style UserCache with TTL (eliminates repeated DB round-trips)
  - Connection pool with health checking
  - Append-only versioned migrations
  - Audit log + scheduled backup with rotation
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from threading import Lock
from typing import Any, Generator, List, Optional, Sequence

from core.config import config

log = logging.getLogger(__name__)

SCHEMA_VERSION = 5   # bump when adding migrations below


# ─────────────────────────────────────────────────────────────────────────────
# Connection helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False, timeout=config.db.timeout)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA cache_size = -16000")   # 16 MB page cache
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute("PRAGMA mmap_size = 268435456")  # 256 MB
    conn.execute("PRAGMA busy_timeout = 5000")    # 5 s wait on lock
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
# Connection Pool
# ─────────────────────────────────────────────────────────────────────────────

class ConnectionPool:
    def __init__(self, db_path: str, size: int = 5) -> None:
        self._db_path = db_path
        self._pool: Queue[sqlite3.Connection] = Queue(maxsize=size)
        for _ in range(size):
            self._pool.put(_make_conn(db_path))

    @contextmanager
    def get(self) -> Generator[sqlite3.Connection, None, None]:
        conn: Optional[sqlite3.Connection] = None
        try:
            try:
                conn = self._pool.get(timeout=config.db.timeout)
                # Health-check: ping with a cheap query
                conn.execute("SELECT 1")
            except (Empty, sqlite3.OperationalError):
                log.warning("Pool exhausted or conn dead — creating temp connection")
                conn = _make_conn(self._db_path)
                yield conn
                conn.close()
                return
            yield conn
        finally:
            if conn is not None:
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
                                CHECK(priority IN (0,1,2)),
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
]


# ─────────────────────────────────────────────────────────────────────────────
# DatabaseManager
# ─────────────────────────────────────────────────────────────────────────────

class DatabaseManager:
    """
    Thread-safe SQLite manager with:
    - Connection pool
    - Automatic schema migrations
    - Async wrappers (asyncio.to_thread) — never blocks the event loop
    - In-process UserCache
    - Automatic backups
    """

    def __init__(self) -> None:
        db_path = config.db.path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._pool = ConnectionPool(db_path, size=config.db.pool_size)
        self.user_cache = UserCache()
        self._migrate()
        log.info("DatabaseManager ready — %s (schema v%d)", db_path, SCHEMA_VERSION)

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
                    try:
                        conn.executescript(sql)
                        conn.commit()
                    except sqlite3.OperationalError as exc:
                        # Column already exists — safe to ignore on re-run
                        if "duplicate column" in str(exc).lower():
                            log.debug("Migration v%d: skipping duplicate column: %s", version, exc)
                            conn.execute(
                                "INSERT OR REPLACE INTO schema_version VALUES (?)", (version,)
                            )
                            conn.commit()
                        else:
                            raise
            log.info("Schema up-to-date (v%d)", SCHEMA_VERSION)

    # ── Synchronous core ──────────────────────────────────────────────────────

    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        with self._pool.get() as conn:
            try:
                cur = conn.execute(sql, params)
                conn.commit()
                return cur
            except sqlite3.Error as exc:
                conn.rollback()
                log.error("DB execute error: %s | SQL: %.200s", exc, sql)
                raise

    def executemany(self, sql: str, params_list: list[Sequence[Any]]) -> None:
        with self._pool.get() as conn:
            try:
                conn.executemany(sql, params_list)
                conn.commit()
            except sqlite3.Error as exc:
                conn.rollback()
                log.error("DB executemany error: %s | SQL: %.200s", exc, sql)
                raise

    def fetchone(self, sql: str, params: Sequence[Any] = ()) -> Optional[sqlite3.Row]:
        with self._pool.get() as conn:
            try:
                return conn.execute(sql, params).fetchone()
            except sqlite3.Error as exc:
                log.error("DB fetchone error: %s | SQL: %.200s", exc, sql)
                return None

    def fetchall(self, sql: str, params: Sequence[Any] = ()) -> List[sqlite3.Row]:
        with self._pool.get() as conn:
            try:
                return conn.execute(sql, params).fetchall()
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

    # ── Audit log ─────────────────────────────────────────────────────────────

    def log_action(self, user_id: str, action: str,
                   target_id: Optional[str] = None, detail: Optional[str] = None) -> None:
        try:
            self.execute(
                "INSERT INTO audit_log (user_id, action, target_id, detail) VALUES (?,?,?,?)",
                (str(user_id), action, str(target_id) if target_id else None, detail),
            )
        except Exception as exc:
            log.warning("Audit log write failed: %s", exc)

    async def alog_action(self, user_id: str, action: str,
                          target_id: Optional[str] = None, detail: Optional[str] = None) -> None:
        await asyncio.to_thread(self.log_action, user_id, action, target_id, detail)

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

    # ── Stats helper (single query) ───────────────────────────────────────────

    async def user_task_stats(self, uid: str) -> dict[str, int]:
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
            return {"total": 0, "completed": 0, "pending": 0,
                    "cancelled": 0, "overdue": 0, "pinned": 0}
        return {k: int(row[k] or 0) for k in
                ("total", "completed", "pending", "cancelled", "overdue", "pinned")}

    # ── Graceful shutdown ─────────────────────────────────────────────────────

    def close(self) -> None:
        self._pool.close_all()
        log.info("DatabaseManager closed")


# Module-level singleton
db = DatabaseManager()

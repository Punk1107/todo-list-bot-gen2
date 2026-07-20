# 📝 To-Do List Bot Gen 2

A production-grade Discord To-Do List Bot rebuilt from the ground up with a fully modular architecture, bilingual support, advanced security, and smart background automation.

## ✨ What's New in Gen 2

| Feature | Gen 1 | Gen 2 |
|---|---|---|
| Code structure | Single monolithic file | Modular (`core` / `handlers` / `utils` / `locales`) |
| Language | Thai only | 🇹🇭 Thai + 🇬🇧 English (per-user setting) |
| Security | Basic rate limit | Input sanitisation + regex pattern detection + multi-bucket rate limiter |
| Database | Raw SQLite calls | Connection pool + WAL mode + append-only migrations + audit log + caching |
| User helpers | Synchronous (blocks event loop) | Fully async via `asyncio.to_thread` |
| Backups | Manual | Automatic with rotation (configurable interval) |
| Slash commands | Mixed | 100% Discord slash commands |
| Reminders | Basic loop | Smart reminders with overdue re-notification + priority display |
| Deadline DM | None | Direct DM reminders at 24 h / 3 h / 1 h before deadline (bitmask dedup) |
| Recurring tasks | Partial | Full daily / weekly / monthly auto-renewal |
| Export | CSV | CSV with UTF-8 BOM (Excel-compatible) |
| Error handling | Ad-hoc | Structured logging + global `on_app_command_error` handler |
| Config | Scattered | Single typed `AppConfig` from `.env` |
| Task views | Basic | Interactive UI modals, paginated list, category select dropdown, pin toggle |
| Daily digest | None | Configurable daily summary with overdue count |
| Task pinning | None | `/pin` / `/unpin` commands + pinned-first sorting |
| Today / Overdue | None | Dedicated `/today` and `/overdue` quick-views |
| Event loop | Standard | uvloop on Linux/macOS for 2-4x faster throughput |
| Write batching | None | `BulkWriter` — async write queue that flushes in one transaction |
| Read cache | None | `QueryCache` (L1 TTL cache) — eliminates repeated read round-trips |
| WAL checkpoint | None | Automatic WAL truncation to keep disk usage bounded |
| Webserver | Flask (daemon thread) | Pure async `aiohttp` — runs on bot's event loop |
| Persistent views | None | Buttons on old messages survive bot restarts |

---

## 🚀 Quick Start

### 1. Clone & enter directory
```bash
cd "to do list bot gen 2"
```

### 2. Create virtual environment
```bash
python -m venv venv
venv\Scripts\activate    # Windows
source venv/bin/activate # macOS / Linux
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment
```bash
copy .env.example .env
# Edit .env and set DISCORD_TOKEN (required)
```

### 5. Run the bot
```bash
python main.py
```

---

## 📁 Project Structure

```
to do list bot gen 2/
├── main.py                  # Entry point — TodoBot class, event handlers, logging setup
├── requirements.txt         # Pinned dependencies
├── .env.example             # Config template (copy → .env)
├── .gitignore
│
├── core/                    # Core infrastructure
│   ├── config.py            # Typed AppConfig loaded from .env (v3: added QueryCache + BulkWriter tunables)
│   ├── database.py          # Connection pool (default 10), async wrappers, migrations (v1→v7),
│   │                        # UserCache (300 s TTL), StatsCache (60 s TTL), QueryCache (L1 read cache),
│   │                        # BulkWriter (async write-batching), WAL checkpoint, backup
│   └── security.py          # InputValidator + multi-bucket RateLimiter + @rate_limit_check decorator
│
├── handlers/                # Discord Cogs
│   ├── tasks_cog.py         # /add /list /today /overdue /task /done /delete
│   │                        # /pin /unpin /recurring /search /stats /export
│   ├── settings_cog.py      # /setup /lang /help /category /admin
│   ├── reminders_cog.py     # Background loops: reminder, recurring, backup,
│   │                        # cache-cleanup, daily-digest, WAL-checkpoint, deadline-dm
│   └── task_views.py        # Discord UI: AddTaskModal, TaskActionView, TaskListView,
│                            # DeleteConfirmView, LanguageView, CategorySelect, PrioritySelectView
│
├── utils/
│   ├── helpers.py           # Async user helpers, embed builders, date utils,
│   │                        # urgency colour/badge, progress bar, CSV export
│   └── webserver.py         # Async aiohttp keep-alive server (runs on bot's event loop)
│                            # Endpoints: GET /  GET /health  GET /ready  GET /metrics
│
├── locales/
│   ├── i18n.py              # Translation engine (lazy-loads locale modules)
│   ├── th.py                # Thai strings
│   └── en.py                # English strings
│
├── data/                    # Created at runtime
│   ├── tasks.db             # SQLite database (schema v7)
│   └── backups/             # Timestamped DB backup files
│
└── logs/                    # Created at runtime
    └── bot.log              # Rotating log (5 MB × 5 backups)
```

---

## 🌐 Slash Commands

### 📝 Task Commands

| Command | Description |
|---|---|
| `/add` | ➕ Open priority selector → modal to add a new task |
| `/list` | 📋 View your tasks (paginated, filterable by status) |
| `/today` | 📅 Tasks due today in your timezone |
| `/overdue` | 🚨 All overdue pending tasks |
| `/task [id]` | 📌 Full detail view of a task by ID |
| `/done [id]` | ✅ Mark a task as completed |
| `/delete [id]` | 🗑️ Delete a task (with confirmation) |
| `/pin [id]` | 📌 Pin a task (shows first in lists) |
| `/unpin [id]` | 📌 Unpin a task |
| `/recurring [id] [interval]` | 🔄 Set recurring: `daily` / `weekly` / `monthly` / `none` |
| `/search [query]` | 🔍 Search tasks by name, tags, or description |
| `/stats` | 📊 Your task statistics with progress bar |
| `/export` | 📤 Export all tasks as a CSV file |

### ⚙️ Settings Commands

| Command | Description |
|---|---|
| `/setup [timezone]` | ⚙️ Set your timezone and notification channel |
| `/lang` | 🌐 Switch language (Thai / English) |
| `/category list` | 📂 List your categories |
| `/category add` | ➕ Add a custom category |
| `/category remove [id]` | 🗑️ Remove a custom category |
| `/help` | 📖 Show all commands |

### 🔐 Admin Commands *(owner-only)*

| Command | Description |
|---|---|
| `/admin stats` | 📊 Bot-wide statistics (users, tasks, rate-limit hits) |
| `/admin backup` | 💾 Trigger a manual database backup |
| `/admin cache_purge` | 🗑️ Purge expired user cache entries |

---

## 🔒 Security Features

- **Input sanitisation** — strips control characters; detects SQL/script injection patterns
- **Multi-bucket rate limiting** — separate limits for commands (30/min), task creation (100/hr), searches (10/min), and exports (5/day)
- **Block duration** — users exceeding limits are blocked for a configurable period (default 5 min)
- **Audit log** — every action recorded to the `audit_log` table via `BulkWriter` (non-blocking)
- **Owner isolation** — users can only view and edit their own tasks
- **Permission checks** — every button and modal interaction verifies ownership before acting

---

## 🗄️ Database Schema (v7)

The database uses append-only versioned migrations (existing entries are never modified).

| Table | Purpose |
|---|---|
| `users` | Per-user settings: timezone, channel, language, role, notification preferences, streak, theme, premium |
| `tasks` | Task data: name, deadline, priority, status, recurring, tags, description, pinned, subtask parent, custom reminder, progress, time-tracking, dm_reminded bitmask |
| `categories` | User-defined and system-default categories (name, emoji, colour) |
| `task_assignments` | Many-to-many task–user assignment mapping |
| `task_comments` | Per-task comments / notes from collaborators |
| `user_achievements` | Badge and milestone tracking per user |
| `audit_log` | Immutable action log (user, action, target, detail, timestamp) |
| `schema_version` | Tracks the current migration version |

### Migration History

| Version | Change |
|---|---|
| v1 | Baseline schema: users, categories, tasks, task_assignments, indexes |
| v2 | Audit log table |
| v3 | Seed default system categories (General, Urgent, Personal, Home, Study) |
| v4 | `is_pinned` column + compound indexes for stats queries |
| v5 | `custom_reminder` on tasks + `notify_enabled` / `daily_digest` on users |
| v6 | Expanded user/task columns (streak, theme, premium, progress, time-tracking), `task_comments`, `user_achievements`, compound indexes |
| v7 | `dm_reminded` bitmask column on tasks for deadline DM deduplication |

---

## ⚙️ Configuration Reference

All settings are loaded from `.env`. Copy `.env.example` to get started.

### Required

| Variable | Description |
|---|---|
| `DISCORD_TOKEN` | Your bot token from the Discord Developer Portal |

### Bot

| Variable | Default | Description |
|---|---|---|
| `DEFAULT_TIMEZONE` | `Asia/Bangkok` | Default timezone for new users |
| `DEFAULT_LANG` | `th` | Default language: `th` or `en` |
| `BOT_OWNER_IDS` | *(empty)* | Comma-separated Discord user IDs with admin access |

### Database

| Variable | Default | Description |
|---|---|---|
| `DATABASE_PATH` | `data/tasks.db` | SQLite file path |
| `DB_POOL_SIZE` | `10` | Connection pool size |
| `DB_TIMEOUT` | `30` | Query timeout in seconds |
| `DB_BACKUP_ENABLED` | `true` | Enable automatic backups |
| `DB_BACKUP_INTERVAL_HOURS` | `24` | Backup frequency |
| `DB_MAX_BACKUPS` | `7` | How many backup files to keep |
| `DB_QUERY_CACHE_TTL` | `30.0` | L1 QueryCache TTL in seconds (`0` to disable) |
| `DB_BULK_WRITE_INTERVAL_MS` | `500` | BulkWriter flush interval in milliseconds |
| `DB_WAL_CHECKPOINT_HOURS` | `6` | How often to run a WAL TRUNCATE checkpoint |

### Rate Limiting

| Variable | Default | Description |
|---|---|---|
| `RATE_COMMANDS_PER_MIN` | `30` | Max commands per minute per user |
| `RATE_TASKS_PER_HOUR` | `100` | Max task creations per hour per user |
| `RATE_SEARCHES_PER_MIN` | `10` | Max searches per minute per user |
| `RATE_EXPORTS_PER_DAY` | `5` | Max CSV exports per day per user |
| `RATE_BLOCK_SECONDS` | `300` | Block duration after exceeding a limit |
| `MAX_INPUT_LENGTH` | `2000` | Maximum raw input length |
| `MAX_TASK_NAME_LENGTH` | `200` | Maximum task name length |
| `MAX_DESCRIPTION_LENGTH` | `1000` | Maximum description length |

### Notifications

| Variable | Default | Description |
|---|---|---|
| `REMINDER_INTERVAL_MIN` | `30` | How often (minutes) the channel reminder loop runs |
| `RECURRING_INTERVAL_MIN` | `60` | How often (minutes) the recurring renewal loop runs |
| `OVERDUE_REMIND_HOURS` | `6` | Hours between overdue re-notifications |
| `DAILY_SUMMARY_ENABLED` | `true` | Enable daily digest messages |
| `DAILY_SUMMARY_HOUR` | `8` | UTC hour to send the daily digest (0–23) |
| `DM_REMINDER_INTERVAL_MIN` | `15` | How often (minutes) to check for deadline DM reminders |

### Keep-Alive Web Server

| Variable | Default | Description |
|---|---|---|
| `WEBSERVER_ENABLED` | `true` | Enable the async aiohttp keep-alive server |
| `WEBSERVER_HOST` | `0.0.0.0` | Bind host |
| `WEBSERVER_PORT` | `8080` | Bind port |

---

## 🛠️ Discord Bot Setup

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new Application → Add a Bot
3. Under **Bot** → Enable **Message Content Intent** and **Server Members Intent**
4. Under **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Permissions: `Send Messages`, `Embed Links`, `Attach Files`, `Read Message History`
5. Copy the generated URL and invite the bot to your server

---

## 🌩️ Deploy on Render (Free Tier)

1. Push this project to GitHub
2. Create a new **Web Service** on Render
3. Set all environment variables from `.env.example`
4. Build command: `pip install -r requirements.txt`
5. Start command: `python main.py`
6. The built-in async aiohttp server (`/health` endpoint) prevents Render from sleeping

---

## 📦 Dependencies

| Package | Purpose |
|---|---|
| `discord.py >= 2.4.0` | Discord API client |
| `python-dotenv >= 1.0.0` | Load `.env` variables |
| `pytz >= 2024.1` | Timezone conversion |
| `aiofiles >= 23.2.1` | Async file I/O |
| `aiohttp >= 3.9.0` | Async HTTP + keep-alive web server |
| `uvloop >= 0.19.0` | *(Linux/macOS only)* Faster event loop — silently ignored on Windows |

---

## 🔄 Background Loops (RemindersCog)

| Loop | Interval | Purpose |
|---|---|---|
| `reminder_loop` | Configurable (default 30 min) | Send deadline reminders and overdue alerts to user notification channels |
| `recurring_loop` | Configurable (default 60 min) | Renew completed recurring tasks by creating the next occurrence |
| `daily_digest_loop` | Every 5 min (fires once/day at configured UTC hour) | Send a daily summary of today's tasks and overdue count |
| `backup_loop` | Configurable (default 24 hr) | Create a timestamped SQLite backup with automatic rotation |
| `cleanup_loop` | Every 10 min | Purge expired `UserCache` / `QueryCache` entries and stale rate-limiter buckets |
| `db_wal_checkpoint_loop` | Configurable (default 6 hr) | Run WAL TRUNCATE checkpoint to keep disk usage bounded |
| `deadline_dm_loop` | Configurable (default 15 min) | Send DMs directly to task owners at 24 h / 3 h / 1 h before deadline (bitmask dedup via `dm_reminded`) |

---

## 🏗️ Architecture Notes

### Performance
- **Connection pool** — 10 SQLite connections with health checks and overflow support
- **QueryCache (L1)** — TTL-based read cache keyed by `blake2b(sql + params)` to eliminate hot repeated reads (default TTL 30 s, max 2048 entries)
- **BulkWriter** — accumulates write operations (audit log, reminder timestamps, dm_reminded updates) and flushes them in a single transaction every 500 ms, dramatically reducing per-row transaction overhead
- **uvloop** — optionally replaces the default asyncio event loop on Linux/macOS for 2–4× throughput
- **WAL mode** — SQLite runs in Write-Ahead Logging mode with a 64 MB page cache, 1 GB mmap, and periodic `TRUNCATE` checkpoints

### Caching Layers
| Cache | TTL | Purpose |
|---|---|---|
| `UserCache` | 300 s | User settings (lang, timezone, channel, role) |
| `StatsCache` | 60 s | Per-user task statistics aggregate |
| `QueryCache` | Configurable (default 30 s) | Generic SQL read results (fetchone / fetchall) |

### Graceful Shutdown
On `SIGINT` / `SIGTERM`, the bot:
1. Flushes the `BulkWriter` queue (prevents data loss)
2. Stops the aiohttp web server
3. Closes all database pool connections
4. Shuts down the event loop

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
| Recurring tasks | Partial | Full daily / weekly / monthly auto-renewal |
| Export | CSV | CSV with UTF-8 BOM (Excel-compatible) |
| Error handling | Ad-hoc | Structured logging + global `on_app_command_error` handler |
| Config | Scattered | Single typed `AppConfig` from `.env` |
| Task views | Basic | Interactive UI modals, paginated list, category select dropdown, pin toggle |
| Daily digest | None | Configurable daily summary with overdue count |
| Task pinning | None | `/pin` / `/unpin` commands + pinned-first sorting |
| Today / Overdue | None | Dedicated `/today` and `/overdue` quick-views |

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
├── main.py                  # Entry point — bot class, event handlers, logging
├── requirements.txt         # Pinned dependencies
├── .env.example             # Config template (copy → .env)
├── .gitignore
│
├── core/                    # Core infrastructure
│   ├── config.py            # Typed AppConfig loaded from .env
│   ├── database.py          # Connection pool, async wrappers, migrations,
│   │                        # UserCache (300 s TTL), StatsCache (60 s TTL), backup
│   └── security.py          # InputValidator + multi-bucket RateLimiter + decorator
│
├── handlers/                # Discord Cogs
│   ├── tasks_cog.py         # /add /list /today /overdue /task /done /delete
│   │                        # /pin /unpin /recurring /search /stats /export
│   ├── settings_cog.py      # /setup /lang /help /category /admin
│   ├── reminders_cog.py     # Background loops: reminder, recurring, backup,
│   │                        # cache-cleanup, daily-digest
│   └── task_views.py        # Discord UI: AddTaskModal, TaskActionView,
│                            # TaskListView, DeleteConfirmView, LanguageView,
│                            # CategorySelect
│
├── utils/
│   ├── helpers.py           # Async user helpers, embed builders, date utils,
│   │                        # urgency colour/badge, progress bar, CSV export
│   └── webserver.py         # Lightweight Flask keep-alive server (daemon thread)
│
├── locales/
│   ├── i18n.py              # Translation engine (lazy-loads locale modules)
│   ├── th.py                # Thai strings
│   └── en.py                # English strings
│
├── data/                    # Created at runtime
│   ├── tasks.db             # SQLite database (schema v5)
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
| `/add` | ➕ Open modal to add a new task |
| `/list` | 📋 View your tasks (paginated, filterable) |
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
- **Audit log** — every action recorded to the `audit_log` table in the database
- **Owner isolation** — users can only view and edit their own tasks
- **Permission checks** — every button and modal interaction verifies ownership before acting

---

## 🗄️ Database Schema (v5)

The database uses append-only versioned migrations (existing entries are never modified).

| Table | Purpose |
|---|---|
| `users` | Per-user settings: timezone, channel, language, notification preferences |
| `tasks` | Task data: name, deadline, priority, status, recurring, tags, description, pinned, subtask parent, custom reminder |
| `categories` | User-defined and system-default categories (name, emoji, colour) |
| `task_assignments` | Many-to-many task–user assignment mapping |
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
| `DB_POOL_SIZE` | `5` | Connection pool size |
| `DB_TIMEOUT` | `30` | Query timeout in seconds |
| `DB_BACKUP_ENABLED` | `true` | Enable automatic backups |
| `DB_BACKUP_INTERVAL_HOURS` | `24` | Backup frequency |
| `DB_MAX_BACKUPS` | `7` | How many backup files to keep |

### Rate Limiting

| Variable | Default | Description |
|---|---|---|
| `RATE_COMMANDS_PER_MIN` | `30` | Max commands per minute per user |
| `RATE_TASKS_PER_HOUR` | `100` | Max task creations per hour per user |
| `RATE_SEARCHES_PER_MIN` | `10` | Max searches per minute per user |
| `RATE_EXPORTS_PER_DAY` | `5` | Max CSV exports per day per user |
| `RATE_BLOCK_SECONDS` | `300` | Block duration after exceeding a limit |
| `MAX_TASK_NAME_LENGTH` | `200` | Maximum task name length |
| `MAX_DESCRIPTION_LENGTH` | `1000` | Maximum description length |

### Notifications

| Variable | Default | Description |
|---|---|---|
| `REMINDER_INTERVAL_MIN` | `30` | How often (minutes) the reminder loop runs |
| `RECURRING_INTERVAL_MIN` | `60` | How often (minutes) the recurring renewal loop runs |
| `OVERDUE_REMIND_HOURS` | `6` | Hours between overdue re-notifications |
| `DAILY_SUMMARY_ENABLED` | `true` | Enable daily digest messages |
| `DAILY_SUMMARY_HOUR` | `8` | UTC hour to send the daily digest (0–23) |

### Keep-Alive Web Server

| Variable | Default | Description |
|---|---|---|
| `WEBSERVER_ENABLED` | `true` | Enable the Flask keep-alive server |
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
6. The built-in keep-alive Flask server (`/health` endpoint) prevents Render from sleeping

---

## 📦 Dependencies

| Package | Purpose |
|---|---|
| `discord.py >= 2.4.0` | Discord API client |
| `python-dotenv >= 1.0.0` | Load `.env` variables |
| `pytz >= 2024.1` | Timezone conversion |
| `aiofiles >= 23.2.1` | Async file I/O |
| `aiohttp >= 3.9.0` | Async HTTP (used internally by discord.py) |
| `Flask >= 3.0.0` | Keep-alive web server |

---

## 🔄 Background Loops (RemindersCog)

| Loop | Interval | Purpose |
|---|---|---|
| `reminder_loop` | Configurable (default 30 min) | Send deadline reminders and overdue alerts to user channels |
| `recurring_loop` | Configurable (default 60 min) | Renew completed recurring tasks by creating the next occurrence |
| `daily_digest_loop` | Every 5 min (fires once/day at configured hour) | Send a daily summary of today's tasks and overdue count |
| `backup_loop` | Configurable (default 24 hr) | Create a timestamped SQLite backup with automatic rotation |
| `cleanup_loop` | Every 10 min | Purge expired `UserCache` entries and stale rate-limiter buckets |

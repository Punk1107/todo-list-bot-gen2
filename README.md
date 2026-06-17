# 📝 To-Do List Bot Gen 2

A production-grade Discord To-Do List Bot rebuilt from the ground up.

## ✨ What's New in Gen 2

| Feature | Gen 1 | Gen 2 |
|---|---|---|
| Code structure | Single monolithic file | Modular (core / handlers / utils / locales) |
| Language | Thai only | 🇹🇭 Thai + 🇬🇧 English (per-user) |
| Security | Basic rate limit | Input sanitisation + regex pattern detection + multi-bucket rate limiter |
| Database | Raw SQLite calls | Connection pool + WAL mode + append-only migrations + audit log |
| Backups | Manual | Automatic with rotation |
| Slash commands | Mixed | 100% Discord slash commands |
| Reminders | Basic loop | Smart reminders with overdue re-notification |
| Recurring tasks | Partial | Full daily/weekly/monthly auto-renewal |
| Export | CSV | CSV with UTF-8 BOM (Excel compatible) |
| Error handling | Ad-hoc | Structured logging + global error handler |
| Config | Scattered | Single typed `AppConfig` from `.env` |

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
source venv/bin/activate # macOS/Linux
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment
```bash
copy .env.example .env
# Edit .env and set DISCORD_TOKEN
```

### 5. Run the bot
```bash
python main.py
```

---

## 📁 Project Structure

```
to do list bot gen 2/
├── main.py                  # Entry point
├── requirements.txt
├── .env.example             # Config template (copy to .env)
├── .gitignore
│
├── core/                    # Core infrastructure
│   ├── config.py            # Typed config from .env
│   ├── database.py          # Connection pool, migrations, backup
│   └── security.py          # Input validator + rate limiter
│
├── handlers/                # Discord Cogs
│   ├── tasks_cog.py         # /add /list /done /delete /search /stats /export
│   ├── settings_cog.py      # /setup /lang /help /category
│   ├── reminders_cog.py     # Background reminder/recurring/backup loops
│   └── task_views.py        # Discord UI Modals & Views
│
├── utils/
│   ├── helpers.py           # Shared utility functions
│   └── webserver.py         # Keep-alive Flask server
│
├── locales/
│   ├── i18n.py              # Translation engine
│   ├── th.py                # Thai strings
│   └── en.py                # English strings
│
├── data/                    # Created at runtime
│   ├── tasks.db
│   └── backups/
│
└── logs/                    # Created at runtime
    └── bot.log
```

---

## 🔒 Security Features

- **Input sanitisation** — strips control chars, detects SQL/script injection
- **Rate limiting** — separate buckets for commands, tasks, searches, exports
- **Audit log** — every action logged to `audit_log` table in DB
- **Owner isolation** — users can only view/edit their own tasks
- **Permission checks** — every button/modal verifies ownership

---

## 🌐 Slash Commands

| Command | Description |
|---|---|
| `/add` | ➕ เพิ่ม Task ใหม่ / Add new task |
| `/list [filter]` | 📋 ดูรายการ Task / View tasks |
| `/task [id]` | 📌 ดู Task ตาม ID / View task detail |
| `/done [id]` | ✅ ทำเครื่องหมายเสร็จ / Mark done |
| `/delete [id]` | 🗑️ ลบ Task / Delete task |
| `/search [query]` | 🔍 ค้นหา / Search tasks |
| `/stats` | 📊 สถิติ / Your statistics |
| `/export` | 📤 ส่งออก CSV / Export CSV |
| `/setup [timezone]` | ⚙️ ตั้งค่า / Configure bot |
| `/lang` | 🌐 เปลี่ยนภาษา / Change language |
| `/category` | 🏷️ จัดการหมวดหมู่ / Manage categories |
| `/help` | 📖 วิธีใช้ / Help |

---

## 🛠️ Discord Bot Setup

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
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
3. Set environment variables from `.env.example`
4. Build command: `pip install -r requirements.txt`
5. Start command: `python main.py`
6. The keep-alive webserver prevents Render from sleeping

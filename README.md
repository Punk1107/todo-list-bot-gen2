# 📝 To-Do List Discord Bot Gen 4.0

### Enterprise-Grade Discord Productivity, Collaboration & Project Management System

> Powered by **Supabase PostgreSQL (Schema v28)**, **Realtime CDC**, **17 Modular Cogs**, **9-Language NLP Date Engine**, **True LRU Caching**, **Row Level Security (RLS)**, and **Deno Edge Analytics** — engineered for agile teams and power users who demand zero-lag responsiveness, transparency, and data integrity.

---

![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)
![discord.py](https://img.shields.io/badge/discord.py-2.4%2B-5865F2?logo=discord&logoColor=white)
![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL%20v28-3ECF8E?logo=supabase&logoColor=white)
![Modular Cogs](https://img.shields.io/badge/Modular%20Cogs-17%20Loaded-purple)
![Languages](https://img.shields.io/badge/Languages-9%20Supported-orange)
![Themes](https://img.shields.io/badge/Themes-10%20Curated-pink)
![Tests](https://img.shields.io/badge/Tests-18%20Suites%20Passing-brightgreen)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## 📑 Table of Contents

1. [✨ What's New in Gen 4.0](#-whats-new-in-gen-40)
2. [🏛️ System Architecture & 17 Modular Cogs](#-system-architecture--17-modular-cogs)
3. [🌐 9-Language Support & Smart Date Engine](#-9-language-support--smart-date-engine)
4. [📖 Complete Slash & Context Menu Command Directory](#-complete-slash--context-menu-command-directory)
   - [1. Personal Task Management](#1-personal-task-management)
   - [2. Safe Recovery & Recycle Bin](#2-safe-recovery--recycle-bin)
   - [3. Eisenhower 4D Matrix & Saved Smart Lists](#3-eisenhower-4d-matrix--saved-smart-lists)
   - [4. Audit Trail & Weekly Retrospective](#4-audit-trail--weekly-retrospective)
   - [5. Team Collaboration & Shared Projects](#5-team-collaboration--shared-projects)
   - [6. Multi-Select Bulk Operations](#6-multi-select-bulk-operations)
   - [7. Focus & Pomodoro Timer](#7-focus--pomodoro-timer)
   - [8. Gamification, Streaks & Leaderboards](#8-gamification-streaks--leaderboards)
   - [9. Templates & Routine Workflows](#9-templates--routine-workflows)
   - [10. Full Text Search & AI-Ready Recommendations](#10-full-text-search--ai-ready-recommendations)
   - [11. File Attachments](#11-file-attachments)
   - [12. Private Calendar Feeds](#12-private-calendar-feeds)
   - [13. Task Import](#13-task-import)
   - [14. Productivity Analytics (Supabase Edge)](#14-productivity-analytics-supabase-edge)
   - [15. Settings, i18n & Embed Themes](#15-settings-i18n--embed-themes)
   - [16. System Monitoring & Health Telemetry](#16-system-monitoring--health-telemetry)
5. [🎛️ Interactive UI & Defensive Design](#-interactive-ui--defensive-design)
6. [⚡ Performance, Caching & Scalability](#-performance-caching--scalability)
7. [🔄 Background Automation & Schedulers (8 Loops)](#-background-automation--schedulers-8-loops)
8. [🛡️ Security & Row Level Security (RLS)](#-security--row-level-security-rls)
9. [🐘 Database Schema History (Auto-Migrations v1 ➔ v28)](#-database-schema-history-auto-migrations-v1--v28)
10. [🌩️ Supabase Realtime & Edge Functions](#-supabase-realtime--edge-functions)
11. [📅 Private Calendar Feeds & Async Webserver](#-private-calendar-feeds--async-webserver)
12. [🚀 Installation & Deployment Guide](#-installation--deployment-guide)
13. [⚙️ Environment Variables Reference](#-environment-variables-reference)
14. [🧪 Test Suite & Quality Assurance (18 Modules)](#-test-suite--quality-assurance-18-modules)
15. [📂 Project File Structure Tree](#-project-file-structure-tree)

---

## ✨ What's New in Gen 4.0

Gen 4.0 represents a massive leap beyond Gen 3.0, taking the system from a task tracking bot to an **enterprise-grade project collaboration and productivity platform**.

| Feature Area | Gen 1 / 2 | Gen 3.0 | **Gen 4.0 (Current Production)** |
|---|---|---|---|
| **Database & Schema** | SQLite monolithic (v1–v7) | Supabase PostgreSQL Schema v23 | **Supabase PostgreSQL Schema v28** (28 Auto-Migrations, 24 tables, Partial Indexes for zero-lag background queries) |
| **Cog Architecture** | Monolithic / 6 Cogs | 14 Modular Cogs | **17 Modular Cogs** (+ `recovery`, `organization`, `history_reporting`) |
| **Accidental Deletion & Recovery** | Permanent deletion immediately | Permanent deletion immediately | **Recycle Bin & Safe Soft Delete** (`/trash`, `/restore`, 30-day retention, cascading subtask restoration, focus session auto-halt) |
| **Task Prioritization Framework** | Single Priority number | Priority 0–7 | **Eisenhower 4D Matrix** (`/matrix` Q1–Q4 Drill-down) + **Saved Smart Filters** (`/filter save\|list\|use\|delete` with JSONB criteria) |
| **Audit Trail & History** | None | Raw `audit_log` table | **Task Audit Trail** (`/history` activity timeline + snooze counts) + **Weekly Retrospective** (`/retrospective` self-digest & coaching tips) |
| **Data Export** | Basic CSV export | CSV export | **Interactive Offline HTML Dashboard** (`/export format:html` with live search, dark/light mode, and real-time checkbox progress) + CSV |
| **Project Permissions (RBAC)** | None | Fixed Roles (Lead/Member/Viewer) | **Granular Role Permissions** (`/project permissions` setting matrix per role) + **Confidential Tasks** (`/project set-private` & `is_private` flag) |
| **Discord Native Integration** | Slash commands only | Slash commands only | **Right-Click Message Context Menu (`Add to To-Do`)** with Jump Link, **Discussion Threads (`🌐 Public` / `🔒 Private`)**, and **Multi-Select Bulk Actions** (`/bulk`) |
| **Calendar Sync** | None | In-progress | **Private iCalendar Feed Subscriptions** (`/calendar link\|rotate\|revoke` syncing with Google Calendar, Apple Calendar, and Outlook) |
| **Embed Personalization** | Static Blurple embed | Static Blurple embed | **10 Curated Color Themes** (`/theme`, `/settings theme`) with gradient progress bars and instant live previews |
| **Caching Engine** | FIFO Cache | Basic in-memory cache | **True LRU Eviction (`OrderedDict.move_to_end`)** across `UserCache`, `StatsCache`, and `QueryCache` with Table-Scoped Invalidation across all 24 tables |
| **Background Write Safety** | Direct writes | Basic BulkWriter | **Bounded `BulkWriter`** (10,000 capacity limit, Chunked transactions of 50 items, per-item fallback, and retry caps) |
| **Languages (i18n)** | Thai / English | 9 Languages | **9 Languages with Discord Locale Auto-Detection** (TH, EN, ZH, JA, KO, ES, RU, FR, DE) |
| **Automated Testing** | Minimal | ~264 unit tests | **18 Comprehensive Test Suites** covering Performance, RLS, Recurrence, Realtime WS, Workflows, and Discord Native integration |

---

### 🌟 Key Feature Highlights in Gen 4.0

```text
 🗑️ Recycle Bin & Soft Delete    🧭 Eisenhower 4D Matrix         📜 Task Audit Trail & Retrospectives
 ┌──────────────────────────┐    ┌──────────────────────────┐    ┌──────────────────────────────────┐
 │ • 30-Day Retention       │    │ • Q1: Urgent & Important │    │ • Full timeline of edits/status  │
 │ • Cascading Restoration  │    │ • Q2: Schedule Deep Work │    │ • Snooze bottleneck analysis     │
 │ • Halts Active Focus     │    │ • Q3: Delegate / Roles   │    │ • Weekly completion % coaching   │
 │ • /trash & /restore      │    │ • Q4: Eliminate Backlog  │    │ • Standalone Offline HTML Export │
 └──────────────────────────┘    └──────────────────────────┘    └──────────────────────────────────┘
 🔐 Granular Role Permissions    🎨 10 Curated Embed Themes      📅 Private iCal Subscriptions
 ┌──────────────────────────┐    ┌──────────────────────────┐    ┌──────────────────────────────────┐
 │ • Custom Member/Viewer   │    │ • Cyberpunk, Emerald,    │    │ • Google, Apple, Outlook Sync    │
 │ • Confidential Tasks     │    │   Sunset, Midnight, Gold │    │ • Rotating Token Security        │
 │ • Blocker Dependencies   │    │ • Dynamic Progress Bars  │    │ • Async keep-alive TCPSite       │
 │ • Discord Role Routing   │    │ • Live Preview Modals    │    │ • Zero extra cloud fees          │
 └──────────────────────────┘    └──────────────────────────┘    └──────────────────────────────────┘
```

---

## 🏛️ System Architecture & 17 Modular Cogs

The application is built on an asynchronous, decoupled event-driven architecture powered by Python 3.11+, `discord.py` 2.4+, and `asyncpg`.

```mermaid
flowchart TD
    subgraph Discord_Gateway ["🌐 Discord Gateway & API"]
        DISCORD["Discord Client / Interaction"]
        CTX_MENU["🖱️ Message Context Menu\n'Add to To-Do'"]
        THREADS["🧵 Task Discussion Threads\nPublic & Private"]
    end

    subgraph Bot_Core ["🤖 Bot Core Layer (main.py)"]
        LOADER["🧩 Extension Loader\n17 Modular Cogs"]
        DISPATCHER["🛡️ Security & Rate Limiting\ncore/security.py"]
        THEME["🎨 Theme Engine\ncore/theme.py (10 Themes)"]
        WEBSERVER["🌐 Async aiohttp Webserver\n/metrics · /ready · /calendar.ics"]
    end

    subgraph Feature_Cogs ["📦 17 Modular Feature Cogs"]
        direction TB
        COG_TASKS["handlers.tasks_cog\nPersonal Tasks, Stats, Export"]
        COG_COLLAB["collaboration.cog\nProjects, RBAC, Private Tasks"]
        COG_RECOVERY["recovery.cog\nRecycle Bin & Soft Delete"]
        COG_ORG["organization.cog\nEisenhower Matrix & Filters"]
        COG_HIST["history_reporting.cog\nAudit Trail & Retrospective"]
        COG_ROUTINE["routine_workflows.cog\nTemplates & Auto-Routines"]
        COG_BULK["discord_native.bulk_cog\nBulk Multi-Select Actions"]
        COG_FOCUS["focus.cog\nPOD / Pomodoro Focus Mode"]
        COG_GAME["gamification.cog\nStreaks, Badges, Leaderboard"]
        COG_SEARCH["search_recommendation.cog\nPostgreSQL FTS & AI Scoring"]
        COG_STORAGE["storage.cog\nSupabase File Attachments"]
        COG_CAL["calendar_feed.cog\niCal Subscription Tokens"]
        COG_IMPORT["task_import.cog\nCSV / JSON Batch Import"]
        COG_ANALYTICS["analytics.cog\nEdge Function Dispatcher"]
        COG_REMINDERS["handlers.reminders_cog\n8 Background Schedulers"]
        COG_SETTINGS["handlers.settings_cog\ni18n, Categories, Themes"]
        COG_MONITOR["handlers.monitoring_cog\nHealth, Errors, Telemetry"]
    end

    subgraph Data_Layer ["⚡ Data & Persistence Layer"]
        DB_MGR["core/database.py\nSchema v28 Engine"]
        LRU_CACHE["🧠 True LRU Caches (OrderedDict)\nUserCache · StatsCache · QueryCache"]
        BULK_WRITER["📝 Bounded BulkWriter\n10,000 Cap · Chunked 50-Item Batches"]
        RLS["🔒 Row Level Security\nsecurity_rls (SET LOCAL user_id)"]
        REALTIME["⚡ Supabase Realtime\nPhoenix WS & Debounced Tracker"]
        PG[("🐘 Supabase PostgreSQL\n24 Tables · Partial Indexes\nAuto-Migrations v1–v28")]
    end

    DISCORD --> DISPATCHER
    CTX_MENU --> DISPATCHER
    THREADS --> DISPATCHER
    DISPATCHER --> LOADER
    LOADER --> Feature_Cogs
    Feature_Cogs --> DB_MGR
    Feature_Cogs --> THEME
    Feature_Cogs --> WEBSERVER
    DB_MGR --> LRU_CACHE
    DB_MGR --> BULK_WRITER
    DB_MGR --> RLS
    DB_MGR --> PG
    REALTIME -. CDC Push .-> Feature_Cogs
```

### 🗂️ Module Architecture Map

| Module / Directory | Responsibility | Primary Classes / Services |
|---|---|---|
| [`main.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/main.py) | Application entrypoint, Cog registration, lifecycle hooks, graceful shutdown | `TodoBot`, `on_ready`, `setup_hook`, `close` |
| [`core/database.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/core/database.py) | **Schema v28** engine, connection pooling, True LRU caches, bounded `BulkWriter` | `DatabaseManager`, `QueryCache`, `BulkWriter`, `UserCache` |
| [`core/security.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/core/security.py) | SQL/Script injection protection, thread-safe rate limiting, sanitization | `RateLimiter`, `InputValidator`, `@rate_limit_check` |
| [`core/theme.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/core/theme.py) | 10 curated color palettes, dynamic progress bar rendering, embed theming | `Theme`, `THEMES`, `get_theme`, `render_themed_progress_bar` |
| [`recovery/`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/recovery/cog.py) | Recycle Bin, 30-day soft deletion, subtask cascade restoration | `RecoveryCog`, `RecoveryService`, `TrashPaginationView` |
| [`organization/`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/organization/cog.py) | Eisenhower 4D Matrix (Q1–Q4) and Custom Saved Filters / Smart Lists | `OrganizationCog`, `OrganizationService`, `EisenhowerMatrixView` |
| [`history_reporting/`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/history_reporting/cog.py) | Audit trail timeline, weekly retrospective digest, offline HTML dashboard export | `HistoryReportingCog`, `HistoryService`, `WeeklyRetrospectiveView` |
| [`collaboration/`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/collaboration/cog.py) | Shared projects, Kanban boards, granular RBAC, private tasks, dependencies | `CollaborationCog`, `CollaborationService`, `ProjectPermissionsView` |
| [`routine_workflows/`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/routine_workflows/cog.py) | Task templates, Definition of Done checklists, role/member join auto-routines | `RoutineWorkflowsCog`, `RoutineService`, `TemplateCreateModal` |
| [`discord_native/`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/discord_native/bulk_cog.py) | Multi-select bulk personal task operations (done, snooze, delete) | `BulkActionsCog`, `BulkTaskView`, `BulkTaskSelect` |
| [`realtime/`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/realtime/dashboard_tracker.py) | Phoenix WebSocket client, CDC Postgres change router, debounced dashboard updater | `PhoenixWSClient`, `RealtimeDispatcher`, `DashboardTracker` |
| [`security_rls/`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/security_rls/client.py) | PostgreSQL Row Level Security (RLS) client and migration CLI runner | `RLSClient`, `scoped_user_context`, `migration_runner.py` |
| [`recurrence/`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/recurrence/rules.py) | Extended recurrence engine (weekdays, intervals, monthly dates with month-end clamp) | `validate_rule`, `decode_rule`, `next_deadline` |
| [`task_features/`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/task_features/service.py) | Task comments, progress % tracking, and Definition of Done checklists | `TaskFeaturesService`, `TaskCommentModal`, `TaskProgressModal` |
| [`utils/webserver.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/utils/webserver.py) | Pure async keep-alive aiohttp server (`/`, `/health`, `/ready`, `/metrics`, `/calendar/{token}.ics`) | `start_async`, `_calendar_feed`, `_metrics` |
| [`handlers/`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/handlers/tasks_cog.py) | Tasks, Reminders, Settings, and Monitoring slash command handlers | `TasksCog`, `RemindersCog`, `SettingsCog`, `MonitoringCog` |

---

## 🌐 9-Language Support & Smart Date Engine

The bot features a comprehensive internationalization engine supporting **9 languages** with per-user language preference and Discord Locale auto-detection:

| Code | Language | Native Name | Flag | Date Parser Capabilities |
|:---:|---|---|:---:|---|
| `th` | Thai | ไทย | 🇹🇭 | พ.ศ. (Buddhist Era -543 offset), วันพรุ่งนี้, มกราคม–ธันวาคม, บ่าย/เย็น |
| `en` | English | English | 🇬🇧 | Natural relative (+2h, +3d), tomorrow at 5pm, next Friday, ISO 8601 |
| `zh` | Chinese | 中文 | 🇨🇳 | 明天, 后天, 下周五, 18点30分, 年/月/日 format |
| `ja` | Japanese | 日本語 | 🇯🇵 | 明日, 明後日, 来週金曜日, 18時30分, 年月日 format |
| `ko` | Korean | 한국어 | 🇰🇷 | 내일, 모레, 다음주 금요일, 18시 30분, 년월일 format |
| `es` | Spanish | Español | 🇪🇸 | mañana, pasado mañana, próximo viernes, a las 18:30 |
| `ru` | Russian | Русский | 🇷🇺 | завтра, послезавтра, в следующую пятницу, в 18:30 |
| `fr` | French | Français | 🇫🇷 | demain, après-demain, vendredi prochain, à 18h30 |
| `de` | German | Deutsch | 🇩🇪 | morgen, übermorgen, nächsten Freitag, um 18:30 Uhr |

Users can freely switch language at any time via `/lang` or let the bot auto-detect their Discord client language upon their first interaction.

---

## 📖 Complete Slash & Context Menu Command Directory

### 1. Personal Task Management
> 📂 Cog Module: [`handlers/tasks_cog.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/handlers/tasks_cog.py)

| Command / Context Action | Description | Parameters & Options |
|---|---|---|
| **`Add to To-Do`** *(Context Menu)* | Right-click any Discord message to convert it into a Task immediately | Target message (adds clickable jump link in embed) |
| `/add` | Create a new task (opens modal or accepts arguments) | `[task]` `[deadline]` `[priority: 0-7]` `[category]` `[tags]` |
| `/list` | View personal tasks with pagination & status filters | `[status: all\|pending\|completed]` `[category]` `[priority]` |
| `/today` | View all tasks due today in your local timezone | — |
| `/overdue` | View all past-due tasks requiring immediate attention | — |
| `/task` | Inspect a task in detail (subtasks, checklist, files, comments) | `task_id` *(with autocomplete)* |
| `/done` | Mark a task as completed | `task_id` `[force: True/False]` *(bypasses incomplete checklist)* |
| `/delete` | Safely move a task to the Recycle Bin (soft delete) | `task_id` *(with autocomplete)* |
| `/pin` / `/unpin` | Pin or unpin a task to keep it at the top of lists | `task_id` *(with autocomplete)* |
| `/recurring` | Configure recurring recurrence rules | `task_id` `[rule: daily\|weekdays\|weekly\|monthly\|JSON]` |
| `/snooze` | Postpone a task's deadline | `task_id` `[hours: default 24]` |
| `/stats` | View personal productivity overview stats | — |
| `/task-stats` | Interactive Productivity Dashboard with tab switching | Interactive: Overview, Speed & Timeliness, Refresh |
| `/digest` | On-demand Daily Digest showing your schedule right now | — |
| `/export` | Export tasks as Interactive Offline HTML Dashboard or CSV | `[format: html (default) \| csv]` |

---

### 2. Safe Recovery & Recycle Bin
> 📂 Cog Module: [`recovery/cog.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/recovery/cog.py)

| Command | Description | Notes |
|---|---|---|
| `/trash` | Open the interactive Recycle Bin browser | Shows all soft-deleted tasks with creation & deletion timestamps. Includes **Restore** and **Purge Permanently** buttons. |
| `/restore` | Restore a deleted task by ID | Restores the task, all child subtasks, and relinks parent hierarchy. |

> [!NOTE]
> Soft-deleted tasks are retained for **30 days**. Active Pomodoro focus sessions on deleted tasks are automatically stopped. Expired trash is purged automatically during the daily `cleanup_loop`.

---

### 3. Eisenhower 4D Matrix & Saved Smart Lists
> 📂 Cog Module: [`organization/cog.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/organization/cog.py)

| Command | Description | Details |
|---|---|---|
| `/matrix` | Open interactive Eisenhower 4-Quadrant Matrix | Divides tasks into **Q1: Do First** (P4–P7 & urgent), **Q2: Schedule** (P4–P7 & planned), **Q3: Delegate** (P0–P3 & urgent), and **Q4: Eliminate** (P0–P3 & planned). |
| `/filter save` | Save a custom filter criteria as a Smart List | Set criteria: `name`, `tags`, `min_priority`, `max_priority`, `status`, `project_id`, `due_within_days`, `sort_by`. (Max 25 filters/user). |
| `/filter list` | View all your saved Smart Lists | Displays summary of criteria and task counts for each saved list. |
| `/filter use` | Execute and view tasks from a saved Smart List | Fast autocomplete selector; renders paginated filtered embed. |
| `/filter delete` | Delete a saved Smart List | Autocomplete selector; safely deletes filter criteria. |

---

### 4. Audit Trail & Weekly Retrospective
> 📂 Cog Module: [`history_reporting/cog.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/history_reporting/cog.py)

| Command | Description | Details |
|---|---|---|
| `/history` | View complete task audit history & activity trail | Shows chronological log of creation, edits, priority updates, status transitions, and snooze counter. |
| `/retrospective` | View weekly retrospective self-digest on-demand | Calculates weekly completion rate %, snooze bottleneck tasks (top postponed tasks), overdue carryovers, and coaching tips. |

---

### 5. Team Collaboration & Shared Projects
> 📂 Cog Module: [`collaboration/cog.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/collaboration/cog.py)

The Collaboration Cog provides **19 comprehensive commands** for team execution:

| Command | Description | Roles Allowed |
|---|---|---|
| `/project create` | Create a new shared server project | Server Members |
| `/project list` | List all projects in this server (active/completed/archived) | Server Members |
| `/project view` | Open interactive project dashboard with live stats | Project Members |
| `/project board` | Open interactive Kanban board (`Pending`, `In Progress`, `Done`) | Project Members |
| `/project add-task` | Add a task with optional priority and `is_private` flag | Project Members (Subject to RBAC) |
| `/project set-priority` | Update project priority level (P0 to P7) | Leads / Admins |
| `/project complete-task` | Mark a project task as completed (triggers CDC broadcast) | Assignees / Leads / Admins |
| `/project my-tasks` | View all tasks assigned to you across server projects | Server Members |
| `/project dependency-add`| Make a task wait for another task (with cycle protection) | Project Members |
| `/project dependency-remove` | Remove a dependency blocker between tasks | Project Members |
| `/project assign-role` | Assign a task to a Discord Role (sends DMs to role members) | Project Members |
| `/project workload` | Visual workload breakdown by member and Discord role | Project Members |
| `/project members` | View and manage project members and their roles | Project Members |
| `/project add-member` | Add a user as `member` or `lead` (sends invite DM) | Leads / Admins |
| `/project activity` | View recent project activity feed | Project Members |
| `/project archive` | Archive or mark project as completed | Leads / Admins |
| `/project set-channel` | Set dedicated channel for real-time task completion broadcasts | Leads / Admins |
| `/project permissions`| **Configure granular RBAC permissions matrix** per role | Leads / Owner / Admins |
| `/project set-private`| **Toggle confidential task privacy** (visible only to creator & leads) | Creator / Leads / Admins |

---

### 6. Multi-Select Bulk Operations
> 📂 Cog Module: [`discord_native/bulk_cog.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/discord_native/bulk_cog.py)

| Command | Description | Behavior |
|---|---|---|
| `/bulk done` | Complete multiple tasks simultaneously | Opens paginated multi-select dropdown; awards gamification XP. |
| `/bulk snooze` | Snooze multiple tasks by 24 hours | Defensively extends deadline while preserving time component. |
| `/bulk delete` | Move multiple tasks to the Recycle Bin | Double-confirmation warning to prevent accidental mass deletion. |

---

### 7. Focus & Pomodoro Timer
> 📂 Cog Module: [`focus/cog.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/focus/cog.py)

| Command | Description | Behavior |
|---|---|---|
| `/focus start` | Start a 25-minute Pomodoro session on a task | Persisted to PostgreSQL (`focus_sessions`). Survives bot restarts. |
| `/focus stop` | Stop timer and record actual focused hours | Adds exact elapsed time to task's `actual_hours`. |
| `/focus status` | Check remaining work/break time on active session | Displays end time in user's configured timezone. |

---

### 8. Gamification, Streaks & Leaderboards
> 📂 Cog Module: [`gamification/cog.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/gamification/cog.py)

| Command | Description | Details |
|---|---|---|
| `/streak` | Check your consecutive task completion streak | Updated daily upon task completion in user's local timezone. |
| `/habits` | View productivity summary and unlocked Badges | Tracks First Step, Consistency Champion, Speed Demon, Night Owl. |
| `/leaderboard` | View server leaderboard (shared tasks completed) | Filterable by `week` (last 7 days) or `month` (last 30 days). |

---

### 9. Templates & Routine Workflows
> 📂 Cog Module: [`routine_workflows/cog.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/routine_workflows/cog.py)

| Command | Description | Details |
|---|---|---|
| `/template create` | Create a reusable task template with subtasks & DoD checklist | Interactive modal with JSON/text checklist items. |
| `/template use` | Instantiate parent task, subtasks, and checklists in 1 click | Autocomplete template picker; calculates relative deadlines. |
| `/template list` | View available templates (Built-in, Server, Personal) | Shows built-in standard agile, bugfix, and onboarding templates. |
| `/template view` | Inspect template structure, subtasks, and checklist items | Displays relative day offsets and priority presets. |
| `/template delete` | Delete a custom task template | Custom templates only; built-ins are protected. |
| `/routine rule-add` | Set an auto-task assignment rule for Discord events | Trigger on `member_join` or `role_added`. |
| `/routine rule-list`| List active automated routine rules in this server | Shows trigger event, target role, and assigned template. |
| `/routine rule-remove`| Delete an automated routine rule | Requires server `manage_guild` permission. |

---

### 10. Full Text Search & AI-Ready Recommendations
> 📂 Cog Module: [`search_recommendation/cog.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/search_recommendation/cog.py)

| Command | Description | Options |
|---|---|---|
| `/search` | Advanced FTS search across titles, tags, and notes | `query`, `status`, `priority`, `sort`, `scope (personal/guild)` |
| `/recommend` | Multi-factor weighted prioritization ranking | `limit (1-10)`, `scope`, `preset (balanced/urgency/priority)` |

---

### 11. File Attachments
> 📂 Cog Module: [`storage/cog.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/storage/cog.py)

| Command | Description | Limits |
|---|---|---|
| `/attach` | Upload a file attachment to a task | Max 15 MB. Supported: images, PDF, Office docs, text, ZIP. |
| `/attachments` | Browse, download, or delete attachments on a task | Interactive gallery view with signed Supabase CDN URLs. |

---

### 12. Private Calendar Feeds
> 📂 Cog Module: [`calendar_feed/cog.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/calendar_feed/cog.py)

| Command | Description | Security |
|---|---|---|
| `/calendar link` | Generate private iCalendar (`.ics`) subscription URL | SHA-256 hashed secret token; HTTPS required. |
| `/calendar rotate` | Revoke compromised calendar link and generate new one | Instantly invalidates previous token. |
| `/calendar revoke` | Disable calendar subscription entirely | Deletes token record from database. |

---

### 13. Task Import
> 📂 Cog Module: [`task_import/cog.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/task_import/cog.py)

| Command | Description | Options |
|---|---|---|
| `/import` | Batch import tasks from UTF-8 CSV or JSON file | `file` (attachment), `missing_deadline (default_1_day / no_deadline)` |

---

### 14. Productivity Analytics (Supabase Edge)
> 📂 Cog Module: [`analytics/cog.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/analytics/cog.py)

| Command | Description | Engine |
|---|---|---|
| `/analytics snapshot` | Trigger on-demand visual productivity report to DM | Supabase Deno Edge Function + QuickChart graphic renderer |
| `/analytics weekly` | Toggle weekly automated DM report delivery | Edge Function cron job trigger |

---

### 15. Settings, i18n & Embed Themes
> 📂 Cog Module: [`handlers/settings_cog.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/handlers/settings_cog.py)

| Command | Description | Options |
|---|---|---|
| `/setup` | Configure personal timezone and alert channel | `timezone` (e.g. `Asia/Bangkok`, `UTC`, `America/New_York`) |
| `/lang` | Interactive language selector (9 languages) | Visual flag picker modal |
| `/theme` / `/settings theme` | **Personalize Discord embed color theme** | Select from 10 themes with live preview and custom gradient bars |
| `/category list\|add\|remove` | Manage custom task categories | Custom name and emoji selector |
| `/admin stats` | Bot-wide system telemetry (owner only) | Total users, tasks, cache metrics, rate limiter counters |
| `/admin cache_purge` | Manually purge expired cache entries (owner only) | Cleans LRU cache entries immediately |

---

### 16. System Monitoring & Health Telemetry
> 📂 Cog Module: [`handlers/monitoring_cog.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/handlers/monitoring_cog.py)

| Command | Description | Permission |
|---|---|---|
| `/health` | Check live database ping, latency, memory usage, uptime | Administrator |
| `/errors` | View top aggregated errors in the last 24 hours | Administrator |
| `/cmdstats` | View command execution volume since last restart | Administrator |
| `/monitoring setup` | Configure server admin alert channel and health check intervals | Administrator (Interactive Modal) |
| `/monitoring status` | Display current monitoring settings for this server | Administrator |

---

## 🎛️ Interactive UI & Defensive Design

### 5-Row Personal Task Action Panel (`TaskActionView`)

Every personal task embed features an interactive, defensive control panel:

```text
┌────────────────────────────────────────────────────────────────────────┐
│  🔴 #108 Deploy Production Microservices                               │
│  📅 Tomorrow at 18:30 (Asia/Bangkok) · ⏱️ in 22 hours                   │
│  📁 Category: DevOps · ⚡ Priority: P6 Critical · 📈 Progress: [████░░] 60%│
├────────────────────────────────────────────────────────────────────────┤
│  Row 0:  [ ✅ Mark Done ]   [ ✏️ Edit ]      [ 📍 Pin/Unpin ]  [ ➕ Subtask ] │
│  Row 1:  [ 🗑️ Delete ]      [ ⏰ Snooze ]    [ 📎 Files ]                    │
│  Row 2:  [ 🏷️ Select Category Dropdown (Work, Study, Health...)      ▼ ]│
│  Row 3:  [ ⚡ Select Priority Dropdown (P0 Normal ➔ P7 Emergency)    ▼ ]│
│  Row 4:  [ 📈 Progress ]   [ 💬 Comments ]  [ ☑️ Checklist ] [ 📜 History ] │
└────────────────────────────────────────────────────────────────────────┘
```

### Defensive Architecture Principles
1. **User Identity Isolation**: Every button, modal, and select checks `str(interaction.user.id) == view.uid`. Other users attempting to click buttons receive an ephemeral permission denial.
2. **Persistent View Hydration**: In `setup_hook()`, `register_all_persistent_views()` automatically binds active task IDs into memory. Buttons on historical messages continue working even after bot restarts.
3. **Optimistic Locking & Race Protection**: Status changes utilize SQL atomic queries (`UPDATE ... WHERE status='Pending' RETURNING task_id`) to prevent duplicate completions under concurrent clicks.
4. **DoD Checklist Guard**: Marking a task done via `/done` or the `✅ Mark Done` button warns the user if Definition of Done items remain unchecked, requiring an explicit bypass (`force: True`).

---

## ⚡ Performance, Caching & Scalability

### 1. True LRU Caching Engine (`core/database.py`)
All cache stores (`UserCache`, `StatsCache`, and `QueryCache`) utilize `collections.OrderedDict.move_to_end()` to provide O(1) **True Least-Recently-Used (LRU)** eviction:
* **Table-Scoped Invalidation**: Cache entries are tagged with table dependencies. A write to `tasks` invalidates only queries referencing `tasks`, while keeping cached user settings and categories intact across all **24 known tables** (`_KNOWN_TABLES`).
* **The 24 Tracked Tables**: `tasks`, `users`, `categories`, `projects`, `project_members`, `project_activity_log`, `task_attachments`, `task_assignments`, `guild_settings`, `audit_log`, `schema_version`, `task_completion_events`, `user_achievements`, `project_task_threads`, `project_task_dependencies`, `project_task_role_assignments`, `task_templates`, `task_checklists`, `routine_event_rules`, `project_role_permissions`, `saved_filters`, `focus_sessions`, `calendar_feed_tokens`, `task_comments`.
* **Minute-Quantized SQL Autocomplete**: Autocomplete queries truncate the current timestamp to minute boundaries, achieving >85% L1 cache hit rate while typing without sacrificing accuracy.
* **Tuple Hashing with JSON Fallback**: Cache keys utilize fast hashable parameter tuples with recursive JSON serialization for complex nested filters.

### 2. High-Throughput Bounded `BulkWriter`
Audit logging and metric writes are decoupled from the request cycle:
* **Bounded Queue**: Capped at `max_queue_size = 10,000` items with drop warnings to guarantee unbounded memory leaks never crash the bot under DDoS.
* **Chunked Transactions**: Flushes in batches of 50 items inside a single PostgreSQL transaction.
* **Per-Item Fallback & Retry Cap**: If a batch transaction fails, it gracefully falls back to single-row inserts and discards corrupted items exceeding `_MAX_ITEM_RETRIES = 5`.

### 3. Database Partial Indexes (Schema v27 & v28)
Background loops never scan full tables thanks to highly targeted partial indexes:
```sql
-- High-frequency scheduler indexes
CREATE INDEX idx_tasks_recurring_due ON tasks(deadline ASC)
    WHERE status='Pending' AND is_deleted=FALSE AND (recurring IS NOT NULL OR recurrence_rule IS NOT NULL);

CREATE INDEX idx_tasks_deadline_dm_pending ON tasks(deadline ASC, dm_reminded)
    WHERE status='Pending' AND is_deleted=FALSE;

CREATE INDEX idx_users_daily_digest ON users(daily_digest, notify_enabled)
    WHERE daily_digest = 1 AND notify_enabled = 1 AND channel_id IS NOT NULL;

CREATE INDEX idx_tasks_trash ON tasks(owner_id, deleted_at)
    WHERE is_deleted = TRUE;
```

---

## 🔄 Background Automation & Schedulers (8 Loops)

The bot operates **8 background loops** and continuous workers on the event loop:

| Loop / Worker | Frequency | Primary Responsibility | Defensive Guards |
|---|:---:|---|---|
| `reminder_loop` | 1 min | Send channel deadline warnings for approaching tasks | `last_reminder` debounce timestamp |
| `recurring_loop` | 1 min | Compute next deadline and renew recurring tasks | Partial index `idx_tasks_recurring_due` |
| `deadline_dm_loop` | 1 min | Dispatch private DMs at 24h, 3h, and 1h thresholds | Bitmask field `dm_reminded` (1, 2, 4) |
| `daily_digest_loop` | 1 min | Dispatch 8:00 AM Daily Digest in user's local timezone | `last_digest_date` guard persists across restarts |
| `weekly_retrospective_loop` | 1 min | Dispatch Sunday 20:00 Weekly Retrospective digest | Weekend UTC guard + `last_retrospective_date` |
| `cleanup_loop` | 24 hours | Purge audit logs >30d and **permanently purge trash >30d** | `recovery_service.purge_expired_trash(30)` |
| `session_loop` *(Focus)* | 15 sec | Progress work/break Pomodoro timers and alert user | Auto-stops if task completed or soft-deleted |
| `streak_reminder_loop` *(Gamification)* | 1 min | Send evening streak preservation reminders at 20:00 | Checks if tasks completed today in user TZ |
| `BulkWriter Worker` | 2.0 sec / 50 items | Flushes pending audit log batches to PostgreSQL | Bounded queue with retry exhaustion drop |
| `DashboardTracker Worker` | 1.5 sec | Debounces rapid task changes into a single embed edit | Cancel and reschedule debounce timer |

---

## 🛡️ Security & Row Level Security (RLS)

### 1. SQL & Script Injection Defense (`core/security.py`)
Incoming user input is filtered through `_SUSPICIOUS_RE`:
* Detects SQL injection chains (`; DROP`, `; SELECT`, `UNION SELECT`, `--`, `/*`) and cross-site scripting attacks (`<script`, `javascript:`, `onerror=`).
* Uses boundary-aware token matching to avoid false positives on legitimate task titles such as *"Select team lead"*, *"Drop off package"*, or *"Update documentation"*.

### 2. Thread-Safe Rate Limiter
In-memory sliding window rate limiter protects Discord API limits:
* `command`: 30 req/min
* `task_create`: 100 req/hour
* `search`: 10 req/min
* `export`: 5 req/day

### 3. PostgreSQL Row Level Security (RLS) Client
The `security_rls/` module enforces engine-level data privacy:
* All operations wrapped in `scoped_user_context(conn, user_id)` execute `SELECT set_config('app.current_user_id', $1, true)`.
* PostgreSQL engine evaluates `current_app_user() == owner_id`, guaranteeing cross-tenant data leakage is impossible even if application queries have bugs.
* Migration CLI runner:
  ```bash
  python -m security_rls.migration_runner --dry-run
  python -m security_rls.migration_runner --apply
  python -m security_rls.migration_runner --export
  python -m security_rls.migration_runner --rollback
  ```

---

## 🐘 Database Schema History (Auto-Migrations v1 ➔ v28)

The bot contains a built-in automated migration runner that verifies and migrates the PostgreSQL database sequentially on startup:

| Version | Scope & Added Tables / Columns | Purpose |
|:---:|---|---|
| **v1** | Core schema: `users`, `categories`, `tasks`, `audit_log`, `schema_version` | Foundational task management tables |
| **v2** | `tasks.parent_task_id`, `tasks.category_id` | Subtasks and categorization support |
| **v3** | `tasks.is_pinned`, `tasks.description` | Task pinning and extended descriptions |
| **v4** | `tasks.recurring`, `users.channel_id` | Recurrence strings and alert channel routing |
| **v5** | `tasks.tags`, `users.notify_enabled` | Tagging support and notification master toggle |
| **v6** | `task_comments`, `user_achievements`, `users.last_active` | Discussion comments, badges, and user telemetry |
| **v7** | `tasks.dm_reminded` | Bitmask tracking for 24h, 3h, and 1h DM notifications |
| **v8** | `users_lang_check` constraint | Expanded to 6 languages (`th`, `en`, `zh`, `ja`, `ko`, `es`) |
| **v9** | `users_lang_check` constraint | Expanded to 9 languages (`+ ru`, `fr`, `de`) |
| **v10** | `guild_settings` | Per-guild configuration overrides in database |
| **v11** | Composite PK fix on `guild_settings` | Multi-tenant guild settings stability |
| **v12** | `users.last_digest_date`, `users.digest_hour`, `tasks.completed_at` | Daily digest restart guard and productivity tracking |
| **v13** | `projects`, `project_members`, `project_activity_log`, `tasks.project_id`, `tasks.guild_id` | Team collaboration, shared projects, and multi-tenant scoping |
| **v14** | `task_attachments`, Supabase Realtime CDC publication (`supabase_realtime`) | File attachments and WebSocket live updates |
| **v15** | `tasks.search_vector` generated tsvector column + GIN index | PostgreSQL Full-Text Search (FTS) with weighted A/B/C/D ranking |
| **v16** | `users.weekly_digest`, `projects.lang` | Weekly summary toggles and project locale localization |
| **v17** | `projects.priority` (0–7), `projects.manual_progress` (0–100) | Project priority rankings and manual progress overrides |
| **v18** | `focus_sessions` table, `tasks.recurrence_rule` JSONB | Durable Pomodoro focus timers and advanced recurrence engine |
| **v19** | `task_completion_events`, `users.streak_last_completion`, `users.streak_reminder_date` | Timezone-aware streak tracking and audit completion events |
| **v20** | `tasks.source_message_url`, `project_task_threads` | Discord message context menus and discussion thread binding |
| **v21** | `project_task_dependencies`, `project_task_role_assignments` | Task dependency blocking and Discord role assignment |
| **v22** | `tasks.deadline` (DROP NOT NULL), `calendar_feed_tokens` table | Optional deadlines and private iCalendar feed subscriptions |
| **v23** | `task_templates`, `task_checklists`, `routine_event_rules` | Templates, Definition of Done checklists, and event-driven routines |
| **v24** | `tasks.is_deleted`, `tasks.deleted_at`, `tasks.is_private`, `project_role_permissions` | **Recycle Bin soft delete**, confidential tasks, and granular RBAC |
| **v25** | `saved_filters` table with JSONB criteria | **Eisenhower Matrix & Saved Smart Filters** (Smart Lists) |
| **v26** | `idx_audit_target_created`, `users.weekly_retrospective`, `users.last_retrospective_date` | Task Audit Trail speedups and Weekly Retrospective scheduler settings |
| **v27** | Partial indexes: `idx_tasks_recurring_due`, `idx_tasks_deadline_dm_pending`, `idx_tasks_pending_reminders`, `idx_focus_sessions_active_lookup` | **Performance & Stability Phase 1**: Zero-lag background schedulers |
| **v28** | Partial indexes: `idx_users_daily_digest`, `idx_users_weekly_retrospective`, `idx_users_streak_reminder`, `idx_tasks_user_active_root` | **Performance & Stability Phase 2**: Zero-lag user scans and active task queries |

---

## 🌩️ Supabase Realtime & Edge Functions

### 1. Supabase Realtime CDC (Change Data Capture)
* **Phoenix WebSocket Protocol**: Subscribes directly to PostgreSQL Write-Ahead Logs (WAL) via `realtime:public:tasks`.
* **Zero-Spam Debounce**: When multiple collaborators check off tasks rapidly, `DashboardTracker` coalesces changes within 1.5 seconds, executing a single Discord embed edit.
* **Auto-Reconnect**: Exponential backoff with jitter handles network interruptions gracefully.

### 2. Supabase Deno Edge Functions
* **Weekly Analytics Engine** (`supabase/functions/weekly-analytics/`):
  * Written in TypeScript for the Deno runtime.
  * Triggered on-demand via `/analytics snapshot` or weekly cron (`0 8 * * 1`).
  * Computes complex completion rates, generates visual PNG charts via QuickChart, and delivers rich embeds directly to user DMs.

---

## 📅 Private Calendar Feeds & Async Webserver

The bot runs a non-blocking `aiohttp` web server on the main event loop (`utils/webserver.py`):

```text
GET /                       -> 200 JSON {"status": "online", "uptime_s": 1420.5}
GET /health                 -> 200 JSON {"status": "ok"}
GET /ready                  -> 200/503 Readiness probe (checks live PostgreSQL pool connection)
GET /metrics                -> 200 JSON Internal telemetry (DB pool, cache sizes, BulkWriter stats)
GET /calendar/{token}.ics   -> 200 text/calendar (Live private iCalendar feed for external calendars)
```

### Calendar Sync Setup
1. Run `/calendar link` in Discord to receive your unique feed URL.
2. In **Google Calendar**, select **Other calendars (+)** ➔ **From URL** ➔ Paste the link.
3. In **Apple Calendar / Outlook**, select **File** ➔ **New Calendar Subscription**.
4. Deadlines, priority tags, and task names sync automatically.

---

## 🚀 Installation & Deployment Guide

### Prerequisites
* Python 3.11+
* A Supabase project (Free or Pro tier) with PostgreSQL
* A Discord Bot Application with `applications.commands` and `bot` scopes (Intents: Server Members, Message Content)

### 1. Clone & Dependencies
```bash
git clone https://github.com/Punk1107/todo-list-bot-gen2.git
cd todo-list-bot-gen2

python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure Environment
```bash
cp .env.example .env
# Edit .env with your credentials (see section below)
```

### 3. Initialize Database & RLS
The database schema automatically runs all **28 migrations** on first startup! To apply PostgreSQL Row Level Security policies:
```bash
python -m security_rls.migration_runner --apply
```

### 4. Deploy Deno Edge Function (Optional)
```bash
cd supabase
supabase secrets set DISCORD_BOT_TOKEN="your_discord_bot_token"
supabase functions deploy weekly-analytics
```

### 5. Launch the Bot
```bash
python main.py
```

---

## ⚙️ Environment Variables Reference

| Variable | Required | Default | Description |
|---|:---:|:---:|---|
| `DISCORD_TOKEN` | **Yes** | — | Discord Bot Token from Developer Portal |
| `DATABASE_PATH` | **Yes** | — | PostgreSQL connection URI (`postgresql://postgres:...@...:5432/postgres`) |
| `DB_POOL_SIZE` | No | `5` | Asyncpg connection pool size |
| `DB_TIMEOUT` | No | `30` | Query timeout in seconds |
| `DB_QUERY_CACHE_TTL` | No | `30.0` | L1 QueryCache expiration time in seconds (0 = disabled) |
| `DB_BULK_WRITE_INTERVAL_MS`| No | `500` | BulkWriter flush interval in milliseconds |
| `BOT_OWNER_IDS` | No | — | Comma-separated Discord user IDs with bot owner access |
| `RATE_COMMANDS_PER_MIN` | No | `30` | Max commands per minute per user before rate limiting |
| `RATE_TASKS_PER_HOUR` | No | `100` | Max tasks created per hour per user |
| `RATE_SEARCHES_PER_MIN` | No | `10` | Max searches per minute per user |
| `RATE_EXPORTS_PER_DAY` | No | `5` | Max task exports per day per user |
| `RATE_BLOCK_SECONDS` | No | `300` | Duration (seconds) a user is temporarily blocked upon abuse |
| `REMINDER_INTERVAL_MIN` | No | `30` | Interval (minutes) for deadline approaching checks |
| `RECURRING_INTERVAL_MIN`| No | `60` | Interval (minutes) for renewing recurring tasks |
| `OVERDUE_REMIND_HOURS` | No | `6` | Frequency (hours) to re-notify about overdue tasks |
| `DM_REMINDER_INTERVAL_MIN`| No | `15` | Interval (minutes) for 24h, 3h, and 1h deadline DM checks |
| `SUPABASE_URL` | **Yes** | — | Supabase REST URL (`https://xyz.supabase.co`) |
| `SUPABASE_KEY` | **Yes** | — | Supabase `service_role` secret key |
| `SUPABASE_REALTIME_ENABLED`| No | `true` | Enable Supabase Realtime WebSocket listener |
| `SUPABASE_REALTIME_HEARTBEAT_SEC`| No | `30` | Realtime Phoenix WebSocket heartbeat frequency |
| `SUPABASE_REALTIME_DEBOUNCE_SEC`| No | `1.5` | Dashboard update debounce delay in seconds |
| `SUPABASE_STORAGE_ENABLED` | No | `true` | Enable task file attachments feature |
| `SUPABASE_STORAGE_BUCKET`  | No | `task-attachments`| Supabase Storage bucket name |
| `MAX_ATTACHMENT_SIZE_MB`   | No | `15` | Maximum allowed attachment size in megabytes |
| `SUPABASE_STORAGE_ALLOWED_EXT`| No | `png,jpg,pdf...` | Comma-separated list of allowed file extensions |
| `WEBSERVER_ENABLED` | No | `true` | Enable aiohttp async keep-alive web server |
| `WEBSERVER_HOST` | No | `0.0.0.0` | Web server bind IP |
| `WEBSERVER_PORT` | No | `8080` | Web server listening port |
| `CALENDAR_PUBLIC_URL` | No | — | Public HTTPS base URL for iCal feeds (`https://todo.example.com`) |
| `MONITORING_ENABLED` | No | `true` | Master toggle for health & error telemetry |
| `ADMIN_LOG_CHANNEL_ID` | No | — | Discord Channel ID for critical admin alerts |
| `HEALTH_CHECK_INTERVAL_MIN`| No | `5` | Interval (minutes) for automated health checks |
| `ALERT_RATE_LIMIT_SEC` | No | `300` | Rate limit cooldown (seconds) between repeated error alerts |
| `DEFAULT_TIMEZONE` | No | `Asia/Bangkok` | Default timezone for new users |
| `DEFAULT_LANG` | No | `th` | Fallback language (`th`, `en`, `zh`, `ja`, etc.) |

---

## 🧪 Test Suite & Quality Assurance (18 Modules)

The test suite consists of **18 test modules** guaranteeing zero regressions across all features:

```bash
pytest tests/ -v
```

| Test Suite Module | Coverage Area |
|---|---|
| [`tests/test_perf_stability_2.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/tests/test_perf_stability_2.py) | True LRU cache eviction, SQL split parsing, autocomplete minute-quantization, BulkWriter retry exhaustion, recurrence DST, Recycle Bin soft delete/restore, Saved Filters, Eisenhower Matrix, Retrospective data, and HTML export. |
| [`tests/test_rls_policies.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/tests/test_rls_policies.py) | Row Level Security SQL script parsing, scoped session contextvars, and cross-user tenant isolation. |
| [`tests/test_search_recommendation.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/tests/test_search_recommendation.py) | Full-Text Search tsvector rank calculations, sanitize query filters, and composite priority recommendation scoring. |
| [`tests/test_discord_native.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/tests/test_discord_native.py) | Message context menu registration (`Add to To-Do`), source message jump links, task thread creation, and bulk views. |
| [`tests/test_routine_workflows.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/tests/test_routine_workflows.py) | Template creation, relative deadline instantiation, Definition of Done checklists, and role assignment routine rules. |
| [`tests/test_collaboration_scope.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/tests/test_collaboration_scope.py) | Project RBAC permissions, personal vs project data boundaries, role assignments, and private task filtering. |
| [`tests/test_conflict_resolution.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/tests/test_conflict_resolution.py) | Defensive deadline validation, concurrent status change optimistic locking, and circular dependency detection. |
| [`tests/test_recurrence_rules.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/tests/test_recurrence_rules.py) | Weekdays rules, day/week interval rules, monthly dates with short month clamping (Feb 28/29), and JSONB decoding. |
| [`tests/test_realtime.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/tests/test_realtime.py) | Phoenix WebSocket protocol client, CDC event dispatching, and DashboardTracker debounce timing. |
| [`tests/test_storage.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/tests/test_storage.py) | File size limits, extension whitelisting, upload path hashing, and TaskAttachment models. |
| [`tests/test_focus_mode.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/tests/test_focus_mode.py) | Pomodoro timer intervals (25/5 min), elapsed time capping, session state transitions, and auto-halt on task deletion. |
| [`tests/test_gamification.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/tests/test_gamification.py) | Timezone-aware streak updates, badge awards, evening reminder claim locks, and guild leaderboards. |
| [`tests/test_analytics.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/tests/test_analytics.py) | Edge Function HTTP caller, productivity score formula, and QuickChart URL construction. |
| [`tests/test_date_parser_i18n.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/tests/test_date_parser_i18n.py) | Natural language date parsing across all 9 languages (BE dates, Kanji/Hangul formats, relative deltas). |
| [`tests/test_locales.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/tests/test_locales.py) | Key completeness across all JSON translation files and parameter interpolation integrity. |
| [`tests/test_reminders.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/tests/test_reminders.py) | PostgreSQL parameter typing and asyncpg codec compatibility across reminder loops. |
| [`tests/test_sql_split.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/tests/test_sql_split.py) | SQL migration statement tokenizer handling quoted strings and dollar-quoted blocks (`DO $$ ... $$`). |
| [`tests/test_ux_improvements.py`](file:///c:/Users/User/Documents/to%20do%20list%20bot%20gen%202/tests/test_ux_improvements.py) | Visual checklist rendering, relative parser shortcuts (`+2h`, `+3d`), and dropdown select components. |

---

## 📂 Project File Structure Tree

```text
to do list bot gen 2/
├── main.py                         # App entrypoint, TodoBot class, Cog loading, lifecycle hooks
├── requirements.txt                # Production dependencies
├── .env.example                    # Template environment variables
├── README.md                       # Comprehensive documentation
│
├── core/                           # Foundation Layer
│   ├── config.py                   # Dataclass settings loaded from environment
│   ├── database.py                 # Schema v28 engine, True LRU Caches, Bounded BulkWriter
│   ├── security.py                 # RateLimiter, InputValidator, SQL/XSS regex filter
│   └── theme.py                    # 10 Curated Embed Color Themes & Progress Bar generator
│
├── handlers/                       # Core Command Cogs & UI Handlers
│   ├── tasks_cog.py                # Personal tasks, FTS, /task-stats, /digest, /export, Context Menu
│   ├── task_views.py               # TaskActionView 5-row layout, Modals, Category & Priority dropdowns
│   ├── reminders_cog.py            # 6 Background loops: reminders, recurring, digest, retrospectives
│   ├── settings_cog.py             # /setup, /lang, /theme, /category, /admin stats & cache_purge
│   └── monitoring_cog.py           # /health, /errors, /cmdstats, /monitoring setup & status
│
├── recovery/                       # Safe Recovery & Recycle Bin (Cog #15)
│   ├── cog.py                      # /trash, /restore slash commands
│   ├── models.py                   # DeletedTask, TrashQuery models
│   ├── service.py                  # Soft delete, cascading recovery, 30-day purge logic
│   └── views.py                    # TrashPaginationView with restore/permanent delete controls
│
├── organization/                   # Eisenhower Matrix & Smart Lists (Cog #16)
│   ├── cog.py                      # /matrix, /filter save|list|use|delete slash commands
│   ├── models.py                   # SavedFilter, EisenhowerQuadrant, MatrixData models
│   ├── service.py                  # Quadrant evaluation engine & JSONB filter query builder
│   └── views.py                    # EisenhowerMatrixView with quadrant drill-down quick actions
│
├── history_reporting/              # Audit Trail & Weekly Retrospective (Cog #17)
│   ├── cog.py                      # /history, /retrospective slash commands
│   ├── models.py                   # TaskHistoryRecord, WeeklyRetrospectiveData models
│   ├── service.py                  # Audit timeline parser, retrospective metrics, HTML exporter
│   └── views.py                    # TaskHistoryView, WeeklyRetrospectiveView
│
├── collaboration/                  # Team Shared Projects (Cog #6)
│   ├── cog.py                      # /project command group (19 slash commands)
│   ├── models.py                   # Project, ProjectMember, ProjectTask, RolePermissions models
│   ├── service.py                  # RBAC engine, dependencies, private tasks, activity log
│   └── views.py                    # ProjectPermissionsView, Kanban boards, ProjectDashboardView
│
├── routine_workflows/              # Task Templates & Auto-Routines (Cog #14)
│   ├── cog.py                      # /template and /routine slash command groups, Discord event listeners
│   ├── models.py                   # TaskTemplate, RoutineRule models
│   ├── service.py                  # Template instantiation & event-driven rule matching
│   └── views.py                    # TemplateCreateModal, RoutineRuleView
│
├── discord_native/                 # Native Discord Interactions (Cog #11)
│   └── bulk_cog.py                 # /bulk done|snooze|delete multi-select actions & BulkTaskView
│
├── focus/                          # Pomodoro Timer (Cog #2)
│   └── cog.py                      # /focus start|stop|status and 15s session_loop scheduler
│
├── gamification/                   # Streaks & Achievements (Cog #10)
│   ├── cog.py                      # /streak, /habits, /leaderboard and streak_reminder_loop
│   └── service.py                  # Streak calculations, badge rules, and guild rankings
│
├── search_recommendation/          # FTS Search & AI Prioritization (Cog #8)
│   ├── cog.py                      # /search and /recommend commands
│   ├── service.py                  # Composite scoring engine (Urgency + Priority + Age)
│   └── views.py                    # SearchResultsView, RecommendationView
│
├── storage/                        # Supabase File Attachments (Cog #7)
│   ├── cog.py                      # /attach and /attachments commands
│   ├── service.py                  # Storage validation (15MB cap, allowed extensions)
│   └── views.py                    # TaskAttachmentsView gallery
│
├── calendar_feed/                  # iCalendar Subscription Sync (Cog #12)
│   ├── cog.py                      # /calendar link|rotate|revoke commands
│   └── service.py                  # SHA-256 token hashing & .ics VCALENDAR generation
│
├── task_import/                    # CSV/JSON Batch Import (Cog #13)
│   ├── cog.py                      # /import command
│   └── service.py                  # Multi-format task parser & batch validation
│
├── analytics/                      # Supabase Deno Edge Caller (Cog #9)
│   ├── cog.py                      # /analytics snapshot & /analytics weekly
│   └── client.py                   # Async HTTP client for Supabase Edge Functions
│
├── task_features/                  # Task Subsystems (Comments, Progress %, DoD)
│   ├── models.py                   # TaskComment, TaskProgress, ChecklistItem models
│   ├── service.py                  # Access validation & checklist state transitions
│   └── views.py                    # Modals and interactive checklist toggles
│
├── recurrence/                     # Extended Recurrence Engine
│   └── rules.py                    # Weekdays, intervals, monthly dates calculation & JSONB decoding
│
├── realtime/                       # Supabase Realtime CDC Listener
│   ├── client.py                   # Phoenix WebSocket client over aiohttp
│   ├── dispatcher.py               # CDC postgres_changes event router
│   └── dashboard_tracker.py        # Live dashboard message updater with 1.5s debounce
│
├── security_rls/                   # PostgreSQL Row Level Security
│   ├── client.py                   # RLS-enforced database client adapter
│   ├── context.py                  # Scoped user session context manager
│   ├── migration_runner.py         # CLI tool for RLS migrations (--dry-run/apply/rollback)
│   └── sql/                        # Versioned RLS policy SQL files
│
├── monitoring/                     # Admin Health & Telemetry Subsystem
│   ├── health_monitor.py           # Periodic resource checks (DB ping, memory, lag)
│   ├── error_tracker.py            # 24-hour error frequency aggregator
│   └── alert_dispatcher.py         # Rate-limited admin alert channel dispatcher
│
├── utils/                          # Shared Utility Helpers
│   ├── helpers.py                  # parse_deadline() 9-language NLP engine, embed builders
│   ├── date_parser.py              # Multilingual date normalization
│   ├── conflict_resolver.py        # Concurrency safety & deadline defensive checks
│   └── webserver.py                # Async keep-alive server (/metrics, /ready, /calendar.ics)
│
├── locales/                        # Internationalization (i18n)
│   ├── i18n.py                     # Translation loader & fallback manager
│   ├── th.json                     # Thai translations
│   ├── en.json                     # English translations
│   ├── zh.json                     # Chinese translations
│   ├── ja.json                     # Japanese translations
│   ├── ko.json                     # Korean translations
│   ├── es.json                     # Spanish translations
│   ├── ru.json                     # Russian translations
│   ├── fr.json                     # French translations
│   └── de.json                     # German translations
│
├── supabase/                       # Supabase Edge Functions
│   └── functions/weekly-analytics/ # Deno TypeScript Edge Function with QuickChart
│
└── tests/                          # 18 Automated Test Modules (pytest)
    ├── test_analytics.py           # Deno Edge Function client & scoring
    ├── test_collaboration_scope.py # Project permissions, RBAC & private tasks
    ├── test_conflict_resolution.py # Optimistic locking & cyclic dependency checks
    ├── test_date_parser_i18n.py    # 9-language NLP date engine (BE, Kanji, deltas)
    ├── test_discord_native.py      # Context menus, threads & bulk actions
    ├── test_focus_mode.py          # Pomodoro timers & auto-halt on delete
    ├── test_gamification.py        # Streaks, badges & guild leaderboards
    ├── test_locales.py             # Translation key completeness (9 languages)
    ├── test_perf_stability_2.py    # LRU caches, SQL splits, Recycle Bin, Filters, HTML export
    ├── test_realtime.py            # Phoenix WS Realtime & debounced updates
    ├── test_recurrence_rules.py    # Weekdays, intervals, monthly clamping & JSONB
    ├── test_reminders.py           # Reminder query typing & asyncpg codecs
    ├── test_rls_policies.py        # Row Level Security isolation policies
    ├── test_routine_workflows.py   # Templates, DoD checklists & routine automations
    ├── test_search_recommendation.py # PostgreSQL FTS tsvector & AI scoring
    ├── test_sql_split.py           # SQL tokenizer for multi-statement migrations
    ├── test_storage.py             # File size limits & attachment models
    └── test_ux_improvements.py     # Checklists, dropdowns & relative syntax
```

---

## 📄 License

This project is licensed under the **MIT License**.

---

<div align="center">

**📝 To-Do List Discord Bot Gen 4.0**

*Engineered for teams who take productivity, reliability, and speed seriously.*

[Report a Bug](https://github.com/Punk1107/todo-list-bot-gen2/issues) · [Request a Feature](https://github.com/Punk1107/todo-list-bot-gen2/issues)

</div>

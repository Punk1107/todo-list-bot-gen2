"""
English (EN) language strings
"""

STRINGS = {
    # ─── General ───────────────────────────────────────────────────────────────
    "lang_name": "English",
    "lang_flag": "🇬🇧",
    "yes": "Yes",
    "no": "No",
    "cancel": "Cancel",
    "confirm": "Confirm",
    "success": "Success",
    "error": "Error",
    "warning": "Warning",
    "loading": "Loading...",
    "not_found": "Not Found",
    "permission_denied": "❌ You do not have permission to use this command",
    "bot_name": "📝 To-Do List Bot Gen 2",
    "footer_text": "To-Do List Bot Gen 2 • Built for maximum productivity",

    # ─── Rate Limiting ──────────────────────────────────────────────────────────
    "rate_limited": "⏳ You are sending commands too fast. Please wait **{seconds:.0f} seconds** and try again.",
    "task_rate_limited": "⏳ You have exceeded the task creation limit ({limit}/hour). Please wait **{seconds:.0f} seconds**.",

    # ─── Setup ─────────────────────────────────────────────────────────────────
    "setup_title": "⚙️ Bot Setup",
    "setup_desc": "Configure the following settings to get started.",
    "setup_timezone": "Timezone",
    "setup_timezone_desc": "Example: Asia/Bangkok, UTC, America/New_York",
    "setup_success": "✅ Setup complete! Timezone: **{tz}** | Channel: {channel}",
    "setup_invalid_tz": "❌ Invalid timezone `{tz}`. Please check and try again.\n[Full timezone list](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)",
    "setup_channel_required": "❌ Please use this command in a Discord channel.",

    # ─── Language ──────────────────────────────────────────────────────────────
    "lang_changed": "✅ Language changed to **English** successfully.",
    "lang_select_title": "🌐 Select Language / เลือกภาษา",
    "lang_select_desc": "Choose your preferred language.",

    # ─── Task Creation ──────────────────────────────────────────────────────────
    "task_add_title": "➕ Add New Task",
    "task_name_label": "Task Name",
    "task_name_placeholder": "e.g. Submit report, Team meeting",
    "task_deadline_label": "Deadline (DD/MM/YYYY HH:MM)",
    "task_deadline_placeholder": "e.g. 25/12/2025 18:00",
    "task_priority_label": "⚡ Priority",
    "task_priority_placeholder": "0–7  (0=Normal, 3=Medium, 5=Important, 7=Critical)",
    "task_desc_label": "Description (optional)",
    "task_desc_placeholder": "Additional details...",
    "task_tags_label": "Tags (optional)",
    "task_tags_placeholder": "e.g. work, urgent, home",
    "task_created": "✅ Task created successfully! ID: **#{task_id}**",
    "task_invalid_deadline": "❌ Invalid date format. Please use: `DD/MM/YYYY HH:MM`\nExample: `25/12/2025 18:00`",
    "task_past_deadline": "❌ Deadline must be in the future.",
    "task_invalid_priority": "❌ Priority must be a number between 0 and 7.",
    "task_name_too_long": "❌ Task name is too long (max 200 characters).",
    "task_desc_too_long": "❌ Description is too long (max 1000 characters).",

    # ─── Task List ──────────────────────────────────────────────────────────────
    "tasks_title": "📋 Your Tasks",
    "tasks_empty": "📭 No tasks yet.\nPress **`/add`** to create your first task!",
    "tasks_page": "Page {page}/{total}",
    "tasks_total": "Total tasks: **{count}**",
    "tasks_filter_pending": "⏳ Pending",
    "tasks_filter_Pending": "⏳ Pending",
    "tasks_filter_done": "✅ Done",
    "tasks_filter_Completed": "✅ Completed",
    "tasks_filter_cancelled": "❌ Cancelled",
    "tasks_filter_Cancelled": "❌ Cancelled",
    "tasks_filter_all": "📋 All",
    "tasks_filter_today": "📅 Today",
    "tasks_filter_overdue": "🚨 Overdue",
    "tasks_filter_pinned": "📌 Pinned",
    "list_filter_placeholder": "🔽 Filter by status...",

    # ─── Task Details ───────────────────────────────────────────────────────────
    "task_detail_title": "📌 Task Detail #{task_id}",
    "task_detail_name": "📝 Task Name",
    "task_detail_status": "🔖 Status",
    "task_detail_deadline": "📅 Deadline",
    "task_detail_priority": "⚡ Priority",
    "task_detail_category": "🏷️ Category",
    "task_detail_tags": "🔖 Tags",
    "task_detail_desc": "📄 Description",
    "task_detail_recurring": "🔄 Recurring",
    "task_detail_subtasks": "📊 Subtasks",
    "task_detail_created": "📆 Created",
    "task_detail_updated": "🔄 Last Updated",
    "task_not_found": "❌ Task #**{task_id}** not found.",
    "task_not_owned": "❌ This task does not belong to you.",

    # ─── Task Actions ───────────────────────────────────────────────────────────
    "btn_done": "✅ Mark Done",
    "btn_delete": "🗑️ Delete",
    "btn_edit": "✏️ Edit",
    "btn_subtask": "➕ Subtask",
    "btn_prev": "◀ Prev",
    "btn_next": "Next ▶",
    "btn_refresh": "🔄 Refresh",
    "btn_back": "🔙 Back",
    "btn_confirm_delete": "🗑️ Confirm Delete",

    "task_marked_done": "✅ Task **#{task_id}** marked as done!",
    "task_already_done": "⚠️ This task is already completed.",
    "task_already_cancelled": "⚠️ This task is already cancelled.",
    "task_deleted": "🗑️ Task **#{task_id}** has been deleted.",
    "task_delete_confirm": "⚠️ Are you sure you want to delete this task?\n> **{task_name}**\nThis action cannot be undone.",

    # ─── Pin / Unpin ────────────────────────────────────────────────────────────
    "task_pinned": "📌 Task **#{task_id}** pinned successfully.",
    "task_unpinned": "📌 Task **#{task_id}** unpinned.",

    # ─── Task Edit ──────────────────────────────────────────────────────────────
    "task_edit_title": "✏️ Edit Task #{task_id}",
    "task_edit_success": "✅ Task updated successfully.",

    # ─── Subtasks ──────────────────────────────────────────────────────────────
    "subtask_add_title": "➕ Add Subtask",
    "subtask_for": "For Task: **{parent_name}**",
    "subtask_created": "✅ Subtask created successfully!",
    "subtask_no_nested": "⚠️ You cannot add a subtask to another subtask.",
    "subtask_progress": "Subtasks: {done}/{total} ({pct:.0f}%)",

    # ─── Categories ─────────────────────────────────────────────────────────────
    "cat_title": "🏷️ Categories",
    "cat_list_title": "📂 All Categories",
    "cat_empty": "No categories yet.",
    "cat_add_title": "➕ Add New Category",
    "cat_name_label": "Category Name",
    "cat_emoji_label": "Emoji (optional)",
    "cat_created": "✅ Category **{name}** created!",
    "cat_not_found": "❌ Category not found.",

    # ─── Priority Labels ─────────────────────────────────────────────────
    "priority_0": "⬜ Normal",
    "priority_1": "🟦 Low",
    "priority_2": "🟩 Medium-Low",
    "priority_3": "🟨 Medium",
    "priority_4": "🟧 Medium-High",
    "priority_5": "🟥 Important",
    "priority_6": "🔴 Urgent",
    "priority_7": "🆘 Critical",
    # Dropdown descriptions
    "priority_0_desc": "Not time-sensitive, do whenever",
    "priority_1_desc": "Low urgency, can wait",
    "priority_2_desc": "Handle within this week",
    "priority_3_desc": "Do within the next couple of days",
    "priority_4_desc": "Important, must do today or tomorrow",
    "priority_5_desc": "Urgent! Act within a few hours",
    "priority_6_desc": "Very urgent! Act immediately",
    "priority_7_desc": "Critical! Major impact, fix right now",
    # Dropdown UI strings
    "priority_select_placeholder": "⚡ Select priority level...",
    "priority_select_title": "⚡ Select Priority",
    "priority_select_desc": "Choose the priority level before filling in task details.",
    "priority_changed": "✅ Priority updated! Task **#{task_id}** is now **{priority}**",
    # Legacy aliases (kept for backward compat)
    "priority_low": "⬜ Normal",
    "priority_medium": "🟨 Medium",
    "priority_high": "🔴 Urgent",

    # ─── Status Labels ──────────────────────────────────────────────────────────
    "status_pending": "⏳ Pending",
    "status_completed": "✅ Completed",
    "status_cancelled": "❌ Cancelled",
    "status_overdue": "🚨 Overdue",

    # ─── Recurring ──────────────────────────────────────────────────────────────
    "recurring_daily": "🔄 Daily",
    "recurring_weekly": "🔄 Weekly",
    "recurring_monthly": "🔄 Monthly",
    "recurring_none": "—",

    # ─── Reminders ──────────────────────────────────────────────────────────────
    "reminder_title": "⏰ Task Reminder",
    "reminder_overdue": "🚨 **Task Overdue!**\n`{task}` was due on {deadline}",
    "reminder_due_soon": "⚡ **Task Due Soon!**\n`{task}` is due in {time_left}",
    "reminder_due_today": "📅 **Task Due Today!**\n`{task}` is due at {time}",

    # ─── Export ─────────────────────────────────────────────────────────────────
    "export_success": "📤 Export complete! File: `{filename}`",
    "export_empty": "📭 No data to export.",
    "export_rate_limited": "⏳ You have exceeded the export limit ({limit}/day). Try again tomorrow.",

    # ─── Search ─────────────────────────────────────────────────────────────────
    "search_title": "🔍 Search Results: `{query}`",
    "search_empty": "🔍 No tasks matching `{query}` found.",
    "search_query_label": "Search Query",
    "search_query_placeholder": "Type task name or tag...",

    # ─── Stats ──────────────────────────────────────────────────────────────────
    "stats_title": "📊 Your Statistics",
    "stats_total": "Total Tasks",
    "stats_completed": "Completed",
    "stats_pending": "Pending",
    "stats_overdue": "Overdue",
    "stats_completion_rate": "Completion Rate",
    "stats_categories": "Categories Used",

    # ─── Help ───────────────────────────────────────────────────────────────────
    "help_title": "📖 To-Do List Bot Gen 2 — Help",
    "help_desc": "A full-featured To-Do List bot with Thai & English support.",
    "help_commands": "All Commands",
    "help_add": "Add a new task",
    "help_list": "View all tasks",
    "help_done": "Mark a task as done",
    "help_delete": "Delete a task",
    "help_edit": "Edit a task",
    "help_search": "Search tasks",
    "help_categories": "Manage categories",
    "help_stats": "View your statistics",
    "help_export": "Export tasks as CSV",
    "help_setup": "Configure the bot",
    "help_lang": "Change language",
    "help_reminder": "Set reminders",

    # ─── Errors ─────────────────────────────────────────────────────────────────
    "err_generic": "❌ An error occurred. Please try again.",
    "err_db": "❌ A database error occurred. Please contact an administrator.",
    "err_no_setup": "⚠️ Please configure the bot first using `/setup`.",
    "err_input_invalid": "❌ Invalid input: {detail}",
    "err_suspicious": "🚫 Suspicious behaviour detected. Command blocked.",
}

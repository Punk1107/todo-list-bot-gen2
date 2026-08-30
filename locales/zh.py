"""
Chinese Simplified (ZH) language strings — 简体中文
"""

STRINGS = {
    # ─── General ───────────────────────────────────────────────────────────────
    "lang_name": "简体中文",
    "lang_flag": "🇨🇳",
    "yes": "是",
    "no": "否",
    "cancel": "取消",
    "confirm": "确认",
    "success": "成功",
    "error": "错误",
    "warning": "警告",
    "loading": "加载中...",
    "not_found": "未找到",
    "permission_denied": "❌ 您没有权限使用此命令",
    "bot_name": "📝 To-Do List Bot Gen 2",
    "footer_text": "To-Do List Bot Gen 2 • 为最高生产力而生",

    # ─── Rate Limiting ──────────────────────────────────────────────────────────
    "rate_limited": "⏳ 您发送命令的速度过快，请等待 **{seconds:.0f} 秒** 后重试。",
    "task_rate_limited": "⏳ 您超过了任务创建限制（{limit}/小时），请等待 **{seconds:.0f} 秒**。",

    # ─── Setup ─────────────────────────────────────────────────────────────────
    "setup_title": "⚙️ 机器人设置",
    "setup_desc": "请配置以下设置以开始使用。",
    "setup_timezone": "时区",
    "setup_timezone_desc": "例如：Asia/Bangkok、UTC、America/New_York",
    "setup_success": "✅ 设置完成！时区：**{tz}** | 频道：{channel}",
    "setup_invalid_tz": "❌ 时区 `{tz}` 无效，请检查后重试。\n[完整时区列表](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)",
    "setup_channel_required": "❌ 请在 Discord 频道中使用此命令。",

    # ─── Language ──────────────────────────────────────────────────────────────
    "lang_changed": "✅ 语言已更改为 **简体中文**。",
    "lang_select_title": "🌐 选择语言 / Select Language",
    "lang_select_desc": "请选择您偏好的语言。",

    # ─── Task Creation ──────────────────────────────────────────────────────────
    "task_add_title": "➕ 添加新任务",
    "task_name_label": "任务名称",
    "task_name_placeholder": "例如：提交报告、团队会议",
    "task_deadline_label": "截止日期（日/月/年 时:分）",
    "task_deadline_placeholder": "例如：25/12/2025 18:00",
    "task_priority_label": "⚡ 优先级",
    "task_priority_placeholder": "0–7（0=普通，3=中等，5=重要，7=紧急）",
    "task_desc_label": "描述（可选）",
    "task_desc_placeholder": "添加更多详情...",
    "task_tags_label": "标签（可选）",
    "task_tags_placeholder": "例如：工作、紧急、家庭",
    "task_created": "✅ 任务创建成功！ID：**#{task_id}**",
    "task_invalid_deadline": "❌ 日期格式无效，请使用：`日/月/年 时:分`\n示例：`25/12/2025 18:00`",
    "task_past_deadline": "❌ 截止日期必须在将来。",
    "task_invalid_priority": "❌ 优先级必须是 0 到 7 之间的数字。",
    "task_name_too_long": "❌ 任务名称过长（最多 200 个字符）。",
    "task_desc_too_long": "❌ 描述过长（最多 1000 个字符）。",

    # ─── Task List ──────────────────────────────────────────────────────────────
    "tasks_title": "📋 您的任务",
    "tasks_empty": "📭 暂无任务。\n按 **`/add`** 创建您的第一个任务！",
    "tasks_page": "第 {page}/{total} 页",
    "tasks_total": "总任务数：**{count}**",
    "tasks_filter_pending": "⏳ 待处理",
    "tasks_filter_Pending": "⏳ 待处理",
    "tasks_filter_done": "✅ 已完成",
    "tasks_filter_Completed": "✅ 已完成",
    "tasks_filter_cancelled": "❌ 已取消",
    "tasks_filter_Cancelled": "❌ 已取消",
    "tasks_filter_all": "📋 全部",
    "tasks_filter_today": "📅 今天",
    "tasks_filter_overdue": "🚨 已逾期",
    "tasks_filter_pinned": "📌 已固定",
    "list_filter_placeholder": "🔽 按状态筛选...",

    # ─── Task Details ───────────────────────────────────────────────────────────
    "task_detail_title": "📌 任务详情 #{task_id}",
    "task_detail_name": "📝 任务名称",
    "task_detail_status": "🔖 状态",
    "task_detail_deadline": "📅 截止日期",
    "task_detail_priority": "⚡ 优先级",
    "task_detail_category": "🏷️ 分类",
    "task_detail_tags": "🔖 标签",
    "task_detail_desc": "📄 描述",
    "task_detail_recurring": "🔄 重复",
    "task_detail_subtasks": "📊 子任务",
    "task_detail_created": "📆 创建时间",
    "task_detail_updated": "🔄 最后更新",
    "task_not_found": "❌ 任务 #**{task_id}** 未找到。",
    "task_not_owned": "❌ 此任务不属于您。",

    # ─── Task Actions ───────────────────────────────────────────────────────────
    "btn_done": "✅ 标记完成",
    "btn_delete": "🗑️ 删除",
    "btn_edit": "✏️ 编辑",
    "btn_subtask": "➕ 子任务",
    "btn_prev": "◀ 上一页",
    "btn_next": "下一页 ▶",
    "btn_refresh": "🔄 刷新",
    "btn_back": "🔙 返回",
    "btn_confirm_delete": "🗑️ 确认删除",

    "task_marked_done": "✅ 任务 **#{task_id}** 已标记为完成！",
    "task_already_done": "⚠️ 此任务已经完成。",
    "task_already_cancelled": "⚠️ 此任务已经取消。",
    "task_deleted": "🗑️ 任务 **#{task_id}** 已删除。",
    "task_delete_confirm": "⚠️ 确定要删除此任务吗？\n> **{task_name}**\n此操作无法撤销。",

    # ─── Pin / Unpin ────────────────────────────────────────────────────────────
    "task_pinned": "📌 任务 **#{task_id}** 已固定。",
    "task_unpinned": "📌 任务 **#{task_id}** 已取消固定。",

    # ─── Task Edit ──────────────────────────────────────────────────────────────
    "task_edit_title": "✏️ 编辑任务 #{task_id}",
    "task_edit_success": "✅ 任务更新成功。",

    # ─── Subtasks ──────────────────────────────────────────────────────────────
    "subtask_add_title": "➕ 添加子任务",
    "subtask_for": "父任务：**{parent_name}**",
    "subtask_created": "✅ 子任务创建成功！",
    "subtask_no_nested": "⚠️ 无法为子任务添加子任务。",
    "subtask_progress": "子任务：{done}/{total}（{pct:.0f}%）",

    # ─── Categories ─────────────────────────────────────────────────────────────
    "cat_title": "🏷️ 分类",
    "cat_list_title": "📂 所有分类",
    "cat_empty": "暂无分类。",
    "cat_add_title": "➕ 添加新分类",
    "cat_name_label": "分类名称",
    "cat_emoji_label": "表情符号（可选）",
    "cat_created": "✅ 分类 **{name}** 已创建！",
    "cat_not_found": "❌ 未找到分类。",

    # ─── Priority Labels ─────────────────────────────────────────────────
    "priority_0": "⬜ 普通",
    "priority_1": "🟦 低",
    "priority_2": "🟩 中低",
    "priority_3": "🟨 中等",
    "priority_4": "🟧 中高",
    "priority_5": "🟥 重要",
    "priority_6": "🔴 紧急",
    "priority_7": "🆘 极紧急",
    "priority_0_desc": "不紧急，随时可做",
    "priority_1_desc": "低紧迫性，可等待",
    "priority_2_desc": "本周内处理",
    "priority_3_desc": "在接下来几天内完成",
    "priority_4_desc": "重要，今明两天必须完成",
    "priority_5_desc": "紧急！几小时内处理",
    "priority_6_desc": "非常紧急！立即行动",
    "priority_7_desc": "极紧急！重大影响，立刻修复",
    "priority_select_placeholder": "⚡ 选择优先级...",
    "priority_select_title": "⚡ 选择优先级",
    "priority_select_desc": "在填写任务详情前选择优先级。",
    "priority_changed": "✅ 优先级已更新！任务 **#{task_id}** 现在是 **{priority}**",
    "priority_low": "⬜ 普通",
    "priority_medium": "🟨 中等",
    "priority_high": "🔴 紧急",

    # ─── Status Labels ──────────────────────────────────────────────────────────
    "status_pending": "⏳ 待处理",
    "status_completed": "✅ 已完成",
    "status_cancelled": "❌ 已取消",
    "status_overdue": "🚨 已逾期",

    # ─── Recurring ──────────────────────────────────────────────────────────────
    "recurring_daily": "🔄 每天",
    "recurring_weekly": "🔄 每周",
    "recurring_monthly": "🔄 每月",
    "recurring_none": "—",

    # ─── Reminders ──────────────────────────────────────────────────────────────
    "reminder_title": "⏰ 任务提醒",
    "reminder_overdue": "🚨 **任务已逾期！**\n`{task}` 应于 {deadline} 完成",
    "reminder_due_soon": "⚡ **任务即将截止！**\n`{task}` 还有 {time_left}",
    "reminder_due_today": "📅 **今天截止！**\n`{task}` 将于 {time} 截止",

    "dm_reminder_title": "⏰ 截止日期提醒（私信）",
    "dm_reminder_24h": "📅 **您的任务即将到期！**\n`{task}` 还有 **{time_left}**。",
    "dm_reminder_3h": "🟠 **不到 3 小时了！**\n`{task}` 截止日期临近！还剩 **{time_left}**。",
    "dm_reminder_1h": "🚨 **不到 1 小时了！**\n`{task}` 即将到期！还剩 **{time_left}**！",
    "dm_reminder_footer": "已完成？使用 `/done {task_id}` 或点击 ✅ 完成 停止提醒。",

    # ─── Export ─────────────────────────────────────────────────────────────────
    "export_success": "📤 导出完成！文件：`{filename}`",
    "export_empty": "📭 没有可导出的数据。",
    "export_rate_limited": "⏳ 您超过了导出限制（{limit}/天），请明天再试。",

    # ─── Search ─────────────────────────────────────────────────────────────────
    "search_title": "🔍 搜索结果：`{query}`",
    "search_empty": "🔍 未找到匹配 `{query}` 的任务。",
    "search_query_label": "搜索关键词",
    "search_query_placeholder": "输入任务名称或标签...",

    # ─── Stats ──────────────────────────────────────────────────────────────────
    "stats_title": "📊 您的统计",
    "stats_total": "总任务数",
    "stats_completed": "已完成",
    "stats_pending": "待处理",
    "stats_overdue": "已逾期",
    "stats_completion_rate": "完成率",
    "stats_categories": "使用的分类",
    "stats_note_empty":    "还没有任务！使用 `/add` 开始吧 🚀",
    "stats_note_overdue":  "⚠️ {overdue} 个任务已逾期 — 使用 `/overdue` 查看",
    "stats_note_all_done": "🏆 所有任务已完成！出色的工作！",
    "stats_note_progress": "您已完成 {pct}% — 继续加油！",

    # ─── Help ───────────────────────────────────────────────────────────────────
    "help_title": "📖 To-Do List Bot Gen 2 — 帮助",
    "help_desc": "功能完整的待办事项机器人，支持多语言。",
    "help_commands": "所有命令",
    "help_add": "添加新任务",
    "help_list": "查看所有任务",
    "help_done": "将任务标记为完成",
    "help_delete": "删除任务",
    "help_edit": "编辑任务",
    "help_search": "搜索任务",
    "help_categories": "管理分类",
    "help_stats": "查看您的统计",
    "help_export": "以 CSV 导出任务",
    "help_setup": "配置机器人",
    "help_lang": "更改语言",
    "help_reminder": "设置提醒",

    # ─── Errors ─────────────────────────────────────────────────────────────────
    "err_generic": "❌ 发生错误，请重试。",
    "err_db": "❌ 数据库错误，请联系管理员。",
    "err_no_setup": "⚠️ 请先使用 `/setup` 配置机器人。",
    "err_input_invalid": "❌ 输入无效：{detail}",
    "err_suspicious": "🚫 检测到可疑行为，命令已被阻止。",
}

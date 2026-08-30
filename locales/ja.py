"""
Japanese (JA) language strings — 日本語
"""

STRINGS = {
    # ─── General ───────────────────────────────────────────────────────────────
    "lang_name": "日本語",
    "lang_flag": "🇯🇵",
    "yes": "はい",
    "no": "いいえ",
    "cancel": "キャンセル",
    "confirm": "確認",
    "success": "成功",
    "error": "エラー",
    "warning": "警告",
    "loading": "読み込み中...",
    "not_found": "見つかりません",
    "permission_denied": "❌ このコマンドを使用する権限がありません",
    "bot_name": "📝 To-Do List Bot Gen 2",
    "footer_text": "To-Do List Bot Gen 2 • 最高の生産性のために",

    # ─── Rate Limiting ──────────────────────────────────────────────────────────
    "rate_limited": "⏳ コマンドの送信が速すぎます。**{seconds:.0f} 秒**後に再試行してください。",
    "task_rate_limited": "⏳ タスク作成の上限（{limit}/時間）を超えました。**{seconds:.0f} 秒**お待ちください。",

    # ─── Setup ─────────────────────────────────────────────────────────────────
    "setup_title": "⚙️ Bot 設定",
    "setup_desc": "以下の設定を行ってください。",
    "setup_timezone": "タイムゾーン",
    "setup_timezone_desc": "例：Asia/Tokyo、UTC、America/New_York",
    "setup_success": "✅ 設定完了！タイムゾーン：**{tz}** | チャンネル：{channel}",
    "setup_checklist": "✅ タイムゾーン  ✅ 通知チャンネル  ☑️ 言語（`/lang` を使用）",
    "setup_invalid_tz": "❌ タイムゾーン `{tz}` は無効です。確認して再試行してください。\n[タイムゾーン一覧](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)",
    "setup_channel_required": "❌ Discord チャンネルでこのコマンドを使用してください。",

    # ─── Language ──────────────────────────────────────────────────────────────
    "lang_changed": "✅ 言語が **日本語** に変更されました。",
    "lang_select_title": "🌐 言語を選択 / Select Language",
    "lang_select_desc": "ご希望の言語をお選びください。",

    # ─── Task Creation ──────────────────────────────────────────────────────────
    "task_add_title": "➕ 新しいタスクを追加",
    "task_name_label": "タスク名",
    "task_name_placeholder": "例：レポートを提出する、チームミーティング",
    "task_deadline_label": "締め切り（日/月/年 時:分）",
    "task_deadline_placeholder": "例：25/12/2025 18:00",
    "task_priority_label": "⚡ 優先度",
    "task_priority_placeholder": "0〜7（0=普通、3=中、5=重要、7=緊急）",
    "task_desc_label": "説明（任意）",
    "task_desc_placeholder": "詳細を追加...",
    "task_tags_label": "タグ（任意）",
    "task_tags_placeholder": "例：仕事、緊急、家庭",
    "task_created": "✅ タスクを作成しました！ID：**#{task_id}**",
    "task_invalid_deadline": "❌ 無効な日付形式です。使用形式：`日/月/年 時:分`\n例：`25/12/2025 18:00`",
    "task_past_deadline": "❌ 締め切りは未来の日時にしてください。",
    "task_invalid_priority": "❌ 優先度は 0〜7 の数値にしてください。",
    "task_name_too_long": "❌ タスク名が長すぎます（最大 200 文字）。",
    "task_desc_too_long": "❌ 説明が長すぎます（最大 1000 文字）。",

    # ─── Task List ──────────────────────────────────────────────────────────────
    "tasks_title": "📋 あなたのタスク",
    "tasks_empty": "📭 タスクがありません。\n**`/add`** で最初のタスクを作成しましょう！",
    "tasks_page": "{page}/{total} ページ",
    "tasks_total": "合計タスク数：**{count}**",
    "tasks_summary": "{total} タスク · {overdue} 期限超過",
    "today_summary": "📅 今日：**{count}** タスク · ⚠️ 期限超過：**{overdue}**",
    "overdue_summary": "🚨 期限超過合計：**{total}** タスク",
    "tasks_filter_pending": "⏳ 未完了",
    "tasks_filter_Pending": "⏳ 未完了",
    "tasks_filter_done": "✅ 完了",
    "tasks_filter_Completed": "✅ 完了",
    "tasks_filter_cancelled": "❌ キャンセル",
    "tasks_filter_Cancelled": "❌ キャンセル",
    "tasks_filter_all": "📋 すべて",
    "tasks_filter_today": "📅 今日",
    "tasks_filter_overdue": "🚨 期限超過",
    "tasks_filter_pinned": "📌 固定済み",
    "list_filter_placeholder": "🔽 ステータスで絞り込む...",

    # ─── Task Details ───────────────────────────────────────────────────────────
    "task_detail_title": "📌 タスク詳細 #{task_id}",
    "task_detail_name": "📝 タスク名",
    "task_detail_status": "🔖 ステータス",
    "task_detail_deadline": "📅 締め切り",
    "task_detail_priority": "⚡ 優先度",
    "task_detail_category": "🏷️ カテゴリ",
    "task_detail_tags": "🔖 タグ",
    "task_detail_desc": "📄 説明",
    "task_detail_recurring": "🔄 繰り返し",
    "task_detail_subtasks": "📊 サブタスク",
    "task_detail_created": "📆 作成日",
    "task_detail_updated": "🔄 最終更新",
    "task_not_found": "❌ タスク #**{task_id}** が見つかりません。",
    "task_not_owned": "❌ このタスクはあなたのものではありません。",

    # ─── Task Actions ───────────────────────────────────────────────────────────
    "btn_done": "✅ 完了にする",
    "btn_mark_done": "✅ 完了にマーク",
    "btn_delete": "🗑️ 削除",
    "btn_edit": "✏️ 編集",
    "btn_subtask": "➕ サブタスク",
    "btn_snooze": "⏰ スヌーズ (+1日)",
    "btn_prev": "◀ 前へ",
    "btn_next": "次へ ▶",
    "btn_refresh": "🔄 更新",
    "btn_back": "🔙 戻る",
    "btn_confirm_delete": "🗑️ 削除を確認",
    "page_indicator": "📄 {page} / {total} ページ",
    "delete_confirm_title": "⚠️ 削除の確認",
    "delete_confirm_desc": "このタスクを削除しますか？\n> **{task_name}**\n\n⚠️ この操作は**元に戻せません**。",

    "task_marked_done": "✅ タスク **#{task_id}** を完了にしました！",
    "task_already_done": "⚠️ このタスクはすでに完了しています。",
    "task_already_cancelled": "⚠️ このタスクはすでにキャンセルされています。",
    "task_deleted": "🗑️ タスク **#{task_id}** を削除しました。",
    "task_delete_confirm": "⚠️ このタスクを削除しますか？\n> **{task_name}**\nこの操作は元に戻せません。",

    # ─── Pin / Unpin ────────────────────────────────────────────────────────────
    "task_pinned": "📌 タスク **#{task_id}** を固定しました。",
    "task_unpinned": "📌 タスク **#{task_id}** の固定を解除しました。",

    # ─── Task Edit ──────────────────────────────────────────────────────────────
    "task_edit_title": "✏️ タスクを編集 #{task_id}",
    "task_edit_success": "✅ タスクを更新しました。",

    # ─── Subtasks ──────────────────────────────────────────────────────────────
    "subtask_add_title": "➕ サブタスクを追加",
    "subtask_for": "親タスク：**{parent_name}**",
    "subtask_created": "✅ サブタスクを作成しました！",
    "subtask_no_nested": "⚠️ サブタスクにサブタスクを追加することはできません。",
    "subtask_progress": "サブタスク：{done}/{total}（{pct:.0f}%）",

    # ─── Categories ─────────────────────────────────────────────────────────────
    "cat_title": "🏷️ カテゴリ",
    "cat_list_title": "📂 すべてのカテゴリ",
    "cat_empty": "カテゴリがありません。",
    "cat_section_default": "📌 デフォルトカテゴリ",
    "cat_section_custom": "🗂️ マイカテゴリ",
    "cat_add_title": "➕ 新しいカテゴリを追加",
    "cat_name_label": "カテゴリ名",
    "cat_emoji_label": "絵文字（任意）",
    "cat_created": "✅ カテゴリ **{name}** を作成しました！",
    "cat_not_found": "❌ カテゴリが見つかりません。",

    # ─── Priority Labels ─────────────────────────────────────────────────
    "priority_0": "⬜ 普通",
    "priority_1": "🟦 低",
    "priority_2": "🟩 やや低",
    "priority_3": "🟨 中",
    "priority_4": "🟧 やや高",
    "priority_5": "🟥 重要",
    "priority_6": "🔴 緊急",
    "priority_7": "🆘 最優先",
    "priority_0_desc": "急ぎではない、いつでも可",
    "priority_1_desc": "緊急度低、後回し可",
    "priority_2_desc": "今週中に対応",
    "priority_3_desc": "数日以内に対応",
    "priority_4_desc": "重要、今日〜明日中に",
    "priority_5_desc": "緊急！数時間以内に対応",
    "priority_6_desc": "非常に緊急！即時対応",
    "priority_7_desc": "最優先！大きな影響あり、今すぐ対応",
    "priority_select_placeholder": "⚡ 優先度を選択...",
    "priority_select_title": "⚡ 優先度を選択",
    "priority_select_desc": "タスク詳細を入力する前に優先度を選んでください。",
    "priority_changed": "✅ 優先度を更新しました！タスク **#{task_id}** は **{priority}** になりました",
    "priority_low": "⬜ 普通",
    "priority_medium": "🟨 中",
    "priority_high": "🔴 緊急",

    # ─── Status Labels ──────────────────────────────────────────────────────────
    "status_pending": "⏳ 未完了",
    "status_completed": "✅ 完了",
    "status_cancelled": "❌ キャンセル",
    "status_overdue": "🚨 期限超過",

    # ─── Recurring ──────────────────────────────────────────────────────────────
    "recurring_daily": "🔄 毎日",
    "recurring_weekly": "🔄 毎週",
    "recurring_monthly": "🔄 毎月",
    "recurring_none": "—",

    # ─── Reminders ──────────────────────────────────────────────────────────────
    "reminder_title": "⏰ タスクリマインダー",
    "reminder_overdue": "🚨 **タスクが期限超過です！**\n`{task}` は {deadline} が期限でした",
    "reminder_due_soon": "⚡ **まもなく締め切り！**\n`{task}` まであと {time_left}",
    "reminder_due_today": "📅 **今日が締め切りです！**\n`{task}` は {time} が期限です",
    "reminder_action_hint": "`/done {task_id}` を使用するか ✅ 完了 を押してリマインダーを停止してください。",

    "dm_reminder_title": "⏰ 締め切りリマインダー（DM）",
    "dm_reminder_24h": "📅 **タスクの期限が近づいています！**\n`{task}` まであと **{time_left}**。",
    "dm_reminder_3h": "🟠 **残り 3 時間未満！**\n`{task}` の期限が迫っています！残り **{time_left}**。",
    "dm_reminder_1h": "🚨 **残り 1 時間未満！**\n`{task}` の期限直前！残り **{time_left}**！",
    "dm_reminder_footer": "完了しましたか？`/done {task_id}` を使うか ✅ 完了 を押してリマインダーを停止してください。",

    # ─── Export ─────────────────────────────────────────────────────────────────
    "export_success": "📤 エクスポート完了！ファイル：`{filename}`",
    "export_empty": "📭 エクスポートするデータがありません。",
    "export_rate_limited": "⏳ エクスポートの上限（{limit}/日）を超えました。明日再試行してください。",

    # ─── Search ─────────────────────────────────────────────────────────────────
    "search_title": "🔍 検索結果：`{query}`",
    "search_results_count": "🔍 検索：**{query}** — {count} 件見つかりました",
    "search_empty": "🔍 `{query}` に一致するタスクが見つかりません。",
    "search_query_label": "検索キーワード",
    "search_query_placeholder": "タスク名またはタグを入力...",

    # ─── Stats ──────────────────────────────────────────────────────────────────
    "stats_title": "📊 あなたの統計",
    "stats_total": "合計タスク数",
    "stats_completed": "完了",
    "stats_pending": "未完了",
    "stats_overdue": "期限超過",
    "stats_completion_rate": "完了率",
    "stats_categories": "使用カテゴリ",
    "stats_header_on_track": "🎯 順調です！",
    "stats_header_overdue": "⚠️ {overdue} 件のタスクが期限超過！",
    "stats_header_all_done": "🏆 すべて完了！",
    "stats_header_empty": "📭 タスクなし",
    "stats_note_empty":    "タスクがありません！`/add` で始めましょう 🚀",
    "stats_note_overdue":  "⚠️ {overdue} 件のタスクが期限超過 — `/overdue` で確認",
    "stats_note_all_done": "🏆 すべてのタスクが完了！素晴らしい！",
    "stats_note_progress": "{pct}% 完了 — 引き続き頑張りましょう！",

    # ─── Help ───────────────────────────────────────────────────────────────────
    "help_title": "📖 To-Do List Bot Gen 2 — ヘルプ",
    "help_desc": "多言語対応の高機能 To-Do Bot。",
    "help_commands": "すべてのコマンド",
    "help_quickstart": "🚀 クイックスタート\n`1.` `/setup Asia/Tokyo` でタイムゾーンを設定\n`2.` `/add` で最初のタスクを作成\n`3.` `/list` でタスクを確認",
    "help_add": "新しいタスクを追加",
    "help_list": "すべてのタスクを表示",
    "help_done": "タスクを完了にする",
    "help_delete": "タスクを削除",
    "help_edit": "タスクを編集",
    "help_search": "タスクを検索",
    "help_categories": "カテゴリを管理",
    "help_stats": "統計を表示",
    "help_export": "タスクを CSV でエクスポート",
    "help_setup": "Bot を設定する",
    "help_lang": "言語を変更",
    "help_reminder": "リマインダーを設定",

    # ─── Errors ─────────────────────────────────────────────────────────────────
    "err_generic": "❌ エラーが発生しました。再試行してください。",
    "err_db": "❌ データベースエラーが発生しました。管理者にお問い合わせください。",
    "err_no_setup": "⚠️ 最初に `/setup` で Bot を設定してください。",
    "err_input_invalid": "❌ 無効な入力：{detail}",
    "err_suspicious": "🚫 不審な動作が検出されました。コマンドをブロックしました。",

    # ─── Snooze Confirm ─────────────────────────────────────────────────────────
    "snooze_confirm_title": "⏰ 延期の確認",
    "snooze_confirm_desc": "このタスクの期限を1日延期しますか？\n> **{task_name}**\n📅 新しい期限: `{new_deadline}`",
    "btn_confirm_snooze": "⏰ 延期を確定 (+1日)",

    # ─── Help Categories (Interactive Select) ───────────────────────────────────
    "help_cat_overview": "🚀 概要とクイックスタート",
    "help_cat_tasks": "📝 タスクコマンド",
    "help_cat_settings": "⚙️ 設定とカテゴリー",
    "help_cat_tips": "💡 ヒントとショートカット",
    "help_version_footer": "To-Do List Bot Gen 2 • /help • github.com",

    # ─── Daily Digest & Overdue ─────────────────────────────────────────────────
    "digest_title": "☀️ 今日のタスクダイジェスト — {date}",
    "digest_no_tasks": "今日のタスクはありません！",
    "digest_today_tasks": "今日のタスク",
    "digest_upcoming_title": "🔮 今後のタスク (今後3日間)",
    "digest_motivational_clean": "✨ 素晴らしい！今日は期限切れタスクがありません。良い一日を！",
    "digest_motivational_busy": "💪 今日は{count}件のタスクがあります。集中して達成しましょう！",
    "digest_motivational_overdue": "⚠️ 注意！期限切れタスクが{overdue}件あります。片付けましょう！",
    "overdue_none": "期限切れのタスクはありません！順調です 🎉",
    "overdue_note": "💪 頑張ってください！期限切れタスクを解消しましょう。",
    "task_done_with_name": "✅ タスク **#{task_id}** ({task_name}) を完了にしました！",

    # ─── Settings & Meta ────────────────────────────────────────────────────────
    "setup_current_tz": "現在のタイムゾーン: **{tz}**",
    "lang_current_active": "現在設定されている言語: {flag} **{name}**",
    "cat_task_count": "{count}件のタスク",
    "task_detail_created": "作成日時",
    "task_detail_updated": "更新日時",

    # ─── UX/UI Additions (stubs — fall back to EN) ───────────────────────────────
    # "cat_no_category", "cat_removed", "setup_lang_field", "stats_cancelled",
    # "priority_timeout", "reminder_field_*", "dm_reminder_field_*", "digest_stats_line"
    # etc. are intentionally omitted; the i18n system falls back to EN automatically.
}

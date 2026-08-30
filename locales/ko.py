"""
Korean (KO) language strings — 한국어
"""

STRINGS = {
    # ─── General ───────────────────────────────────────────────────────────────
    "lang_name": "한국어",
    "lang_flag": "🇰🇷",
    "yes": "예",
    "no": "아니오",
    "cancel": "취소",
    "confirm": "확인",
    "success": "성공",
    "error": "오류",
    "warning": "경고",
    "loading": "로딩 중...",
    "not_found": "찾을 수 없음",
    "permission_denied": "❌ 이 명령어를 사용할 권한이 없습니다",
    "bot_name": "📝 To-Do List Bot Gen 2",
    "footer_text": "To-Do List Bot Gen 2 • 최고의 생산성을 위해",

    # ─── Rate Limiting ──────────────────────────────────────────────────────────
    "rate_limited": "⏳ 명령어를 너무 빠르게 보내고 있습니다. **{seconds:.0f}초** 후에 다시 시도하세요.",
    "task_rate_limited": "⏳ 작업 생성 한도({limit}/시간)를 초과했습니다. **{seconds:.0f}초** 기다려주세요.",

    # ─── Setup ─────────────────────────────────────────────────────────────────
    "setup_title": "⚙️ Bot 설정",
    "setup_desc": "시작하려면 다음 설정을 구성해주세요.",
    "setup_timezone": "시간대",
    "setup_timezone_desc": "예: Asia/Seoul, UTC, America/New_York",
    "setup_success": "✅ 설정 완료! 시간대: **{tz}** | 이름: {channel}",
    "setup_checklist": "✅ 시간대  ✅ 알림 채널  ☑️ 언어 (`/lang` 사용)",
    "setup_invalid_tz": "❌ 시간대 `{tz}`이(가) 유효하지 않습니다. 다시 확인해주세요.\n[시간대 전체 목록](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)",
    "setup_channel_required": "❌ Discord 채널에서 이 명령어를 사용해주세요.",

    # ─── Language ──────────────────────────────────────────────────────────────
    "lang_changed": "✅ 언어가 **한국어** 로 변경되었습니다.",
    "lang_select_title": "🌐 언어 선택 / Select Language",
    "lang_select_desc": "원하는 언어를 선택해주세요.",

    # ─── Task Creation ──────────────────────────────────────────────────────────
    "task_add_title": "➕ 새 작업 추가",
    "task_name_label": "작업 이름",
    "task_name_placeholder": "예: 보고서 제출, 팀 회의",
    "task_deadline_label": "마감일 (일/월/년 시:분)",
    "task_deadline_placeholder": "예: 25/12/2025 18:00",
    "task_priority_label": "⚡ 우선순위",
    "task_priority_placeholder": "0~7 (0=보통, 3=중간, 5=중요, 7=긴급)",
    "task_desc_label": "설명 (선택사항)",
    "task_desc_placeholder": "추가 세부 정보...",
    "task_tags_label": "태그 (선택사항)",
    "task_tags_placeholder": "예: 업무, 긴급, 가정",
    "task_created": "✅ 작업이 성공적으로 생성되었습니다! ID: **#{task_id}**",
    "task_invalid_deadline": "❌ 날짜 형식이 올바르지 않습니다. 사용 형식: `일/월/년 시:분`\n예: `25/12/2025 18:00`",
    "task_past_deadline": "❌ 마감일은 미래로 설정해야 합니다.",
    "task_invalid_priority": "❌ 우선순위는 0에서 7 사이의 숫자여야 합니다.",
    "task_name_too_long": "❌ 작업 이름이 너무 깁니다 (최대 200자).",
    "task_desc_too_long": "❌ 설명이 너무 깁니다 (최대 1000자).",

    # ─── Task List ──────────────────────────────────────────────────────────────
    "tasks_title": "📋 내 작업 목록",
    "tasks_empty": "📭 작업이 없습니다.\n**`/add`** 를 눌러 첫 번째 작업을 만들어보세요!",
    "tasks_page": "{page}/{total} 페이지",
    "tasks_total": "전체 작업 수: **{count}**",
    "tasks_summary": "{total} 작업 · {overdue} 기한 초과",
    "today_summary": "📅 오늘: **{count}** 작업 · ⚠️ 기한 초과: **{overdue}**",
    "overdue_summary": "🚨 기한 초과 전체: **{total}** 작업",
    "tasks_filter_pending": "⏳ 진행 중",
    "tasks_filter_Pending": "⏳ 진행 중",
    "tasks_filter_done": "✅ 완료",
    "tasks_filter_Completed": "✅ 완료",
    "tasks_filter_cancelled": "❌ 취소됨",
    "tasks_filter_Cancelled": "❌ 취소됨",
    "tasks_filter_all": "📋 전체",
    "tasks_filter_today": "📅 오늘",
    "tasks_filter_overdue": "🚨 기한 초과",
    "tasks_filter_pinned": "📌 고정됨",
    "list_filter_placeholder": "🔽 상태로 필터링...",

    # ─── Task Details ───────────────────────────────────────────────────────────
    "task_detail_title": "📌 작업 상세 #{task_id}",
    "task_detail_name": "📝 작업 이름",
    "task_detail_status": "🔖 상태",
    "task_detail_deadline": "📅 마감일",
    "task_detail_priority": "⚡ 우선순위",
    "task_detail_category": "🏷️ 카테고리",
    "task_detail_tags": "🔖 태그",
    "task_detail_desc": "📄 설명",
    "task_detail_recurring": "🔄 반복",
    "task_detail_subtasks": "📊 하위 작업",
    "task_detail_created": "📆 생성일",
    "task_detail_updated": "🔄 마지막 업데이트",
    "task_not_found": "❌ 작업 #**{task_id}** 을(를) 찾을 수 없습니다.",
    "task_not_owned": "❌ 이 작업은 귀하의 것이 아닙니다.",

    # ─── Task Actions ───────────────────────────────────────────────────────────
    "btn_done": "✅ 완료 표시",
    "btn_mark_done": "✅ 완료로 표시",
    "btn_delete": "🗑️ 삭제",
    "btn_edit": "✏️ 편집",
    "btn_subtask": "➕ 하위 작업",
    "btn_snooze": "⏰ 스르즈 (+1일)",
    "btn_prev": "◀ 이전",
    "btn_next": "다음 ▶",
    "btn_refresh": "🔄 새로고침",
    "btn_back": "🔙 뒤로",
    "btn_confirm_delete": "🗑️ 삭제 확인",
    "page_indicator": "📄 {page} / {total} 페이지",
    "delete_confirm_title": "⚠️ 삭제 확인",
    "delete_confirm_desc": "이 작업을 삭제하시겠습니까?\n> **{task_name}**\n\n⚠️ 이 작업은 **되돌릴 수 없습니다**.",

    "task_marked_done": "✅ 작업 **#{task_id}** 이(가) 완료로 표시되었습니다!",
    "task_already_done": "⚠️ 이 작업은 이미 완료되었습니다.",
    "task_already_cancelled": "⚠️ 이 작업은 이미 취소되었습니다.",
    "task_deleted": "🗑️ 작업 **#{task_id}** 이(가) 삭제되었습니다.",
    "task_delete_confirm": "⚠️ 이 작업을 삭제하시겠습니까?\n> **{task_name}**\n이 작업은 되돌릴 수 없습니다.",

    # ─── Pin / Unpin ────────────────────────────────────────────────────────────
    "task_pinned": "📌 작업 **#{task_id}** 이(가) 고정되었습니다.",
    "task_unpinned": "📌 작업 **#{task_id}** 의 고정이 해제되었습니다.",

    # ─── Task Edit ──────────────────────────────────────────────────────────────
    "task_edit_title": "✏️ 작업 편집 #{task_id}",
    "task_edit_success": "✅ 작업이 성공적으로 업데이트되었습니다.",

    # ─── Subtasks ──────────────────────────────────────────────────────────────
    "subtask_add_title": "➕ 하위 작업 추가",
    "subtask_for": "상위 작업: **{parent_name}**",
    "subtask_created": "✅ 하위 작업이 성공적으로 생성되었습니다!",
    "subtask_no_nested": "⚠️ 하위 작업에는 하위 작업을 추가할 수 없습니다.",
    "subtask_progress": "하위 작업: {done}/{total} ({pct:.0f}%)",

    # ─── Categories ─────────────────────────────────────────────────────────────
    "cat_title": "🏷️ 카테고리",
    "cat_list_title": "📂 전체 카테고리",
    "cat_empty": "카테고리가 없습니다.",
    "cat_section_default": "📌 기본 카테고리",
    "cat_section_custom": "🗂️ 나의 카테고리",
    "cat_add_title": "➕ 새 카테고리 추가",
    "cat_name_label": "카테고리 이름",
    "cat_emoji_label": "이모지 (선택사항)",
    "cat_created": "✅ 카테고리 **{name}** 이(가) 생성되었습니다!",
    "cat_not_found": "❌ 카테고리를 찾을 수 없습니다.",

    # ─── Priority Labels ─────────────────────────────────────────────────
    "priority_0": "⬜ 보통",
    "priority_1": "🟦 낮음",
    "priority_2": "🟩 중하",
    "priority_3": "🟨 중간",
    "priority_4": "🟧 중상",
    "priority_5": "🟥 중요",
    "priority_6": "🔴 긴급",
    "priority_7": "🆘 최우선",
    "priority_0_desc": "급하지 않음, 언제든 가능",
    "priority_1_desc": "낮은 긴급도, 나중에 가능",
    "priority_2_desc": "이번 주 내 처리",
    "priority_3_desc": "며칠 내 처리",
    "priority_4_desc": "중요, 오늘~내일 완료",
    "priority_5_desc": "긴급! 몇 시간 내 처리",
    "priority_6_desc": "매우 긴급! 즉시 처리",
    "priority_7_desc": "최우선! 큰 영향, 지금 당장 처리",
    "priority_select_placeholder": "⚡ 우선순위 선택...",
    "priority_select_title": "⚡ 우선순위 선택",
    "priority_select_desc": "작업 상세 정보를 입력하기 전에 우선순위를 선택하세요.",
    "priority_changed": "✅ 우선순위가 업데이트되었습니다! 작업 **#{task_id}** 이(가) **{priority}** 이(가) 되었습니다",
    "priority_low": "⬜ 보통",
    "priority_medium": "🟨 중간",
    "priority_high": "🔴 긴급",

    # ─── Status Labels ──────────────────────────────────────────────────────────
    "status_pending": "⏳ 진행 중",
    "status_completed": "✅ 완료",
    "status_cancelled": "❌ 취소됨",
    "status_overdue": "🚨 기한 초과",

    # ─── Recurring ──────────────────────────────────────────────────────────────
    "recurring_daily": "🔄 매일",
    "recurring_weekly": "🔄 매주",
    "recurring_monthly": "🔄 매월",
    "recurring_none": "—",

    # ─── Reminders ──────────────────────────────────────────────────────────────
    "reminder_title": "⏰ 작업 알림",
    "reminder_overdue": "🚨 **작업 기한이 초과되었습니다!**\n`{task}` 의 기한은 {deadline}이었습니다",
    "reminder_due_soon": "⚡ **마감이 임박했습니다!**\n`{task}` 까지 {time_left} 남았습니다",
    "reminder_due_today": "📅 **오늘이 마감일입니다!**\n`{task}` 의 마감 시간은 {time}입니다",
    "reminder_action_hint": "`/done {task_id}` 를 사용하거나 ✅ 완료 를 눔러 알림을 중지하세요.",

    "dm_reminder_title": "⏰ 마감일 알림 (DM)",
    "dm_reminder_24h": "📅 **작업 마감이 가까워지고 있습니다!**\n`{task}` 까지 **{time_left}** 남았습니다.",
    "dm_reminder_3h": "🟠 **3시간 미만 남았습니다!**\n`{task}` 의 마감이 빠르게 다가옵니다! **{time_left}** 남았습니다.",
    "dm_reminder_1h": "🚨 **1시간 미만 남았습니다!**\n`{task}` 의 마감이 거의 다 왔습니다! **{time_left}** 남았습니다!",
    "dm_reminder_footer": "이미 완료하셨나요? `/done {task_id}` 를 사용하거나 ✅ 완료 를 눌러 알림을 중지하세요.",

    # ─── Export ─────────────────────────────────────────────────────────────────
    "export_success": "📤 내보내기 완료! 파일: `{filename}`",
    "export_empty": "📭 내보낼 데이터가 없습니다.",
    "export_rate_limited": "⏳ 내보내기 한도({limit}/일)를 초과했습니다. 내일 다시 시도하세요.",

    # ─── Search ─────────────────────────────────────────────────────────────────
    "search_title": "🔍 검색 결과: `{query}`",
    "search_results_count": "🔍 검색: **{query}** — {count}개 찾았습니다",
    "search_empty": "🔍 `{query}` 에 일치하는 작업이 없습니다.",
    "search_query_label": "검색어",
    "search_query_placeholder": "작업 이름 또는 태그 입력...",

    # ─── Stats ──────────────────────────────────────────────────────────────────
    "stats_title": "📊 내 통계",
    "stats_total": "전체 작업",
    "stats_completed": "완료",
    "stats_pending": "진행 중",
    "stats_overdue": "기한 초과",
    "stats_completion_rate": "완료율",
    "stats_categories": "사용된 카테고리",
    "stats_header_on_track": "🎯 순조롭습니다!",
    "stats_header_overdue": "⚠️ {overdue}개 작업 기한 초과!",
    "stats_header_all_done": "🏆 모두 완료!",
    "stats_header_empty": "📭 작업 없음",
    "stats_note_empty":    "작업이 없습니다! `/add` 로 시작하세요 🚀",
    "stats_note_overdue":  "⚠️ {overdue}개 작업이 기한 초과 — `/overdue` 로 확인하세요",
    "stats_note_all_done": "🏆 모든 작업 완료! 훌륭합니다!",
    "stats_note_progress": "{pct}% 완료 — 계속 파이팅!",

    # ─── Help ───────────────────────────────────────────────────────────────────
    "help_title": "📖 To-Do List Bot Gen 2 — 도움말",
    "help_desc": "다국어를 지원하는 고기능 To-Do Bot.",
    "help_commands": "모든 명령어",
    "help_quickstart": "🚀 퀘 스타트\n`1.` `/setup Asia/Seoul` 로 시간대 설정\n`2.` `/add` 로 첫 번째 작업 생성\n`3.` `/list` 로 작업 확인",
    "help_add": "새 작업 추가",
    "help_list": "모든 작업 보기",
    "help_done": "작업 완료 표시",
    "help_delete": "작업 삭제",
    "help_edit": "작업 편집",
    "help_search": "작업 검색",
    "help_categories": "카테고리 관리",
    "help_stats": "통계 보기",
    "help_export": "작업을 CSV로 내보내기",
    "help_setup": "Bot 설정",
    "help_lang": "언어 변경",
    "help_reminder": "알림 설정",

    # ─── Errors ─────────────────────────────────────────────────────────────────
    "err_generic": "❌ 오류가 발생했습니다. 다시 시도해주세요.",
    "err_db": "❌ 데이터베이스 오류가 발생했습니다. 관리자에게 문의해주세요.",
    "err_no_setup": "⚠️ 먼저 `/setup` 으로 Bot을 설정해주세요.",
    "err_input_invalid": "❌ 잘못된 입력: {detail}",
    "err_suspicious": "🚫 의심스러운 동작이 감지되었습니다. 명령어가 차단되었습니다.",

    # ─── Snooze Confirm ─────────────────────────────────────────────────────────
    "snooze_confirm_title": "⏰ 연기 확인",
    "snooze_confirm_desc": "이 작업의 마감일을 1일 연기하시겠습니까?\n> **{task_name}**\n📅 새 마감일: `{new_deadline}`",
    "btn_confirm_snooze": "⏰ 연기 확인 (+1일)",

    # ─── Help Categories (Interactive Select) ───────────────────────────────────
    "help_cat_overview": "🚀 개요 및 빠른 시작",
    "help_cat_tasks": "📝 작업 명령어",
    "help_cat_settings": "⚙️ 설정 및 카테고리",
    "help_cat_tips": "💡 팁 및 단축키",
    "help_version_footer": "To-Do List Bot Gen 2 • /help • github.com",

    # ─── Daily Digest & Overdue ─────────────────────────────────────────────────
    "digest_title": "☀️ 오늘 작업 요약 — {date}",
    "digest_no_tasks": "오늘 마감인 작업이 없습니다!",
    "digest_today_tasks": "오늘의 작업",
    "digest_upcoming_title": "🔮 다가오는 작업 (향후 3일)",
    "digest_motivational_clean": "✨ 훌륭합니다! 오늘 마감인 작업이 없습니다. 좋은 하루 되세요!",
    "digest_motivational_busy": "💪 오늘 {count}개의 작업이 있습니다. 힘내서 완료해 보세요!",
    "digest_motivational_overdue": "⚠️ 주의! 마감 기한이 지난 작업이 {overdue}개 있습니다.",
    "overdue_none": "기한이 지난 작업이 없습니다! 완벽하게 관리되고 있습니다 🎉",
    "overdue_note": "💪 힘내세요! 기한 지난 작업을 하나씩 해결해 봅시다.",
    "task_done_with_name": "✅ 작업 **#{task_id}** ({task_name}) 완료 처리되었습니다!",

    # ─── Settings & Meta ────────────────────────────────────────────────────────
    "setup_current_tz": "현재 표준시: **{tz}**",
    "lang_current_active": "현재 활성화된 언어: {flag} **{name}**",
    "cat_task_count": "{count}개 작업",
    "task_detail_created": "생성일",
    "task_detail_updated": "수정일",

    # ─── UX/UI Additions (stubs — fall back to EN) ───────────────────────────────
    # "cat_no_category", "cat_removed", "setup_lang_field", "stats_cancelled",
    # "priority_timeout", "reminder_field_*", "dm_reminder_field_*", "digest_stats_line"
    # etc. are intentionally omitted; the i18n system falls back to EN automatically.
}

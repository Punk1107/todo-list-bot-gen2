"""
Russian (RU) language strings — Русский
"""

STRINGS = {
    # ─── General ───────────────────────────────────────────────────────────────
    "lang_name": "Русский",
    "lang_flag": "🇷🇺",
    "yes": "Да",
    "no": "Нет",
    "cancel": "Отмена",
    "confirm": "Подтвердить",
    "success": "Успешно",
    "error": "Ошибка",
    "warning": "Предупреждение",
    "loading": "Загрузка...",
    "not_found": "Не найдено",
    "permission_denied": "❌ У вас нет прав для использования этой команды",
    "bot_name": "📝 To-Do List Bot Gen 2",
    "footer_text": "To-Do List Bot Gen 2 • Создан для максимальной продуктивности",

    # ─── Rate Limiting ──────────────────────────────────────────────────────────
    "rate_limited": "⏳ Вы отправляете команды слишком часто. Подождите **{seconds:.0f} сек.** и попробуйте снова.",
    "task_rate_limited": "⏳ Вы превысили лимит создания задач ({limit}/час). Подождите **{seconds:.0f} сек.**",

    # ─── Setup ─────────────────────────────────────────────────────────────────
    "setup_title": "⚙️ Настройка бота",
    "setup_desc": "Настройте следующие параметры для начала работы.",
    "setup_timezone": "Часовой пояс",
    "setup_timezone_desc": "Например: Europe/Moscow, Asia/Bangkok, UTC",
    "setup_success": "✅ Настройка завершена! Часовой пояс: **{tz}** | Канал: {channel}",
    "setup_checklist": "✅ Часовой пояс  ✅ Канал уведомлений  ☑️ Язык (используйте `/lang`)",
    "setup_invalid_tz": "❌ Неверный часовой пояс `{tz}`. Проверьте и попробуйте снова.\n[Список часовых поясов](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)",
    "setup_channel_required": "❌ Пожалуйста, используйте эту команду в канале Discord.",

    # ─── Language ──────────────────────────────────────────────────────────────
    "lang_changed": "✅ Язык успешно изменен на **Русский**.",
    "lang_select_title": "🌐 Выбор языка / Select Language",
    "lang_select_desc": "Выберите предпочитаемый язык.",

    # ─── Task Creation ──────────────────────────────────────────────────────────
    "task_add_title": "➕ Добавить новую задачу",
    "task_name_label": "Название задачи",
    "task_name_placeholder": "Например: Сдать отчет, Встреча с командой",
    "task_deadline_label": "Срок (ДД/ММ/ГГГГ ЧЧ:ММ)",
    "task_deadline_placeholder": "Например: 25/12/2025 18:00",
    "task_priority_label": "⚡ Приоритет",
    "task_priority_placeholder": "0–7 (0=Обычный, 3=Средний, 5=Важный, 7=Критический)",
    "task_desc_label": "Описание (необязательно)",
    "task_desc_placeholder": "Дополнительные детали...",
    "task_tags_label": "Теги (необязательно)",
    "task_tags_placeholder": "Например: работа, срочно, дом",
    "task_created": "✅ Задача успешно создана! ID: **#{task_id}**",
    "task_invalid_deadline": "❌ Неверный формат даты. Используйте: `ДД/ММ/ГГГГ ЧЧ:ММ`\nПример: `25/12/2025 18:00`",
    "task_past_deadline": "❌ Срок выполнения должен быть в будущем.",
    "task_invalid_priority": "❌ Приоритет должен быть числом от 0 до 7.",
    "task_name_too_long": "❌ Название задачи слишком длинное (макс. 200 символов).",
    "task_desc_too_long": "❌ Описание слишком длинное (макс. 1000 символов).",

    # ─── Task List ──────────────────────────────────────────────────────────────
    "tasks_title": "📋 Ваши задачи",
    "tasks_empty": "📭 Задач пока нет.\nНажмите **`/add`**, чтобы создать свою первую задачу!",
    "tasks_page": "Страница {page}/{total}",
    "tasks_total": "Всего задач: **{count}**",
    "tasks_summary": "{total} задач · {overdue} просрочено",
    "today_summary": "📅 Сегодня: **{count}** задач(и) · ⚠️ Просрочено: **{overdue}**",
    "overdue_summary": "🚨 Всего просрочено: **{total}** задач(и)",
    "tasks_filter_pending": "⏳ В ожидании",
    "tasks_filter_Pending": "⏳ В ожидании",
    "tasks_filter_done": "✅ Выполнено",
    "tasks_filter_Completed": "✅ Выполнено",
    "tasks_filter_cancelled": "❌ Отменено",
    "tasks_filter_Cancelled": "❌ Отменено",
    "tasks_filter_all": "📋 Все",
    "tasks_filter_today": "📅 Сегодня",
    "tasks_filter_overdue": "🚨 Просроченные",
    "tasks_filter_pinned": "📌 Закрепленные",
    "list_filter_placeholder": "🔽 Фильтр по статусу...",

    # ─── Task Details ───────────────────────────────────────────────────────────
    "task_detail_title": "📌 Детали задачи #{task_id}",
    "task_detail_name": "📝 Название задачи",
    "task_detail_status": "🔖 Статус",
    "task_detail_deadline": "📅 Срок",
    "task_detail_priority": "⚡ Приоритет",
    "task_detail_category": "🏷️ Категория",
    "task_detail_tags": "🔖 Теги",
    "task_detail_desc": "📄 Описание",
    "task_detail_recurring": "🔄 Повторение",
    "task_detail_subtasks": "📊 Подзадачи",
    "task_detail_created": "📆 Создано",
    "task_detail_updated": "🔄 Обновлено",
    "task_not_found": "❌ Задача #**{task_id}** не найдена.",
    "task_not_owned": "❌ Эта задача вам не принадлежит.",

    # ─── Task Actions ───────────────────────────────────────────────────────────
    "btn_done": "✅ Выполнено",
    "btn_mark_done": "✅ Отметить выполненной",
    "btn_delete": "🗑️ Удалить",
    "btn_edit": "✏️ Редактировать",
    "btn_subtask": "➕ Подзадача",
    "btn_snooze": "⏰ Отложить (+1 день)",
    "btn_prev": "◀ Назад",
    "btn_next": "Вперед ▶",
    "btn_refresh": "🔄 Обновить",
    "btn_back": "🔙 Назад",
    "btn_confirm_delete": "🗑️ Подтвердить удаление",
    "page_indicator": "📄 Страница {page} / {total}",
    # Delete confirm embed
    "delete_confirm_title": "⚠️ Подтверждение удаления",
    "delete_confirm_desc": "Вы уверены, что хотите навсегда удалить эту задачу?\n> **{task_name}**\n\n⚠️ Это действие **нельзя отменить**.",

    "task_marked_done": "✅ Задача **#{task_id}** отмечена как выполненная!",
    "task_already_done": "⚠️ Эта задача уже завершена.",
    "task_already_cancelled": "⚠️ Эта задача уже отменена.",
    "task_deleted": "🗑️ Задача **#{task_id}** была удалена.",
    "task_delete_confirm": "⚠️ Вы уверены, что хотите удалить эту задачу?\n> **{task_name}**\nЭто действие нельзя отменить.",

    # ─── Pin / Unpin ────────────────────────────────────────────────────────────
    "task_pinned": "📌 Задача **#{task_id}** успешно закреплена.",
    "task_unpinned": "📌 Задача **#{task_id}** откреплена.",

    # ─── Task Edit ──────────────────────────────────────────────────────────────
    "task_edit_title": "✏️ Редактирование задачи #{task_id}",
    "task_edit_success": "✅ Задача успешно обновлена.",

    # ─── Subtasks ──────────────────────────────────────────────────────────────
    "subtask_add_title": "➕ Добавить подзадачу",
    "subtask_for": "Для задачи: **{parent_name}**",
    "subtask_created": "✅ Подзадача успешно создана!",
    "subtask_no_nested": "⚠️ Нельзя добавлять подзадачу к другой подзадаче.",
    "subtask_progress": "Подзадачи: {done}/{total} ({pct:.0f}%)",

    # ─── Categories ─────────────────────────────────────────────────────────────
    "cat_title": "🏷️ Категории",
    "cat_list_title": "📂 Все категории",
    "cat_empty": "Категорий пока нет.",
    "cat_section_default": "📌 Стандартные категории",
    "cat_section_custom": "🗂️ Ваши категории",
    "cat_add_title": "➕ Добавить категорию",
    "cat_name_label": "Название категории",
    "cat_emoji_label": "Эмодзи (необязательно)",
    "cat_created": "✅ Категория **{name}** создана!",
    "cat_not_found": "❌ Категория не найдена.",

    # ─── Priority Labels ─────────────────────────────────────────────────
    "priority_0": "⬜ Обычный",
    "priority_1": "🟦 Низкий",
    "priority_2": "🟩 Ниже среднего",
    "priority_3": "🟨 Средний",
    "priority_4": "🟧 Выше среднего",
    "priority_5": "🟥 Важный",
    "priority_6": "🔴 Срочный",
    "priority_7": "🆘 Критический",
    # Dropdown descriptions
    "priority_0_desc": "Не срочно, можно сделать когда угодно",
    "priority_1_desc": "Низкая срочность, может подождать",
    "priority_2_desc": "Выполнить на этой неделе",
    "priority_3_desc": "Выполнить в ближайшие пару дней",
    "priority_4_desc": "Важно, сделать сегодня или завтра",
    "priority_5_desc": "Срочно! Выполнить за несколько часов",
    "priority_6_desc": "Очень срочно! Действовать немедленно",
    "priority_7_desc": "Критично! Огромное влияние, исправить прямо сейчас",
    # Dropdown UI strings
    "priority_select_placeholder": "⚡ Выберите уровень приоритета...",
    "priority_select_title": "⚡ Выбор приоритета",
    "priority_select_desc": "Выберите уровень приоритета перед заполнением деталей задачи.",
    "priority_changed": "✅ Приоритет обновлен! Задача **#{task_id}** теперь **{priority}**",
    # Legacy aliases (kept for backward compat)
    "priority_low": "⬜ Обычный",
    "priority_medium": "🟨 Средний",
    "priority_high": "🔴 Срочный",

    # ─── Status Labels ──────────────────────────────────────────────────────────
    "status_pending": "⏳ В ожидании",
    "status_completed": "✅ Выполнено",
    "status_cancelled": "❌ Отменено",
    "status_overdue": "🚨 Просрочено",

    # ─── Recurring ──────────────────────────────────────────────────────────────
    "recurring_daily": "🔄 Ежедневно",
    "recurring_weekly": "🔄 Еженедельно",
    "recurring_monthly": "🔄 Ежемесячно",
    "recurring_none": "—",

    # ─── Reminders ──────────────────────────────────────────────────────────────
    "reminder_title": "⏰ Напоминание о задаче",
    "reminder_overdue": "🚨 **Задача просрочена!**\n`{task}` должна была быть выполнена {deadline}",
    "reminder_due_soon": "⚡ **Скоро дедлайн!**\n`{task}` истекает через {time_left}",
    "reminder_due_today": "📅 **Дедлайн сегодня!**\n`{task}` должна быть завершена в {time}",
    "reminder_action_hint": "Используйте `/done {task_id}` или нажмите ✅ Выполнено, чтобы остановить напоминания.",

    # DM deadline reminders
    "dm_reminder_title": "⏰ Напоминание о дедлайне (ЛС)",
    "dm_reminder_24h": "📅 **Срок выполнения задачи приближается!**\nУ задачи `{task}` осталось всего **{time_left}**.",
    "dm_reminder_3h": "🟠 **Осталось менее 3 часов!**\nДедлайн задачи `{task}` стремительно приближается! Осталось всего **{time_left}**.",
    "dm_reminder_1h": "🚨 **Менее 1 часа!**\nСрок выполнения задачи `{task}` почти истек! Осталось всего **{time_left}**!",
    "dm_reminder_footer": "Уже готово? Используйте `/done {task_id}` или нажмите ✅ Выполнено, чтобы отключить напоминания.",

    # ─── Export ─────────────────────────────────────────────────────────────────
    "export_success": "📤 Экспорт завершен! Файл: `{filename}`",
    "export_empty": "📭 Нет данных для экспорта.",
    "export_rate_limited": "⏳ Вы превысили лимит экспорта ({limit}/день). Попробуйте снова завтра.",

    # ─── Search ─────────────────────────────────────────────────────────────────
    "search_title": "🔍 Результаты поиска: `{query}`",
    "search_results_count": "🔍 Поиск: **{query}** — найдено результатов: {count}",
    "search_empty": "🔍 Задач по запросу `{query}` не найдено.",
    "search_query_label": "Поисковый запрос",
    "search_query_placeholder": "Введите название задачи или тег...",

    # ─── Stats ──────────────────────────────────────────────────────────────────
    "stats_title": "📊 Ваша статистика",
    "stats_total": "Всего задач",
    "stats_completed": "Выполнено",
    "stats_pending": "В ожидании",
    "stats_overdue": "Просрочено",
    "stats_completion_rate": "Процент завершения",
    "stats_categories": "Использовано категорий",
    # Dynamic stats header messages
    "stats_header_on_track": "🎯 Все под контролем!",
    "stats_header_overdue": "⚠️ {overdue} задач(и) просрочено!",
    "stats_header_all_done": "🏆 Все выполнено!",
    "stats_header_empty": "📭 Задач пока нет",
    # Motivational notes in /stats embed
    "stats_note_empty": "Задач пока нет! Используйте `/add`, чтобы начать 🚀",
    "stats_note_overdue": "⚠️ {overdue} задач(и) просрочено — используйте `/overdue` для проверки",
    "stats_note_all_done": "🏆 Все задачи выполнены! Отличная работа!",
    "stats_note_progress": "Выполнено {pct}% — продолжайте в том же духе!",

    # ─── Help ───────────────────────────────────────────────────────────────────
    "help_title": "📖 To-Do List Bot Gen 2 — Справка",
    "help_desc": "Многофункциональный бот списка задач с поддержкой нескольких языков.",
    "help_commands": "Все команды",
    "help_quickstart": "🚀 Быстрый старт\n`1.` Настройте часовой пояс с помощью `/setup Europe/Moscow`\n`2.` Создайте первую задачу через `/add`\n`3.` Просмотрите задачи через `/list`",
    "help_add": "Добавить новую задачу",
    "help_list": "Показать все задачи",
    "help_done": "Отметить задачу выполненной",
    "help_delete": "Удалить задачу",
    "help_edit": "Редактировать задачу",
    "help_search": "Поиск задач",
    "help_categories": "Управление категориями",
    "help_stats": "Посмотреть вашу статистику",
    "help_export": "Экспортировать задачи в CSV",
    "help_setup": "Настроить бота",
    "help_lang": "Изменить язык",
    "help_reminder": "Настроить напоминания",

    # ─── Errors ─────────────────────────────────────────────────────────────────
    "err_generic": "❌ Произошла ошибка. Пожалуйста, попробуйте снова.",
    "err_db": "❌ Ошибка базы данных. Обратитесь к администратору.",
    "err_no_setup": "⚠️ Сначала настройте бота с помощью команды `/setup`.",
    "err_input_invalid": "❌ Недопустимый ввод: {detail}",
    "err_suspicious": "🚫 Обнаружено подозрительное поведение. Команда заблокирована.",

    # ─── Snooze Confirm ─────────────────────────────────────────────────────────
    "snooze_confirm_title": "⏰ Подтверждение переноса",
    "snooze_confirm_desc": "Вы уверены, что хотите отложить эту задачу на 1 день?\n> **{task_name}**\n📅 Новый срок: `{new_deadline}`",
    "btn_confirm_snooze": "⏰ Подтвердить (+1 день)",

    # ─── Help Categories (Interactive Select) ───────────────────────────────────
    "help_cat_overview": "🚀 Обзор и быстрый старт",
    "help_cat_tasks": "📝 Команды задач",
    "help_cat_settings": "⚙️ Настройки и категории",
    "help_cat_tips": "💡 Советы и секреты",
    "help_version_footer": "To-Do List Bot Gen 2 • /help • github.com",

    # ─── Daily Digest & Overdue ─────────────────────────────────────────────────
    "digest_title": "☀️ Ежедневная сводка задач — {date}",
    "digest_no_tasks": "На сегодня задач нет!",
    "digest_today_tasks": "Задачи на сегодня",
    "digest_upcoming_title": "🔮 Предстоящие задачи (след. 3 дня)",
    "digest_motivational_clean": "✨ Отлично! На сегодня расписание свободно. Хорошего дня!",
    "digest_motivational_busy": "💪 У вас сегодня {count} задач(и). Сфокусируйтесь и побеждайте!",
    "digest_motivational_overdue": "⚠️ Внимание! У вас {overdue} просроченных задач(и). Давайте догоним график!",
    "overdue_none": "Нет просроченных задач! Вы идете точно по графику 🎉",
    "overdue_note": "💪 Вы справитесь! Завершите просроченные задачи сегодня.",
    "task_done_with_name": "✅ Задача **#{task_id}** ({task_name}) отмечена как выполненная!",

    # ─── Settings & Meta ────────────────────────────────────────────────────────
    "setup_current_tz": "Текущий часовой пояс: **{tz}**",
    "lang_current_active": "Текущий активный язык: {flag} **{name}**",
    "cat_task_count": "{count} задач(и)",
    "task_detail_created": "Создано",
    "task_detail_updated": "Обновлено",

    # ─── UX/UI Additions (stubs — fall back to EN) ───────────────────────────────
    # "cat_no_category", "cat_removed", "setup_lang_field", "stats_cancelled",
    # "priority_timeout", "reminder_field_*", "dm_reminder_field_*", "digest_stats_line"
    # etc. are intentionally omitted; the i18n system falls back to EN automatically.
}

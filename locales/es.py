"""
Spanish (ES) language strings — Español
"""

STRINGS = {
    # ─── General ───────────────────────────────────────────────────────────────
    "lang_name": "Español",
    "lang_flag": "🇪🇸",
    "yes": "Sí",
    "no": "No",
    "cancel": "Cancelar",
    "confirm": "Confirmar",
    "success": "Éxito",
    "error": "Error",
    "warning": "Advertencia",
    "loading": "Cargando...",
    "not_found": "No encontrado",
    "permission_denied": "❌ No tienes permiso para usar este comando",
    "bot_name": "📝 To-Do List Bot Gen 2",
    "footer_text": "To-Do List Bot Gen 2 • Para la máxima productividad",

    # ─── Rate Limiting ──────────────────────────────────────────────────────────
    "rate_limited": "⏳ Estás enviando comandos demasiado rápido. Por favor espera **{seconds:.0f} segundos** e inténtalo de nuevo.",
    "task_rate_limited": "⏳ Has superado el límite de creación de tareas ({limit}/hora). Espera **{seconds:.0f} segundos**.",

    # ─── Setup ─────────────────────────────────────────────────────────────────
    "setup_title": "⚙️ Configuración del Bot",
    "setup_desc": "Configura los siguientes ajustes para comenzar.",
    "setup_timezone": "Zona horaria",
    "setup_timezone_desc": "Ejemplo: America/Mexico_City, UTC, Europe/Madrid",
    "setup_success": "✅ ¡Configuración completa! Zona horaria: **{tz}** | Canal: {channel}",
    "setup_checklist": "✅ Zona horaria  ✅ Canal de notificaciones  ☑️ Idioma (usa `/lang`)",
    "setup_invalid_tz": "❌ La zona horaria `{tz}` no es válida. Por favor verifica e intenta de nuevo.\n[Lista completa de zonas horarias](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)",
    "setup_channel_required": "❌ Por favor usa este comando en un canal de Discord.",

    # ─── Language ──────────────────────────────────────────────────────────────
    "lang_changed": "✅ Idioma cambiado a **Español** exitosamente.",
    "lang_select_title": "🌐 Seleccionar idioma / Select Language",
    "lang_select_desc": "Elige tu idioma preferido.",

    # ─── Task Creation ──────────────────────────────────────────────────────────
    "task_add_title": "➕ Agregar nueva tarea",
    "task_name_label": "Nombre de la tarea",
    "task_name_placeholder": "Ej: Entregar informe, Reunión de equipo",
    "task_deadline_label": "Fecha límite (DD/MM/AAAA HH:MM)",
    "task_deadline_placeholder": "Ej: 25/12/2025 18:00",
    "task_priority_label": "⚡ Prioridad",
    "task_priority_placeholder": "0–7 (0=Normal, 3=Medio, 5=Importante, 7=Crítico)",
    "task_desc_label": "Descripción (opcional)",
    "task_desc_placeholder": "Detalles adicionales...",
    "task_tags_label": "Etiquetas (opcional)",
    "task_tags_placeholder": "Ej: trabajo, urgente, hogar",
    "task_created": "✅ ¡Tarea creada exitosamente! ID: **#{task_id}**",
    "task_invalid_deadline": "❌ Formato de fecha inválido. Usa: `DD/MM/AAAA HH:MM`\nEjemplo: `25/12/2025 18:00`",
    "task_past_deadline": "❌ La fecha límite debe ser en el futuro.",
    "task_invalid_priority": "❌ La prioridad debe ser un número entre 0 y 7.",
    "task_name_too_long": "❌ El nombre de la tarea es demasiado largo (máximo 200 caracteres).",
    "task_desc_too_long": "❌ La descripción es demasiado larga (máximo 1000 caracteres).",

    # ─── Task List ──────────────────────────────────────────────────────────────
    "tasks_title": "📋 Tus tareas",
    "tasks_empty": "📭 Aún no hay tareas.\n¡Presiona **`/add`** para crear tu primera tarea!",
    "tasks_page": "Página {page}/{total}",
    "tasks_total": "Total de tareas: **{count}**",
    "tasks_summary": "{total} tareas · {overdue} vencidas",
    "today_summary": "📅 Hoy: **{count}** tarea(s) · ⚠️ Vencidas: **{overdue}**",
    "overdue_summary": "🚨 Total vencidas: **{total}** tarea(s)",
    "tasks_filter_pending": "⏳ Pendiente",
    "tasks_filter_Pending": "⏳ Pendiente",
    "tasks_filter_done": "✅ Completado",
    "tasks_filter_Completed": "✅ Completado",
    "tasks_filter_cancelled": "❌ Cancelado",
    "tasks_filter_Cancelled": "❌ Cancelado",
    "tasks_filter_all": "📋 Todos",
    "tasks_filter_today": "📅 Hoy",
    "tasks_filter_overdue": "🚨 Vencido",
    "tasks_filter_pinned": "📌 Fijado",
    "list_filter_placeholder": "🔽 Filtrar por estado...",

    # ─── Task Details ───────────────────────────────────────────────────────────
    "task_detail_title": "📌 Detalle de tarea #{task_id}",
    "task_detail_name": "📝 Nombre de la tarea",
    "task_detail_status": "🔖 Estado",
    "task_detail_deadline": "📅 Fecha límite",
    "task_detail_priority": "⚡ Prioridad",
    "task_detail_category": "🏷️ Categoría",
    "task_detail_tags": "🔖 Etiquetas",
    "task_detail_desc": "📄 Descripción",
    "task_detail_recurring": "🔄 Recurrente",
    "task_detail_subtasks": "📊 Subtareas",
    "task_detail_created": "📆 Creado",
    "task_detail_updated": "🔄 Última actualización",
    "task_not_found": "❌ Tarea #**{task_id}** no encontrada.",
    "task_not_owned": "❌ Esta tarea no te pertenece.",

    # ─── Task Actions ───────────────────────────────────────────────────────────
    "btn_done": "✅ Marcar completado",
    "btn_mark_done": "✅ Marcar como completado",
    "btn_delete": "🗑️ Eliminar",
    "btn_edit": "✏️ Editar",
    "btn_subtask": "➕ Subtarea",
    "btn_snooze": "⏰ Posponer (+1 día)",
    "btn_prev": "◀ Anterior",
    "btn_next": "Siguiente ▶",
    "btn_refresh": "🔄 Actualizar",
    "btn_back": "🔙 Volver",
    "btn_confirm_delete": "🗑️ Confirmar eliminación",
    "page_indicator": "📄 Página {page} / {total}",
    "delete_confirm_title": "⚠️ Confirmar eliminación",
    "delete_confirm_desc": "¿Estás seguro de que deseas eliminar permanentemente esta tarea?\n> **{task_name}**\n\n⚠️ Esta acción **no se puede deshacer**.",

    "task_marked_done": "✅ ¡Tarea **#{task_id}** marcada como completada!",
    "task_already_done": "⚠️ Esta tarea ya está completada.",
    "task_already_cancelled": "⚠️ Esta tarea ya está cancelada.",
    "task_deleted": "🗑️ Tarea **#{task_id}** eliminada.",
    "task_delete_confirm": "⚠️ ¿Estás seguro de que deseas eliminar esta tarea?\n> **{task_name}**\nEsta acción no se puede deshacer.",

    # ─── Pin / Unpin ────────────────────────────────────────────────────────────
    "task_pinned": "📌 Tarea **#{task_id}** fijada exitosamente.",
    "task_unpinned": "📌 Tarea **#{task_id}** desfijada.",

    # ─── Task Edit ──────────────────────────────────────────────────────────────
    "task_edit_title": "✏️ Editar tarea #{task_id}",
    "task_edit_success": "✅ Tarea actualizada exitosamente.",

    # ─── Subtasks ──────────────────────────────────────────────────────────────
    "subtask_add_title": "➕ Agregar subtarea",
    "subtask_for": "Para la tarea: **{parent_name}**",
    "subtask_created": "✅ ¡Subtarea creada exitosamente!",
    "subtask_no_nested": "⚠️ No puedes agregar una subtarea a otra subtarea.",
    "subtask_progress": "Subtareas: {done}/{total} ({pct:.0f}%)",

    # ─── Categories ─────────────────────────────────────────────────────────────
    "cat_title": "🏷️ Categorías",
    "cat_list_title": "📂 Todas las categorías",
    "cat_empty": "Aún no hay categorías.",
    "cat_section_default": "📌 Categorías predeterminadas",
    "cat_section_custom": "🗂️ Mis categorías",
    "cat_add_title": "➕ Agregar nueva categoría",
    "cat_name_label": "Nombre de la categoría",
    "cat_emoji_label": "Emoji (opcional)",
    "cat_created": "✅ ¡Categoría **{name}** creada!",
    "cat_not_found": "❌ Categoría no encontrada.",

    # ─── Priority Labels ─────────────────────────────────────────────────
    "priority_0": "⬜ Normal",
    "priority_1": "🟦 Baja",
    "priority_2": "🟩 Media-Baja",
    "priority_3": "🟨 Media",
    "priority_4": "🟧 Media-Alta",
    "priority_5": "🟥 Importante",
    "priority_6": "🔴 Urgente",
    "priority_7": "🆘 Crítico",
    "priority_0_desc": "No urgente, hacer cuando sea posible",
    "priority_1_desc": "Baja urgencia, puede esperar",
    "priority_2_desc": "Manejar durante esta semana",
    "priority_3_desc": "Hacer en los próximos días",
    "priority_4_desc": "Importante, debe hacerse hoy o mañana",
    "priority_5_desc": "¡Urgente! Actuar en pocas horas",
    "priority_6_desc": "¡Muy urgente! Actuar de inmediato",
    "priority_7_desc": "¡Crítico! Gran impacto, solucionar ahora",
    "priority_select_placeholder": "⚡ Seleccionar nivel de prioridad...",
    "priority_select_title": "⚡ Seleccionar prioridad",
    "priority_select_desc": "Elige el nivel de prioridad antes de completar los detalles.",
    "priority_changed": "✅ ¡Prioridad actualizada! La tarea **#{task_id}** ahora es **{priority}**",
    "priority_low": "⬜ Normal",
    "priority_medium": "🟨 Media",
    "priority_high": "🔴 Urgente",

    # ─── Status Labels ──────────────────────────────────────────────────────────
    "status_pending": "⏳ Pendiente",
    "status_completed": "✅ Completado",
    "status_cancelled": "❌ Cancelado",
    "status_overdue": "🚨 Vencido",

    # ─── Recurring ──────────────────────────────────────────────────────────────
    "recurring_daily": "🔄 Diario",
    "recurring_weekly": "🔄 Semanal",
    "recurring_monthly": "🔄 Mensual",
    "recurring_none": "—",

    # ─── Reminders ──────────────────────────────────────────────────────────────
    "reminder_title": "⏰ Recordatorio de tarea",
    "reminder_overdue": "🚨 **¡Tarea vencida!**\n`{task}` debía completarse el {deadline}",
    "reminder_due_soon": "⚡ **¡Tarea próxima a vencer!**\n`{task}` vence en {time_left}",
    "reminder_due_today": "📅 **¡Vence hoy!**\n`{task}` vence a las {time}",
    "reminder_action_hint": "Usa `/done {task_id}` o presiona ✅ Completado para detener los recordatorios.",

    "dm_reminder_title": "⏰ Recordatorio de fecha límite (DM)",
    "dm_reminder_24h": "📅 **¡Tu tarea se acerca a su fecha límite!**\n`{task}` tiene solo **{time_left}** restante.",
    "dm_reminder_3h": "🟠 **¡Menos de 3 horas!**\n¡La fecha límite de `{task}` se acerca! Solo **{time_left}** restante.",
    "dm_reminder_1h": "🚨 **¡Menos de 1 hora restante!**\n¡`{task}` está casi en su fecha límite! ¡Solo **{time_left}** restante!",
    "dm_reminder_footer": "¿Ya terminaste? Usa `/done {task_id}` o presiona ✅ Completado para detener los recordatorios.",

    # ─── Export ─────────────────────────────────────────────────────────────────
    "export_success": "📤 ¡Exportación completa! Archivo: `{filename}`",
    "export_empty": "📭 No hay datos para exportar.",
    "export_rate_limited": "⏳ Has superado el límite de exportación ({limit}/día). Intenta mañana.",

    # ─── Search ─────────────────────────────────────────────────────────────────
    "search_title": "🔍 Resultados de búsqueda: `{query}`",
    "search_results_count": "🔍 Búsqueda: **{query}** — {count} resultado(s) encontrado(s)",
    "search_empty": "🔍 No se encontraron tareas que coincidan con `{query}`.",
    "search_query_label": "Búsqueda",
    "search_query_placeholder": "Escribe nombre de tarea o etiqueta...",

    # ─── Stats ──────────────────────────────────────────────────────────────────
    "stats_title": "📊 Tus estadísticas",
    "stats_total": "Total de tareas",
    "stats_completed": "Completadas",
    "stats_pending": "Pendientes",
    "stats_overdue": "Vencidas",
    "stats_completion_rate": "Tasa de completado",
    "stats_categories": "Categorías usadas",
    "stats_header_on_track": "🎯 ¡En camino!",
    "stats_header_overdue": "⚠️ ¡{overdue} tarea(s) vencida(s)!",
    "stats_header_all_done": "🏆 ¡Todo completado!",
    "stats_header_empty": "📭 Sin tareas aún",
    "stats_note_empty":    "¡Aún no hay tareas! Usa `/add` para empezar 🚀",
    "stats_note_overdue":  "⚠️ {overdue} tarea(s) vencida(s) — usa `/overdue` para revisar",
    "stats_note_all_done": "🏆 ¡Todas las tareas completadas! ¡Excelente trabajo!",
    "stats_note_progress": "Estás {pct}% completado — ¡sigue así!",

    # ─── Help ───────────────────────────────────────────────────────────────────
    "help_title": "📖 To-Do List Bot Gen 2 — Ayuda",
    "help_desc": "Un bot de lista de tareas completo con soporte multiidioma.",
    "help_commands": "Todos los comandos",
    "help_quickstart": "🚀 Inicio rápido\n`1.` Usa `/setup America/Mexico_City` para tu zona horaria\n`2.` Usa `/add` para crear tu primera tarea\n`3.` Usa `/list` para ver todas tus tareas",
    "help_add": "Agregar nueva tarea",
    "help_list": "Ver todas las tareas",
    "help_done": "Marcar tarea como completada",
    "help_delete": "Eliminar tarea",
    "help_edit": "Editar tarea",
    "help_search": "Buscar tareas",
    "help_categories": "Gestionar categorías",
    "help_stats": "Ver tus estadísticas",
    "help_export": "Exportar tareas como CSV",
    "help_setup": "Configurar el bot",
    "help_lang": "Cambiar idioma",
    "help_reminder": "Configurar recordatorios",

    # ─── Errors ─────────────────────────────────────────────────────────────────
    "err_generic": "❌ Ocurrió un error. Por favor inténtalo de nuevo.",
    "err_db": "❌ Error de base de datos. Por favor contacta al administrador.",
    "err_no_setup": "⚠️ Por favor configura el bot primero usando `/setup`.",
    "err_input_invalid": "❌ Entrada inválida: {detail}",
    "err_suspicious": "🚫 Comportamiento sospechoso detectado. Comando bloqueado.",

    # ─── Snooze Confirm ─────────────────────────────────────────────────────────
    "snooze_confirm_title": "⏰ Confirmar posposición",
    "snooze_confirm_desc": "¿Estás seguro de que deseas posponer esta tarea 1 día?\n> **{task_name}**\n📅 Nueva fecha límite: `{new_deadline}`",
    "btn_confirm_snooze": "⏰ Confirmar (+1 día)",

    # ─── Help Categories (Interactive Select) ───────────────────────────────────
    "help_cat_overview": "🚀 Visión general y Guía rápida",
    "help_cat_tasks": "📝 Comandos de tareas",
    "help_cat_settings": "⚙️ Ajustes y Categorías",
    "help_cat_tips": "💡 Consejos y Atajos",
    "help_version_footer": "To-Do List Bot Gen 2 • /help • github.com",

    # ─── Daily Digest & Overdue ─────────────────────────────────────────────────
    "digest_title": "☀️ Resumen diario de tareas — {date}",
    "digest_no_tasks": "¡No hay tareas pendientes para hoy!",
    "digest_today_tasks": "Tareas de hoy",
    "digest_upcoming_title": "🔮 Próximas tareas (próximos 3 días)",
    "digest_motivational_clean": "✨ ¡Genial! Tu agenda está despejada hoy. ¡Que tengas un gran día!",
    "digest_motivational_busy": "💪 Tienes {count} tarea(s) para hoy. ¡A por ellas!",
    "digest_motivational_overdue": "⚠️ ¡Atención! Tienes {overdue} tarea(s) atrasada(s). ¡Ponte al día!",
    "overdue_none": "¡No hay tareas atrasadas! Vas perfectamente al día 🎉",
    "overdue_note": "💪 ¡Tú puedes! Revisa y completa tus tareas atrasadas.",
    "task_done_with_name": "✅ ¡Tarea **#{task_id}** ({task_name}) marcada como completada!",

    # ─── Settings & Meta ────────────────────────────────────────────────────────
    "setup_current_tz": "Zona horaria actual: **{tz}**",
    "lang_current_active": "Idioma activo actualmente: {flag} **{name}**",
    "cat_task_count": "{count} tarea(s)",
    "task_detail_created": "Creado",
    "task_detail_updated": "Actualizado",
}

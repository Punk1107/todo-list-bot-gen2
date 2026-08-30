"""
German (DE) language strings — Deutsch
"""

STRINGS = {
    # ─── General ───────────────────────────────────────────────────────────────
    "lang_name": "Deutsch",
    "lang_flag": "🇩🇪",
    "yes": "Ja",
    "no": "Nein",
    "cancel": "Abbrechen",
    "confirm": "Bestätigen",
    "success": "Erfolg",
    "error": "Fehler",
    "warning": "Warnung",
    "loading": "Wird geladen...",
    "not_found": "Nicht gefunden",
    "permission_denied": "❌ Du hast keine Berechtigung, diesen Befehl zu verwenden",
    "bot_name": "📝 To-Do List Bot Gen 2",
    "footer_text": "To-Do List Bot Gen 2 • Für maximale Produktivität entwickelt",

    # ─── Rate Limiting ──────────────────────────────────────────────────────────
    "rate_limited": "⏳ Du sendest Befehle zu schnell. Bitte warte **{seconds:.0f} Sekunden** und versuche es erneut.",
    "task_rate_limited": "⏳ Du hast das Aufgaben-Erstellungslimit überschritten ({limit}/Stunde). Bitte warte **{seconds:.0f} Sekunden**.",

    # ─── Setup ─────────────────────────────────────────────────────────────────
    "setup_title": "⚙️ Bot-Einrichtung",
    "setup_desc": "Konfiguriere die folgenden Einstellungen, um zu beginnen.",
    "setup_timezone": "Zeitzone",
    "setup_timezone_desc": "Beispiel: Europe/Berlin, UTC, America/New_York",
    "setup_success": "✅ Einrichtung abgeschlossen! Zeitzone: **{tz}** | Kanal: {channel}",
    "setup_checklist": "✅ Zeitzone  ✅ Benachrichtigungskanal  ☑️ Sprache (nutze `/lang`)",
    "setup_invalid_tz": "❌ Ungültige Zeitzone `{tz}`. Bitte überprüfen und erneut versuchen.\n[Vollständige Zeitzonenliste](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)",
    "setup_channel_required": "❌ Bitte verwende diesen Befehl in einem Discord-Kanal.",

    # ─── Language ──────────────────────────────────────────────────────────────
    "lang_changed": "✅ Sprache erfolgreich auf **Deutsch** umgestellt.",
    "lang_select_title": "🌐 Sprache auswählen / Select Language",
    "lang_select_desc": "Wähle deine bevorzugte Sprache.",

    # ─── Task Creation ──────────────────────────────────────────────────────────
    "task_add_title": "➕ Neue Aufgabe hinzufügen",
    "task_name_label": "Aufgabenname",
    "task_name_placeholder": "z.B. Bericht abgeben, Team-Meeting",
    "task_deadline_label": "Fälligkeitsdatum (TT/MM/JJJJ HH:MM)",
    "task_deadline_placeholder": "z.B. 25/12/2025 18:00",
    "task_priority_label": "⚡ Priorität",
    "task_priority_placeholder": "0–7 (0=Normal, 3=Mittel, 5=Wichtig, 7=Kritisch)",
    "task_desc_label": "Beschreibung (optional)",
    "task_desc_placeholder": "Weitere Details...",
    "task_tags_label": "Tags (optional)",
    "task_tags_placeholder": "z.B. arbeit, dringend, haushalt",
    "task_created": "✅ Aufgabe erfolgreich erstellt! ID: **#{task_id}**",
    "task_invalid_deadline": "❌ Ungültiges Datumsformat. Bitte verwende: `TT/MM/JJJJ HH:MM`\nBeispiel: `25/12/2025 18:00`",
    "task_past_deadline": "❌ Die Frist muss in der Zukunft liegen.",
    "task_invalid_priority": "❌ Priorität muss eine Zahl zwischen 0 und 7 sein.",
    "task_name_too_long": "❌ Aufgabenname ist zu lang (maximal 200 Zeichen).",
    "task_desc_too_long": "❌ Beschreibung ist zu lang (maximal 1000 Zeichen).",

    # ─── Task List ──────────────────────────────────────────────────────────────
    "tasks_title": "📋 Deine Aufgaben",
    "tasks_empty": "📭 Noch keine Aufgaben vorhanden.\nDrücke **`/add`**, um deine erste Aufgabe zu erstellen!",
    "tasks_page": "Seite {page}/{total}",
    "tasks_total": "Aufgaben insgesamt: **{count}**",
    "tasks_summary": "{total} Aufgaben · {overdue} überfällig",
    "today_summary": "📅 Heute: **{count}** Aufgabe(n) · ⚠️ Überfällig: **{overdue}**",
    "overdue_summary": "🚨 Insgesamt überfällig: **{total}** Aufgabe(n)",
    "tasks_filter_pending": "⏳ Ausstehend",
    "tasks_filter_Pending": "⏳ Ausstehend",
    "tasks_filter_done": "✅ Erledigt",
    "tasks_filter_Completed": "✅ Erledigt",
    "tasks_filter_cancelled": "❌ Abgebrochen",
    "tasks_filter_Cancelled": "❌ Abgebrochen",
    "tasks_filter_all": "📋 Alle",
    "tasks_filter_today": "📅 Heute",
    "tasks_filter_overdue": "🚨 Überfällig",
    "tasks_filter_pinned": "📌 Angeheftet",
    "list_filter_placeholder": "🔽 Nach Status filtern...",

    # ─── Task Details ───────────────────────────────────────────────────────────
    "task_detail_title": "📌 Aufgabendetails #{task_id}",
    "task_detail_name": "📝 Aufgabenname",
    "task_detail_status": "🔖 Status",
    "task_detail_deadline": "📅 Frist",
    "task_detail_priority": "⚡ Priorität",
    "task_detail_category": "🏷️ Kategorie",
    "task_detail_tags": "🔖 Tags",
    "task_detail_desc": "📄 Beschreibung",
    "task_detail_recurring": "🔄 Wiederholung",
    "task_detail_subtasks": "📊 Teilaufgaben",
    "task_detail_created": "📆 Erstellt",
    "task_detail_updated": "🔄 Zuletzt aktualisiert",
    "task_not_found": "❌ Aufgabe #**{task_id}** nicht gefunden.",
    "task_not_owned": "❌ Diese Aufgabe gehört dir nicht.",

    # ─── Task Actions ───────────────────────────────────────────────────────────
    "btn_done": "✅ Erledigt",
    "btn_mark_done": "✅ Als erledigt markieren",
    "btn_delete": "🗑️ Löschen",
    "btn_edit": "✏️ Bearbeiten",
    "btn_subtask": "➕ Teilaufgabe",
    "btn_snooze": "⏰ Schlummern (+1 Tag)",
    "btn_prev": "◀ Zurück",
    "btn_next": "Weiter ▶",
    "btn_refresh": "🔄 Aktualisieren",
    "btn_back": "🔙 Zurück",
    "btn_confirm_delete": "🗑️ Löschen bestätigen",
    "page_indicator": "📄 Seite {page} / {total}",
    # Delete confirm embed
    "delete_confirm_title": "⚠️ Löschung bestätigen",
    "delete_confirm_desc": "Möchtest du diese Aufgabe wirklich dauerhaft löschen?\n> **{task_name}**\n\n⚠️ Diese Aktion kann **nicht rückgängig** gemacht werden.",

    "task_marked_done": "✅ Aufgabe **#{task_id}** als erledigt markiert!",
    "task_already_done": "⚠️ Diese Aufgabe ist bereits abgeschlossen.",
    "task_already_cancelled": "⚠️ Diese Aufgabe ist bereits abgebrochen.",
    "task_deleted": "🗑️ Aufgabe **#{task_id}** wurde gelöscht.",
    "task_delete_confirm": "⚠️ Möchtest du diese Aufgabe wirklich löschen?\n> **{task_name}**\nDiese Aktion kann nicht rückgängig gemacht werden.",

    # ─── Pin / Unpin ────────────────────────────────────────────────────────────
    "task_pinned": "📌 Aufgabe **#{task_id}** erfolgreich angeheftet.",
    "task_unpinned": "📌 Aufgabe **#{task_id}** nicht mehr angeheftet.",

    # ─── Task Edit ──────────────────────────────────────────────────────────────
    "task_edit_title": "✏️ Aufgabe bearbeiten #{task_id}",
    "task_edit_success": "✅ Aufgabe erfolgreich aktualisiert.",

    # ─── Subtasks ──────────────────────────────────────────────────────────────
    "subtask_add_title": "➕ Teilaufgabe hinzufügen",
    "subtask_for": "Für Aufgabe: **{parent_name}**",
    "subtask_created": "✅ Teilaufgabe erfolgreich erstellt!",
    "subtask_no_nested": "⚠️ Du kannst einer Teilaufgabe keine weitere Teilaufgabe hinzufügen.",
    "subtask_progress": "Teilaufgaben: {done}/{total} ({pct:.0f}%)",

    # ─── Categories ─────────────────────────────────────────────────────────────
    "cat_title": "🏷️ Kategorien",
    "cat_list_title": "📂 Alle Kategorien",
    "cat_empty": "Noch keine Kategorien vorhanden.",
    "cat_section_default": "📌 Standard-Kategorien",
    "cat_section_custom": "🗂️ Deine Kategorien",
    "cat_add_title": "➕ Neue Kategorie hinzufügen",
    "cat_name_label": "Kategoriename",
    "cat_emoji_label": "Emoji (optional)",
    "cat_created": "✅ Kategorie **{name}** erstellt!",
    "cat_not_found": "❌ Kategorie nicht gefunden.",

    # ─── Priority Labels ─────────────────────────────────────────────────
    "priority_0": "⬜ Normal",
    "priority_1": "🟦 Niedrig",
    "priority_2": "🟩 Mittel-Niedrig",
    "priority_3": "🟨 Mittel",
    "priority_4": "🟧 Mittel-Hoch",
    "priority_5": "🟥 Wichtig",
    "priority_6": "🔴 Dringend",
    "priority_7": "🆘 Kritisch",
    # Dropdown descriptions
    "priority_0_desc": "Nicht zeitkritisch, jederzeit erledigen",
    "priority_1_desc": "Geringe Dringlichkeit, kann warten",
    "priority_2_desc": "Diese Woche erledigen",
    "priority_3_desc": "In den nächsten Tagen erledigen",
    "priority_4_desc": "Wichtig, heute oder morgen erledigen",
    "priority_5_desc": "Dringend! Innerhalb weniger Stunden handeln",
    "priority_6_desc": "Sehr dringend! Sofort handeln",
    "priority_7_desc": "Kritisch! Große Auswirkung, jetzt beheben",
    # Dropdown UI strings
    "priority_select_placeholder": "⚡ Prioritätsstufe wählen...",
    "priority_select_title": "⚡ Priorität auswählen",
    "priority_select_desc": "Wähle die Prioritätsstufe, bevor du Aufgabendetails ausfüllst.",
    "priority_changed": "✅ Priorität aktualisiert! Aufgabe **#{task_id}** ist jetzt **{priority}**",
    # Legacy aliases (kept for backward compat)
    "priority_low": "⬜ Normal",
    "priority_medium": "🟨 Mittel",
    "priority_high": "🔴 Dringend",

    # ─── Status Labels ──────────────────────────────────────────────────────────
    "status_pending": "⏳ Ausstehend",
    "status_completed": "✅ Erledigt",
    "status_cancelled": "❌ Abgebrochen",
    "status_overdue": "🚨 Überfällig",

    # ─── Recurring ──────────────────────────────────────────────────────────────
    "recurring_daily": "🔄 Täglich",
    "recurring_weekly": "🔄 Wöchentlich",
    "recurring_monthly": "🔄 Monatlich",
    "recurring_none": "—",

    # ─── Reminders ──────────────────────────────────────────────────────────────
    "reminder_title": "⏰ Aufgaben-Erinnerung",
    "reminder_overdue": "🚨 **Aufgabe überfällig!**\n`{task}` war fällig am {deadline}",
    "reminder_due_soon": "⚡ **Aufgabe bald fällig!**\n`{task}` ist fällig in {time_left}",
    "reminder_due_today": "📅 **Aufgabe heute fällig!**\n`{task}` ist fällig um {time}",
    "reminder_action_hint": "Verwende `/done {task_id}` oder klicke auf ✅ Erledigt, um Erinnerungen zu stoppen.",

    # DM deadline reminders
    "dm_reminder_title": "⏰ Frist-Erinnerung (PN)",
    "dm_reminder_24h": "📅 **Deine Aufgabe nähert sich ihrer Frist!**\n`{task}` hat nur noch **{time_left}** übrig.",
    "dm_reminder_3h": "🟠 **Weniger als 3 Stunden übrig!**\nDie Frist für `{task}` rückt schnell näher! Nur noch **{time_left}**.",
    "dm_reminder_1h": "🚨 **Unter 1 Stunde verbleibend!**\n`{task}` erreicht fast ihre Frist! Nur noch **{time_left}** verbleibend!",
    "dm_reminder_footer": "Schon fertig? Verwende `/done {task_id}` oder klicke auf ✅ Erledigt, um Erinnerungen zu stoppen.",

    # ─── Export ─────────────────────────────────────────────────────────────────
    "export_success": "📤 Export abgeschlossen! Datei: `{filename}`",
    "export_empty": "📭 Keine Daten zum Exportieren vorhanden.",
    "export_rate_limited": "⏳ Du hast das Exportlimit überschritten ({limit}/Tag). Bitte morgen erneut versuchen.",

    # ─── Search ─────────────────────────────────────────────────────────────────
    "search_title": "🔍 Suchergebnisse: `{query}`",
    "search_results_count": "🔍 Suche: **{query}** — {count} Ergebnis(se) gefunden",
    "search_empty": "🔍 Keine passenden Aufgaben für `{query}` gefunden.",
    "search_query_label": "Suchbegriff",
    "search_query_placeholder": "Aufgabenname oder Tag eingeben...",

    # ─── Stats ──────────────────────────────────────────────────────────────────
    "stats_title": "📊 Deine Statistiken",
    "stats_total": "Aufgaben insgesamt",
    "stats_completed": "Erledigt",
    "stats_pending": "Ausstehend",
    "stats_overdue": "Überfällig",
    "stats_completion_rate": "Abschlussrate",
    "stats_categories": "Genutzte Kategorien",
    # Dynamic stats header messages
    "stats_header_on_track": "🎯 Alles im Plan!",
    "stats_header_overdue": "⚠️ {overdue} Aufgabe(n) überfällig!",
    "stats_header_all_done": "🏆 Alles erledigt!",
    "stats_header_empty": "📭 Noch keine Aufgaben",
    # Motivational notes in /stats embed
    "stats_note_empty": "Noch keine Aufgaben vorhanden! Verwende `/add`, um loszulegen 🚀",
    "stats_note_overdue": "⚠️ {overdue} Aufgabe(n) überfällig — nutze `/overdue`, um sie zu prüfen",
    "stats_note_all_done": "🏆 Alle Aufgaben erledigt! Fantastische Arbeit!",
    "stats_note_progress": "Du hast {pct}% geschafft — weiter so!",

    # ─── Help ───────────────────────────────────────────────────────────────────
    "help_title": "📖 To-Do List Bot Gen 2 — Hilfe",
    "help_desc": "Ein voll ausgestatteter To-Do-Listen-Bot mit mehrsprachiger Unterstützung.",
    "help_commands": "Alle Befehle",
    "help_quickstart": "🚀 Schnellstart\n`1.` Nutze `/setup Europe/Berlin`, um deine Zeitzone festzulegen\n`2.` Nutze `/add`, um deine erste Aufgabe zu erstellen\n`3.` Nutze `/list`, um alle Aufgaben anzuzeigen",
    "help_add": "Eine neue Aufgabe hinzufügen",
    "help_list": "Alle Aufgaben anzeigen",
    "help_done": "Eine Aufgabe als erledigt markieren",
    "help_delete": "Eine Aufgabe löschen",
    "help_edit": "Eine Aufgabe bearbeiten",
    "help_search": "Aufgaben durchsuchen",
    "help_categories": "Kategorien verwalten",
    "help_stats": "Deine Statistiken anzeigen",
    "help_export": "Aufgaben als CSV exportieren",
    "help_setup": "Den Bot konfigurieren",
    "help_lang": "Sprache ändern",
    "help_reminder": "Erinnerungen einstellen",

    # ─── Errors ─────────────────────────────────────────────────────────────────
    "err_generic": "❌ Ein Fehler ist aufgetreten. Bitte versuche es erneut.",
    "err_db": "❌ Ein Datenbankfehler ist aufgetreten. Bitte kontaktiere einen Administrator.",
    "err_no_setup": "⚠️ Bitte konfiguriere den Bot zuerst mit `/setup`.",
    "err_input_invalid": "❌ Ungültige Eingabe: {detail}",
    "err_suspicious": "🚫 Verdächtiges Verhalten erkannt. Befehl blockiert.",

    # ─── Snooze Confirm ─────────────────────────────────────────────────────────
    "snooze_confirm_title": "⏰ Schlummern bestätigen",
    "snooze_confirm_desc": "Möchtest du diese Aufgabe wirklich um 1 Tag verschieben?\n> **{task_name}**\n📅 Neue Frist: `{new_deadline}`",
    "btn_confirm_snooze": "⏰ Bestätigen (+1 Tag)",

    # ─── Help Categories (Interactive Select) ───────────────────────────────────
    "help_cat_overview": "🚀 Übersicht & Schnellstart",
    "help_cat_tasks": "📝 Aufgaben-Befehle",
    "help_cat_settings": "⚙️ Einstellungen & Kategorien",
    "help_cat_tips": "💡 Tipps & Tricks",
    "help_version_footer": "To-Do List Bot Gen 2 • /help • github.com",

    # ─── Daily Digest & Overdue ─────────────────────────────────────────────────
    "digest_title": "☀️ Tägliche Aufgabenübersicht — {date}",
    "digest_no_tasks": "Heute stehen keine Aufgaben an!",
    "digest_today_tasks": "Heutige Aufgaben",
    "digest_upcoming_title": "🔮 Bevorstehende Aufgaben (nächste 3 Tage)",
    "digest_motivational_clean": "✨ Großartig! Dein Plan ist heute leer. Hab einen schönen Tag!",
    "digest_motivational_busy": "💪 Du hast heute {count} Aufgabe(n). Bleib fokussiert und pack es an!",
    "digest_motivational_overdue": "⚠️ Achtung! Du hast {overdue} überfällige Aufgabe(n). Holen wir das auf!",
    "overdue_none": "Keine überfälligen Aufgaben! Du bist voll im Zeitplan 🎉",
    "overdue_note": "💪 Du schaffst das! Schließe deine überfälligen Aufgaben heute ab.",
    "task_done_with_name": "✅ Aufgabe **#{task_id}** ({task_name}) als erledigt markiert!",

    # ─── Settings & Meta ────────────────────────────────────────────────────────
    "setup_current_tz": "Aktuelle Zeitzone: **{tz}**",
    "lang_current_active": "Derzeit aktive Sprache: {flag} **{name}**",
    "cat_task_count": "{count} Aufgabe(n)",
    "task_detail_created": "Erstellt",
    "task_detail_updated": "Aktualisiert",

    # ─── UX/UI Additions (stubs — fall back to EN) ───────────────────────────────
    # "cat_no_category", "cat_removed", "setup_lang_field", "stats_cancelled",
    # "priority_timeout", "reminder_field_*", "dm_reminder_field_*", "digest_stats_line"
    # etc. are intentionally omitted; the i18n system falls back to EN automatically.
}

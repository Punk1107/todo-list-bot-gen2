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
    "task_snoozed": "⏰ Aufgabe um 1 Tag verschoben! Neue Frist: `{deadline}`",

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

    # ─── UX/UI Additions ─────────────────────────────────────────────────────────
    "cat_no_category": "— Keine Kategorie",
    "cat_removed": "🗑️ Kategorie **{name}** wurde entfernt.",
    "setup_lang_field": "🌐 Sprache",
    "stats_cancelled": "Abgebrochen",
    "priority_timeout": "⌛ Auswahl abgelaufen. Bitte führe den Befehl erneut aus.",
    "reminder_field_deadline": "📅 Frist",
    "reminder_field_priority": "⚡ Priorität",
    "reminder_field_task_id": "🆔 Aufgaben-ID",
    "dm_reminder_field_time_left": "⏱️ Verbleibende Zeit",
    "digest_stats_line": "📊 **{pending}** ausstehend  ·  🚨 **{overdue}** überfällig",
    "help_overview_browse": (
        "Nutze das Dropdown-Menü unten, um Befehle nach Kategorien anzuzeigen:\n"
        "• **📝 Aufgaben-Befehle**: Erstellen, bearbeiten, abschließen und verwalten\n"
        "• **⚙️ Einstellungen & Kategorien**: Zeitzone, Sprache und Kategorien\n"
        "• **💡 Tipps & Tricks**: Nützliche Funktionen und Best Practices"
    ),

    # ─── Productivity Analytics (/task-stats) ────────────────────────────────────
    "taskstats_title":              "📊 Produktivitäts-Dashboard  ·  {username}",
    "taskstats_overview_tab":       "📊 Übersicht",
    "taskstats_speed_tab":          "⏱️ Geschwindigkeit & Pünktlichkeit",
    "taskstats_refresh":            "🔄 Aktualisieren",

    # Overview section
    "taskstats_score_label":        "🏆 Produktivitätswert",
    "taskstats_score_value":        "{score}/100  {badge}",
    "taskstats_completion_label":   "✅ Abschlussrate",
    "taskstats_completion_value":   "{rate}%  ({done}/{total} Aufgaben)",
    "taskstats_velocity_label":     "⚡ Arbeitsgeschwindigkeit",
    "taskstats_velocity_value":     "7 Tage: **{v7}** Aufgaben  ·  30 Tage: **{v30}** Aufgaben",
    "taskstats_streak_label":       "🔥 Serie",
    "taskstats_streak_value":       "{days} Tage in Folge",
    "taskstats_pending_overdue":    "⏳ Ausstehend: **{pending}**  ·  🚨 Überfällig: **{overdue}**",

    # Speed / Timeliness section
    "taskstats_speed_title":        "⏱️ Analyse zu Geschwindigkeit & Pünktlichkeit  ·  {username}",
    "taskstats_ontime_label":       "✅ Pünktlich erledigt",
    "taskstats_ontime_value":       "{rate}%  ({count} Aufgaben)",
    "taskstats_late_label":         "⚠️ Verspätet erledigt",
    "taskstats_late_value":         "{rate}%  ({count} Aufgaben)",
    "taskstats_turnaround_label":   "⏰ Durchschn. Bearbeitungszeit",
    "taskstats_turnaround_value":   "{hours}",
    "taskstats_lead_label":         "🚀 Durchschn. Vorlaufzeit (pünktlich)",
    "taskstats_lead_value":         "{hours} vor der Frist",
    "taskstats_lag_label":          "🐌 Durchschn. Verzögerung (verspätet)",
    "taskstats_lag_value":          "{hours} nach der Frist",
    "taskstats_no_completed":       "Noch keine erledigten Aufgaben — schließe heute deine erste ab! 🚀",
    "taskstats_tip_label":          "💡 Persönlicher Tipp",

    # Badges
    "badge_master":     "🏆 Produktivitäts-Meister",
    "badge_pro":        "🎯 Pünktlichkeits-Profi",
    "badge_achiever":   "🛡️ Beständiger Macher",
    "badge_rising":     "⚡ Aufsteigender Schwung",
    "badge_pacing":     "🐢 Braucht Fokus",
    "badge_new":        "🌱 Gerade erst gestartet",

    # Tips
    "tip_master":       "Hervorragend! Du übertriffst alle Erwartungen. Setze deine Ziele ruhig noch höher!",
    "tip_pro":          "Fast perfekt! Plane täglich 10 Minuten voraus, um deinen Wert noch weiter zu steigern.",
    "tip_achiever":     "Guter Schwung! Nutze Teilaufgaben für große Projekte, um schneller voranzukommen.",
    "tip_rising":       "Guter Start! Sortiere Aufgaben nach Priorität, um deinen Fokus zu schärfen.",
    "tip_pacing":       "Keine Sorge! Teile große Aufgaben in kleinere auf und blocke feste Zeiten im Kalender.",
    "tip_new":          "Auf geht's! Erstelle deine erste Aufgabe mit `/add` und erledige sie noch heute! 💪",

    # Formatting helpers
    "duration_days":    "{d} T. {h} Std.",
    "duration_hours":   "{h} Std. {m} Min.",
    "duration_mins":    "{m} Min.",
    "duration_na":      "Noch keine Daten",

    # ─── On-Demand /digest command ───────────────────────────────────────────────
    "digest_cmd_desc":    "☀️ Zeige deine heutige Aufgabenübersicht sofort an",
    "digest_btn_list":    "📋 Alle Aufgaben anzeigen",
    "digest_btn_add":     "➕ Neue Aufgabe hinzufügen",
    "digest_btn_refresh": "🔄 Aktualisieren",

    # ─── Conflict Resolution & Defensive Programming ──────────────────────────
    # Deadline validation — enhanced
    "task_past_deadline_detailed": (
        "❌ Die Frist muss in der Zukunft liegen.\n"
        "🕒 Deine aktuelle Zeit: **{current_time}**\n"
        "📅 Eingegebene Zeit: **{input_time}**"
    ),
    "task_invalid_year": "❌ Das angegebene Jahr liegt außerhalb des gültigen Bereichs (2000 – aktuelles Jahr +10).",
    # Subtask integrity
    "subtask_deadline_exceeds_parent": (
        "❌ Die Frist der Unteraufgabe ({subtask_dl}) darf nicht später als die der Hauptaufgabe sein ({parent_dl})."
    ),
    "subtask_parent_closed": "❌ Einer abgeschlossenen oder abgebrochenen Aufgabe können keine Unteraufgaben hinzugefügt werden.",
    # Duplicate task conflict embed
    "conflict_duplicate_title": "⚠️ Konflikt erkannt: Aufgabenname bereits vorhanden",
    "conflict_duplicate_desc": (
        "Eine ausstehende Aufgabe namens **\"{existing_name}\"** (ID: **#{existing_id}**) existiert bereits.\n"
        "Bestehende Frist: **{existing_deadline}**\n\n"
        "Wie möchtest du vorgehen?"
    ),
    # Conflict resolution buttons
    "btn_conflict_autorename": "🏷️ Speichern als \"{new_name}\"",
    "btn_conflict_force":      "⚡ Trotzdem erstellen",
    "btn_conflict_view":       "🔍 Bestehende Aufgabe ansehen",
    "btn_conflict_cancel":     "❌ Abbrechen",
    # Conflict resolution outcomes
    "conflict_cancelled":       "❌ Aufgabenerstellung abgebrochen.",
    "conflict_autorename_done": "✅ Aufgabe als **\"{new_name}\"** gespeichert! ID: **#{task_id}**",
    # Edit validation
    "edit_past_deadline_blocked": (
        "❌ Die Frist kann nicht in der Vergangenheit liegen.\n"
        "🕒 Deine aktuelle Zeit: **{current_time}**\n"
        "📅 Eingegebene Zeit: **{input_time}**"
    ),

    # ─── Shared Projects (Collaboration) ───────────────────────────────────────
    "proj_guild_only":              "❌ Dieser Befehl kann nur in einem Discord-Server verwendet werden.",
    "proj_not_found":               "❌ Projekt **#{project_id}** wurde in diesem Server nicht gefunden.",
    "proj_no_permission":           "❌ Du hast keine Berechtigung für diese Aktion. Benötigte Rolle: **Projektleiter** oder Server-Administrator.",
    "proj_not_active":              "❌ Dieses Projekt ist **{status}** und kann keine neuen Aufgaben annehmen.",

    "proj_list_title":              "📁 Gemeinsame Projekte — {guild}",
    "proj_list_empty":              "Keine Projekte gefunden. Erstelle eines mit `/project create`!",
    "proj_footer":                  "{count} Projekt(e) gefunden",

    "proj_create_modal_title":      "🎉 Neues Projekt erstellen",
    "proj_name_label":              "Projektname",
    "proj_name_placeholder":        "z.B. Website-Redesign, Eventplanung",
    "proj_desc_label":              "Beschreibung (optional)",
    "proj_desc_placeholder":        "Worum geht es in diesem Projekt?",
    "proj_color_label":             "Farbe (Hex, optional)",
    "proj_emoji_label":             "Emoji / Symbol (optional)",
    "proj_created_success":         "🎉 Projekt **{name}** erfolgreich erstellt!",

    "proj_progress":                "📈 Fortschritt",
    "proj_pending":                 "Ausstehend",
    "proj_in_progress":             "In Bearbeitung",
    "proj_completed":               "Abgeschlossen",
    "proj_cancelled":               "Abgebrochen",
    "proj_overdue":                 "Überfällig",
    "proj_members":                 "Mitglieder",
    "proj_status_label":            "Status",
    "proj_leaderboard":             "Top-Mitwirkende",
    "proj_lb_tasks":                "Aufgabe(n)",
    "proj_footer_id":               "Projekt #{project_id}",
    "proj_tasks_done":              "erledigt",

    "proj_board_select_col":        "Spalte wechseln...",
    "proj_board_empty_col":         "Keine Aufgaben in **{column}** momentan.",
    "proj_board_more":              "...und {count} weitere Aufgabe(n). Nutze /project board.",

    "proj_no_claimable":            "✅ Alle verfügbaren Aufgaben wurden bereits beansprucht!",
    "proj_claim_select_title":      "🙋 Aufgabe übernehmen",
    "proj_claim_select_desc":       "Wähle eine Aufgabe aus der Liste, um sie zu übernehmen. Sie wird auf **In Bearbeitung** gesetzt.",
    "proj_claim_select_placeholder":"Aufgabe zum Übernehmen wählen...",
    "proj_claimed_title":           "✅ Aufgabe übernommen!",
    "proj_claimed_desc":            "Du hast **#{task_id} — {name}** übernommen. Viel Erfolg! 💪",
    "proj_claimed_footer":          "Die Aufgabe ist jetzt In Bearbeitung und dir zugewiesen.",

    "proj_task_not_found":          "❌ Aufgabe **#{task_id}** wurde in diesem Projekt nicht gefunden.",
    "proj_add_task_modal_title":    "➕ Aufgabe hinzufügen — {name}",
    "proj_task_added":              "✅ Aufgabe **#{task_id} — {name}** zum Projekt hinzugefügt!",

    "proj_members_title":           "Mitglieder",
    "proj_members_empty":           "Noch keine Mitglieder.",
    "proj_members_count":           "{count} Mitglied(er)",

    "proj_activity_title":          "Aktivitätsfeed",
    "proj_activity_empty":          "Noch keine Aktivitäten aufgezeichnet.",

    "proj_my_tasks_title":          "🙋 Zugewiesene Aufgaben von {user}",
    "proj_my_tasks_empty":          "Du hast keine zugewiesenen Aufgaben in diesem Server. Nutze `/project board` zum Übernehmen!",
    "proj_my_tasks_footer":         "{count} aktive Aufgabe(n) zugewiesen",

    "proj_archived_success":        "📦 Projekt **{name}** wurde archiviert.",
    "proj_completed_success":       "✅ Projekt **{name}** wurde als abgeschlossen markiert. Gut gemacht! 🏆",

    # Realtime & Storage
    "rt_task_completed_title": "Aufgabe abgeschlossen!",
    "rt_task_completed_body": "{user} hat **#{task_id} - {task_name}** abgeschlossen\nProjekt {project_emoji} **{project_name}**",
    "rt_task_claimed_title": "Aufgabe uebernommen!",
    "rt_task_claimed_body": "{user} hat **#{task_id} - {task_name}** uebernommen\nProjekt {project_emoji} **{project_name}**",
    "rt_attachment_uploaded_title": "Neuer Anhang!",
    "rt_attachment_uploaded_body": "{user} hat **{file_name}** ({file_size}) hochgeladen\nZur Aufgabe **#{task_id} - {task_name}**",
    "storage_attachments_title": "Anhaenge fuer Aufgabe #{task_id}",
    "storage_no_attachments": "Noch keine Dateien. Nutze /attach zum Hochladen.",
    "storage_more_files": "und {count} weitere Datei(en)...",
    "storage_file_count": "{count} Datei(en) angehaengt",
    "storage_upload_success_title": "Upload erfolgreich!",
    "storage_upload_success": "**{filename}** ({filesize}) wurde Aufgabe **#{task_id}** angehaengt.",
    "storage_deleted_success": "Datei erfolgreich geloescht.",
    "storage_delete_no_permission": "Du kannst nur Dateien loeschen, die du hochgeladen hast, oder du musst Administrator sein.",
    "storage_not_found": "Anhang nicht gefunden. Er wurde moeglicherweise bereits geloescht.",
    "storage_disabled": "Dateispeicher ist in dieser Bot-Instanz deaktiviert.",
    "storage_file_too_large": "Datei zu gross! Maximale Groesse: {max_mb} MB.",
    "storage_invalid_extension": "Dateityp nicht erlaubt. Erlaubte Typen: {allowed}",
    "proj_channel_set_title": "🔔 Benachrichtigungskanal festgelegt",
    "proj_channel_set_body": "Projekt {project_emoji} **{project_name}** sendet Benachrichtigungen an {channel}.",
    # ─── Analytics ─────────────────────────────────────────────────────────────
    "analytics_snapshot_title": "📊 Dein Wochenbericht wird erstellt...",
    "analytics_snapshot_desc": "Statistiken der letzten 7 Tage werden abgerufen. Dein Bericht kommt gleich per DM!",
    "analytics_snapshot_sent": "✅ Dein wöchentlicher Produktivitätsbericht wurde an deine DMs gesendet!",
    "analytics_snapshot_failed": "❌ Bericht konnte nicht erstellt werden: {error}",
    "analytics_snapshot_dm_disabled": "⚠️ Bericht erstellt, aber DM konnte nicht gesendet werden. Bitte erlaube DMs von Servermitgliedern.",
    "analytics_weekly_enabled": "✅ Wöchentliche Zusammenfassung **aktiviert**! Du erhältst jeden Montagmorgen einen Bericht.",
    "analytics_weekly_disabled": "🔕 Wöchentliche Zusammenfassung **deaktiviert**.",
    "analytics_not_configured": "⚠️ Analytics ist auf dieser Bot-Instanz nicht konfiguriert.",

    # ─── FTS-Enhanced Search ──────────────────────────────────────────────────
    "search_fts_title":             "🔍 Aufgaben suchen",
    "search_fts_empty":             "Keine Aufgaben gefunden, die Ihrer Suche oder den Filtern entsprechen.",
    "search_fts_total":             "{total} Ergebnis(se) gefunden",
    "search_fts_powered":           "Unterstützt durch PostgreSQL Full Text Search",
    "search_sort_relevance":        "📊 Beste Übereinstimmung",
    "search_sort_deadline_asc":     "📅 Früheste Frist",
    "search_sort_deadline_desc":    "📅 Späteste Frist",
    "search_sort_priority":         "🔴 Höchste Priorität",
    "search_sort_created":          "🆕 Neueste zuerst",
    "search_filter_label":          "Filter",
    "search_filter_status":         "Status: {status}",
    "search_filter_priority":       "Priorität: P{min}–P{max}",
    "search_filter_scope_guild":    "Bereich: Server",
    "search_filter_scope_personal": "Bereich: Persönlich",
    "search_btn_prev":              "◀ Zurück",
    "search_btn_next":              "Weiter ▶",
    "search_btn_refresh":           "🔄 Aktualisieren",
    "search_page_indicator":        "📄 {page} / {total}",
    # ─── Recommendation ───────────────────────────────────────────────────────
    "recommend_title":              "🎯 Aufgabenempfehlungen",
    "recommend_desc":               "Ihre Top {count} Prioritätsaufgabe(n) basierend auf Frist, Priorität und Status:",
    "recommend_empty":              "🎉 Keine ausstehenden Aufgaben! Sie sind auf dem neuesten Stand.",
    "recommend_rank":               "#{rank} — {task}",
    "recommend_score":              "Punktzahl: **{score}/100**",
    "recommend_deadline_label":     "⏰ Frist",
    "recommend_priority_label":     "Priorität",
    "recommend_why":                "Warum empfohlen:",
    "recommend_footer":             "Empfehlungs-Engine v1 · Regelbasiert · KI-bereit",
    "recommend_action_finish":      "✅ Abschließen — bereits in Bearbeitung!",
    "recommend_action_overdue":     "🚨 Überfällig — sofort erledigen!",
    "recommend_action_urgent":      "⚡ Bald fällig — als nächstes angehen!",
    "recommend_action_high_priority": "🔴 Hohe Priorität — Zeit einplanen.",
    "recommend_action_start":       "▶️ Mit dieser Aufgabe beginnen.",
    "recommend_breakdown_title":    "📊 Punkteaufschlüsselung",
    "recommend_breakdown_priority":  "Priorität",
    "recommend_breakdown_urgency":   "Dringlichkeit",
    "recommend_breakdown_overdue":   "Überfälligkeit",
    "recommend_breakdown_age":       "Alter",
    "recommend_breakdown_assignment": "Zuweisung",
    "recommend_breakdown_status":    "Status",
    "recommend_scope_personal":     "📋 Persönliche Aufgaben",
    "recommend_scope_guild":        "🏛️ Server-Aufgaben",
    "recommend_weights_info": "Standardgewichtungen: Priorität {priority}% · Dringlichkeit {urgency}% · Überfälligkeit {overdue}%",

    # ─── Snooze Presets ────────────────────────────────────────────────────────
    "snooze_preset_placeholder":  "⏰ Wie lange verschieben?",
    "snooze_preset_1h":           "⏰ +1 Stunde",
    "snooze_preset_3h":           "⏰ +3 Stunden",
    "snooze_preset_1d":           "📅 +1 Tag (gleiche Uhrzeit)",
    "snooze_preset_3d":           "📅 +3 Tage",
    "snooze_preset_next_week":    "📅 Nächsten Montag",

    # ─── Quick Action Dropdown (TaskList / Today / Overdue) ────────────────────
    "quickaction_placeholder":    "⚡ Schnellaktion für eine Aufgabe...",
    "quickaction_done":           "✅ Als erledigt markieren",
    "quickaction_pin":            "📌 Anheften / Lösen",
    "quickaction_snooze":         "⏰ +1 Tag verschieben",
    "quickaction_detail":         "🔍 Details anzeigen",
    "quickaction_select_hint":    "Wähle eine Aufgabe, um eine Aktion auszuführen.",
    "quickaction_none":           "— Aufgabe auswählen —",

    # ─── Today / Overdue View buttons ──────────────────────────────────────────
    "btn_add_task":               "➕ Aufgabe hinzufügen",
    "btn_view_all":               "📋 Alle Aufgaben anzeigen",
    "today_view_title":           "📅 Heutige Aufgaben",
    "overdue_view_title":         "🚨 Überfällige Aufgaben",

    # ─── Search / Recommend Quick Actions ──────────────────────────────────────
    "search_action_placeholder":  "🔍 Suchergebnis öffnen / bearbeiten...",
    "recommend_action_placeholder": "⚡ Schnellaktion für Empfehlung...",

    # ─── Storage Delete Select ─────────────────────────────────────────────────
    "storage_delete_select_placeholder": "🗑️ Datei zum Löschen auswählen...",
    "storage_upload_hint":               "Verwende `/attach [task_id] [datei]`, um weitere Dateien hochzuladen.",

    # ─── Help Categories (extended) ────────────────────────────────────────────
    "help_cat_collab":            "🤝 Zusammenarbeit",
    "help_cat_search":            "🔍 Suche & Analysen",
    "help_cat_files":             "📎 Dateien & Speicher",
    "help_cat_advanced":          "💡 Tipps & Tastenkürzel",
    "help_collab_desc":           "Befehle für geteilte Projektzusammenarbeit",
    "help_search_desc":           "Suche, Empfehlungen und Produktivitätsanalysen",
    "help_files_desc":            "Dateianhänge hochladen und verwalten",
    "help_advanced_desc":         "Profi-Tipps und praktische Tastenkürzel",

    # ─── /add quick-add messages ───────────────────────────────────────────────
    "add_quick_created": "✅ Aufgabe **{task_name}** erstellt! ID: **#{task_id}** · ⏱️ `{time_left}`",
    "add_invalid_priority_choice": "❌ Priorität muss zwischen 0 (Normal) und 7 (Kritisch) liegen.",

    # --- Help Embed Descriptions (settings_cog build_help_embed) ---
    "help_tasks_desc": "Alle Slash-Befehle zum Erstellen, Verfolgen und Abschliessen von Aufgaben:",
    "help_settings_desc": "Konfiguriere deine Einstellungen und organisiere Aufgaben in Kategorien:",
    "help_today": "Aufgaben fuer heute mit Dringlichkeitsmarkierungen anzeigen",
    "help_overdue": "Ueberfaellige Aufgaben anzeigen",
    "help_task_inspect": "Aufgabendetails, Unteraufgaben, Tags und Aktionen anzeigen",
    "help_pin": "Wichtige Aufgaben anpinnen/loesen",
    "help_recurring": "Wiederholungsintervall festlegen (taeglich, woechentlich, monatlich)",
    "help_proj_create": "Neues gemeinsames Projekt im Server erstellen",
    "help_proj_list": "Alle gemeinsamen Projekte mit interaktiver Auswahl anzeigen",
    "help_proj_view": "Projekt-Dashboard, Fortschritt und Mitglieder anzeigen",
    "help_proj_board": "Interaktives Kanban-Aufgaben-Board",
    "help_proj_add_task": "Aufgabe direkt zum Projekt hinzufuegen",
    "help_proj_my_tasks": "Dir zugewiesene Aufgaben in diesem Server anzeigen",
    "help_proj_members": "Projektmitglieder anzeigen und verwalten",
    "help_proj_activity": "Aenderungsprotokoll des Projekts anzeigen",
    "help_proj_archive": "Abgeschlossenes Projekt archivieren",
    "help_search_fts": "Volltextsuche aller Aufgaben mit Filtern",
    "help_recommend": "Intelligente Aufgabenempfehlung nach Fristen und Prioritaet",
    "help_task_stats": "Persoenliche Produktivitaetsstatistiken",
    "help_digest": "Interaktive taegliche Aufgabenzusammenfassung",
    "help_analytics": "Serverweite Aufgabenanalytik",
    "help_attach": "Bild oder Dokument an eine Aufgabe anhaengen",
    "help_attachments": "Anhaenge einer Aufgabe anzeigen oder loeschen",
    "help_cat_list": "Alle Standard- und benutzerdefinierten Kategorien auflisten",
    "help_cat_add": "Neue benutzerdefinierte Kategorie mit Emoji erstellen",
    "help_cat_remove": "Benutzerdefinierte Kategorie loeschen",
    "help_tip_shorthand": "`today 18:00`, `tomorrow`, `+2h`, `+3d`, `25/12` — kein vollstaendiges DD/MM/YYYY noetig!",
    "help_tip_autocomplete": "Beim Eingeben von `/task`, `/done`, `/pin`, `/attach` zeigt Discord deine Aufgaben an!",
    "help_tip_dropdown": "Nutze das Dropdown in `/list`, `/today`, `/overdue` und `/search` fuer schnelle Aktionen.",
    "help_tip_snooze": "Waehle zwischen +1h, +3h, +1d, +3d oder naechstem Montag beim Schlummern!",
    "help_tip_dm": "Der Bot benachrichtigt dich automatisch per DM 24h, 3h und 1h vor Fristen!",
    "help_tip_shorthand_title": "⚡ Kurzbefehle fuer Fristen",
    "help_tip_autocomplete_title": "🔍 Sofort-Autovervollstaendigung",
    "help_tip_dropdown_title": "🎯 Schnellaktions-Dropdown",
    "help_tip_snooze_title": "⏰ Mehrfach-Snooze-Optionen",
    "help_tip_dm_title": "🔔 DM-Erinnerungen",
    # ─── New keys — Bug Fix Round 3 ────────────────────────────────────────────
    "proj_select_dashboard_placeholder": "📂 Projekt-Dashboard auswaehlen...",
    "cat_cannot_remove_default":         "❌ Standard-Kategorien koennen nicht geloescht werden.",
    "task_created_title":                "Aufgabe erstellt!",
    "task_updated_title":                "Aufgabe aktualisiert",
    "confirm_timed_out":                 "⌛ Bestaetigung abgelaufen.",
    "timed_out":                         "⌛ Zeit abgelaufen.",
    "cat_select_placeholder":            "🏷️ Kategorie aendern...",
    "cat_changed_success":               "🏷️ Kategorie aktualisiert!",
    "btn_pin":                           "📍 Anpinnen",
    "btn_unpin":                         "📌 Loesen",
    "task_pinned_badge":                 "📌 Angeheftet",
    "task_unpinned_badge":               "📌 Abgeheftet",
    "stats_refreshed":                   "🔄 Daten aktualisiert ✅",
    "err_with_detail":                   "❌ Ein Fehler ist aufgetreten. Bitte erneut versuchen.\n`{detail}`",
    "monitoring_fetch_failed":           "❌ Daten konnten nicht abgerufen werden — Protokolle pruefen.",
    "refresh_failed":                    "❌ Aktualisierung fehlgeschlagen.",
    "help_quickstart_title":             "🚀 Erste Schritte",
    "help_browse_title":                 "📚 Befehlskategorien",
    "help_category_select_placeholder":  "📖 Hilfekategorie auswaehlen...",
    "err_owner_only":                    "❌ Nur-Besitzer-Befehl.",
    "rt_progress_title":                 "📊 Fortschritt",
    "rt_download_title":                 "🔗 Herunterladen",
    "storage_link_view":                 "🔗 Ansehen",
    "storage_link_download":             "⬇️ Herunterladen",
    "badge_overdue":                     "🔴 UEBERFAELLIG",
    "badge_critical":                    "🟠 KRITISCH",
    "badge_due_today":                   "🟡 HEUTE FAELLIG",
    "badge_upcoming":                    "🔵 BALD FAELLIG",
    "badge_on_track":                    "🟢 AUF KURS",
    "subtasks_more":                     "*(+{count} weitere)*",
    "bot_missing_permissions":           "❌ Dem Bot fehlen Berechtigungen in diesem Kanal.",
    "err_dm_not_allowed":                "❌ Dieser Befehl kann nicht in DMs verwendet werden.",
    "btn_overview_tab":                  "📊 Uebersicht",
    "btn_speed_tab":                     "⏱️ Geschwindigkeit & Puenktlichkeit",

    # ─── Monitoring Setup Modal & Validation ────────────────────────────────
    "monitoring_guild_only":             "❌ Dieser Befehl kann nur auf einem Discord-Server verwendet werden.",
    "monitoring_channel_not_found":      "❌ **Kanal-ID `{ch_id}`** wurde auf diesem Server nicht gefunden.",
    "monitoring_channel_unsendable":     "❌ Kanal `{name}` kann keine Nachrichten empfangen.",
    "monitoring_channel_numeric":        "❌ **Kanal-ID** muss eine Zahl sein.",
    "monitoring_log_channel_saved":      "📢 **Log-Kanal** → {mention}",
    "monitoring_health_interval_saved":  "🏥 **Health-Intervall** → {value} Minuten",
    "monitoring_health_interval_range":  "❌ **Health-Intervall** muss zwischen 1 und 60 Minuten liegen.",
    "monitoring_health_interval_numeric":"❌ **Health-Intervall** muss eine Zahl sein.",
    "monitoring_alert_limit_saved":      "⏱️ **Alert-Rate-Limit** → {value} Sekunden",
    "monitoring_alert_limit_range":      "❌ **Alert-Rate-Limit** muss zwischen 30 und 3600 Sekunden liegen.",
    "monitoring_alert_limit_numeric":    "❌ **Alert-Rate-Limit** muss eine Zahl sein.",
    "monitoring_enabled_saved_on":       "✅ **Monitoring** → Aktiviert ✓",
    "monitoring_enabled_saved_off":      "✅ **Monitoring** → Deaktiviert ✗",
    "monitoring_enabled_boolean":        "❌ **Monitoring aktivieren** muss `true` oder `false` sein.",
    "monitoring_no_changes":             "ℹ️ Keine Änderungen — Füllen Sie mindestens ein Feld aus, um Einstellungen zu speichern.",
    "monitoring_setup_results_title":    "🔧 Monitoring-Setup — Ergebnisse",
    "monitoring_saved_header":           "✅ Erfolgreich gespeichert",
    "monitoring_errors_header":          "⚠️ Fehler gefunden",
    "monitoring_saved_supabase_footer":  "Einstellungen in Supabase gespeichert — sofort wirksam.",
    "monitoring_save_error":             "❌ Fehler beim Speichern — siehe Logs für Details.",
    "monitoring_status_title":           "📋 Monitoring-Einstellungen",
    "monitoring_status_desc":            "Aktuelle Einstellungen für Server **{guild}**",
    "monitoring_not_configured_hint":    "⚠️ Nicht konfiguriert — verwende `/monitoring setup`.",
    "monitoring_channel_not_found_display": "`{ch_id}` (Kanal nicht gefunden)",
    "monitoring_status_channel_label":   "📢 Admin-Log-Kanal",
    "monitoring_status_health_label":    "🏥 Health-Check-Intervall",
    "monitoring_status_health_value":    "{value} Minuten",
    "monitoring_status_rate_label":      "⏱️ Alert-Rate-Limit",
    "monitoring_status_rate_value":      "{value} Sekunden",
    "monitoring_status_enabled_label":   "✅ Monitoring aktiviert",
    "monitoring_status_active":          "Aktiviert ✓",
    "monitoring_status_inactive":        "Deaktiviert ✗",
    "monitoring_status_footer":          "Bearbeiten mit /monitoring setup · In Supabase gespeichert",
    "monitoring_status_fetch_error":     "❌ Einstellungen konnten nicht abgerufen werden — siehe Logs.",

    # ─── Health Embed ────────────────────────────────────────────────────────
    "health_status_title":       "🏥 Bot-Gesundheitsstatus — {status}",
    "health_healthy":            "🟢 Gesund",
    "health_degraded":           "🔴 Beeinträchtigt",
    "health_uptime":             "Betriebszeit",
    "health_guilds":             "Server",
    "health_discord_latency":    "Discord-Latenz",
    "health_database":           "🗄️ Datenbank",
    "health_db_ping":            "Ping",
    "health_pool_size":          "Pool-Größe",
    "health_system":             "💾 System",
    "health_memory":             "Speicher",
    "health_loop_lag":           "Loop-Verzögerung",
    "health_last_checked":       "Zuletzt geprüft",
    "health_db_unreachable":     "❌ Nicht erreichbar",
    "health_mem_unavailable":    "N/A (psutil nicht installiert)",
    "health_bot_label":          "🤖 Bot",

    # ─── Error Tracker Embed ─────────────────────────────────────────────────
    "error_report_title":        "🚨 Fehlerbericht (Letzte 24 Std.)",
    "error_overview_label":      "📊 Übersicht",
    "error_total_errors":        "Fehler gesamt",
    "error_unique_types":        "Einzigartige Typen",
    "error_next_reset":          "Nächster Reset",
    "error_top_title":           "✅ Status",
    "error_none_recorded":       "Keine Fehler aufgezeichnet — alles in Ordnung!",
    "error_last_seen":           "Zuletzt gesehen",
    "error_command":             "Befehl",
    "error_user":                "Benutzer",

    # ─── Command Stats Embed ─────────────────────────────────────────────────
    "cmdstats_title":            "📊 Befehlsnutzungsstatistik",
    "cmdstats_overview_label":   "📈 Übersicht",
    "cmdstats_total_commands":   "Aufrufe gesamt",
    "cmdstats_failed":           "Fehler",
    "cmdstats_error_rate":       "Fehlerrate",
    "cmdstats_top_commands":     "🏆 Top-Befehle",
    "cmdstats_top_errors":       "⚠️ Häufige Fehlertypen",
    "cmdstats_footer":           "Statistik seit letztem Neustart",

    # ─── Analytics Field Labels ──────────────────────────────────────────────
    "analytics_field_score":     "🏆 Produktivitätspunktzahl",
    "analytics_field_completed": "✅ Erledigt",
    "analytics_field_ontime":    "⏱️ Pünktlichkeitsrate",
    "analytics_weekly_status":   "Wöchentliche Zusammenfassung",
}

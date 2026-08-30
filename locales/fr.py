"""
French (FR) language strings — Français
"""

STRINGS = {
    # ─── General ───────────────────────────────────────────────────────────────
    "lang_name": "Français",
    "lang_flag": "🇫🇷",
    "yes": "Oui",
    "no": "Non",
    "cancel": "Annuler",
    "confirm": "Confirmer",
    "success": "Succès",
    "error": "Erreur",
    "warning": "Avertissement",
    "loading": "Chargement...",
    "not_found": "Introuvable",
    "permission_denied": "❌ Vous n'avez pas la permission d'utiliser cette commande",
    "bot_name": "📝 To-Do List Bot Gen 2",
    "footer_text": "To-Do List Bot Gen 2 • Conçu pour une productivité maximale",

    # ─── Rate Limiting ──────────────────────────────────────────────────────────
    "rate_limited": "⏳ Vous envoyez des commandes trop vite. Veuillez attendre **{seconds:.0f} secondes** et réessayer.",
    "task_rate_limited": "⏳ Vous avez dépassé la limite de création de tâches ({limit}/heure). Veuillez attendre **{seconds:.0f} secondes**.",

    # ─── Setup ─────────────────────────────────────────────────────────────────
    "setup_title": "⚙️ Configuration du Bot",
    "setup_desc": "Configurez les paramètres suivants pour commencer.",
    "setup_timezone": "Fuseau horaire",
    "setup_timezone_desc": "Exemple : Europe/Paris, UTC, America/Montreal",
    "setup_success": "✅ Configuration terminée ! Fuseau horaire : **{tz}** | Salon : {channel}",
    "setup_checklist": "✅ Fuseau horaire  ✅ Salon de notifications  ☑️ Langue (utilisez `/lang`)",
    "setup_invalid_tz": "❌ Fuseau horaire `{tz}` invalide. Veuillez vérifier et réessayer.\n[Liste des fuseaux horaires](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)",
    "setup_channel_required": "❌ Veuillez utiliser cette commande dans un salon Discord.",

    # ─── Language ──────────────────────────────────────────────────────────────
    "lang_changed": "✅ Langue changée en **Français** avec succès.",
    "lang_select_title": "🌐 Sélectionner la langue / Select Language",
    "lang_select_desc": "Choisissez votre langue préférée.",

    # ─── Task Creation ──────────────────────────────────────────────────────────
    "task_add_title": "➕ Ajouter une nouvelle tâche",
    "task_name_label": "Nom de la tâche",
    "task_name_placeholder": "Ex : Rendre le rapport, Réunion d'équipe",
    "task_deadline_label": "Date limite (JJ/MM/AAAA HH:MM)",
    "task_deadline_placeholder": "Ex : 25/12/2025 18:00",
    "task_priority_label": "⚡ Priorité",
    "task_priority_placeholder": "0–7 (0=Normale, 3=Moyenne, 5=Importante, 7=Critique)",
    "task_desc_label": "Description (optionnelle)",
    "task_desc_placeholder": "Détails supplémentaires...",
    "task_tags_label": "Étiquettes (optionnelles)",
    "task_tags_placeholder": "Ex : travail, urgent, maison",
    "task_created": "✅ Tâche créée avec succès ! ID : **#{task_id}**",
    "task_invalid_deadline": "❌ Format de date invalide. Utilisez : `JJ/MM/AAAA HH:MM`\nExemple : `25/12/2025 18:00`",
    "task_past_deadline": "❌ La date limite doit être dans le futur.",
    "task_invalid_priority": "❌ La priorité doit être un nombre entre 0 et 7.",
    "task_name_too_long": "❌ Le nom de la tâche est trop long (200 caractères max).",
    "task_desc_too_long": "❌ La description est trop longue (1000 caractères max).",

    # ─── Task List ──────────────────────────────────────────────────────────────
    "tasks_title": "📋 Vos tâches",
    "tasks_empty": "📭 Aucune tâche pour le moment.\nAppuyez sur **`/add`** pour créer votre première tâche !",
    "tasks_page": "Page {page}/{total}",
    "tasks_total": "Total des tâches : **{count}**",
    "tasks_summary": "{total} tâches · {overdue} en retard",
    "today_summary": "📅 Aujourd'hui : **{count}** tâche(s) · ⚠️ En retard : **{overdue}**",
    "overdue_summary": "🚨 Total en retard : **{total}** tâche(s)",
    "tasks_filter_pending": "⏳ En attente",
    "tasks_filter_Pending": "⏳ En attente",
    "tasks_filter_done": "✅ Terminée",
    "tasks_filter_Completed": "✅ Terminée",
    "tasks_filter_cancelled": "❌ Annulée",
    "tasks_filter_Cancelled": "❌ Annulée",
    "tasks_filter_all": "📋 Toutes",
    "tasks_filter_today": "📅 Aujourd'hui",
    "tasks_filter_overdue": "🚨 En retard",
    "tasks_filter_pinned": "📌 Épinglées",
    "list_filter_placeholder": "🔽 Filtrer par statut...",

    # ─── Task Details ───────────────────────────────────────────────────────────
    "task_detail_title": "📌 Détails de la tâche #{task_id}",
    "task_detail_name": "📝 Nom de la tâche",
    "task_detail_status": "🔖 Statut",
    "task_detail_deadline": "📅 Date limite",
    "task_detail_priority": "⚡ Priorité",
    "task_detail_category": "🏷️ Catégorie",
    "task_detail_tags": "🔖 Étiquettes",
    "task_detail_desc": "📄 Description",
    "task_detail_recurring": "🔄 Répétition",
    "task_detail_subtasks": "📊 Sous-tâches",
    "task_detail_created": "📆 Créée le",
    "task_detail_updated": "🔄 Dernière mise à jour",
    "task_not_found": "❌ Tâche #**{task_id}** introuvable.",
    "task_not_owned": "❌ Cette tâche ne vous appartient pas.",

    # ─── Task Actions ───────────────────────────────────────────────────────────
    "btn_done": "✅ Terminer",
    "btn_mark_done": "✅ Marquer comme terminée",
    "btn_delete": "🗑️ Supprimer",
    "btn_edit": "✏️ Modifier",
    "btn_subtask": "➕ Sous-tâche",
    "btn_snooze": "⏰ Reporter (+1 jour)",
    "btn_prev": "◀ Précédent",
    "btn_next": "Suivant ▶",
    "btn_refresh": "🔄 Actualiser",
    "btn_back": "🔙 Retour",
    "btn_confirm_delete": "🗑️ Confirmer la suppression",
    "page_indicator": "📄 Page {page} / {total}",
    # Delete confirm embed
    "delete_confirm_title": "⚠️ Confirmer la suppression",
    "delete_confirm_desc": "Êtes-vous sûr de vouloir supprimer définitivement cette tâche ?\n> **{task_name}**\n\n⚠️ Cette action **ne peut pas être annulée**.",

    "task_marked_done": "✅ Tâche **#{task_id}** marquée comme terminée !",
    "task_already_done": "⚠️ Cette tâche est déjà terminée.",
    "task_already_cancelled": "⚠️ Cette tâche est déjà annulée.",
    "task_deleted": "🗑️ Tâche **#{task_id}** a été supprimée.",
    "task_delete_confirm": "⚠️ Êtes-vous sûr de vouloir supprimer cette tâche ?\n> **{task_name}**\nCette action ne peut pas être annulée.",

    # ─── Pin / Unpin ────────────────────────────────────────────────────────────
    "task_pinned": "📌 Tâche **#{task_id}** épinglée avec succès.",
    "task_unpinned": "📌 Tâche **#{task_id}** désépinglée.",

    # ─── Task Edit ──────────────────────────────────────────────────────────────
    "task_edit_title": "✏️ Modifier la tâche #{task_id}",
    "task_edit_success": "✅ Tâche mise à jour avec succès.",

    # ─── Subtasks ──────────────────────────────────────────────────────────────
    "subtask_add_title": "➕ Ajouter une sous-tâche",
    "subtask_for": "Pour la tâche : **{parent_name}**",
    "subtask_created": "✅ Sous-tâche créée avec succès !",
    "subtask_no_nested": "⚠️ Vous ne pouvez pas ajouter de sous-tâche à une autre sous-tâche.",
    "subtask_progress": "Sous-tâches : {done}/{total} ({pct:.0f}%)",

    # ─── Categories ─────────────────────────────────────────────────────────────
    "cat_title": "🏷️ Catégories",
    "cat_list_title": "📂 Toutes les catégories",
    "cat_empty": "Aucune catégorie pour le moment.",
    "cat_section_default": "📌 Catégories par défaut",
    "cat_section_custom": "🗂️ Vos catégories",
    "cat_add_title": "➕ Ajouter une nouvelle catégorie",
    "cat_name_label": "Nom de la catégorie",
    "cat_emoji_label": "Emoji (optionnel)",
    "cat_created": "✅ Catégorie **{name}** créée !",
    "cat_not_found": "❌ Catégorie introuvable.",

    # ─── Priority Labels ─────────────────────────────────────────────────
    "priority_0": "⬜ Normale",
    "priority_1": "🟦 Faible",
    "priority_2": "🟩 Moyenne-Basse",
    "priority_3": "🟨 Moyenne",
    "priority_4": "🟧 Moyenne-Haute",
    "priority_5": "🟥 Importante",
    "priority_6": "🔴 Urgente",
    "priority_7": "🆘 Critique",
    # Dropdown descriptions
    "priority_0_desc": "Pas urgent, à faire quand possible",
    "priority_1_desc": "Peu urgent, peut attendre",
    "priority_2_desc": "À traiter cette semaine",
    "priority_3_desc": "À faire dans les prochains jours",
    "priority_4_desc": "Important, à faire aujourd'hui ou demain",
    "priority_5_desc": "Urgent ! Agir dans les prochaines heures",
    "priority_6_desc": "Très urgent ! Agir immédiatement",
    "priority_7_desc": "Critique ! Impact majeur, à régler tout de suite",
    # Dropdown UI strings
    "priority_select_placeholder": "⚡ Choisissez le niveau de priorité...",
    "priority_select_title": "⚡ Sélectionner la priorité",
    "priority_select_desc": "Choisissez le niveau de priorité avant de renseigner les détails.",
    "priority_changed": "✅ Priorité mise à jour ! La tâche **#{task_id}** est désormais **{priority}**",
    # Legacy aliases (kept for backward compat)
    "priority_low": "⬜ Normale",
    "priority_medium": "🟨 Moyenne",
    "priority_high": "🔴 Urgente",

    # ─── Status Labels ──────────────────────────────────────────────────────────
    "status_pending": "⏳ En attente",
    "status_completed": "✅ Terminée",
    "status_cancelled": "❌ Annulée",
    "status_overdue": "🚨 En retard",

    # ─── Recurring ──────────────────────────────────────────────────────────────
    "recurring_daily": "🔄 Quotidienne",
    "recurring_weekly": "🔄 Hebdomadaire",
    "recurring_monthly": "🔄 Mensuelle",
    "recurring_none": "—",

    # ─── Reminders ──────────────────────────────────────────────────────────────
    "reminder_title": "⏰ Rappel de tâche",
    "reminder_overdue": "🚨 **Tâche en retard !**\n`{task}` devait être terminée le {deadline}",
    "reminder_due_soon": "⚡ **Tâche bientôt due !**\n`{task}` arrive à échéance dans {time_left}",
    "reminder_due_today": "📅 **Tâche due aujourd'hui !**\n`{task}` arrive à échéance à {time}",
    "reminder_action_hint": "Utilisez `/done {task_id}` ou cliquez sur ✅ Terminer sur la tâche pour arrêter les rappels.",

    # DM deadline reminders
    "dm_reminder_title": "⏰ Rappel d'échéance (MP)",
    "dm_reminder_24h": "📅 **Votre tâche approche de son échéance !**\nIl ne reste que **{time_left}** pour `{task}`.",
    "dm_reminder_3h": "🟠 **Moins de 3 heures restantes !**\nL'échéance de `{task}` approche à grands pas ! Plus que **{time_left}**.",
    "dm_reminder_1h": "🚨 **Moins d'une heure restante !**\n`{task}` est presque arrivée à échéance ! Il ne reste que **{time_left}** !",
    "dm_reminder_footer": "Déjà terminé ? Utilisez `/done {task_id}` ou cliquez sur ✅ Terminer pour arrêter les rappels.",

    # ─── Export ─────────────────────────────────────────────────────────────────
    "export_success": "📤 Exportation terminée ! Fichier : `{filename}`",
    "export_empty": "📭 Aucune donnée à exporter.",
    "export_rate_limited": "⏳ Vous avez dépassé la limite d'exportation ({limit}/jour). Réessayez demain.",

    # ─── Search ─────────────────────────────────────────────────────────────────
    "search_title": "🔍 Résultats de recherche : `{query}`",
    "search_results_count": "🔍 Recherche : **{query}** — {count} résultat(s) trouvé(s)",
    "search_empty": "🔍 Aucune tâche correspondant à `{query}` trouvée.",
    "search_query_label": "Terme de recherche",
    "search_query_placeholder": "Nom de tâche ou étiquette...",

    # ─── Stats ──────────────────────────────────────────────────────────────────
    "stats_title": "📊 Vos statistiques",
    "stats_total": "Total des tâches",
    "stats_completed": "Terminées",
    "stats_pending": "En attente",
    "stats_overdue": "En retard",
    "stats_completion_rate": "Taux de complétion",
    "stats_categories": "Catégories utilisées",
    # Dynamic stats header messages
    "stats_header_on_track": "🎯 Tout est sur les rails !",
    "stats_header_overdue": "⚠️ {overdue} tâche(s) en retard !",
    "stats_header_all_done": "🏆 Tout est terminé !",
    "stats_header_empty": "📭 Aucune tâche pour l'instant",
    # Motivational notes in /stats embed
    "stats_note_empty": "Aucune tâche pour l'instant ! Utilisez `/add` pour commencer 🚀",
    "stats_note_overdue": "⚠️ {overdue} tâche(s) en retard — utilisez `/overdue` pour vérifier",
    "stats_note_all_done": "🏆 Toutes les tâches sont terminées ! Travail exceptionnel !",
    "stats_note_progress": "Vous avez complété {pct}% — continuez ainsi !",

    # ─── Help ───────────────────────────────────────────────────────────────────
    "help_title": "📖 To-Do List Bot Gen 2 — Aide",
    "help_desc": "Un bot complet de gestion de tâches avec support multilingue.",
    "help_commands": "Toutes les commandes",
    "help_quickstart": "🚀 Démarrage rapide\n`1.` Utilisez `/setup Europe/Paris` pour définir votre fuseau horaire\n`2.` Utilisez `/add` pour créer votre première tâche\n`3.` Utilisez `/list` pour afficher toutes vos tâches",
    "help_add": "Ajouter une nouvelle tâche",
    "help_list": "Afficher toutes les tâches",
    "help_done": "Marquer une tâche comme terminée",
    "help_delete": "Supprimer une tâche",
    "help_edit": "Modifier une tâche",
    "help_search": "Rechercher des tâches",
    "help_categories": "Gérer les catégories",
    "help_stats": "Consulter vos statistiques",
    "help_export": "Exporter les tâches en CSV",
    "help_setup": "Configurer le bot",
    "help_lang": "Changer de langue",
    "help_reminder": "Définir des rappels",

    # ─── Errors ─────────────────────────────────────────────────────────────────
    "err_generic": "❌ Une erreur est survenue. Veuillez réessayer.",
    "err_db": "❌ Une erreur de base de données est survenue. Veuillez contacter un administrateur.",
    "err_no_setup": "⚠️ Veuillez d'abord configurer le bot avec `/setup`.",
    "err_input_invalid": "❌ Entrée invalide : {detail}",
    "err_suspicious": "🚫 Comportement suspect détecté. Commande bloquée.",

    # ─── Snooze Confirm ─────────────────────────────────────────────────────────
    "snooze_confirm_title": "⏰ Confirmer le report",
    "snooze_confirm_desc": "Êtes-vous sûr de vouloir reporter cette tâche d'un jour ?\n> **{task_name}**\n📅 Nouvelle date limite : `{new_deadline}`",
    "btn_confirm_snooze": "⏰ Confirmer (+1 jour)",

    # ─── Help Categories (Interactive Select) ───────────────────────────────────
    "help_cat_overview": "🚀 Aperçu et démarrage rapide",
    "help_cat_tasks": "📝 Commandes de tâches",
    "help_cat_settings": "⚙️ Paramètres et catégories",
    "help_cat_tips": "💡 Conseils et astuces",
    "help_version_footer": "To-Do List Bot Gen 2 • /help • github.com",

    # ─── Daily Digest & Overdue ─────────────────────────────────────────────────
    "digest_title": "☀️ Récapitulatif quotidien des tâches — {date}",
    "digest_no_tasks": "Aucune tâche due aujourd'hui !",
    "digest_today_tasks": "Tâches du jour",
    "digest_upcoming_title": "🔮 Tâches à venir (3 prochains jours)",
    "digest_motivational_clean": "✨ Super ! Rien de prévu aujourd'hui. Passez une excellente journée !",
    "digest_motivational_busy": "💪 Vous avez {count} tâche(s) aujourd'hui. Restez concentré et bon courage !",
    "digest_motivational_overdue": "⚠️ Attention ! Vous avez {overdue} tâche(s) en retard. Rapprochons-nous du but !",
    "overdue_none": "Aucune tâche en retard ! Vous êtes parfaitement à jour 🎉",
    "overdue_note": "💪 Vous pouvez le faire ! Finalisez vos tâches en retard aujourd'hui.",
    "task_done_with_name": "✅ Tâche **#{task_id}** ({task_name}) marquée comme terminée !",

    # ─── Settings & Meta ────────────────────────────────────────────────────────
    "setup_current_tz": "Fuseau horaire actuel : **{tz}**",
    "lang_current_active": "Langue actuellement active : {flag} **{name}**",
    "cat_task_count": "{count} tâche(s)",
    "task_detail_created": "Créée le",
    "task_detail_updated": "Mise à jour",

    # ─── UX/UI Additions (stubs — fall back to EN) ───────────────────────────────
    # "cat_no_category", "cat_removed", "setup_lang_field", "stats_cancelled",
    # "priority_timeout", "reminder_field_*", "dm_reminder_field_*", "digest_stats_line"
    # etc. are intentionally omitted; the i18n system falls back to EN automatically.
}

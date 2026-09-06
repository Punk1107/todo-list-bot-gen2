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

    # ─── UX/UI Additions ─────────────────────────────────────────────────────────
    'cat_no_category': '— Sans catégorie',
    'cat_removed': '🗑️ Catégorie **{name}** supprimée.',
    'setup_lang_field': '🌐 Langue',
    'stats_cancelled': 'Annulée',
    'priority_timeout': '⌛ Délai de sélection écoulé. Veuillez réexécuter la commande.',
    'reminder_field_deadline': '📅 Échéance',
    'reminder_field_priority': '⚡ Priorité',
    'reminder_field_task_id': '🆔 ID Tâche',
    'dm_reminder_field_time_left': '⏱️ Temps restant',
    'digest_stats_line': '📊 **{pending}** en attente  ·  🚨 **{overdue}** en retard',
    'help_overview_browse': 'Utilisez le menu déroulant ci-dessous pour consulter les guides de commandes :\n• **📝 Commandes de Tâches** : Créer, modifier, terminer et organiser\n• **⚙️ Paramètres & Catégories** : Fuseau horaire, langue, catégories\n• **💡 Conseils & Raccourcis** : Bonnes pratiques et fonctionnalités intelligentes',

    # ─── Productivity Analytics (/task-stats) ─────────────────────────────────────────────────────────
    'taskstats_title': '📊 Tableau de Bord de Productivité  ·  {username}',
    'taskstats_overview_tab': "📊 Vue d'ensemble",
    'taskstats_speed_tab': '⏱️ Vitesse & Ponctualité',
    'taskstats_refresh': '🔄 Actualiser',
    'taskstats_score_label': '🏆 Score de Productivité',
    'taskstats_score_value': '{score}/100  {badge}',
    'taskstats_completion_label': '✅ Taux de Réalisation',
    'taskstats_completion_value': '{rate}%  ({done}/{total} tâches)',
    'taskstats_velocity_label': '⚡ Vélocité',
    'taskstats_velocity_value': '7 jours : **{v7}** tâches  ·  30 jours : **{v30}** tâches',
    'taskstats_streak_label': '🔥 Série en cours',
    'taskstats_streak_value': "{days} jours d'affilée",
    'taskstats_pending_overdue': '⏳ En attente : **{pending}**  ·  🚨 En retard : **{overdue}**',
    'taskstats_speed_title': '⏱️ Analyse de Vitesse & Ponctualité  ·  {username}',
    'taskstats_ontime_label': '✅ Terminées à Temps',
    'taskstats_ontime_value': '{rate}%  ({count} tâches)',
    'taskstats_late_label': '⚠️ Terminées en Retard',
    'taskstats_late_value': '{rate}%  ({count} tâches)',
    'taskstats_turnaround_label': "⏰ Délai Moyen d'Exécution",
    'taskstats_turnaround_value': '{hours}',
    'taskstats_lead_label': '🚀 Avance Moyenne (tâches à temps)',
    'taskstats_lead_value': "{hours} avant l'échéance",
    'taskstats_lag_label': '🐌 Retard Moyen (tâches en retard)',
    'taskstats_lag_value': "{hours} après l'échéance",
    'taskstats_no_completed': "Aucune tâche terminée pour le moment — terminez votre première tâche aujourd'hui ! 🚀",
    'taskstats_tip_label': '💡 Conseil Personnalisé',
    'badge_master': '🏆 Maître de la Productivité',
    'badge_pro': '🎯 Pro de la Ponctualité',
    'badge_achiever': '🛡️ Réalisateur Régulier',
    'badge_rising': '⚡ Élan Ascendant',
    'badge_pacing': '🐢 Besoin de Concentration',
    'badge_new': '🌱 Tout Juste Démarré',
    'tip_master': 'Remarquable ! Vous dépassez les attentes. Osez viser encore plus haut !',
    'tip_pro': "Quasiment parfait ! Essayez de planifier 10 minutes à l'avance chaque jour pour booster votre score.",
    'tip_achiever': "Bel élan ! Essayez d'ajouter des sous-tâches aux projets importants pour accélérer votre rythme.",
    'tip_rising': 'En pleine progression ! Triez vos tâches par priorité pour aiguiser votre concentration.',
    'tip_pacing': 'Ne baissez pas les bras ! Découpez les grandes tâches et réservez des créneaux chaque jour.',
    'tip_new': "C'est parti ! Ajoutez votre première tâche avec `/add` et terminez-la aujourd'hui ! 💪",
    'duration_days': '{d}j {h}h',
    'duration_hours': '{h}h {m}m',
    'duration_mins': '{m}m',
    'duration_na': 'Pas encore de données',

    # ─── On-Demand /digest command ─────────────────────────────────────────────────────────
    'digest_cmd_desc': '☀️ Consultez instantanément le résumé de vos tâches du jour',
    'digest_btn_list': '📋 Voir toutes les tâches',
    'digest_btn_add': '➕ Ajouter une tâche',
    'digest_btn_refresh': '🔄 Actualiser',

    # ─── Conflict Resolution & Defensive Programming ─────────────────────────────────────────────────────────
    'task_past_deadline_detailed': "❌ L'échéance doit être dans le futur.\n🕒 Votre heure actuelle : **{current_time}**\n📅 Heure saisie : **{input_time}**",
    'task_invalid_year': "❌ L'année indiquée est hors limites (2000 – année actuelle +10).",
    'subtask_deadline_exceeds_parent': "❌ L'échéance de la sous-tâche ({subtask_dl}) ne peut pas dépasser celle de la tâche principale ({parent_dl}).",
    'subtask_parent_closed': "❌ Impossible d'ajouter une sous-tâche à une tâche terminée ou annulée.",
    'conflict_duplicate_title': '⚠️ Conflit détecté : Nom de tâche en double',
    'conflict_duplicate_desc': 'Une tâche en attente nommée **"{existing_name}"** (ID: **#{existing_id}**) existe déjà.\nÉchéance existante : **{existing_deadline}**\n\nComment souhaitez-vous procéder ?',
    'btn_conflict_autorename': '🏷️ Enregistrer sous "{new_name}"',
    'btn_conflict_force': '⚡ Créer quand même',
    'btn_conflict_view': '🔍 Voir la tâche existante',
    'btn_conflict_cancel': '❌ Annuler',
    'conflict_cancelled': '❌ Création de tâche annulée.',
    'conflict_autorename_done': '✅ Tâche enregistrée sous **"{new_name}"** ! ID: **#{task_id}**',
    'edit_past_deadline_blocked': "❌ L'échéance ne peut pas être fixée dans le passé.\n🕒 Votre heure actuelle : **{current_time}**\n📅 Heure saisie : **{input_time}**",
}


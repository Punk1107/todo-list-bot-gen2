"""
i18n -- Internationalisation Manager
Handles TH / EN / ZH / JA / KO / ES / RU / FR / DE language switching per-user.
Language is persisted in the database and cached in UserCache.
"""
from __future__ import annotations
import logging
from typing import Any

log = logging.getLogger(__name__)

SUPPORTED_LANGS = ("th", "en", "zh", "ja", "ko", "es", "ru", "fr", "de")
DEFAULT_LANG = "en"   # fallback when Discord locale does not match any supported lang

DISCORD_NATIVE_FALLBACKS = {
    "context_task_empty": "❌ This message has no text to turn into a task.",
    "context_task_created": "✅ Created task **#{task_id}** from the selected message.",
    "context_source_message": "🔗 Source message",
    "context_jump_link": "Jump to source message",
    "bulk_no_tasks": "📭 You have no open tasks to update.",
    "bulk_select_placeholder": "Select tasks (you can select multiple)",
    "bulk_picker_description": "Select tasks to update · **{selected}** selected · page {page}/{pages}",
    "bulk_select_at_least_one": "Select at least one task first.",
    "bulk_delete_warning": "⚠️ Permanently delete **{count}** selected task(s)? Press Delete again to confirm.",
    "bulk_delete_confirm": "🗑️ Confirm delete",
    "bulk_apply": "Apply",
    "bulk_result": "✅ Completed: **{succeeded}** · Failed or no longer available: **{failed}**",
    "proj_btn_thread": "🧵 Task Thread",
    "proj_thread_public_button": "🌐 Public Thread",
    "proj_thread_private_button": "🔒 Private Thread",
    "proj_thread_select_task": "Choose an active task",
    "proj_thread_picker_description": "Select a task, then choose a public or private discussion thread.",
    "proj_thread_selected": "Selected task **#{task_id}**. Choose the thread visibility below.",
    "proj_thread_select_first": "Choose a task before creating its thread.",
    "proj_thread_no_tasks": "There are no active project tasks to discuss.",
    "proj_thread_channel_required": "Configure a text channel for this project, or open the board in a text channel.",
    "proj_thread_starter": "Discussion for project task **#{task_id}: {task_name}**",
    "proj_thread_created": "✅ Discussion thread created: {url}",
    "proj_thread_exists": "This task already has a discussion thread: {url}",
    "proj_thread_pending": "A discussion thread is already being created for this task. Please try again shortly.",
    "proj_thread_permission_error": "The bot is missing permission to create or manage this thread in the configured channel.",
    "proj_dependency_added": "✅ Task **#{task_id}** now waits for task **#{blocked_by_task_id}**.",
    "proj_dependency_removed": "✅ Removed the dependency from task **#{task_id}** to task **#{blocked_by_task_id}**.",
    "proj_dependency_duplicate": "That dependency already exists.",
    "proj_dependency_missing": "That dependency does not exist.",
    "proj_dependency_cycle": "That dependency would create a cycle.",
    "proj_task_blocked": "⛔ This task cannot progress until these tasks are completed: {blockers}",
    "proj_role_assigned": "✅ Assigned task **#{task_id}** to {role}. Direct messages sent: **{sent}**; failed: **{failed}**.",
    "proj_role_already_assigned": "That role is already assigned to this task.",
    "proj_workload_title": "📊 Workload — {project}",
    "proj_workload_empty": "There are no active tasks in this project.",
    "proj_workload_members": "Member workload",
    "proj_workload_roles": "Role assignments",
    "proj_workload_unassigned": "Unassigned tasks",
    "proj_workload_member_line": "<@{user_id}> — **{count}** active task(s)",
    "proj_workload_role_line": "<@&{role_id}> — **{count}** active task(s)",
    "proj_workload_unassigned_line": "**{count}** task(s)",
    "proj_role_missing": "That Discord role is no longer available in this server.",
    "task_no_deadline": "No deadline",
    "task_deadline_required_for_recurring": "A recurring task must have a deadline. Set a deadline before enabling recurrence.",
    "calendar_public_url_missing": "Calendar feeds require a public HTTPS URL. Set CALENDAR_PUBLIC_URL and try again.",
    "calendar_link_created": "✅ Your private calendar subscription link (keep it secret):\n{url}\nUse `/calendar rotate` to replace it or `/calendar revoke` to disable it.",
    "calendar_revoked": "✅ Calendar subscription disabled.",
    "calendar_no_link": "There is no active calendar subscription to revoke.",
    "import_file_too_large": "❌ The file exceeds the 1 MB import limit.",
    "import_validation_error": "❌ Import cancelled; no tasks were added.\n{error}",
    "import_read_error": "❌ Could not read the attached file: {error}",
    "import_database_error": "❌ Import failed while saving. No tasks were added.",
    "import_success": "✅ Imported **{count}** task(s).",
}

# -- Discord locale -> our lang code -------------------------------------------
# Discord locale strings: https://discord.com/developers/docs/reference#locales
DISCORD_LOCALE_MAP: dict[str, str] = {
    "th":     "th",
    "en-us":  "en",
    "en-gb":  "en",
    "zh-cn":  "zh",
    "zh-tw":  "zh",   # Traditional -> Simplified as best-effort
    "ja":     "ja",
    "ko":     "ko",
    "es-es":  "es",
    "es-419": "es",  # Latin America Spanish
    "ru":     "ru",
    "fr":     "fr",
    "de":     "de",
}


def locale_to_lang(discord_locale: str) -> str:
    """Map a Discord locale string to our internal lang code.

    Normalises the locale to lowercase and replaces underscores with hyphens
    before lookup.  If no exact match is found, tries the base language code
    (e.g. 'en-AU' -> 'en').  Returns DEFAULT_LANG if nothing matches.
    """
    if not discord_locale:
        return DEFAULT_LANG
    norm = str(discord_locale).lower().replace("_", "-")
    if norm in DISCORD_LOCALE_MAP:
        return DISCORD_LOCALE_MAP[norm]
    # Direct match against our supported lang codes ("en", "zh", etc.)
    if norm in SUPPORTED_LANGS:
        return norm
    # Fallback to base language code ("en-AU" -> "en")
    base = norm.split("-")[0]
    if base in SUPPORTED_LANGS:
        return base
    return DEFAULT_LANG


# Lazy-load locale modules
_CACHE: dict[str, dict] = {}


def _load(lang: str) -> dict:
    if lang not in _CACHE:
        if lang == "th":
            from locales.th import STRINGS
        elif lang == "en":
            from locales.en import STRINGS
        elif lang == "zh":
            from locales.zh import STRINGS
        elif lang == "ja":
            from locales.ja import STRINGS
        elif lang == "ko":
            from locales.ko import STRINGS
        elif lang == "es":
            from locales.es import STRINGS
        elif lang == "ru":
            from locales.ru import STRINGS
        elif lang == "fr":
            from locales.fr import STRINGS
        elif lang == "de":
            from locales.de import STRINGS
        else:
            from locales.en import STRINGS   # safe fallback
        _CACHE[lang] = STRINGS
    return _CACHE[lang]


class _SafeDict(dict):
    """dict subclass that returns '{key}' for missing keys instead of raising KeyError.

    Used with str.format_map() so partially-applied templates never crash.
    """
    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"


def t(key: str, lang: str = DEFAULT_LANG, **kwargs: Any) -> str:
    """
    Translate a key for the given language.
    Falls back to English, then the raw key if missing.

    Usage:
        t("task_created", lang="ja", task_id=42)
    """
    # Normalise lang: guard against None / empty / unsupported
    if not lang or lang not in SUPPORTED_LANGS:
        lang = DEFAULT_LANG

    strings  = _load(lang)
    fallback = _load(DEFAULT_LANG)

    template = strings.get(key) or fallback.get(key) or DISCORD_NATIVE_FALLBACKS.get(key) or key
    if not kwargs:
        return template
    try:
        return template.format_map(_SafeDict(kwargs))
    except (KeyError, ValueError, IndexError, AttributeError) as exc:
        log.warning("i18n format error -- key=%s lang=%s err=%s", key, lang, exc)
        return template


def get_flag(lang: str) -> str:
    return _load(lang).get("lang_flag", "🌐")


def get_lang_name(lang: str) -> str:
    return _load(lang).get("lang_name", lang.upper())
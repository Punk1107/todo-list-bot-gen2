"""
i18n — Internationalisation Manager
Handles TH / EN / ZH / JA / KO / ES language switching per-user.
Language is persisted in the database and cached in UserCache.
"""
from __future__ import annotations
import logging
from typing import Any

log = logging.getLogger(__name__)

SUPPORTED_LANGS = ("th", "en", "zh", "ja", "ko", "es")
DEFAULT_LANG = "en"   # fallback when Discord locale does not match any supported lang

# ── Discord locale → our lang code ───────────────────────────────────────────
# Discord locale strings: https://discord.com/developers/docs/reference#locales
DISCORD_LOCALE_MAP: dict[str, str] = {
    "th":    "th",
    "en-US": "en",
    "en-GB": "en",
    "zh-CN": "zh",
    "zh-TW": "zh",   # Traditional → Simplified as best-effort
    "ja":    "ja",
    "ko":    "ko",
    "es-ES": "es",
    "es-419": "es",  # Latin America Spanish
}


def locale_to_lang(discord_locale: str) -> str:
    """Map a Discord locale string to our internal lang code.
    Returns DEFAULT_LANG if no match is found.
    """
    return DISCORD_LOCALE_MAP.get(str(discord_locale), DEFAULT_LANG)


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
        else:
            from locales.en import STRINGS   # safe fallback
        _CACHE[lang] = STRINGS
    return _CACHE[lang]


def t(key: str, lang: str = DEFAULT_LANG, **kwargs: Any) -> str:
    """
    Translate a key for the given language.
    Falls back to English, then the raw key if missing.

    Usage:
        t("task_created", lang="ja", task_id=42)
    """
    strings  = _load(lang)
    fallback = _load(DEFAULT_LANG)

    template = strings.get(key) or fallback.get(key) or key
    try:
        return template.format(**kwargs) if kwargs else template
    except (KeyError, ValueError) as exc:
        log.warning("i18n format error — key=%s lang=%s err=%s", key, lang, exc)
        return template


def get_flag(lang: str) -> str:
    return _load(lang).get("lang_flag", "🌐")


def get_lang_name(lang: str) -> str:
    return _load(lang).get("lang_name", lang.upper())


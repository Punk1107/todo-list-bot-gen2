"""
i18n — Internationalisation Manager
Handles TH/EN language switching per-user
"""
from __future__ import annotations
import logging
from typing import Any

log = logging.getLogger(__name__)

SUPPORTED_LANGS = ("th", "en")
DEFAULT_LANG = "th"

# Lazy-load locale modules
_CACHE: dict[str, dict] = {}


def _load(lang: str) -> dict:
    if lang not in _CACHE:
        if lang == "th":
            from locales.th import STRINGS
        elif lang == "en":
            from locales.en import STRINGS
        else:
            from locales.th import STRINGS
        _CACHE[lang] = STRINGS
    return _CACHE[lang]


def t(key: str, lang: str = DEFAULT_LANG, **kwargs: Any) -> str:
    """
    Translate a key for the given language.
    Falls back to Thai, then the raw key if missing.

    Usage:
        t("task_created", lang="en", task_id=42)
    """
    strings = _load(lang)
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

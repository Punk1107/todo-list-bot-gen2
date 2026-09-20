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

    template = strings.get(key) or fallback.get(key) or key
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
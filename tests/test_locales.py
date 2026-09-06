"""
tests/test_locales.py — Unit tests for internationalisation & locales integrity
Specifically verifies DE (German) and all supported languages.
"""
from __future__ import annotations

import ast
import importlib
import os
import re
from collections import Counter
import pytest

from locales.i18n import SUPPORTED_LANGS, t


@pytest.fixture(scope="module")
def all_locales():
    return {lang: importlib.import_module(f"locales.{lang}").STRINGS for lang in SUPPORTED_LANGS}


def test_supported_langs_contains_de():
    """Ensure German is in SUPPORTED_LANGS."""
    assert "de" in SUPPORTED_LANGS


def test_all_locales_importable(all_locales):
    """Ensure all configured locales can be imported without error."""
    for lang in SUPPORTED_LANGS:
        assert lang in all_locales
        assert isinstance(all_locales[lang], dict)
        assert len(all_locales[lang]) > 200


def test_de_keys_match_en(all_locales):
    """Ensure German has all keys present in English (base template)."""
    en_keys = set(all_locales["en"].keys())
    de_keys = set(all_locales["de"].keys())

    missing = en_keys - de_keys
    extra = de_keys - en_keys

    assert not missing, f"German is missing keys present in English: {missing}"
    assert not extra, f"German has extra keys not present in English: {extra}"


def test_no_duplicate_keys_in_ast():
    """Ensure no locale file contains duplicate dictionary keys in its AST definition."""
    for lang in SUPPORTED_LANGS:
        filepath = os.path.join("locales", f"{lang}.py")
        with open(filepath, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=filepath)

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "STRINGS":
                        if isinstance(node.value, ast.Dict):
                            keys = [k.value for k in node.value.keys if isinstance(k, ast.Constant)]
                            counts = Counter(keys)
                            duplicates = {k: v for k, v in counts.items() if v > 1}
                            assert not duplicates, f"{filepath} has duplicate keys: {duplicates}"


def test_de_placeholders_match_en(all_locales):
    """Ensure all format variables ({name}, {task_id}, etc.) match between EN and DE."""
    en_strings = all_locales["en"]
    de_strings = all_locales["de"]
    placeholder_re = re.compile(r"\{([a-zA-Z0-9_]+)(?::[^}]*)?\}")

    mismatches = []
    for key, en_val in en_strings.items():
        de_val = de_strings.get(key, "")
        en_vars = set(placeholder_re.findall(en_val))
        de_vars = set(placeholder_re.findall(de_val))
        if en_vars != de_vars:
            mismatches.append((key, en_vars, de_vars))

    assert not mismatches, f"Placeholder variable mismatches found between EN and DE: {mismatches}"


def test_conflict_resolution_keys_in_de(all_locales):
    """Ensure all conflict resolution system keys exist and format correctly in DE."""
    de_strings = all_locales["de"]
    required_conflict_keys = [
        "task_past_deadline_detailed",
        "task_invalid_year",
        "subtask_deadline_exceeds_parent",
        "subtask_parent_closed",
        "conflict_duplicate_title",
        "conflict_duplicate_desc",
        "btn_conflict_autorename",
        "btn_conflict_force",
        "btn_conflict_view",
        "btn_conflict_cancel",
        "conflict_cancelled",
        "conflict_autorename_done",
        "edit_past_deadline_blocked",
    ]
    for k in required_conflict_keys:
        assert k in de_strings, f"Key '{k}' is missing from locales/de.py"

    # Test formatting with realistic kwargs
    desc = t(
        "conflict_duplicate_desc",
        lang="de",
        existing_name="Projektbericht",
        existing_id=42,
        existing_deadline="31/12/2026 18:00",
    )
    assert "Projektbericht" in desc
    assert "#42" in desc

    autorename = t("btn_conflict_autorename", lang="de", new_name="Projektbericht (2)")
    assert "Projektbericht (2)" in autorename


def test_task_snoozed_key():
    """Ensure task_snoozed key is present in DE and EN and formats properly."""
    msg_de = t("task_snoozed", lang="de", deadline="26/12/2026 18:00")
    assert "26/12/2026 18:00" in msg_de
    assert "Aufgabe um 1 Tag verschoben" in msg_de

    msg_en = t("task_snoozed", lang="en", deadline="26/12/2026 18:00")
    assert "26/12/2026 18:00" in msg_en
    assert "Task postponed by 1 day" in msg_en

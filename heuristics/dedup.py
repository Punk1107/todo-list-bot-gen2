"""
heuristics/dedup.py — Pure Python Levenshtein & Trigram Task Deduplication Engine.
Detects potential duplicate tasks (>= 80% similarity) before or upon task creation.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from core.database import db


def levenshtein_distance(s1: str, s2: str) -> int:
    """
    Computes Levenshtein edit distance between two strings using dynamic programming.
    Time: O(m*n), Space: O(min(m, n)).
    """
    if len(s1) < len(s2):
        s1, s2 = s2, s1

    if not s2:
        return len(s1)

    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1] + [0] * len(s2)
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (0 if c1 == c2 else 1)
            current_row[j + 1] = min(insertions, deletions, substitutions)
        previous_row = current_row

    return previous_row[-1]


def levenshtein_ratio(s1: str, s2: str) -> float:
    """
    Computes normalized Levenshtein similarity ratio between 0.0 and 1.0.
    """
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    max_len = max(len(s1), len(s2))
    dist = levenshtein_distance(s1, s2)
    return max(0.0, 1.0 - (dist / float(max_len)))


def _extract_trigrams(text: str) -> set[str]:
    """Generates padded character trigrams (3-grams) for a string."""
    padded = f"  {text} "
    return {padded[i : i + 3] for i in range(len(padded) - 2)}


def trigram_similarity(s1: str, s2: str) -> float:
    """
    Computes Trigram similarity (Sørensen–Dice coefficient) between two strings.
    """
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    tri1 = _extract_trigrams(s1)
    tri2 = _extract_trigrams(s2)

    total = len(tri1) + len(tri2)
    if total == 0:
        return 0.0

    intersection = len(tri1.intersection(tri2))
    return (2.0 * intersection) / float(total)


def calculate_task_similarity(s1: str, s2: str) -> float:
    """
    Calculates combined similarity score between two task titles.
    Blends Levenshtein ratio and Trigram similarity for high accuracy across
    both short typos, word reordering, and prefix/suffix variations.
    """
    norm1 = re.sub(r"\s+", " ", s1.strip().lower())
    norm2 = re.sub(r"\s+", " ", s2.strip().lower())

    if norm1 == norm2:
        return 1.0
    if not norm1 or not norm2:
        return 0.0

    lev = levenshtein_ratio(norm1, norm2)
    tri = trigram_similarity(norm1, norm2)

    # Substring containment bonus (e.g. "fix login" in "fix login error")
    sub_ratio = 0.0
    if norm1 in norm2 or norm2 in norm1:
        sub_ratio = min(len(norm1), len(norm2)) / float(max(len(norm1), len(norm2)))

    return max(lev, tri, (0.5 * lev + 0.5 * tri), sub_ratio * 0.9)


async def find_potential_duplicate(
    task_name: str,
    owner_id: str,
    guild_id: Optional[str] = None,
    threshold: float = 0.80,
) -> Optional[dict[str, Any]]:
    """
    Finds existing open tasks that are >= threshold similar to task_name.
    Returns dict with task_id, task, similarity percentage if found, else None.
    """
    if not task_name or not task_name.strip():
        return None

    # Query up to 100 recent non-completed tasks for the user or guild
    query = """
        SELECT task_id, task, status, priority, created_at
        FROM tasks
        WHERE (owner_id = $1 OR (guild_id IS NOT NULL AND guild_id = $2))
          AND status != 'Completed'
        ORDER BY task_id DESC
        LIMIT 100
    """
    rows = await db.fetchall(query, (str(owner_id), str(guild_id) if guild_id else "NONE"))

    best_match: Optional[dict[str, Any]] = None
    best_sim = 0.0

    for r in rows:
        existing_title = str(r["task"] or "")
        sim = calculate_task_similarity(task_name, existing_title)
        if sim >= threshold and sim > best_sim:
            best_sim = sim
            best_match = {
                "task_id": int(r["task_id"]),
                "task": existing_title,
                "similarity": round(best_sim, 2),
                "similarity_pct": int(round(best_sim * 100)),
            }

    return best_match


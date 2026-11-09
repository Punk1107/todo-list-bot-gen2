"""
heuristics package — Smart text algorithms, task deduplication, and similarity scoring.
"""
from __future__ import annotations

from heuristics.dedup import (
    calculate_task_similarity,
    find_potential_duplicate,
    levenshtein_distance,
    levenshtein_ratio,
    trigram_similarity,
)

__all__ = [
    "calculate_task_similarity",
    "find_potential_duplicate",
    "levenshtein_distance",
    "levenshtein_ratio",
    "trigram_similarity",
]


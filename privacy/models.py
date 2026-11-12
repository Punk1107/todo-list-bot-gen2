"""Data models for GDPR Impact & Erasure Reports (Feature 42)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GdprImpactSummary:
    """Preview of personal vs anonymized records affected by account erasure."""
    user_id: str
    personal_tasks: int = 0
    shared_project_tasks: int = 0
    owned_projects: int = 0
    comments_and_docs: int = 0
    time_logs: int = 0
    custom_themes: int = 0


@dataclass
class GdprDeletionReport:
    """Result summary returned after completing GDPR data erasure."""
    user_id: str
    personal_tasks_deleted: int = 0
    shared_tasks_anonymized: int = 0
    projects_transferred: int = 0
    projects_anonymized: int = 0
    user_deleted: bool = False


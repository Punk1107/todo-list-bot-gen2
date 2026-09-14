"""
search_recommendation/recommendation.py — Rule-Based Scoring & Recommendation Engine

All scoring is deterministic, fully explainable, and requires no external APIs.

Architecture note (AI-Ready):
  The RuleBasedScorer implements ScorerProtocol — a future ML/embedding-based
  scorer (e.g. using pgvector cosine distances from a local model) can be dropped
  in by implementing the same protocol, without changing RecommendationEngine,
  service.py, or cog.py.

Scoring factors (all normalized 0–100 before weight multiplication):
  1. priority   — Linear mapped from P0–P7 priority level
  2. urgency    — Non-linear curve based on hours until deadline
  3. overdue    — Severity of being past deadline
  4. age        — Task staleness (encourages clearing old tasks)
  5. assignment — Whether the requesting user is assigned to the task
  6. status     — Momentum bonus for In_Progress tasks
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from search_recommendation.models import (
    FactorScore,
    ScoreBreakdown,
    TaskRecommendation,
    WeightConfig,
)
from search_recommendation.query_builder import SqlQueryBuilder
from core.database import db

log = logging.getLogger(__name__)

_builder = SqlQueryBuilder()

# ─────────────────────────────────────────────────────────────────────────────
# Priority scoring table (P0–P7)
# ─────────────────────────────────────────────────────────────────────────────

_PRIORITY_SCORES: dict[int, tuple[float, str]] = {
    0: (5.0,  "⬜ P0 (None)"),
    1: (15.0, "🟦 P1 (Low)"),
    2: (25.0, "🟩 P2 (Normal)"),
    3: (40.0, "🟨 P3 (Moderate)"),
    4: (58.0, "🟧 P4 (High)"),
    5: (73.0, "🟥 P5 (Very High)"),
    6: (87.0, "🔴 P6 (Critical)"),
    7: (100.0,"🆘 P7 (SOS)"),
}


# ─────────────────────────────────────────────────────────────────────────────
# Rule-Based Scorer
# ─────────────────────────────────────────────────────────────────────────────

class RuleBasedScorer:
    """
    Deterministic, rule-based scorer for task prioritization.
    Implements ScorerProtocol.

    All score() methods are synchronous for bulk efficiency.
    """

    def score_task(
        self,
        task_row: Any,
        user_id: str,
        now: datetime,
        weights: WeightConfig,
    ) -> ScoreBreakdown:
        """
        Compute a full ScoreBreakdown for one task row.
        task_row must be an asyncpg Record or dict with the standard task columns.
        """
        # ── 1. Priority ───────────────────────────────────────────────────────
        raw_priority, priority_label = self._score_priority(task_row)
        w_priority = raw_priority * weights.priority

        # ── 2 & 3. Urgency + Overdue ──────────────────────────────────────────
        raw_urgency, urgency_label, raw_overdue, overdue_label = self._score_deadline(
            task_row, now
        )
        w_urgency = raw_urgency * weights.urgency
        w_overdue = raw_overdue * weights.overdue

        # ── 4. Age ────────────────────────────────────────────────────────────
        raw_age, age_label = self._score_age(task_row, now)
        w_age = raw_age * weights.age

        # ── 5. Assignment ─────────────────────────────────────────────────────
        raw_assignment, assignment_label = self._score_assignment(task_row, user_id)
        w_assignment = raw_assignment * weights.assignment

        # ── 6. Status ─────────────────────────────────────────────────────────
        raw_status, status_label = self._score_status(task_row)
        w_status = raw_status * weights.status

        total = min(
            100.0,
            w_priority + w_urgency + w_overdue + w_age + w_assignment + w_status
        )

        return ScoreBreakdown(
            priority   = FactorScore(raw_priority,   round(w_priority, 2),   priority_label,   weights.priority),
            urgency    = FactorScore(raw_urgency,    round(w_urgency, 2),    urgency_label,    weights.urgency),
            overdue    = FactorScore(raw_overdue,    round(w_overdue, 2),    overdue_label,    weights.overdue),
            age        = FactorScore(raw_age,        round(w_age, 2),        age_label,        weights.age),
            assignment = FactorScore(raw_assignment, round(w_assignment, 2), assignment_label, weights.assignment),
            status     = FactorScore(raw_status,     round(w_status, 2),     status_label,     weights.status),
            total_score= round(total, 2),
        )

    # ── Scoring helpers ───────────────────────────────────────────────────────

    def _score_priority(self, row: Any) -> tuple[float, str]:
        """Map priority level 0–7 to a 0–100 sub-score with label."""
        level = int(row["priority"] or 0)
        level = max(0, min(7, level))
        score, label = _PRIORITY_SCORES[level]
        return score, label

    def _score_deadline(self, row: Any, now: datetime) -> tuple[float, str, float, str]:
        """
        Returns (urgency_score, urgency_label, overdue_score, overdue_label).

        Urgency curve (hours until deadline):
          Overdue or < 2h  → 100
          < 6h             → 92
          < 12h            → 82
          < 24h            → 70
          < 48h            → 52
          < 72h            → 35
          < 168h (1 week)  → 18
          ≥ 168h           → 5

        Overdue severity (hours past deadline):
          0h               → 0 (not overdue)
          < 2h             → 55 (freshly overdue)
          < 6h             → 65
          < 24h            → 75
          < 72h            → 88
          ≥ 72h            → 100 (critically stale)
        """
        deadline_str = row.get("deadline")
        status = row.get("status", "Pending")

        if not deadline_str or status in ("Completed", "Cancelled"):
            # No deadline or finished — neutral scores
            return 5.0, "⬜ No deadline", 0.0, "✅ Not overdue"

        try:
            deadline = datetime.fromisoformat(str(deadline_str))
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return 5.0, "⬜ Invalid deadline", 0.0, "✅ Not overdue"

        delta_seconds = (deadline - now).total_seconds()
        hours_until   = delta_seconds / 3600.0

        if hours_until < 0:
            # Overdue
            hours_past = abs(hours_until)

            # Urgency is maxed out for overdue tasks
            urgency_score, urgency_label = 100.0, "🚨 Overdue"

            # Severity of overdue
            if hours_past < 2:
                overdue_score = 55.0
                overdue_label = f"⚠️ Just overdue (<2h)"
            elif hours_past < 6:
                overdue_score = 65.0
                overdue_label = f"🟧 Overdue {hours_past:.0f}h"
            elif hours_past < 24:
                overdue_score = 75.0
                days_h = hours_past
                overdue_label = f"🟥 Overdue {days_h:.0f}h"
            elif hours_past < 72:
                days = hours_past / 24
                overdue_score = 88.0
                overdue_label = f"🚨 Overdue {days:.1f}d"
            else:
                days = hours_past / 24
                overdue_score = 100.0
                overdue_label = f"💀 Overdue {days:.0f}d (critical)"

            return urgency_score, urgency_label, overdue_score, overdue_label

        # Not overdue — apply urgency curve
        overdue_score, overdue_label = 0.0, "✅ Not overdue"

        if hours_until < 2:
            urgency_score, urgency_label = 100.0, f"🔥 Due in {hours_until*60:.0f}min"
        elif hours_until < 6:
            urgency_score, urgency_label = 92.0, f"⚡ Due in {hours_until:.1f}h"
        elif hours_until < 12:
            urgency_score, urgency_label = 82.0, f"⚡ Due in {hours_until:.1f}h"
        elif hours_until < 24:
            urgency_score, urgency_label = 70.0, f"⏰ Due in {hours_until:.0f}h"
        elif hours_until < 48:
            urgency_score, urgency_label = 52.0, f"📅 Due in {hours_until/24:.1f}d"
        elif hours_until < 72:
            urgency_score, urgency_label = 35.0, f"📅 Due in {hours_until/24:.1f}d"
        elif hours_until < 168:
            urgency_score, urgency_label = 18.0, f"📅 Due in {hours_until/24:.0f}d"
        else:
            urgency_score, urgency_label = 5.0,  f"🗓️ Due in {hours_until/24:.0f}d"

        return urgency_score, urgency_label, overdue_score, overdue_label

    def _score_age(self, row: Any, now: datetime) -> tuple[float, str]:
        """
        Task staleness score — prevents old tasks from being perpetually
        ignored just because they have a far-off deadline.

        Age (days since created_at):
          < 3 days   → 5   (fresh task)
          3–7 days   → 15
          7–14 days  → 35
          14–30 days → 60
          30–60 days → 80
          > 60 days  → 100 (very stale)
        """
        created_str = row.get("created_at")
        if not created_str:
            return 5.0, "🆕 New task"

        try:
            created = created_str if isinstance(created_str, datetime) else datetime.fromisoformat(str(created_str))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return 5.0, "🆕 New task"

        days_old = (now - created).total_seconds() / 86400.0

        if days_old < 3:
            return 5.0,  "🆕 New task"
        elif days_old < 7:
            return 15.0, f"📋 {days_old:.0f}d old"
        elif days_old < 14:
            return 35.0, f"📋 {days_old:.0f}d old"
        elif days_old < 30:
            return 60.0, f"⏳ {days_old:.0f}d old (stale)"
        elif days_old < 60:
            return 80.0, f"📆 {days_old:.0f}d old (very stale)"
        else:
            return 100.0, f"🗄️ {days_old:.0f}d old (ancient)"

    def _score_assignment(self, row: Any, user_id: str) -> tuple[float, str]:
        """
        Boost tasks the requesting user is directly assigned to.
        Also gives partial credit for unassigned tasks (claimable).

        Source: 'assignee_ids' is a comma-separated string from the
        recommendation candidate query.
        """
        assignee_str = row.get("assignee_ids") or ""
        owner_id = row.get("owner_id", "")

        # Owner always gets a strong signal
        if owner_id == user_id:
            if assignee_str:
                assignee_ids = assignee_str.split(",")
                if user_id in assignee_ids:
                    return 100.0, "👤 Owner + Assigned"
            return 70.0, "👤 Owner"

        if assignee_str:
            assignee_ids = assignee_str.split(",")
            if user_id in assignee_ids:
                return 100.0, "👤 Directly assigned"
            # Assigned to someone else — lower relevance for this user
            return 10.0, "👥 Assigned to other"

        # Unassigned — claimable
        return 40.0, "🔓 Unassigned (claimable)"

    def _score_status(self, row: Any) -> tuple[float, str]:
        """
        Status momentum bonus.
        In_Progress tasks get priority — they're already started and
        should be completed to avoid context-switching cost.
        """
        status = row.get("status", "Pending")
        if status == "In_Progress":
            return 100.0, "🏃 In Progress (momentum)"
        elif status == "Pending":
            return 50.0, "⏳ Pending"
        else:
            return 0.0, f"— {status}"


# ─────────────────────────────────────────────────────────────────────────────
# Recommendation Engine
# ─────────────────────────────────────────────────────────────────────────────

class RecommendationEngine:
    """
    Fetches candidate tasks from the DB, scores each one using RuleBasedScorer,
    and returns the top-K recommendations sorted by total_score DESC.

    Implements RecommendationEngineProtocol.
    """

    def __init__(self, scorer: Optional[RuleBasedScorer] = None) -> None:
        # Injectable — allows tests to swap in a mock scorer
        self._scorer: RuleBasedScorer = scorer or RuleBasedScorer()

    async def recommend(
        self,
        user_id: str,
        guild_id: Optional[str],
        limit: int = 5,
        weights: Optional[WeightConfig] = None,
    ) -> list[TaskRecommendation]:
        """
        Fetch candidate tasks, score each one, and return top-K ranked results.

        Args:
            user_id:  Discord user ID (str) of the requesting user.
            guild_id: Optional guild ID for shared-project scope.
            limit:    Maximum number of recommendations to return (max 10).
            weights:  Custom WeightConfig; defaults to WeightConfig.default().
        """
        limit   = max(1, min(limit, 10))
        weights = weights or WeightConfig.default()
        now     = datetime.now(timezone.utc)

        # 1. Fetch candidate pool (over-fetch for accurate ranking)
        candidate_sql, candidate_params = _builder.build_recommendation_candidates_query(
            user_id=user_id,
            guild_id=guild_id,
            limit=min(limit * 40, 200),  # fetch up to 200 candidates to rank from
        )

        try:
            rows = await db.fetchall(candidate_sql, candidate_params)
        except Exception as exc:
            log.error("Recommendation candidates query failed: %s", exc)
            return []

        if not rows:
            return []

        # 2. Score all candidates
        scored: list[tuple[float, Any, ScoreBreakdown]] = []
        for row in rows:
            try:
                breakdown = self._scorer.score_task(row, user_id, now, weights)
                scored.append((breakdown.total_score, row, breakdown))
            except Exception as exc:
                log.warning("Scoring task_id=%s failed: %s", row.get("task_id"), exc)

        # 3. Sort by score DESC, then by deadline ASC as tiebreaker
        scored.sort(key=lambda x: (-x[0], x[1].get("deadline") or "9999"))

        # 4. Build TaskRecommendation objects for top-K
        results: list[TaskRecommendation] = []
        for rank_idx, (score, row, breakdown) in enumerate(scored[:limit], start=1):
            action_hint = self._suggest_action(row, score)
            results.append(TaskRecommendation(
                rank        = rank_idx,
                task_id     = row["task_id"],
                task        = row["task"],
                deadline    = row["deadline"],
                priority    = row["priority"],
                status      = row["status"],
                owner_id    = row["owner_id"],
                guild_id    = row.get("guild_id"),
                project_id  = row.get("project_id"),
                breakdown   = breakdown,
                action_hint = action_hint,
            ))

        return results

    @staticmethod
    def _suggest_action(row: Any, score: float) -> str:
        """Return the i18n key for the most appropriate action hint."""
        status = row.get("status", "Pending")
        deadline_str = row.get("deadline")
        now = datetime.now(timezone.utc)

        if status == "In_Progress":
            return "recommend_action_finish"

        if deadline_str:
            try:
                dl = datetime.fromisoformat(str(deadline_str))
                if dl.tzinfo is None:
                    dl = dl.replace(tzinfo=timezone.utc)
                if dl < now:
                    return "recommend_action_overdue"
                hours = (dl - now).total_seconds() / 3600
                if hours < 24:
                    return "recommend_action_urgent"
            except (ValueError, TypeError):
                pass

        if score >= 70:
            return "recommend_action_high_priority"
        return "recommend_action_start"

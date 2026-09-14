"""
tests/test_search_recommendation.py — Unit Tests for Search & Recommendation

Tests:
  - WeightConfig validation (sum to 1.0, presets, invalid weights)
  - RuleBasedScorer: priority, urgency curve, overdue severity, age, assignment, status
  - RecommendationEngine: ordering, top-K cutoff
  - SqlQueryBuilder: placeholder numbering, filter combinations
  - FtsEngine: ILIKE fallback path
  - ScoreBreakdown: summary_badges()
  - SearchFilter / SearchQuery: default values

All database interactions are mocked using unittest.mock.AsyncMock.
"""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# WeightConfig Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestWeightConfig:

    def test_default_weights_sum_to_one(self):
        from search_recommendation.models import WeightConfig
        w = WeightConfig.default()
        total = w.priority + w.urgency + w.overdue + w.age + w.assignment + w.status
        assert abs(total - 1.0) < 1e-9

    def test_urgency_focused_preset(self):
        from search_recommendation.models import WeightConfig
        w = WeightConfig.urgency_focused()
        total = w.priority + w.urgency + w.overdue + w.age + w.assignment + w.status
        assert abs(total - 1.0) < 1e-9
        assert w.urgency > 0.35, "Urgency-focused should have high urgency weight"

    def test_priority_focused_preset(self):
        from search_recommendation.models import WeightConfig
        w = WeightConfig.priority_focused()
        total = w.priority + w.urgency + w.overdue + w.age + w.assignment + w.status
        assert abs(total - 1.0) < 1e-9
        assert w.priority >= 0.45, "Priority-focused should have high priority weight"

    def test_invalid_weights_raise(self):
        from search_recommendation.models import WeightConfig
        with pytest.raises(ValueError, match="sum to 1.0"):
            WeightConfig(priority=0.5, urgency=0.5, overdue=0.5,
                         age=0.0, assignment=0.0, status=0.0)

    def test_custom_valid_weights(self):
        from search_recommendation.models import WeightConfig
        w = WeightConfig(priority=0.30, urgency=0.30, overdue=0.20,
                         age=0.10, assignment=0.05, status=0.05)
        assert w.priority == 0.30


# ─────────────────────────────────────────────────────────────────────────────
# RuleBasedScorer Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRuleBasedScorer:
    """Tests for the deterministic rule-based scoring engine."""

    def _make_row(self, **kwargs) -> dict:
        """Helper: create a minimal task row dict."""
        now = datetime.now(timezone.utc)
        defaults = {
            "task_id":      1,
            "task":         "Test Task",
            "priority":     3,
            "status":       "Pending",
            "deadline":     (now + timedelta(hours=48)).isoformat(),
            "created_at":   (now - timedelta(days=2)).isoformat(),
            "owner_id":     "user_abc",
            "assignee_ids": None,
        }
        defaults.update(kwargs)
        return defaults

    def _scorer(self):
        from search_recommendation.recommendation import RuleBasedScorer
        return RuleBasedScorer()

    def _weights(self):
        from search_recommendation.models import WeightConfig
        return WeightConfig.default()

    def _now(self):
        return datetime.now(timezone.utc)

    # ── Priority tests ────────────────────────────────────────────────────────

    def test_priority_7_scores_100(self):
        scorer = self._scorer()
        row = self._make_row(priority=7)
        bd = scorer.score_task(row, "user_abc", self._now(), self._weights())
        assert bd.priority.raw_score == 100.0
        assert "P7" in bd.priority.label or "SOS" in bd.priority.label

    def test_priority_0_scores_5(self):
        scorer = self._scorer()
        row = self._make_row(priority=0)
        bd = scorer.score_task(row, "user_abc", self._now(), self._weights())
        assert bd.priority.raw_score == 5.0

    def test_priority_increases_monotonically(self):
        scorer = self._scorer()
        now = self._now()
        w = self._weights()
        scores = []
        for p in range(8):
            row = self._make_row(priority=p)
            bd = scorer.score_task(row, "user_abc", now, w)
            scores.append(bd.priority.raw_score)
        for i in range(len(scores) - 1):
            assert scores[i] < scores[i + 1], f"Priority {i} >= priority {i+1}"

    # ── Urgency tests ─────────────────────────────────────────────────────────

    def test_urgency_overdue_task_scores_100(self):
        scorer = self._scorer()
        now = self._now()
        row = self._make_row(deadline=(now - timedelta(hours=5)).isoformat())
        bd = scorer.score_task(row, "user_abc", now, self._weights())
        assert bd.urgency.raw_score == 100.0

    def test_urgency_due_in_1hour_very_high(self):
        scorer = self._scorer()
        now = self._now()
        row = self._make_row(deadline=(now + timedelta(hours=1)).isoformat())
        bd = scorer.score_task(row, "user_abc", now, self._weights())
        assert bd.urgency.raw_score >= 90.0

    def test_urgency_due_in_30days_low(self):
        scorer = self._scorer()
        now = self._now()
        row = self._make_row(deadline=(now + timedelta(days=30)).isoformat())
        bd = scorer.score_task(row, "user_abc", now, self._weights())
        assert bd.urgency.raw_score <= 10.0

    def test_urgency_no_deadline(self):
        scorer = self._scorer()
        row = self._make_row(deadline=None)
        bd = scorer.score_task(row, "user_abc", self._now(), self._weights())
        assert bd.urgency.raw_score <= 10.0

    # ── Overdue tests ─────────────────────────────────────────────────────────

    def test_overdue_fresh_scores_nonzero(self):
        scorer = self._scorer()
        now = self._now()
        row = self._make_row(
            deadline=(now - timedelta(hours=1)).isoformat(),
            status="Pending"
        )
        bd = scorer.score_task(row, "user_abc", now, self._weights())
        assert bd.overdue.raw_score > 0.0

    def test_overdue_3days_very_high(self):
        scorer = self._scorer()
        now = self._now()
        row = self._make_row(
            deadline=(now - timedelta(days=4)).isoformat(),
            status="Pending"
        )
        bd = scorer.score_task(row, "user_abc", now, self._weights())
        assert bd.overdue.raw_score >= 88.0

    def test_not_overdue_scores_zero(self):
        scorer = self._scorer()
        now = self._now()
        row = self._make_row(deadline=(now + timedelta(hours=10)).isoformat())
        bd = scorer.score_task(row, "user_abc", now, self._weights())
        assert bd.overdue.raw_score == 0.0

    def test_completed_task_overdue_scores_zero(self):
        """Completed tasks should not trigger overdue score."""
        scorer = self._scorer()
        now = self._now()
        row = self._make_row(
            deadline=(now - timedelta(days=2)).isoformat(),
            status="Completed"
        )
        bd = scorer.score_task(row, "user_abc", now, self._weights())
        assert bd.overdue.raw_score == 0.0

    # ── Age tests ─────────────────────────────────────────────────────────────

    def test_age_new_task_low(self):
        scorer = self._scorer()
        now = self._now()
        row = self._make_row(created_at=(now - timedelta(days=1)).isoformat())
        bd = scorer.score_task(row, "user_abc", now, self._weights())
        assert bd.age.raw_score <= 10.0

    def test_age_old_task_high(self):
        scorer = self._scorer()
        now = self._now()
        row = self._make_row(created_at=(now - timedelta(days=90)).isoformat())
        bd = scorer.score_task(row, "user_abc", now, self._weights())
        assert bd.age.raw_score == 100.0, "90-day old task should max out age score"

    def test_age_2week_task_moderate(self):
        scorer = self._scorer()
        now = self._now()
        row = self._make_row(created_at=(now - timedelta(days=20)).isoformat())
        bd = scorer.score_task(row, "user_abc", now, self._weights())
        assert 50.0 <= bd.age.raw_score <= 80.0

    # ── Assignment tests ──────────────────────────────────────────────────────

    def test_owner_gets_high_score(self):
        scorer = self._scorer()
        row = self._make_row(owner_id="user_abc", assignee_ids=None)
        bd = scorer.score_task(row, "user_abc", self._now(), self._weights())
        assert bd.assignment.raw_score >= 70.0

    def test_directly_assigned_scores_100(self):
        scorer = self._scorer()
        row = self._make_row(owner_id="owner_xyz", assignee_ids="user_abc,user_def")
        bd = scorer.score_task(row, "user_abc", self._now(), self._weights())
        assert bd.assignment.raw_score == 100.0

    def test_unassigned_task_scores_partial(self):
        scorer = self._scorer()
        row = self._make_row(owner_id="owner_xyz", assignee_ids=None)
        bd = scorer.score_task(row, "user_abc", self._now(), self._weights())
        assert 30.0 <= bd.assignment.raw_score <= 55.0, "Unassigned should be claimable partial"

    def test_assigned_to_other_scores_low(self):
        scorer = self._scorer()
        row = self._make_row(owner_id="owner_xyz", assignee_ids="user_other")
        bd = scorer.score_task(row, "user_abc", self._now(), self._weights())
        assert bd.assignment.raw_score <= 15.0

    # ── Status tests ──────────────────────────────────────────────────────────

    def test_in_progress_scores_100(self):
        scorer = self._scorer()
        row = self._make_row(status="In_Progress")
        bd = scorer.score_task(row, "user_abc", self._now(), self._weights())
        assert bd.status.raw_score == 100.0

    def test_pending_scores_50(self):
        scorer = self._scorer()
        row = self._make_row(status="Pending")
        bd = scorer.score_task(row, "user_abc", self._now(), self._weights())
        assert bd.status.raw_score == 50.0

    # ── Total score tests ─────────────────────────────────────────────────────

    def test_total_score_bounded_0_100(self):
        """Total score must always be in [0, 100]."""
        scorer = self._scorer()
        now = self._now()
        w = self._weights()
        extreme_row = self._make_row(
            priority=7,
            status="In_Progress",
            deadline=(now - timedelta(days=5)).isoformat(),  # heavily overdue
            created_at=(now - timedelta(days=100)).isoformat(),
            owner_id="user_abc",
            assignee_ids="user_abc",
        )
        bd = scorer.score_task(extreme_row, "user_abc", now, w)
        assert 0.0 <= bd.total_score <= 100.0

    def test_high_priority_overdue_ranks_above_normal(self):
        """An overdue high-priority task should score more than a normal pending task."""
        scorer = self._scorer()
        now = self._now()
        w = self._weights()

        high_row = self._make_row(
            priority=6,
            deadline=(now - timedelta(hours=12)).isoformat(),
            status="Pending",
        )
        normal_row = self._make_row(
            priority=2,
            deadline=(now + timedelta(days=7)).isoformat(),
            status="Pending",
        )
        bd_high   = scorer.score_task(high_row,   "user_abc", now, w)
        bd_normal = scorer.score_task(normal_row, "user_abc", now, w)
        assert bd_high.total_score > bd_normal.total_score


# ─────────────────────────────────────────────────────────────────────────────
# ScoreBreakdown.summary_badges() Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestScoreBreakdown:

    def test_summary_badges_max_4(self):
        from search_recommendation.recommendation import RuleBasedScorer
        from search_recommendation.models import WeightConfig
        scorer = RuleBasedScorer()
        now = datetime.now(timezone.utc)
        row = {
            "task_id": 1, "task": "Test", "priority": 7, "status": "In_Progress",
            "deadline": (now - timedelta(days=2)).isoformat(),
            "created_at": (now - timedelta(days=50)).isoformat(),
            "owner_id": "u1", "assignee_ids": "u1",
        }
        bd = scorer.score_task(row, "u1", now, WeightConfig.default())
        badges = bd.summary_badges()
        assert len(badges) <= 4

    def test_summary_badges_format_contains_pt(self):
        from search_recommendation.recommendation import RuleBasedScorer
        from search_recommendation.models import WeightConfig
        scorer = RuleBasedScorer()
        now = datetime.now(timezone.utc)
        row = {
            "task_id": 1, "task": "Test", "priority": 7, "status": "In_Progress",
            "deadline": (now - timedelta(days=2)).isoformat(),
            "created_at": (now - timedelta(days=50)).isoformat(),
            "owner_id": "u1", "assignee_ids": "u1",
        }
        bd = scorer.score_task(row, "u1", now, WeightConfig.default())
        badges = bd.summary_badges()
        if badges:
            # At least one badge should contain 'pt' (points)
            assert any("pt" in b for b in badges), f"Expected 'pt' in badges: {badges}"


# ─────────────────────────────────────────────────────────────────────────────
# SqlQueryBuilder Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSqlQueryBuilder:

    def _builder(self):
        from search_recommendation.query_builder import SqlQueryBuilder
        return SqlQueryBuilder()

    def test_fts_query_has_placeholders(self):
        from search_recommendation.models import SearchFilter, SortBy
        builder = self._builder()
        sql, params = builder.build_fts_query(
            text="meeting report",
            search_filter=SearchFilter(owner_id="u1"),
            sort_by=SortBy.RELEVANCE,
            page=1,
            page_size=10,
        )
        # Should use $1, $2, etc. — no literal user input in SQL
        assert "$1" in sql
        assert "meeting report" not in sql
        assert "meeting report" in params

    def test_fts_count_query_returns_total_column(self):
        from search_recommendation.models import SearchFilter
        builder = self._builder()
        sql, params = builder.build_fts_count_query(
            text="buy groceries",
            search_filter=SearchFilter(owner_id="u1"),
        )
        assert "COUNT(*)" in sql.upper() or "count(*)" in sql.lower()
        assert "total" in sql.lower()

    def test_filter_query_no_fts_rank(self):
        from search_recommendation.models import SearchFilter, SortBy
        builder = self._builder()
        sql, params = builder.build_filter_query(
            search_filter=SearchFilter(owner_id="u1", status="Pending"),
            sort_by=SortBy.PRIORITY_DESC,
            page=1,
            page_size=5,
        )
        # Should not contain tsvector operators
        assert "@@ " not in sql
        assert "Pending" not in sql  # value should be in params not SQL
        assert "Pending" in params

    def test_status_filter_adds_param(self):
        from search_recommendation.models import SearchFilter, SortBy
        builder = self._builder()
        sql, params = builder.build_filter_query(
            search_filter=SearchFilter(owner_id="u1", status="In_Progress"),
            sort_by=SortBy.PRIORITY_DESC,
            page=1,
            page_size=10,
        )
        assert "In_Progress" in params

    def test_priority_min_filter(self):
        from search_recommendation.models import SearchFilter, SortBy
        builder = self._builder()
        sql, params = builder.build_filter_query(
            search_filter=SearchFilter(owner_id="u1", priority_min=5),
            sort_by=SortBy.PRIORITY_DESC,
            page=1,
            page_size=10,
        )
        assert 5 in params
        assert ">=" in sql

    def test_pagination_offset_calculation(self):
        from search_recommendation.models import SearchFilter, SortBy
        builder = self._builder()
        sql, params = builder.build_filter_query(
            search_filter=SearchFilter(owner_id="u1"),
            sort_by=SortBy.DEADLINE_ASC,
            page=3,
            page_size=10,
        )
        # Page 3, page_size 10 → offset = 20
        assert 20 in params

    def test_guild_scope_excludes_owner_filter(self):
        from search_recommendation.models import SearchFilter, SortBy
        builder = self._builder()
        sql, params = builder.build_filter_query(
            search_filter=SearchFilter(guild_id="guild_123"),
            sort_by=SortBy.RELEVANCE,
            page=1,
            page_size=10,
        )
        assert "guild_123" in params

    def test_sanitize_strips_null_bytes(self):
        from search_recommendation.query_builder import SqlQueryBuilder
        result = SqlQueryBuilder._sanitize_query("hello\x00world")
        assert "\x00" not in result
        assert "hello" in result

    def test_sanitize_truncates_long_query(self):
        from search_recommendation.query_builder import SqlQueryBuilder
        long_input = "a" * 500
        result = SqlQueryBuilder._sanitize_query(long_input)
        assert len(result) <= 200

    def test_recommendation_candidates_includes_assignee_subquery(self):
        builder = self._builder()
        sql, params = builder.build_recommendation_candidates_query(
            user_id="u1", guild_id=None, limit=50
        )
        assert "task_assignments" in sql
        assert "STRING_AGG" in sql or "string_agg" in sql.lower()
        assert "Completed" in sql
        assert "u1" in params


# ─────────────────────────────────────────────────────────────────────────────
# RecommendationEngine Tests (with mocked DB)
# ─────────────────────────────────────────────────────────────────────────────

class TestRecommendationEngine:

    def _make_mock_row(self, task_id: int, priority: int, hours_until_deadline: float,
                       status: str = "Pending", days_old: int = 5,
                       owner_id: str = "u1") -> MagicMock:
        """Create a mock asyncpg Record for testing."""
        now = datetime.now(timezone.utc)
        row = MagicMock()
        row.__getitem__ = lambda self, key: {
            "task_id":      task_id,
            "task":         f"Task #{task_id}",
            "priority":     priority,
            "status":       status,
            "deadline":     (now + timedelta(hours=hours_until_deadline)).isoformat(),
            "created_at":   (now - timedelta(days=days_old)).isoformat(),
            "owner_id":     owner_id,
            "guild_id":     None,
            "project_id":   None,
            "assignee_ids": None,
            "tags":         None,
            "description":  None,
            "note":         None,
        }[key]
        row.get = lambda key, default=None: {
            "task_id": task_id, "task": f"Task #{task_id}",
            "priority": priority, "status": status,
            "deadline": (now + timedelta(hours=hours_until_deadline)).isoformat(),
            "created_at": (now - timedelta(days=days_old)).isoformat(),
            "owner_id": owner_id, "guild_id": None, "project_id": None,
            "assignee_ids": None, "tags": None, "description": None, "note": None,
        }.get(key, default)
        return row

    @pytest.mark.asyncio
    async def test_recommend_returns_top_k(self):
        """Engine should return at most `limit` recommendations."""
        from search_recommendation.recommendation import RecommendationEngine
        from search_recommendation.models import WeightConfig

        now = datetime.now(timezone.utc)
        mock_rows = [
            self._make_mock_row(i, priority=i % 8, hours_until_deadline=float(i * 10))
            for i in range(1, 15)  # 14 candidates
        ]

        engine = RecommendationEngine()
        with patch("search_recommendation.recommendation.db") as mock_db:
            mock_db.fetchall = AsyncMock(return_value=mock_rows)
            results = await engine.recommend(
                user_id="u1", guild_id=None, limit=5,
                weights=WeightConfig.default()
            )

        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_recommend_ordered_by_score_desc(self):
        """Results should be in descending score order."""
        from search_recommendation.recommendation import RecommendationEngine
        from search_recommendation.models import WeightConfig

        mock_rows = [
            self._make_mock_row(1, priority=0, hours_until_deadline=200.0),  # low
            self._make_mock_row(2, priority=7, hours_until_deadline=-5.0),   # overdue + high prio
            self._make_mock_row(3, priority=5, hours_until_deadline=2.0),    # urgent
        ]

        engine = RecommendationEngine()
        with patch("search_recommendation.recommendation.db") as mock_db:
            mock_db.fetchall = AsyncMock(return_value=mock_rows)
            results = await engine.recommend(
                user_id="u1", guild_id=None, limit=3,
                weights=WeightConfig.default()
            )

        scores = [r.total_score for r in results]
        assert scores == sorted(scores, reverse=True), f"Not sorted: {scores}"

    @pytest.mark.asyncio
    async def test_recommend_empty_on_db_error(self):
        """Engine should return [] gracefully on DB error."""
        from search_recommendation.recommendation import RecommendationEngine
        from search_recommendation.models import WeightConfig

        engine = RecommendationEngine()
        with patch("search_recommendation.recommendation.db") as mock_db:
            mock_db.fetchall = AsyncMock(side_effect=Exception("DB connection lost"))
            results = await engine.recommend(
                user_id="u1", guild_id=None, limit=5,
                weights=WeightConfig.default()
            )

        assert results == []

    @pytest.mark.asyncio
    async def test_recommend_rank_is_1indexed(self):
        """First result should have rank=1."""
        from search_recommendation.recommendation import RecommendationEngine
        from search_recommendation.models import WeightConfig

        mock_rows = [self._make_mock_row(1, priority=5, hours_until_deadline=10.0)]

        engine = RecommendationEngine()
        with patch("search_recommendation.recommendation.db") as mock_db:
            mock_db.fetchall = AsyncMock(return_value=mock_rows)
            results = await engine.recommend(
                user_id="u1", guild_id=None, limit=3,
                weights=WeightConfig.default()
            )

        assert results[0].rank == 1


# ─────────────────────────────────────────────────────────────────────────────
# SearchFilter / SearchQuery Default Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSearchModels:

    def test_search_filter_defaults(self):
        from search_recommendation.models import SearchFilter
        f = SearchFilter()
        assert f.owner_id is None
        assert f.guild_id is None
        assert f.status is None
        assert f.include_subtasks is False

    def test_search_query_defaults(self):
        from search_recommendation.models import SearchQuery, SearchFilter, SortBy
        q = SearchQuery(text="hello")
        assert q.page == 1
        assert q.page_size == 10
        assert q.sort_by == SortBy.RELEVANCE

    def test_sort_by_enum_values(self):
        from search_recommendation.models import SortBy
        assert SortBy.RELEVANCE.value == "relevance"
        assert SortBy.DEADLINE_ASC.value == "deadline_asc"
        assert SortBy.PRIORITY_DESC.value == "priority_desc"


# ─────────────────────────────────────────────────────────────────────────────
# Protocol Conformance Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestProtocolConformance:

    def test_fts_engine_implements_protocol(self):
        from search_recommendation.fts_engine import FtsEngine
        from search_recommendation.protocols import SearchEngineProtocol
        engine = FtsEngine()
        assert isinstance(engine, SearchEngineProtocol)

    def test_rule_based_scorer_implements_protocol(self):
        from search_recommendation.recommendation import RuleBasedScorer
        from search_recommendation.protocols import ScorerProtocol
        scorer = RuleBasedScorer()
        assert isinstance(scorer, ScorerProtocol)

    def test_recommendation_engine_implements_protocol(self):
        from search_recommendation.recommendation import RecommendationEngine
        from search_recommendation.protocols import RecommendationEngineProtocol
        engine = RecommendationEngine()
        assert isinstance(engine, RecommendationEngineProtocol)


# ─────────────────────────────────────────────────────────────────────────────
# Cog Registration & Import Verification Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCogLoadAndRegistration:

    def test_cog_imports_cleanly(self):
        """Verify cog module imports without NameError (e.g. Optional / app_commands)."""
        import search_recommendation.cog as cog_module
        assert hasattr(cog_module, "SearchRecommendationCog")
        assert hasattr(cog_module, "setup")

    @pytest.mark.asyncio
    async def test_cog_adds_to_bot_cleanly(self):
        """Verify SearchRecommendationCog registers /search and /recommend without conflict."""
        import discord
        from discord.ext import commands
        from search_recommendation.cog import SearchRecommendationCog

        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        cog = SearchRecommendationCog(bot)
        await bot.add_cog(cog)

        cmd_names = [cmd.name for cmd in bot.tree.get_commands()]
        assert "search" in cmd_names
        assert "recommend" in cmd_names


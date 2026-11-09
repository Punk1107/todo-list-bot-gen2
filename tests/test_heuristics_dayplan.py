"""
tests/test_heuristics_dayplan.py — Unit tests for Gen 5.0 Pillar 7:
Smart Heuristics, Day Planner & Search Parsing.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from day_planner.optimizer import (
    DayPlanResult,
    TimeBlock,
    _parse_time_str,
    optimize_day_schedule,
)
from day_planner.views import DayPlanActionView, build_day_plan_embed
from heuristics.dedup import (
    calculate_task_similarity,
    find_potential_duplicate,
    levenshtein_distance,
    levenshtein_ratio,
    trigram_similarity,
)
from organization.models import EisenhowerMatrixData, EisenhowerQuadrant, EisenhowerTask
from search_recommendation.boolean_parser import (
    BooleanSearchParser,
    TokenType,
    compile_boolean_query,
    tokenize,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Deduplication Engine Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_levenshtein_distance():
    assert levenshtein_distance("", "") == 0
    assert levenshtein_distance("abc", "abc") == 0
    assert levenshtein_distance("kitten", "sitting") == 3
    assert levenshtein_distance("book", "back") == 2


def test_levenshtein_ratio():
    assert levenshtein_ratio("test task", "test task") == 1.0
    assert levenshtein_ratio("", "") == 1.0
    ratio = levenshtein_ratio("update payment gateway", "update payment api")
    assert 0.70 < ratio < 0.95


def test_trigram_similarity():
    sim_exact = trigram_similarity("deploy production backend", "deploy production backend")
    assert sim_exact == 1.0

    sim_diff = trigram_similarity("apple", "banana")
    assert sim_diff == 0.0

    sim_similar = trigram_similarity("fix auth bug", "fix oauth bug")
    assert sim_similar > 0.5


def test_calculate_task_similarity():
    score_exact = calculate_task_similarity("Fix login modal button", "fix login modal button")
    assert score_exact == 1.0

    score_close = calculate_task_similarity("Prepare Q3 financial report", "Prepare Q3 financial reports")
    assert score_close >= 0.85

    score_different = calculate_task_similarity("Write unit tests", "Deploy k8s cluster")
    assert score_different < 0.3


@pytest.mark.asyncio
async def test_find_potential_duplicate():
    mock_rows = [
        {"task_id": 101, "task": "Prepare Q3 Financial Report"},
        {"task_id": 102, "task": "Design Landing Page"},
    ]

    with patch("heuristics.dedup.db.fetchall", new=AsyncMock(return_value=mock_rows)):
        # High similarity task
        match = await find_potential_duplicate("Prepare Q3 Financial Reports", "user_1")
        assert match is not None
        assert match["task_id"] == 101
        assert match["similarity_pct"] >= 80

        # Dissimilar task
        no_match = await find_potential_duplicate("Deploy Docker container", "user_1")
        assert no_match is None


# ─────────────────────────────────────────────────────────────────────────────
# 2. Multi-Tag Boolean & Attribute Search Parser Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_tokenizer():
    query = 'tag:backend AND (priority:p6 OR status:pending) "auth error"'
    tokens = tokenize(query)
    types = [t.type for t in tokens]
    assert types == [
        TokenType.ATTR,
        TokenType.AND,
        TokenType.LPAREN,
        TokenType.ATTR,
        TokenType.OR,
        TokenType.ATTR,
        TokenType.RPAREN,
        TokenType.WORD,
        TokenType.EOF,
    ]


def test_compile_boolean_query_simple():
    sql, params = compile_boolean_query("backend")
    assert "(t.task ILIKE $1 OR (t.description IS NOT NULL AND t.description ILIKE $1))" in sql
    assert params == ["%backend%"]


def test_compile_boolean_query_and_or_not():
    sql, params = compile_boolean_query("tag:backend AND NOT status:completed")
    assert "t.tags ILIKE $1" in sql
    assert "NOT" in sql
    assert "t.status = $2" in sql
    assert params == ["%backend%", "Completed"]


def test_compile_boolean_query_priority_attributes():
    sql, params = compile_boolean_query("priority:>=5")
    assert "t.priority >= $1" in sql
    assert params == [5]

    sql2, params2 = compile_boolean_query("priority:critical")
    assert "t.priority = $1" in sql2
    assert params2 == [7]


def test_compile_boolean_query_has_attributes():
    sql, params = compile_boolean_query("has:attachment OR has:checklist")
    assert "EXISTS (SELECT 1 FROM task_attachments a WHERE a.task_id = t.task_id)" in sql
    assert "EXISTS (SELECT 1 FROM task_checklists c WHERE c.task_id = t.task_id)" in sql
    assert len(params) == 0


def test_compile_boolean_query_with_base_params():
    base = ["user_123"]
    sql, params = compile_boolean_query("tag:urgent", base_params=base)
    assert "$2" in sql
    assert params == ["user_123", "%urgent%"]


# ─────────────────────────────────────────────────────────────────────────────
# 3. Day Planner Schedule Optimizer Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_time_str():
    assert _parse_time_str("09:00") == (9, 0)
    assert _parse_time_str("18:30") == (18, 30)
    assert _parse_time_str("14") == (14, 0)
    assert _parse_time_str("invalid", default_h=8, default_m=15) == (8, 15)


@pytest.mark.asyncio
async def test_optimize_day_schedule():
    mock_matrix = EisenhowerMatrixData(
        q1_tasks=[
            EisenhowerTask(
                task_id=1,
                task="Urgent Prod Incident",
                priority=7,
                status="Pending",
                quadrant=EisenhowerQuadrant.Q1_DO_FIRST,
                is_urgent=True,
                is_important=True,
            )
        ],
        q2_tasks=[
            EisenhowerTask(
                task_id=2,
                task="Refactor Database Core",
                priority=5,
                status="In Progress",
                quadrant=EisenhowerQuadrant.Q2_SCHEDULE,
                is_urgent=False,
                is_important=True,
            )
        ],
    )

    with patch("organization.service.get_eisenhower_matrix", new=AsyncMock(return_value=mock_matrix)):
        plan: DayPlanResult = await optimize_day_schedule(
            user_id="user_123",
            start_time="09:00",
            end_time="17:00",
            focus_mins=45,
            break_mins=15,
        )

        assert plan.start_time == "09:00"
        assert plan.end_time == "17:00"
        assert plan.first_task_id == 1
        assert plan.first_task_title == "Urgent Prod Incident"
        assert plan.tasks_count >= 2

        # Check block types
        block_types = [b.block_type for b in plan.blocks]
        assert "FOCUS" in block_types
        assert "BREAK" in block_types
        assert "LUNCH" in block_types

        # Lunch should be scheduled around 12:00-13:00
        lunch_blocks = [b for b in plan.blocks if b.block_type == "LUNCH"]
        assert len(lunch_blocks) == 1
        assert "12:00" <= lunch_blocks[0].start_str <= "12:30"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Day Plan Embed & View Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_build_day_plan_embed():
    blocks = [
        TimeBlock("09:00", "09:45", "FOCUS", task_id=1, task_title="Fix Auth Bug", priority=6, quadrant="Q1 - Do First"),
        TimeBlock("09:45", "10:00", "BREAK", task_title="☕ Ergonomic Break", is_break=True),
        TimeBlock("12:00", "13:00", "LUNCH", task_title="🍱 Lunch Break", is_break=True),
        TimeBlock("13:00", "13:45", "FOCUS", task_id=2, task_title="Write Docs", priority=4, quadrant="Q2 - Schedule"),
    ]
    plan = DayPlanResult(
        user_id="user_123",
        work_date="2026-11-09",
        start_time="09:00",
        end_time="17:00",
        blocks=blocks,
        total_focus_minutes=90,
        total_break_minutes=75,
        tasks_count=2,
        first_task_id=1,
        first_task_title="Fix Auth Bug",
    )

    embed = build_day_plan_embed(plan, lang="en")
    assert "Smart Daily Schedule" in embed.title
    assert "2026-11-09" in embed.title
    assert len(embed.fields) >= 2


@pytest.mark.asyncio
async def test_day_plan_action_view_timer():
    view = DayPlanActionView(
        user_id="user_123",
        first_task_id=42,
        first_task_title="Deploy Server",
        lang="en",
    )

    # Test interaction check
    mock_wrong_user = MagicMock(user=MagicMock(id="wrong_user"))
    mock_wrong_user.response = MagicMock(send_message=AsyncMock())
    allowed = await view.interaction_check(mock_wrong_user)
    assert allowed is False

    mock_owner = MagicMock(user=MagicMock(id=123))
    mock_owner.user.id = "user_123"
    allowed_owner = await view.interaction_check(mock_owner)
    assert allowed_owner is True

    # Test start timer callback
    with patch("time_tracking.service.start_timer", new=AsyncMock()) as mock_start:
        mock_inter = MagicMock(user=MagicMock(id="user_123"))
        mock_inter.response = MagicMock(edit_message=AsyncMock())
        mock_inter.followup = MagicMock(send=AsyncMock())

        await view.start_timer_callback(mock_inter)
        mock_start.assert_called_once_with(
            user_id="user_123",
            task_id=42,
            note="Day Plan Session",
        )
        assert view.start_btn.disabled is True


# ─────────────────────────────────────────────────────────────────────────────
# 5. FtsEngine Boolean Routing Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_fts_engine_is_boolean_query():
    from search_recommendation.fts_engine import FtsEngine

    engine = FtsEngine()
    assert engine._is_boolean_query("tag:backend") is True
    assert engine._is_boolean_query("backend AND frontend") is True
    assert engine._is_boolean_query("(auth OR oauth)") is True
    assert engine._is_boolean_query("priority:high") is True
    assert engine._is_boolean_query("status:completed") is True
    assert engine._is_boolean_query("due:<=today") is True
    assert engine._is_boolean_query("has:attachment") is True

    # Standard plain text
    assert engine._is_boolean_query("simple search text") is False
    assert engine._is_boolean_query("") is False


@pytest.mark.asyncio
async def test_fts_engine_boolean_search_execution():
    from search_recommendation.fts_engine import FtsEngine
    from search_recommendation.models import SearchFilter, SearchQuery

    engine = FtsEngine()
    query = SearchQuery(
        text="tag:urgent AND status:pending",
        filter=SearchFilter(owner_id="user_123"),
    )

    mock_count = {"total": 1}
    mock_rows = [
        {
            "task_id": 99,
            "task": "Urgent Server Migration",
            "deadline": "2026-11-10T00:00:00Z",
            "priority": 6,
            "status": "Pending",
            "tags": "urgent,devops",
            "description": "Migrate database",
            "note": None,
            "owner_id": "user_123",
            "guild_id": None,
            "project_id": None,
            "is_pinned": 0,
            "created_at": "2026-11-09T00:00:00Z",
            "updated_at": "2026-11-09T00:00:00Z",
            "completed_at": None,
            "rank_score": 0.0,
        }
    ]

    with patch("search_recommendation.fts_engine.db.fetchone", new=AsyncMock(return_value=mock_count)), \
         patch("search_recommendation.fts_engine.db.fetchall", new=AsyncMock(return_value=mock_rows)):
        page = await engine.search(query)
        assert page.total == 1
        assert len(page.items) == 1
        assert page.items[0].task_id == 99
        assert page.items[0].task == "Urgent Server Migration"


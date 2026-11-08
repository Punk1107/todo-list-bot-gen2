"""
tests/test_agile_scrum.py — Comprehensive Unit Tests for Pillar 1: Agile & Scrum Full Suite (Gen 5.0).

Covers all 6 features:
1. Sprint & Milestone Lifecycle (create, start, conflict prevention, close with carryover)
2. Story Points & Velocity Tracker (Fibonacci validation, SQL velocity window, backlog forecasting)
3. Interactive Planning Poker (secret voting, reveal calculations, consensus auto-save)
4. Epics & Multi-Tier Hierarchy (tree view, progress %, story points rollup)
5. Work-In-Progress (WIP) Limits & Swimlanes (WipLimitExceeded guard, swimlane grouping)
6. Interactive Sprint Retrospective Board & Dot Voting (3-vote limit per user, action items conversion)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
import pytest

from agile import service
from agile.models import (
    FIBONACCI_POINTS,
    Epic,
    EpicStatus,
    PlanningPokerSession,
    RetroCard,
    RetroColumn,
    Sprint,
    SprintStatus,
    VelocityStats,
)
from agile.views import (
    build_epic_embed,
    build_poker_embed,
    build_retro_embed,
    build_sprint_embed,
    build_velocity_embed,
)
from collaboration import service as collab_service
from collaboration.models import BoardData, Project, ProjectTask
from collaboration.views import build_board_embed


# ─────────────────────────────────────────────────────────────────────────────
# 1. Feature 1: Sprint & Milestone Lifecycle
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sprint_create():
    now = datetime.now(timezone.utc)
    mock_row = {
        "sprint_id": 101,
        "project_id": 1,
        "name": "Sprint 1 — Core Auth",
        "status": "planned",
        "goal": "Implement JWT and OAuth",
        "start_date": None,
        "end_date": None,
        "created_at": now,
        "total_tasks": 0,
        "completed_tasks": 0,
        "total_points": 0,
        "completed_points": 0,
    }

    with patch.object(service.db, "afetchone", new=AsyncMock(return_value=mock_row)):
        sprint = await service.create_sprint(
            project_id=1,
            name="Sprint 1 — Core Auth",
            goal="Implement JWT and OAuth",
            duration_days=14,
        )
        assert sprint.sprint_id == 101
        assert sprint.name == "Sprint 1 — Core Auth"
        assert sprint.status == "planned"
        assert sprint.goal == "Implement JWT and OAuth"
        assert sprint.is_active is False
        assert sprint.is_closed is False


@pytest.mark.asyncio
async def test_sprint_start_success():
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=14)
    updated_row = {
        "sprint_id": 101,
        "project_id": 1,
        "name": "Sprint 1",
        "status": "active",
        "goal": "Launch v1",
        "start_date": now,
        "end_date": end,
        "created_at": now,
        "total_tasks": 5,
        "completed_tasks": 1,
        "total_points": 13,
        "completed_points": 3,
    }

    # 1st call: check existing active sprint (returns None)
    # 2nd call: update sprint to active
    with patch.object(service.db, "afetchone", new=AsyncMock(side_effect=[None, updated_row])):
        sprint = await service.start_sprint(101, 1)
        assert sprint.status == "active"
        assert sprint.is_active is True
        assert sprint.total_tasks == 5
        assert sprint.completed_tasks == 1
        assert sprint.completion_pct == 20


@pytest.mark.asyncio
async def test_sprint_start_conflict_prevents_two_active():
    active_row = {"sprint_id": 99, "name": "Sprint 0"}

    with patch.object(service.db, "afetchone", new=AsyncMock(return_value=active_row)):
        with pytest.raises(service.SprintAlreadyActiveError) as exc_info:
            await service.start_sprint(101, 1)
        assert "Sprint #99 is already active" in str(exc_info.value)


@pytest.mark.asyncio
async def test_sprint_close_with_carryover_to_backlog():
    now = datetime.now(timezone.utc)
    # Tasks in the sprint: 2 completed (5 pts, 3 pts), 1 pending (8 pts)
    sprint_tasks = [
        {"task_id": 1, "status": "Completed", "story_points": 5},
        {"task_id": 2, "status": "Completed", "story_points": 3},
        {"task_id": 3, "status": "In_Progress", "story_points": 8},
    ]
    closed_row = {
        "sprint_id": 101,
        "project_id": 1,
        "name": "Sprint 1",
        "status": "closed",
        "goal": "Done",
        "start_date": now - timedelta(days=14),
        "end_date": now,
        "created_at": now - timedelta(days=14),
        "total_tasks": 3,
        "completed_tasks": 2,
        "total_points": 16,
        "completed_points": 8,
    }

    with patch.object(service.db, "afetchall", new=AsyncMock(return_value=sprint_tasks)), \
         patch.object(service.db, "aexecute", new=AsyncMock(return_value="UPDATE 1")), \
         patch.object(service.db, "afetchone", new=AsyncMock(return_value=closed_row)), \
         patch("collaboration.service.log_activity", new=AsyncMock()):

        sprint, done_cnt, carried_cnt, pts = await service.close_sprint(
            sprint_id=101,
            project_id=1,
            user_id="user_admin",
            carryover_target="backlog",
        )
        assert sprint.status == "closed"
        assert sprint.is_closed is True
        assert done_cnt == 2
        assert carried_cnt == 1  # 1 unfinished task carried over to backlog
        assert pts == 8          # 8 story points completed


# ─────────────────────────────────────────────────────────────────────────────
# 2. Feature 2: Story Points & Velocity Tracker
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_set_story_points_fibonacci_guard():
    # Valid Fibonacci points
    for pt in [1, 2, 3, 5, 8, 13, 21]:
        with patch.object(service.db, "aexecute", new=AsyncMock(return_value="UPDATE 1")):
            ok = await service.set_task_story_points(task_id=10, points=pt)
            assert ok is True

    # Invalid points must raise InvalidStoryPointError
    for invalid_pt in [0, 4, 6, 7, 9, 10, 15, 50, 100]:
        with pytest.raises(service.InvalidStoryPointError):
            await service.set_task_story_points(task_id=10, points=invalid_pt)


@pytest.mark.asyncio
async def test_velocity_calculation_and_forecasting():
    # 3 past closed sprints
    history_rows = [
        {"sprint_id": 1, "name": "Sprint 1", "completed_points": 20},
        {"sprint_id": 2, "name": "Sprint 2", "completed_points": 25},
        {"sprint_id": 3, "name": "Sprint 3", "completed_points": 15},
    ]
    # Sum = 60 points / 3 sprints = 20.0 avg velocity
    backlog_row = {"backlog_tasks_count": 8, "backlog_points": 50}

    with patch.object(service.db, "afetchall", new=AsyncMock(return_value=history_rows)), \
         patch.object(service.db, "afetchone", new=AsyncMock(return_value=backlog_row)):

        stats = await service.get_velocity_stats(project_id=1)
        assert stats.project_id == 1
        assert stats.average_velocity == 20.0
        assert stats.backlog_tasks_count == 8
        assert stats.backlog_points == 50
        # 50 points remaining / 20.0 avg velocity = 2.5 -> ceil = 3 sprints
        assert stats.forecast_sprints == 3
        assert len(stats.sprint_history) == 3


# ─────────────────────────────────────────────────────────────────────────────
# 3. Feature 3: Interactive Planning Poker
# ─────────────────────────────────────────────────────────────────────────────

def test_planning_poker_voting_flow():
    # Start poker session
    session = service.start_poker(task_id=45, host_id="host_1", task_title="Design API Gateway")
    assert session.task_id == 45
    assert session.is_revealed is False
    assert session.voter_count == 0

    # User 1 secret vote
    service.vote_poker(task_id=45, user_id="u1", points=5)
    # User 2 secret vote
    service.vote_poker(task_id=45, user_id="u2", points=8)
    # User 3 secret vote
    service.vote_poker(task_id=45, user_id="u3", points=5)

    assert session.voter_count == 3
    # Before reveal, votes are concealed in embed
    embed_hidden = build_poker_embed(session)
    assert "[Voted 🔒]" in embed_hidden.fields[0].value

    # Reveal votes
    revealed_session = service.reveal_poker(task_id=45)
    assert revealed_session.is_revealed is True
    # Mean: (5 + 8 + 5) / 3 = 6.0
    assert revealed_session.mean == 6.0
    # Median: sorted [5, 5, 8] -> 5.0
    assert revealed_session.median == 5.0
    # Nearest Fibonacci to 6.0 is 5
    assert revealed_session.nearest_fibonacci == 5

    # Revealed embed shows stats
    embed_revealed = build_poker_embed(revealed_session)
    assert "Revealed Cards" in embed_revealed.fields[0].name
    assert "Mean (Average)" in embed_revealed.fields[1].value


def test_planning_poker_consensus_detection():
    service.start_poker(task_id=77, host_id="host_1", task_title="Bugfix")
    service.vote_poker(task_id=77, user_id="u1", points=3)
    service.vote_poker(task_id=77, user_id="u2", points=3)
    service.vote_poker(task_id=77, user_id="u3", points=3)

    revealed = service.reveal_poker(task_id=77)
    assert revealed.consensus == 3  # All voters agreed on 3


# ─────────────────────────────────────────────────────────────────────────────
# 4. Feature 4: Epics & Multi-Tier Hierarchy
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_epic_creation_and_attach():
    now = datetime.now(timezone.utc)
    epic_row = {
        "epic_id": 10,
        "project_id": 2,
        "name": "Database Redesign",
        "description": "Schema v36 Migration",
        "color": "#5865F2",
        "status": "in_progress",
        "created_at": now,
        "total_tasks": 0,
        "completed_tasks": 0,
        "total_points": 0,
        "completed_points": 0,
    }

    with patch.object(service.db, "afetchone", new=AsyncMock(return_value=epic_row)):
        epic = await service.create_epic(2, "Database Redesign", "Schema v36 Migration", "#5865F2")
        assert epic.epic_id == 10
        assert epic.name == "Database Redesign"
        assert epic.progress_pct == 0

    with patch.object(service.db, "aexecute", new=AsyncMock(return_value="UPDATE 1")):
        ok = await service.attach_task_to_epic(task_id=12, epic_id=10, project_id=2)
        assert ok is True


@pytest.mark.asyncio
async def test_epic_hierarchy_tree_and_progress():
    tasks_tree_rows = [
        {"task_id": 1, "task": "Parent Task 1", "status": "Completed", "priority": 1, "story_points": 5, "parent_task_id": None},
        {"task_id": 2, "task": "Subtask 1.1", "status": "Completed", "priority": 1, "story_points": 2, "parent_task_id": 1},
        {"task_id": 3, "task": "Parent Task 2", "status": "In_Progress", "priority": 2, "story_points": 8, "parent_task_id": None},
    ]

    with patch.object(service.db, "afetchall", new=AsyncMock(return_value=tasks_tree_rows)):
        tree = await service.get_epic_tasks_tree(epic_id=10)
        assert len(tree) == 2  # 2 parent tasks
        parent_1 = tree[0]
        assert parent_1["task_id"] == 1
        assert len(parent_1["subtasks"]) == 1
        assert parent_1["subtasks"][0]["task_id"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# 5. Feature 5: Work-In-Progress (WIP) Limits & Swimlanes on Kanban
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_wip_limit_configuration_and_retrieval():
    with patch.object(collab_service.db, "aexecute", new=AsyncMock()), \
         patch.object(collab_service.db, "afetchone", new=AsyncMock(return_value={"setting_value": "4"})), \
         patch("collaboration.service.log_activity", new=AsyncMock()):

        val = await collab_service.set_project_wip_limit(
            project_id=5,
            guild_id="guild_1",
            wip_limit=4,
            actor_id="user_lead",
            is_guild_admin=True,
        )
        assert val == 4

        retrieved = await collab_service.get_project_wip_limit(5, "guild_1")
        assert retrieved == 4


@pytest.mark.asyncio
async def test_wip_limit_guard_raises_exception():
    fake_project = Project(
        project_id=5,
        guild_id="guild_1",
        name="Backend",
        description="",
        emoji="📁",
        color="#5865F2",
        status="active",
        created_by="u1",
        created_at=datetime.now(timezone.utc),
        role_permissions={},
    )
    fake_task = ProjectTask(
        task_id=99,
        project_id=5,
        guild_id="guild_1",
        task="Optimize SQL Queries",
        description="",
        status="Pending",
        priority=2,
        priority_emoji="🟩",
        deadline=None,
        is_private=False,
        created_by="u1",
        created_at=datetime.now(timezone.utc),
        assignees=[],
        assigned_roles=[],
        blocked_by=[],
    )

    # When WIP limit = 3 and current In_Progress tasks = 3, transition must fail!
    with patch("collaboration.service.get_project", new=AsyncMock(return_value=fake_project)), \
         patch("collaboration.service.get_project_task", new=AsyncMock(return_value=fake_task)), \
         patch("collaboration.service.get_project_wip_limit", new=AsyncMock(return_value=3)), \
         patch.object(collab_service.db, "fetch_one", new=AsyncMock(return_value={"cnt": 3})), \
         patch("collaboration.service._get_incomplete_task_blockers", new=AsyncMock(return_value=[])):

        with pytest.raises(collab_service.WipLimitExceeded) as exc_info:
            await collab_service.update_task_status(
                task_id=99,
                project_id=5,
                guild_id="guild_1",
                new_status="In_Progress",
                actor_id="u1",
                is_guild_admin=True,
            )
        assert exc_info.value.limit == 3
        assert exc_info.value.current == 3
        assert "WIP Limit Exceeded" in str(exc_info.value)


def test_kanban_board_wip_and_swimlanes():
    p = Project(
        project_id=1, guild_id="g1", name="Scrum Team", description="", emoji="🚀",
        color="#5865F2", status="active", created_by="u1", created_at=datetime.now(timezone.utc),
        role_permissions={},
    )
    t1 = ProjectTask(
        task_id=1, project_id=1, guild_id="g1", task="Task 1", description="",
        status="In_Progress", priority=3, priority_emoji="🟨", deadline=None,
        is_private=False, created_by="u1", created_at=datetime.now(timezone.utc),
        assignees=["user_alice"], assigned_roles=[], blocked_by=[],
    )
    t2 = ProjectTask(
        task_id=2, project_id=1, guild_id="g1", task="Task 2", description="",
        status="In_Progress", priority=1, priority_emoji="🟦", deadline=None,
        is_private=False, created_by="u1", created_at=datetime.now(timezone.utc),
        assignees=["user_bob"], assigned_roles=[], blocked_by=[],
    )

    board = BoardData(
        project=p,
        pending=[],
        in_progress=[t1, t2],
        completed=[],
        cancelled=[],
        wip_limit=2,  # Exactly at WIP limit
    )

    # In_Progress column should display Maxed badge
    embed = build_board_embed(board, lang="th", column="in_progress")
    assert "[WIP: 2/2 Maxed]" in embed.title

    # Swimlane grouping by assignee
    embed_swimlane = build_board_embed(board, lang="th", column="in_progress", swimlane="assignee")
    assert "Swimlane: Assignee" in embed_swimlane.title
    field_names = [f.name for f in embed_swimlane.fields]
    assert any("<@user_alice>" in name for name in field_names)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Feature 6: Interactive Sprint Retrospective Board & Dot Voting
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_retro_card_submission():
    now = datetime.now(timezone.utc)
    card_row = {
        "retro_id": 1,
        "sprint_id": 10,
        "column_type": "well",
        "content": "Great pairing on database migrations!",
        "author_id": "u1",
        "votes": 0,
        "created_at": now,
    }

    with patch.object(service.db, "afetchone", new=AsyncMock(return_value=card_row)):
        card = await service.add_retro_card(10, "well", "Great pairing on database migrations!", "u1")
        assert card.retro_id == 1
        assert card.column_type == "well"
        assert card.votes == 0


@pytest.mark.asyncio
async def test_retro_dot_voting_limit_guard():
    # Clear in-memory votes for clean test state
    service._RETRO_USER_VOTES.clear()

    card_row = {
        "retro_id": 5,
        "sprint_id": 10,
        "column_type": "action",
        "content": "Refactor API responses",
        "author_id": "u1",
        "votes": 1,
        "created_at": datetime.now(timezone.utc),
    }

    with patch.object(service.db, "afetchone", new=AsyncMock(return_value=card_row)):
        # Votes 1, 2, 3 should succeed
        v1 = await service.vote_retro_card(5, sprint_id=10, user_id="voter_1")
        assert service.get_user_remaining_votes(10, "voter_1") == 2

        v2 = await service.vote_retro_card(5, sprint_id=10, user_id="voter_1")
        assert service.get_user_remaining_votes(10, "voter_1") == 1

        v3 = await service.vote_retro_card(5, sprint_id=10, user_id="voter_1")
        assert service.get_user_remaining_votes(10, "voter_1") == 0

        # 4th vote must raise DotVotesExhaustedError!
        with pytest.raises(service.DotVotesExhaustedError) as exc_info:
            await service.vote_retro_card(5, sprint_id=10, user_id="voter_1")
        assert "used all 3 dot votes" in str(exc_info.value)


@pytest.mark.asyncio
async def test_retro_convert_actions_to_backlog():
    action_cards = [
        {"retro_id": 1, "content": "Write integration tests for payments"},
        {"retro_id": 2, "content": "Set up Grafana alerts for latency"},
    ]

    with patch.object(service.db, "afetchall", new=AsyncMock(return_value=action_cards)), \
         patch.object(service.db, "aexecute", new=AsyncMock(return_value="INSERT 1")), \
         patch("collaboration.service.log_activity", new=AsyncMock()):

        count = await service.convert_action_items_to_tasks(sprint_id=10, project_id=1, user_id="lead_1")
        assert count == 2


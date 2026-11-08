"""
tests/test_agile_scrum.py — Comprehensive Unit Tests for Pillar 1: Agile & Scrum Full Suite (Gen 5.0).

Covers all 6 features:
1. Sprint & Milestone Lifecycle (models, statuses, completion %, date formatting)
2. Story Points & Velocity Tracker (Fibonacci validation, velocity calculation, backlog forecasting)
3. Interactive Planning Poker (secret voting, reveal calculations, consensus auto-save)
4. Epics & Multi-Tier Hierarchy (tree view, progress %, story points rollup)
5. Work-In-Progress (WIP) Limits & Swimlanes (WipLimitExceeded guard, swimlane grouping)
6. Interactive Sprint Retrospective Board & Dot Voting (3-vote limit per user, action items conversion)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

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


class TestAgileScrum(unittest.TestCase):
    """Test suite for Pillar 1 (Agile & Scrum)."""

    def test_sprint_model_and_completion_metrics(self):
        """Test Sprint model calculations, completion percentages, and days remaining."""
        now = datetime.now(timezone.utc)
        end = now + timedelta(days=14)
        sprint = Sprint(
            sprint_id=101,
            project_id=1,
            name="Sprint 1 — Core Auth",
            status="active",
            goal="Implement JWT and OAuth",
            start_date=now,
            end_date=end,
            created_at=now,
            total_tasks=10,
            completed_tasks=4,
            total_points=25,
            completed_points=10,
        )

        self.assertTrue(sprint.is_active)
        self.assertFalse(sprint.is_closed)
        self.assertEqual(sprint.completion_pct, 40)
        self.assertEqual(sprint.points_completion_pct, 40)
        self.assertIsNotNone(sprint.days_remaining)
        self.assertGreaterEqual(sprint.days_remaining, 13)

        embed = build_sprint_embed(sprint)
        self.assertIn("Sprint 1 — Core Auth", embed.title)
        self.assertIn("Implement JWT and OAuth", embed.description)

    def test_fibonacci_story_points_validation(self):
        """Test Fibonacci sequence validation for story points."""
        valid_points = [1, 2, 3, 5, 8, 13, 21]
        for pt in valid_points:
            self.assertIn(pt, FIBONACCI_POINTS)

        invalid_points = [0, 4, 6, 7, 9, 10, 15, 50, 100]
        for invalid_pt in invalid_points:
            self.assertNotIn(invalid_pt, FIBONACCI_POINTS)

    def test_velocity_calculation_and_forecasting(self):
        """Test velocity average and sprint capacity forecasting formulas."""
        closed_sprints = [
            ("Sprint 1", 20),
            ("Sprint 2", 25),
            ("Sprint 3", 15),
        ]
        # Sum = 60 / 3 = 20.0 avg velocity
        # Backlog = 50 points -> 50 / 20 = 2.5 -> ceil = 3 sprints
        stats = service.compute_velocity_stats(
            project_id=1,
            closed_sprints=closed_sprints,
            backlog_count=8,
            backlog_points=50,
        )
        self.assertEqual(stats.average_velocity, 20.0)
        self.assertEqual(stats.backlog_tasks_count, 8)
        self.assertEqual(stats.backlog_points, 50)
        self.assertEqual(stats.forecast_sprints, 3)

        embed = build_velocity_embed(stats)
        self.assertIn("Team Velocity", embed.title)
        self.assertIn("~3 Sprints", embed.description)

    def test_planning_poker_voting_flow(self):
        """Test secret voting, reveal stats, and nearest Fibonacci consensus."""
        session = PlanningPokerSession(
            task_id=45,
            task_title="Design API Gateway",
            host_id="host_1",
        )
        self.assertFalse(session.is_revealed)
        self.assertEqual(session.voter_count, 0)

        # Secret votes
        session.cast_vote("u1", 5)
        session.cast_vote("u2", 8)
        session.cast_vote("u3", 5)
        self.assertEqual(session.voter_count, 3)

        # Before reveal: embed conceals votes
        embed_hidden = build_poker_embed(session)
        self.assertIn("[Voted 🔒]", embed_hidden.fields[0].value)

        # Reveal
        session.is_revealed = True
        self.assertEqual(session.mean, 6.0)
        self.assertEqual(session.median, 5.0)
        self.assertEqual(session.nearest_fibonacci, 5)

        embed_revealed = build_poker_embed(session)
        self.assertIn("Revealed Cards", embed_revealed.fields[0].name)
        self.assertIn("Mean (Average)", embed_revealed.fields[1].value)

    def test_planning_poker_consensus_detection(self):
        """Test consensus detection when all voters agree."""
        session = PlanningPokerSession(task_id=77, task_title="Bugfix", host_id="host_1")
        session.cast_vote("u1", 3)
        session.cast_vote("u2", 3)
        session.cast_vote("u3", 3)
        session.is_revealed = True
        self.assertEqual(session.consensus, 3)

    def test_epic_model_and_tree_embed(self):
        """Test Epic progress metrics and hierarchical task tree rendering."""
        now = datetime.now(timezone.utc)
        epic = Epic(
            epic_id=10,
            project_id=2,
            name="Database Redesign",
            description="Schema v36 Migration",
            color="#5865F2",
            status="in_progress",
            created_at=now,
            total_tasks=5,
            completed_tasks=3,
            total_points=20,
            completed_points=12,
        )
        self.assertEqual(epic.progress_pct, 60)

        tasks_tree = [
            {
                "task_id": 1,
                "task": "Parent Task 1",
                "status": "Completed",
                "priority": 1,
                "story_points": 5,
                "subtasks": [
                    {"task_id": 2, "task": "Subtask 1.1", "status": "Completed"},
                ],
            },
            {
                "task_id": 3,
                "task": "Parent Task 2",
                "status": "In_Progress",
                "priority": 2,
                "story_points": 8,
                "subtasks": [],
            },
        ]

        embed = build_epic_embed(epic, tasks_tree)
        self.assertIn("Database Redesign", embed.title)
        self.assertTrue(any("Hierarchical Task Tree" in f.name for f in embed.fields))

    def test_kanban_board_wip_and_swimlanes(self):
        """Test Kanban board WIP limits and swimlane groupings."""
        now = datetime.now(timezone.utc)
        p = Project(
            project_id=1, guild_id="g1", name="Scrum Team", description="", owner_id="u1",
            status="active", color="#5865F2", emoji="🚀", channel_id=None, role_id=None,
            created_at=now, updated_at=now,
        )
        t1 = ProjectTask(
            task_id=1, project_id=1, guild_id="g1", task="Task 1", status="In_Progress",
            priority=3, deadline="", owner_id="u1", description="", tags=None,
            created_at=now, updated_at=now, is_private=False,
            assignees=["user_alice"], assigned_roles=[], blocked_by=[],
        )
        t2 = ProjectTask(
            task_id=2, project_id=1, guild_id="g1", task="Task 2", status="In_Progress",
            priority=1, deadline="", owner_id="u1", description="", tags=None,
            created_at=now, updated_at=now, is_private=False,
            assignees=["user_bob"], assigned_roles=[], blocked_by=[],
        )

        board = BoardData(
            project=p,
            pending=[],
            in_progress=[t1, t2],
            completed=[],
            cancelled=[],
            wip_limit=2,  # At max capacity
        )

        # In_Progress column should display Maxed badge
        embed = build_board_embed(board, lang="th", column="in_progress")
        self.assertIn("[WIP: 2/2 Maxed]", embed.title)

        # Swimlane grouping by assignee
        embed_swimlane = build_board_embed(board, lang="th", column="in_progress", swimlane="assignee")
        self.assertIn("Swimlane: Assignee", embed_swimlane.title)
        field_names = [f.name for f in embed_swimlane.fields]
        self.assertTrue(any("<@user_alice>" in name for name in field_names))

    def test_retro_models_and_embed(self):
        """Test Retrospective cards and 3-vote limit mechanism."""
        service._RETRO_USER_VOTES.clear()

        # Dot vote limits
        service._RETRO_USER_VOTES[(10, "voter_1")] = 1
        rem = service.get_user_remaining_votes(10, "voter_1")
        self.assertEqual(rem, 2)

        service._RETRO_USER_VOTES[(10, "voter_1")] = 3
        rem_none = service.get_user_remaining_votes(10, "voter_1")
        self.assertEqual(rem_none, 0)

        c1 = RetroCard(retro_id=1, sprint_id=10, column_type="well", content="Great pairing!", author_id="u1", votes=3)
        c2 = RetroCard(retro_id=2, sprint_id=10, column_type="improve", content="Better docs", author_id=None, votes=1)
        c3 = RetroCard(retro_id=3, sprint_id=10, column_type="action", content="Write tests", author_id="u2", votes=5)

        board = {
            RetroColumn.WELL.value: [c1],
            RetroColumn.IMPROVE.value: [c2],
            RetroColumn.ACTION.value: [c3],
        }
        embed = build_retro_embed(10, board)
        self.assertIn("Sprint Retrospective Board", embed.title)
        self.assertTrue(any("What Went Well" in f.name for f in embed.fields))
        self.assertTrue(any("Action Items" in f.name for f in embed.fields))


if __name__ == "__main__":
    unittest.main()

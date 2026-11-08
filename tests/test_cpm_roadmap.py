"""
tests/test_cpm_roadmap.py — Comprehensive Unit Tests for Pillar 2:
Critical Path Method (CPM), Roadmaps & Gantt Engine (Gen 5.0).

Covers:
  1. CPM Forward/Backward Pass, Slack calculation, and Critical Path identification
  2. Circular dependency (Cycle) detection guard
  3. Lead risk warning when critical tasks are overdue
  4. In-Discord ASCII Gantt codeblock rendering
  5. High-Res In-Memory PNG Gantt Chart generation via Pure Pillow
  6. Strategic Milestone Health Predictor (🟢 On Track / 🟡 At Risk / 🔴 Delayed)
  7. Milestone bottleneck identification and data models
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import io
import unittest

from cpm_roadmap import cpm_engine, gantt_renderer, roadmap_service
from cpm_roadmap.models import (
    CPMGraphResult,
    CPMNode,
    HealthStatus,
    MilestoneHealth,
    ProjectMilestone,
)
from cpm_roadmap.views import build_cpm_embed, build_gantt_embed, build_roadmap_embed


class TestCPMRoadmap(unittest.TestCase):
    """Test suite for Pillar 2 (CPM, Gantt & Roadmap)."""

    def test_cpm_forward_backward_pass_and_critical_path(self):
        """
        Test network graph with 4 tasks:
          Task 1 (8h): Root
          Task 2 (16h): depends on 1
          Task 3 (8h): depends on 1
          Task 4 (8h): depends on 2 and 3
        Critical path must be: 1 -> 2 -> 4 (Total = 32h = 4.0d).
        Task 3 must have Slack = 8.0h (Non-critical).
        """
        now = datetime.now(timezone.utc)
        n1 = CPMNode(task_id=1, task_name="Database Schema", duration_hours=8.0, status="Completed")
        n2 = CPMNode(task_id=2, task_name="Backend API", duration_hours=16.0, status="In_Progress", predecessors=[1])
        n3 = CPMNode(task_id=3, task_name="Design Mockups", duration_hours=8.0, status="In_Progress", predecessors=[1])
        n4 = CPMNode(task_id=4, task_name="Frontend Integration", duration_hours=8.0, status="Pending", predecessors=[2, 3])

        n1.successors = [2, 3]
        n2.successors = [4]
        n3.successors = [4]

        nodes = {1: n1, 2: n2, 3: n3, 4: n4}
        result = cpm_engine.calculate_cpm_graph(nodes, project_id=1)

        self.assertFalse(result.has_cycle)
        self.assertEqual(result.total_duration_hours, 32.0)
        self.assertEqual(result.total_duration_days, 4.0)

        # Nodes check
        res_n1 = result.nodes[1]
        res_n2 = result.nodes[2]
        res_n3 = result.nodes[3]
        res_n4 = result.nodes[4]

        # Task 1: ES=0, EF=8, LS=0, LF=8, Slack=0 (Critical)
        self.assertEqual(res_n1.early_start, 0.0)
        self.assertEqual(res_n1.early_finish, 8.0)
        self.assertEqual(res_n1.late_start, 0.0)
        self.assertEqual(res_n1.late_finish, 8.0)
        self.assertEqual(res_n1.slack, 0.0)
        self.assertTrue(res_n1.is_critical)

        # Task 2: ES=8, EF=24, LS=8, LF=24, Slack=0 (Critical)
        self.assertEqual(res_n2.early_start, 8.0)
        self.assertEqual(res_n2.early_finish, 24.0)
        self.assertEqual(res_n2.slack, 0.0)
        self.assertTrue(res_n2.is_critical)

        # Task 3: ES=8, EF=16, LS=16, LF=24, Slack=8.0 (Float time)
        self.assertEqual(res_n3.early_start, 8.0)
        self.assertEqual(res_n3.early_finish, 16.0)
        self.assertEqual(res_n3.late_start, 16.0)
        self.assertEqual(res_n3.late_finish, 24.0)
        self.assertEqual(res_n3.slack, 8.0)
        self.assertFalse(res_n3.is_critical)

        # Task 4: ES=24, EF=32, LS=24, LF=32, Slack=0 (Critical)
        self.assertEqual(res_n4.early_start, 24.0)
        self.assertEqual(res_n4.early_finish, 32.0)
        self.assertEqual(res_n4.slack, 0.0)
        self.assertTrue(res_n4.is_critical)

        # Critical Path Sequence
        self.assertEqual(result.critical_path, [1, 2, 4])

    def test_cpm_cycle_detection(self):
        """Test circular dependency detection (A -> B -> A)."""
        n1 = CPMNode(task_id=10, task_name="Task A", duration_hours=8.0, predecessors=[20], successors=[20])
        n2 = CPMNode(task_id=20, task_name="Task B", duration_hours=8.0, predecessors=[10], successors=[10])
        nodes = {10: n1, 20: n2}

        result = cpm_engine.calculate_cpm_graph(nodes, project_id=2)
        self.assertTrue(result.has_cycle)
        self.assertTrue(result.is_at_risk)
        self.assertIn("Circular Dependency", result.risk_reason)

    def test_cpm_lead_risk_alerting(self):
        """Test risk flag when a critical path task is overdue."""
        now = datetime.now(timezone.utc)
        past_deadline = now - timedelta(days=2)
        n1 = CPMNode(
            task_id=99,
            task_name="Security Audit",
            duration_hours=16.0,
            status="In_Progress",
            deadline=past_deadline,
        )
        nodes = {99: n1}

        result = cpm_engine.calculate_cpm_graph(nodes, project_id=3)
        self.assertTrue(result.is_at_risk)
        self.assertIn("Security Audit", result.risk_reason)
        self.assertIn("Critical Path", result.risk_reason)

    def test_ascii_gantt_rendering(self):
        """Test ASCII Gantt chart generation for Discord embed codeblock."""
        n1 = CPMNode(task_id=1, task_name="Setup Infrastructure", duration_hours=8.0, early_start=0.0, early_finish=8.0, is_critical=True)
        n2 = CPMNode(task_id=2, task_name="Documentation", duration_hours=8.0, early_start=8.0, early_finish=16.0, slack=16.0, is_critical=False)
        result = CPMGraphResult(
            project_id=1,
            nodes={1: n1, 2: n2},
            critical_path=[1],
            total_duration_hours=24.0,
            total_duration_days=3.0,
        )

        ascii_text = gantt_renderer.render_ascii_gantt(result)
        self.assertIn("Setup Infr", ascii_text)
        self.assertIn("█", ascii_text)  # Critical path block
        self.assertIn("■", ascii_text)  # Normal block
        self.assertIn("Legend:", ascii_text)

        # Embed builder
        embed = build_gantt_embed(ascii_text, "Test Project")
        self.assertIn("In-Discord Gantt Chart", embed.title)

    def test_png_gantt_rendering(self):
        """Test High-Res PNG Gantt chart generation using Pure Pillow (in-memory)."""
        n1 = CPMNode(task_id=1, task_name="Core Engine", duration_hours=16.0, early_start=0.0, early_finish=16.0, is_critical=True)
        n2 = CPMNode(task_id=2, task_name="UI Components", duration_hours=8.0, early_start=16.0, early_finish=24.0, is_critical=True, predecessors=[1])
        result = CPMGraphResult(
            project_id=1,
            nodes={1: n1, 2: n2},
            critical_path=[1, 2],
            total_duration_hours=24.0,
            total_duration_days=3.0,
        )

        buf = gantt_renderer.render_png_gantt(result, "Alpha Release")
        self.assertIsInstance(buf, io.BytesIO)
        content = buf.getvalue()
        # Verify valid PNG header bytes
        self.assertTrue(content.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(content), 1000)

    def test_milestone_health_on_track(self):
        """Test On-Track status when progress matches elapsed time."""
        now = datetime.now(timezone.utc)
        start_date = now - timedelta(days=10)
        target_date = now + timedelta(days=20)  # Total 30 days, elapsed 10 days = 33.3%

        milestone = ProjectMilestone(
            milestone_id=1,
            project_id=10,
            title="Q1 Beta Release",
            target_date=target_date,
            total_tasks=10,
            completed_tasks=4,  # 40% progress >= 33.3% elapsed -> On Track
            total_points=20,
            completed_points=8,
        )

        health = roadmap_service.calculate_milestone_health(milestone, start_date, now)
        self.assertEqual(health.status, HealthStatus.ON_TRACK)
        self.assertIn("สอดคล้องกับกรอบเวลา", health.recommendation)
        self.assertEqual(len(health.bottleneck_tasks), 0)

    def test_milestone_health_at_risk_and_delayed(self):
        """Test At-Risk (10-25% lag) and Delayed (>25% lag) classifications."""
        now = datetime.now(timezone.utc)
        start_date = now - timedelta(days=20)
        target_date = now + timedelta(days=10)  # Total 30 days, elapsed 20 days = 66.7%

        # 1. At Risk: 50% completed vs 66.7% elapsed -> 16.7% gap
        at_risk_milestone = ProjectMilestone(
            milestone_id=2,
            project_id=10,
            title="Q2 Launch",
            target_date=target_date,
            total_tasks=10,
            completed_tasks=5,
            total_points=20,
            completed_points=10,
        )

        # 2. Delayed: 10% completed vs 66.7% elapsed -> 56.7% gap
        delayed_milestone = ProjectMilestone(
            milestone_id=3,
            project_id=10,
            title="Q3 Expansion",
            target_date=target_date,
            total_tasks=10,
            completed_tasks=1,
            total_points=20,
            completed_points=2,
        )

        bottlenecks = [
            {"task_id": 55, "task": "Payment Gateway", "status": "In_Progress", "deadline": now - timedelta(days=1), "blocked_dependents_count": 3}
        ]

        h_risk = roadmap_service.calculate_milestone_health(at_risk_milestone, start_date, now, bottlenecks)
        self.assertEqual(h_risk.status, HealthStatus.AT_RISK)
        self.assertIn("ลดขอบเขตงาน", h_risk.recommendation)
        self.assertEqual(len(h_risk.bottleneck_tasks), 1)

        h_delay = roadmap_service.calculate_milestone_health(delayed_milestone, start_date, now, bottlenecks)
        self.assertEqual(h_delay.status, HealthStatus.DELAYED)
        self.assertIn("ไม่ทันตามเป้าหมาย", h_delay.recommendation)
        self.assertEqual(len(h_delay.bottleneck_tasks), 1)

    def test_milestone_model_methods(self):
        """Test ProjectMilestone calculations and from_row mapping."""
        now = datetime.now(timezone.utc)
        row = {
            "milestone_id": 10,
            "project_id": 5,
            "title": "Mobile MVP",
            "target_date": now,
            "status": "active",
            "total_tasks": 15,
            "completed_tasks": 9,
            "total_points": 30,
            "completed_points": 18,
        }
        ms = ProjectMilestone.from_row(row)
        self.assertEqual(ms.milestone_id, 10)
        self.assertEqual(ms.completion_pct, 60)
        self.assertEqual(ms.points_completion_pct, 60)

    def test_embed_builders(self):
        """Test embed builders for CPM, Gantt, and Roadmap."""
        n1 = CPMNode(task_id=1, task_name="Core Auth", duration_hours=8.0, is_critical=True)
        result = CPMGraphResult(
            project_id=1,
            nodes={1: n1},
            critical_path=[1],
            total_duration_hours=8.0,
            total_duration_days=1.0,
        )

        cpm_embed = build_cpm_embed(result, "Auth Project")
        self.assertIn("Critical Path Method", cpm_embed.title)
        self.assertTrue(any("ลำดับสายงานวิกฤต" in f.name for f in cpm_embed.fields))

        ms = ProjectMilestone(milestone_id=1, project_id=1, title="M1", target_date=datetime.now(timezone.utc))
        health = MilestoneHealth(
            milestone_id=1,
            title="M1",
            target_date=datetime.now(timezone.utc),
            status=HealthStatus.ON_TRACK,
            elapsed_pct=20.0,
            progress_pct=25.0,
            gap_pct=-5.0,
            recommendation="Good pace",
        )
        roadmap_embed = build_roadmap_embed("Auth Project", 1, [ms], {1: health})
        self.assertIn("Strategic Milestone Roadmap", roadmap_embed.title)


if __name__ == "__main__":
    unittest.main()

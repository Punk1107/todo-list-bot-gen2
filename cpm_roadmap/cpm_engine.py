"""
cpm_roadmap/cpm_engine.py — Pure SQL & Python Critical Path Method (CPM) Graph Engine.

Computes:
  - Directed Acyclic Graph (DAG) extraction from project_task_dependencies
  - Topological sort with circular dependency (cycle) detection
  - Forward Pass: Early Start (ES) and Early Finish (EF)
  - Backward Pass: Late Start (LS) and Late Finish (LF)
  - Slack / Float Time: Slack = LS - ES = LF - EF
  - Critical Path identification (Slack == 0)
  - Project Lead Risk alerts
"""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from core.database import db
from cpm_roadmap.models import CPMGraphResult, CPMNode

log = logging.getLogger(__name__)


def calculate_cpm_graph(
    nodes: Dict[int, CPMNode],
    project_id: int = 0,
    project_deadline: Optional[datetime] = None,
) -> CPMGraphResult:
    """
    Pure graph analysis: executes CPM calculation on a network of CPMNodes.
    Computes Forward/Backward pass, slack times, and identifies Critical Path.
    """
    if not nodes:
        return CPMGraphResult(
            project_id=project_id,
            nodes={},
            critical_path=[],
            total_duration_hours=0.0,
            total_duration_days=0.0,
        )

    # 1. Topological Sort (Kahn's Algorithm) & Cycle Detection
    in_degree: Dict[int, int] = {tid: len(node.predecessors) for tid, node in nodes.items()}
    queue = deque([tid for tid, deg in in_degree.items() if deg == 0])
    topo_order: List[int] = []

    while queue:
        curr = queue.popleft()
        topo_order.append(curr)
        for succ in nodes[curr].successors:
            if succ in in_degree:
                in_degree[succ] -= 1
                if in_degree[succ] == 0:
                    queue.append(succ)

    # If sorted count != total count, a cycle (circular dependency) exists
    if len(topo_order) < len(nodes):
        return CPMGraphResult(
            project_id=project_id,
            nodes=nodes,
            critical_path=[],
            total_duration_hours=0.0,
            total_duration_days=0.0,
            has_cycle=True,
            is_at_risk=True,
            risk_reason="ตรวจพบ Circular Dependency (ความสัมพันธ์วนลูป) ในโครงการ กรุณาตรวจสอบ Task Dependencies",
        )

    # 2. Forward Pass: Calculate Early Start (ES) and Early Finish (EF)
    for tid in topo_order:
        node = nodes[tid]
        if not node.predecessors:
            node.early_start = 0.0
        else:
            node.early_start = max(nodes[p].early_finish for p in node.predecessors if p in nodes)
        node.early_finish = node.early_start + node.duration_hours

    # Total project duration is the maximum EF among all nodes
    total_hours = max((node.early_finish for node in nodes.values()), default=0.0)

    # 3. Backward Pass: Calculate Late Finish (LF) and Late Start (LS)
    for tid in reversed(topo_order):
        node = nodes[tid]
        if not node.successors:
            node.late_finish = total_hours
        else:
            node.late_finish = min(nodes[s].late_start for s in node.successors if s in nodes)
        node.late_start = node.late_finish - node.duration_hours

    # 4. Compute Slack & Mark Critical Path Nodes (Slack == 0)
    critical_nodes_set: Set[int] = set()
    for tid, node in nodes.items():
        node.slack = round(node.late_start - node.early_start, 2)
        if abs(node.slack) < 0.01:
            node.is_critical = True
            critical_nodes_set.add(tid)
        else:
            node.is_critical = False

    # 5. Extract Ordered Critical Path Sequence
    critical_path: List[int] = []
    current_candidates = [tid for tid in topo_order if tid in critical_nodes_set]
    if current_candidates:
        curr = current_candidates[0]
        critical_path.append(curr)
        while True:
            next_crit = [
                s for s in nodes[curr].successors
                if s in critical_nodes_set and abs(nodes[s].early_start - nodes[curr].early_finish) < 0.01
            ]
            if not next_crit:
                break
            curr = next_crit[0]
            critical_path.append(curr)

    # 6. Lead Risk Analysis
    now = datetime.now(timezone.utc)
    is_at_risk = False
    risk_reason = None

    for tid in critical_path:
        crit_node = nodes[tid]
        if crit_node.status != "Completed" and crit_node.deadline and crit_node.deadline < now:
            is_at_risk = True
            risk_reason = (
                f"🚨 **งานบน Critical Path ล่าช้ากว่ากำหนด:** `#{crit_node.task_id}` {crit_node.task_name[:40]} "
                f"(เกินกำหนดส่งเมื่อ <t:{int(crit_node.deadline.timestamp())}:R>) จะทำให้ทั้งโครงการล่าช้า!"
            )
            break

    total_days = round(total_hours / 8.0, 1)

    return CPMGraphResult(
        project_id=project_id,
        nodes=nodes,
        critical_path=critical_path,
        total_duration_hours=round(total_hours, 1),
        total_duration_days=total_days,
        is_at_risk=is_at_risk,
        risk_reason=risk_reason,
        has_cycle=False,
    )


async def calculate_project_cpm(project_id: int) -> CPMGraphResult:
    """
    Execute CPM network analysis on a project using pure SQL and graph algorithms.
    Returns CPMGraphResult with nodes, critical path, total duration, and risk warnings.
    """
    # 1. Fetch project deadline & info
    proj_row = await db.afetchone(
        "SELECT project_id, name, created_at FROM projects WHERE project_id = $1",
        (project_id,),
    )
    proj_start = proj_row["created_at"] if proj_row and proj_row.get("created_at") else datetime.now(timezone.utc)

    # 2. Fetch all open / active tasks for this project
    task_rows = await db.afetchall(
        """
        SELECT task_id, task, status, estimated_hours, deadline, created_at
        FROM tasks
        WHERE project_id = $1 AND is_deleted = FALSE
        ORDER BY task_id ASC
        """,
        (project_id,),
    )
    if not task_rows:
        return CPMGraphResult(
            project_id=project_id,
            nodes={},
            critical_path=[],
            total_duration_hours=0.0,
            total_duration_days=0.0,
        )

    # 3. Fetch dependencies from project_task_dependencies
    dep_rows = await db.afetchall(
        """
        SELECT task_id, blocked_by_task_id
        FROM project_task_dependencies
        WHERE project_id = $1
        """,
        (project_id,),
    )

    # 4. Build Nodes map
    nodes: Dict[int, CPMNode] = {}
    for r in task_rows:
        tid = int(r["task_id"])
        est_h = r["estimated_hours"]
        if est_h and float(est_h) > 0:
            duration = float(est_h)
        elif r["deadline"] and r["created_at"]:
            delta = (r["deadline"] - r["created_at"]).total_seconds() / 3600.0
            duration = max(4.0, min(160.0, delta))
        else:
            duration = 8.0

        nodes[tid] = CPMNode(
            task_id=tid,
            task_name=str(r["task"]),
            duration_hours=duration,
            status=str(r["status"]),
            deadline=r["deadline"],
        )

    # 5. Populate Predecessors and Successors
    for dep in (dep_rows or []):
        suc_id = int(dep["task_id"])
        pred_id = int(dep["blocked_by_task_id"])
        if suc_id in nodes and pred_id in nodes:
            nodes[suc_id].predecessors.append(pred_id)
            nodes[pred_id].successors.append(suc_id)

    return calculate_cpm_graph(nodes, project_id=project_id)

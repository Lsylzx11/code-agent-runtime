from __future__ import annotations

from pathlib import Path

from ..runtime.checkpoint import WorkflowCheckpoint
from ..runtime.scheduler import DagScheduler
from ..schemas import TaskSpec
from .planner import TaskPlanner
from .subagent import SubAgent


class MainAgent:
    """Explicit manager boundary: it dispatches specs and returns workflow state."""

    def __init__(self, subagent: SubAgent, scheduler: DagScheduler | None = None) -> None:
        self.subagent = subagent
        self.scheduler = scheduler or DagScheduler()

    def execute(self, workflow_id: str, tasks: list[TaskSpec], workspace: Path) -> dict:
        checkpoint = WorkflowCheckpoint(workspace, workflow_id)
        return self.scheduler.run(workflow_id, tasks, self.subagent.run, checkpoint)

    def plan_and_execute(self, workflow_id: str, request: str, workspace: Path,
                         planner: TaskPlanner) -> dict:
        """Turn a natural-language request into validated work before scheduling it."""
        tasks = planner.plan(request, workspace)
        return self.execute(workflow_id, tasks, workspace)


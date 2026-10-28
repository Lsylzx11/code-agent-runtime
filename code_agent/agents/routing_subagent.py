from __future__ import annotations

from dataclasses import replace

from ..runtime.worktree import GitWorktreeManager
from ..schemas import AgentResult, TaskSpec
from .review_agent import ReviewAgent
from .subagent import SubAgent


class RoutingSubAgent:
    """Routes writes to isolated worktrees and review roles to the review agent."""

    def __init__(self, worker: SubAgent, reviewer: ReviewAgent, manager: GitWorktreeManager) -> None:
        self.worker, self.reviewer, self.manager = worker, reviewer, manager

    def run(self, task: TaskSpec, upstream: dict[str, AgentResult]) -> AgentResult:
        if task.context.get("role") == "review":
            return self.reviewer.run(task, upstream, self.manager)
        active_task = task
        if task.write_access:
            worktree = self.manager.create(task.task_id)
            active_task = replace(task, workspace=str(worktree))
        result = self.worker.run(active_task, upstream)
        if task.write_access:
            result.artifacts.append(f"worktree:{self.manager.path_for(task.task_id)}")
        return result


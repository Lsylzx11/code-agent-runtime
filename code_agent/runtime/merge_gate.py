from __future__ import annotations

from ..schemas import AgentResult
from .worktree import GitWorktreeManager, WorktreeError


class MergeGate:
    """Commits and merges only an unchanged, explicitly approved review target."""

    def merge(self, review: AgentResult, manager: GitWorktreeManager) -> str:
        details = review.review or {}
        if details.get("verdict") != "approved":
            raise WorktreeError("review is not approved for merge")
        target = next((item.removeprefix("reviewed_task:") for item in review.artifacts
                       if item.startswith("reviewed_task:")), None)
        fingerprint = details.get("fingerprint")
        if not target or not isinstance(fingerprint, str):
            raise WorktreeError("review lacks merge target or fingerprint")
        return manager.merge_approved(target, fingerprint, f"code-agent: {target} ({review.task_id})")


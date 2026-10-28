from __future__ import annotations

import re
import subprocess
import hashlib
from pathlib import Path


class WorktreeError(RuntimeError):
    pass


class GitWorktreeManager:
    """Creates one task branch/worktree without touching the primary checkout."""

    def __init__(self, workspace: Path, workflow_id: str) -> None:
        self.workspace = workspace.resolve()
        self.workflow_id = self._safe_name(workflow_id)
        self.root = self.workspace.parent / f".{self.workspace.name}.code-agent-worktrees" / self.workflow_id
        self._git(["rev-parse", "--is-inside-work-tree"])

    @staticmethod
    def _safe_name(value: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9_-]", "_", value).strip("_")
        if not normalized:
            raise WorktreeError("worktree name must contain letters or digits")
        return normalized[:64]

    def _git(self, arguments: list[str], cwd: Path | None = None) -> str:
        completed = subprocess.run(["git", *arguments], cwd=cwd or self.workspace,
                                   text=True, encoding="utf-8", errors="replace",
                                   capture_output=True, timeout=30)
        if completed.returncode:
            message = (completed.stderr or completed.stdout).strip()
            raise WorktreeError(f"git {' '.join(arguments)} failed: {message}")
        return completed.stdout.strip()

    def branch_name(self, task_id: str) -> str:
        return f"code-agent/{self.workflow_id}/{self._safe_name(task_id)}"

    def path_for(self, task_id: str) -> Path:
        return self.root / self._safe_name(task_id)

    def create(self, task_id: str) -> Path:
        path = self.path_for(task_id)
        if path.exists():
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._git(["worktree", "add", "-b", self.branch_name(task_id), str(path), "HEAD"])
        return path

    def diff_summary(self, task_id: str) -> str:
        path = self.path_for(task_id)
        if not path.exists():
            raise WorktreeError(f"no worktree for task {task_id}")
        changed = self._git(["status", "--short"], path) or "(no uncommitted changes)"
        check = self._git(["diff", "--check"], path) or "(clean)"
        return f"Changed files:\n{changed}\n\nWhitespace check:\n{check}"

    def fingerprint(self, task_id: str) -> str:
        """Hash tracked diffs plus untracked file contents for review-to-merge integrity."""
        path = self.path_for(task_id)
        status = self._git(["status", "--porcelain"], path)
        digest = hashlib.sha256()
        digest.update(self._git(["diff", "--binary", "HEAD"], path).encode("utf-8"))
        digest.update(status.encode("utf-8"))
        for line in status.splitlines():
            if line.startswith("?? "):
                file_path = path / line[3:]
                if file_path.is_file():
                    digest.update(line[3:].encode("utf-8"))
                    digest.update(file_path.read_bytes())
        return digest.hexdigest()

    def preflight_primary(self) -> None:
        status = self._git(["status", "--porcelain"], self.workspace)
        # Runtime checkpoints are owned by this agent; other modifications require
        # explicit user cleanup before an automated merge can continue.
        foreign = [line for line in status.splitlines() if ".code-agent/" not in line.replace("\\", "/")]
        if foreign:
            raise WorktreeError("primary worktree has uncommitted changes: " + "; ".join(foreign))

    def commit_task(self, task_id: str, message: str) -> str:
        path = self.path_for(task_id)
        self._git(["add", "--all"], path)
        status = self._git(["status", "--porcelain"], path)
        if not status:
            raise WorktreeError("reviewed worktree has no changes to commit")
        self._git(["commit", "-m", message], path)
        return self._git(["rev-parse", "HEAD"], path)

    def merge_approved(self, task_id: str, expected_fingerprint: str, message: str) -> str:
        if self.fingerprint(task_id) != expected_fingerprint:
            raise WorktreeError("worktree changed after review; a new review is required")
        self.preflight_primary()
        commit = self.commit_task(task_id, message)
        self.preflight_primary()
        self._git(["merge", "--no-ff", "--no-edit", self.branch_name(task_id)], self.workspace)
        return commit

    def remove(self, task_id: str, force: bool = False) -> None:
        path = self.path_for(task_id)
        if path.exists():
            args = ["worktree", "remove", str(path)] + (["--force"] if force else [])
            self._git(args)



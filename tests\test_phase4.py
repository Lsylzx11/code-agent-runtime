import subprocess
import unittest
import uuid
import shutil
import json
from pathlib import Path

from code_agent.agents.review_agent import REVIEW_TOOLS, ReviewAgent
from code_agent.agents.routing_subagent import RoutingSubAgent
from code_agent.runtime.worktree import GitWorktreeManager
from code_agent.runtime.merge_gate import MergeGate
from code_agent.runtime.worktree import WorktreeError
from code_agent.schemas import AgentResult, TaskSpec


def git(root: Path, *arguments: str) -> None:
    completed = subprocess.run(["git", *arguments], cwd=root, text=True,
                               capture_output=True, encoding="utf-8")
    if completed.returncode:
        raise AssertionError(completed.stderr or completed.stdout)


class WritingWorker:
    def run(self, task, upstream):
        path = Path(task.workspace) / "app.py"
        path.write_text("value = 2\n", encoding="utf-8")
        return AgentResult("completed", "implemented", 1, task_id=task.task_id,
                           agent_id="writer", summary="implemented")


class FakeReviewCodeAgent:
    def __init__(self, output="review passed"):
        self.output, self.prompt, self.context = output, "", None
    def run(self, prompt, context):
        self.prompt, self.context = prompt, context
        return AgentResult("completed", self.output, 0)


class PhaseFourTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / ".test-workspace" / f"{self._testMethodName}-{uuid.uuid4().hex}"
        self.root.mkdir(parents=True, exist_ok=True)
        git(self.root, "init")
        git(self.root, "config", "user.email", "test@example.invalid")
        git(self.root, "config", "user.name", "Test Agent")
        (self.root / "app.py").write_text("value = 1\n", encoding="utf-8")
        git(self.root, "add", "app.py")
        git(self.root, "commit", "-m", "initial")

    def tearDown(self):
        # Remove child worktrees before deleting their primary checkout. Ignore
        # cleanup errors in locked-down Windows test sandboxes; they are not a
        # product-runtime concern and CI can still proceed to the next test.
        isolated_root = self.root.parent / f".{self.root.name}.code-agent-worktrees"
        shutil.rmtree(isolated_root, ignore_errors=True)
        subprocess.run(["git", "worktree", "prune"], cwd=self.root,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        shutil.rmtree(self.root, ignore_errors=True)

    def test_write_task_uses_branch_worktree_and_review_is_read_only(self):
        manager = GitWorktreeManager(self.root, "review-flow")
        review_model = FakeReviewCodeAgent()
        router = RoutingSubAgent(WritingWorker(), ReviewAgent(review_model), manager)
        write_task = TaskSpec("implement", "change app", workspace=str(self.root), write_access=True,
                              context={"role": "implement"})
        implementation = router.run(write_task, {})
        worktree = manager.path_for("implement")
        self.assertTrue(worktree.is_dir())
        self.assertEqual((self.root / "app.py").read_text(encoding="utf-8"), "value = 1\n")
        self.assertEqual((worktree / "app.py").read_text(encoding="utf-8"), "value = 2\n")
        self.assertIn(f"worktree:{worktree}", implementation.artifacts)

        review_task = TaskSpec("review", "review the change", dependencies=("implement",),
                               workspace=str(self.root), context={"role": "review"})
        reviewed = router.run(review_task, {"implement": implementation})
        self.assertEqual(reviewed.status, "completed")
        self.assertEqual(review_model.context.workspace, worktree)
        self.assertEqual(review_model.context.allowed_tools, REVIEW_TOOLS)
        self.assertIn("Changed files:", review_model.prompt)
        self.assertIn("app.py", review_model.prompt)

    def test_diff_summary_reports_cleanliness(self):
        manager = GitWorktreeManager(self.root, "diff-flow")
        worktree = manager.create("implement")
        (worktree / "app.py").write_text("value = 3\n", encoding="utf-8")
        summary = manager.diff_summary("implement")
        self.assertIn("Whitespace check:\n(clean)", summary)
        self.assertIn("app.py", summary)

    def test_explicit_approved_review_commits_and_merges_unchanged_diff(self):
        manager = GitWorktreeManager(self.root, "merge-flow")
        reviewer = FakeReviewCodeAgent(json.dumps({
            "verdict": "approved", "findings": [], "test_evidence": "unit tests passed",
        }))
        router = RoutingSubAgent(WritingWorker(), ReviewAgent(reviewer), manager)
        implementation = router.run(TaskSpec("implement", "change", workspace=str(self.root), write_access=True,
                                              context={"role": "implement"}), {})
        review = router.run(TaskSpec("review", "review", dependencies=("implement",), workspace=str(self.root),
                                     context={"role": "review"}), {"implement": implementation})
        commit = MergeGate().merge(review, manager)
        self.assertRegex(commit, r"^[0-9a-f]{40}$")
        self.assertEqual((self.root / "app.py").read_text(encoding="utf-8"), "value = 2\n")
        self.assertEqual(subprocess.run(["git", "status", "--porcelain"], cwd=self.root,
                                        text=True, capture_output=True).stdout, "")

    def test_merge_rejects_changes_after_review(self):
        manager = GitWorktreeManager(self.root, "fingerprint-flow")
        reviewer = FakeReviewCodeAgent('{"verdict":"approved","findings":[],"test_evidence":"ok"}')
        router = RoutingSubAgent(WritingWorker(), ReviewAgent(reviewer), manager)
        implementation = router.run(TaskSpec("implement", "change", workspace=str(self.root), write_access=True,
                                              context={"role": "implement"}), {})
        review = router.run(TaskSpec("review", "review", dependencies=("implement",), workspace=str(self.root),
                                     context={"role": "review"}), {"implement": implementation})
        (manager.path_for("implement") / "app.py").write_text("value = 99\n", encoding="utf-8")
        with self.assertRaisesRegex(WorktreeError, "changed after review"):
            MergeGate().merge(review, manager)


if __name__ == "__main__":
    unittest.main()


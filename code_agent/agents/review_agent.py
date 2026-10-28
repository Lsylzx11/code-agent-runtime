from __future__ import annotations

from pathlib import Path
import json
import re

from ..runtime.agent_loop import CodeAgent
from ..runtime.context import AgentContext
from ..runtime.worktree import GitWorktreeManager
from ..schemas import AgentResult, TaskSpec


REVIEW_TOOLS = {"read_file", "list_files", "glob", "grep", "run_command", "run_tests"}


def parse_review(text: str, fingerprint: str) -> dict:
    """A malformed response is never eligible for automated merge."""
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.IGNORECASE)
    try:
        value = json.loads(candidate)
    except (TypeError, json.JSONDecodeError):
        value = {}
    verdict = value.get("verdict") if isinstance(value, dict) else None
    findings = value.get("findings", []) if isinstance(value, dict) else []
    evidence = value.get("test_evidence", "") if isinstance(value, dict) else ""
    if verdict not in {"approved", "rejected", "needs_human"}:
        verdict = "needs_human"
    if not isinstance(findings, list) or not all(isinstance(item, str) for item in findings):
        findings = ["invalid findings format"]
        verdict = "needs_human"
    if not isinstance(evidence, str):
        evidence = ""
        verdict = "needs_human"
    return {"verdict": verdict, "findings": findings, "test_evidence": evidence,
            "fingerprint": fingerprint}


class ReviewAgent:
    """Reviews a write task in its isolated worktree without write tools."""

    def __init__(self, agent: CodeAgent, agent_id: str = "reviewer") -> None:
        self.agent, self.agent_id = agent, agent_id

    def run(self, task: TaskSpec, upstream: dict[str, AgentResult], manager: GitWorktreeManager) -> AgentResult:
        candidates = [result for result in upstream.values()
                      if any(artifact.startswith("worktree:") for artifact in result.artifacts)]
        if not candidates:
            return AgentResult("failed", "review requires an upstream isolated write task", 0,
                               task_id=task.task_id, agent_id=self.agent_id,
                               errors=["no worktree artifact supplied"])
        target = candidates[-1]
        target_task_id = target.task_id or ""
        worktree = manager.path_for(target_task_id)
        prompt = (f"{task.description}\n\nReview target task: {target_task_id}\n"
                  f"{manager.diff_summary(target_task_id)}\n\n"
                  "Do not modify files. Return only JSON with verdict (approved, rejected, or needs_human), "
                  "findings (string array), and test_evidence (string). Approval only means ready for explicit human-approved merge.")
        context = AgentContext(workspace=Path(worktree), memory_scope=f"review:{task.task_id}",
                               allowed_tools=REVIEW_TOOLS)
        result = self.agent.run(prompt, context)
        result.task_id, result.agent_id, result.summary = task.task_id, self.agent_id, result.output
        result.artifacts.append(f"reviewed_worktree:{worktree}")
        result.artifacts.append(f"reviewed_task:{target_task_id}")
        result.review = parse_review(result.output, manager.fingerprint(target_task_id))
        return result


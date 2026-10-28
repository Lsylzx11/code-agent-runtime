from __future__ import annotations

from pathlib import Path

from ..runtime.agent_loop import CodeAgent
from ..runtime.context import AgentContext
from ..schemas import AgentResult, TaskSpec


class SubAgent:
    """Runs one TaskSpec with a new, non-shared AgentContext."""

    def __init__(self, agent: CodeAgent, agent_id: str) -> None:
        self.agent, self.agent_id = agent, agent_id

    def run(self, task: TaskSpec, upstream: dict[str, AgentResult]) -> AgentResult:
        evidence = "\n".join(f"[{task_id}] {result.summary or result.output}"
                             for task_id, result in upstream.items())
        prompt = task.description + (f"\n\nUpstream results:\n{evidence}" if evidence else "")
        context = AgentContext(workspace=Path(task.workspace), memory_scope=f"task:{task.task_id}")
        result = self.agent.run(prompt, context)
        result.task_id = task.task_id
        result.agent_id = self.agent_id
        result.summary = result.output
        return result


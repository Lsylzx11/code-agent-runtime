from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable

from ..schemas import AgentResult, TaskSpec
from .checkpoint import WorkflowCheckpoint
from .reducer import reduce_result


Worker = Callable[[TaskSpec, dict[str, AgentResult]], AgentResult]


class DagScheduler:
    """Dependency scheduler that only parallelizes explicitly read-only tasks."""

    def __init__(self, max_read_concurrency: int = 3) -> None:
        self.max_read_concurrency = max(1, max_read_concurrency)

    @staticmethod
    def _validate(tasks: Iterable[TaskSpec]) -> dict[str, TaskSpec]:
        task_list = list(tasks)
        indexed = {task.task_id: task for task in task_list}
        if len(indexed) != len(task_list):
            raise ValueError("task ids must be unique")
        for task in indexed.values():
            unknown = set(task.dependencies) - set(indexed)
            if unknown:
                raise ValueError(f"{task.task_id} has unknown dependencies: {sorted(unknown)}")
        return indexed

    def run(self, workflow_id: str, tasks: list[TaskSpec], worker: Worker,
            checkpoint: WorkflowCheckpoint | None = None) -> dict:
        indexed = self._validate(tasks)
        state = checkpoint.load() if checkpoint else None
        if state is None:
            state = {"workflow_id": workflow_id,
                     "task_status": {key: "pending" for key in indexed},
                     "task_results": {}}
        if state["workflow_id"] != workflow_id:
            raise ValueError("checkpoint workflow id does not match")
        if set(state["task_status"]) != set(indexed):
            raise ValueError("checkpoint task set does not match the current plan")
        # A stored completed result is authoritative; anything that was running is safe to retry.
        for task_id, status in list(state["task_status"].items()):
            if status == "running":
                state["task_status"][task_id] = "pending"
        while True:
            pending = [task for task in indexed.values() if state["task_status"].get(task.task_id) == "pending"]
            for task in pending:
                dependency_statuses = [state["task_status"].get(dep) for dep in task.dependencies]
                if any(status in ("failed", "blocked") for status in dependency_statuses):
                    state["task_status"][task.task_id] = "blocked"
            ready = [task for task in pending if all(state["task_status"].get(dep) == "completed"
                                                      for dep in task.dependencies)]
            if not ready:
                break
            write_tasks = [task for task in ready if task.write_access]
            batch = [write_tasks[0]] if write_tasks else ready[:self.max_read_concurrency]
            for task in batch:
                state["task_status"][task.task_id] = "running"
            if checkpoint:
                checkpoint.save(state)
            def execute(task: TaskSpec) -> AgentResult:
                upstream = {dep: state["task_results"][dep] for dep in task.dependencies}
                result = worker(task, upstream)
                if result.task_id != task.task_id:
                    raise ValueError(f"worker returned result for {result.task_id!r}, expected {task.task_id!r}")
                return result
            if len(batch) == 1:
                produced = [execute(batch[0])]
            else:
                with ThreadPoolExecutor(max_workers=len(batch)) as executor:
                    produced = list(executor.map(execute, batch))
            for result in produced:
                reduce_result(state, result)
            if checkpoint:
                checkpoint.save(state)
        if any(status == "pending" for status in state["task_status"].values()):
            raise ValueError("workflow contains a dependency cycle")
        if checkpoint:
            checkpoint.save(state)
        return state


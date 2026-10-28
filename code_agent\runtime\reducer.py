from __future__ import annotations

from ..schemas import AgentResult, TaskStatus


def result_status(result: AgentResult) -> TaskStatus:
    return "completed" if result.status == "completed" else "failed"


def reduce_result(state: dict, result: AgentResult) -> dict:
    """Merge one result without interpreting its semantic content."""
    if not result.task_id:
        raise ValueError("workflow results require task_id")
    state["task_results"][result.task_id] = result
    state["task_status"][result.task_id] = result_status(result)
    return state


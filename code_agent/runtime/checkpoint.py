from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from ..schemas import AgentResult, ToolResult


def _serialize_result(result: AgentResult) -> dict:
    value = asdict(result)
    return value


def _deserialize_result(value: dict) -> AgentResult:
    value = dict(value)
    value["tool_results"] = [ToolResult(**item) for item in value.get("tool_results", [])]
    return AgentResult(**value)


class WorkflowCheckpoint:
    """Atomic JSON state for stopping and resuming a workflow."""

    def __init__(self, workspace: Path, workflow_id: str) -> None:
        safe_id = "".join(char if char.isalnum() or char in "_-" else "_" for char in workflow_id)
        if not safe_id:
            raise ValueError("workflow_id must contain a usable character")
        self.path = workspace / ".code-agent" / "workflows" / f"{safe_id}.json"

    def save(self, state: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "workflow_id": state["workflow_id"],
            "task_status": state["task_status"],
            "task_results": {key: _serialize_result(value)
                             for key, value in state["task_results"].items()},
        }
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    def load(self) -> dict | None:
        if not self.path.exists():
            return None
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return {
            "workflow_id": payload["workflow_id"],
            "task_status": dict(payload["task_status"]),
            "task_results": {key: _deserialize_result(value)
                             for key, value in payload["task_results"].items()},
        }


from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ToolStatus = Literal["ok", "error", "denied", "timeout"]
AgentStatus = Literal["completed", "max_steps", "cancelled", "failed"]
TaskStatus = Literal["pending", "running", "completed", "failed", "blocked"]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    call_id: str
    tool_name: str
    status: ToolStatus
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class AgentResult:
    status: AgentStatus
    output: str
    steps: int
    tool_results: list[ToolResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    task_id: str | None = None
    agent_id: str | None = None
    summary: str = ""
    artifacts: list[str] = field(default_factory=list)
    review: dict[str, Any] | None = None


@dataclass(frozen=True)
class TaskSpec:
    """A serializable unit of work passed from the manager to one subagent."""

    task_id: str
    description: str
    dependencies: tuple[str, ...] = ()
    context: dict[str, Any] = field(default_factory=dict)
    workspace: str = "."
    write_access: bool = False


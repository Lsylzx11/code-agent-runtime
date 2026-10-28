from __future__ import annotations

from ..schemas import ToolCall, ToolResult
from ..runtime.context import AgentContext
from .permissions import PermissionPolicy
from .registry import ToolRegistry


class ToolDispatcher:
    def __init__(self, registry: ToolRegistry, policy: PermissionPolicy) -> None:
        self.registry, self.policy = registry, policy

    def execute(self, call: ToolCall, context: AgentContext) -> ToolResult:
        tool = self.registry.get(call.name)
        if tool is None:
            return ToolResult(call.id, call.name, "error", "unknown tool")
        if context.allowed_tools is not None and call.name not in context.allowed_tools:
            return ToolResult(call.id, call.name, "denied", "tool is not allowed in this context")
        denial = self.policy.check(tool.permission, call.name, call.arguments)
        if denial:
            return ToolResult(call.id, call.name, "denied", f"permission denied: {denial}")
        try:
            content = tool.handler(context.workspace, **call.arguments)
            return ToolResult(call.id, call.name, "ok", str(content))
        except TimeoutError as exc:
            return ToolResult(call.id, call.name, "timeout", str(exc))
        except Exception as exc:
            return ToolResult(call.id, call.name, "error", f"{type(exc).__name__}: {exc}")


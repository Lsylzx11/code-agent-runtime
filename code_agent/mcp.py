from __future__ import annotations

from typing import Protocol, Any

from .tools.models import ToolDefinition
from .tools.registry import ToolRegistry


class MCPClient(Protocol):
    name: str
    def list_tools(self) -> list[dict[str, Any]]: ...
    def call_tool(self, name: str, arguments: dict[str, Any]) -> str: ...


def install_mcp_tools(registry: ToolRegistry, client: MCPClient) -> None:
    """Register a client's discovered tools under a collision-safe namespace."""
    server = "".join(ch if ch.isalnum() else "_" for ch in client.name).strip("_")
    if not server:
        raise ValueError("MCP client name has no usable characters")
    for remote in client.list_tools():
        raw_name = remote["name"]
        safe_name = "".join(ch if ch.isalnum() else "_" for ch in raw_name).strip("_")
        name = f"mcp__{server}__{safe_name}"
        if len(name) > 64 or not safe_name:
            raise ValueError(f"invalid MCP tool name: {raw_name!r}")
        registry.register(ToolDefinition(
            name=name, description=remote.get("description", ""),
            input_schema=remote.get("inputSchema", {"type": "object"}), permission="execute",
            handler=lambda _workspace, _client=client, _name=raw_name, **kwargs: _client.call_tool(_name, kwargs),
        ))


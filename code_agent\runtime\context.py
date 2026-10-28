from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AgentContext:
    """Mutable state owned by exactly one agent run."""

    workspace: Path
    messages: list[dict] = field(default_factory=list)
    allowed_tools: set[str] | None = None
    memory_scope: str = "default"
    max_steps: int = 20


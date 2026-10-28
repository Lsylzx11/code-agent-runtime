from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PermissionPolicy:
    """Non-interactive policy; callers can replace ``approve`` for a UI flow."""

    allow_read: bool = True
    allow_write: bool = True
    allow_execute: bool = False
    forbidden_fragments: tuple[str, ...] = (
        "rm -rf /", "shutdown", "reboot", "mkfs", "dd if=", "format ",
    )
    approve: object | None = None

    def check(self, permission: str, name: str, arguments: dict) -> str | None:
        if permission == "read" and not self.allow_read:
            return "read access is disabled"
        if permission == "write" and not self.allow_write:
            return "write access is disabled"
        if permission == "execute":
            command = arguments.get("command", "")
            if not isinstance(command, str):
                return "command must be a string"
            lowered = command.lower()
            if any(fragment in lowered for fragment in self.forbidden_fragments):
                return "command matches the destructive-command deny list"
            if not self.allow_execute:
                return "command execution is disabled"
        if self.approve is not None and not self.approve(name, arguments, permission):
            return "operation was not approved"
        return None


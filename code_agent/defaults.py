from __future__ import annotations

from .tools import filesystem
from .tools.models import ToolDefinition
from .tools.registry import ToolRegistry
from .tools.terminal import run_command


def build_code_registry() -> ToolRegistry:
    registry = ToolRegistry()
    def add(name, description, schema, permission, handler):
        registry.register(ToolDefinition(name, description, schema, permission, handler))
    add("read_file", "Read a UTF-8 text file.", {"type": "object"}, "read", filesystem.read_file)
    add("list_files", "List files in a directory.", {"type": "object"}, "read", filesystem.list_files)
    add("glob", "Find files by glob pattern.", {"type": "object"}, "read", filesystem.glob_files)
    add("grep", "Search text files for a literal query.", {"type": "object"}, "read", filesystem.grep)
    add("write_file", "Create or overwrite a UTF-8 file.", {"type": "object"}, "write", filesystem.write_file)
    add("edit_file", "Replace exactly one text block in a file.", {"type": "object"}, "write", filesystem.edit_file)
    def command(workspace, command: str, timeout_seconds: int = 120):
        output, code, timed_out = run_command(workspace, command, timeout_seconds)
        return f"exit_code={code}; timed_out={timed_out}\n{output}"
    add("run_command", "Run a command in the workspace.", {"type": "object"}, "execute", command)
    add("run_tests", "Run a test command in the workspace.", {"type": "object"}, "execute", command)
    return registry


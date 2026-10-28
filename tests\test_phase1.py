import unittest
from pathlib import Path

from code_agent.defaults import build_code_registry
from code_agent.memory import FileMemory
from code_agent.mcp import install_mcp_tools
from code_agent.runtime.agent_loop import CodeAgent
from code_agent.runtime.context import AgentContext
from code_agent.schemas import ModelResponse, ToolCall
from code_agent.tools.dispatcher import ToolDispatcher
from code_agent.tools.permissions import PermissionPolicy


class ScriptedModel:
    def __init__(self, responses): self.responses = iter(responses)
    def generate(self, messages, tools): return next(self.responses)


class FakeMCP:
    name = "docs-server"
    def list_tools(self): return [{"name": "lookup", "description": "lookup", "inputSchema": {"type": "object"}}]
    def call_tool(self, name, arguments): return f"{name}:{arguments['topic']}"


class PhaseOneTests(unittest.TestCase):
    def setUp(self):
        # Keep the fixture below the project root. Some locked-down Windows
        # environments deny Python access to the OS temporary directory.
        self.root = Path.cwd() / ".test-workspace" / self._testMethodName
        self.root.mkdir(parents=True, exist_ok=True)
        self.registry = build_code_registry()
        self.dispatcher = ToolDispatcher(self.registry, PermissionPolicy(allow_execute=True))

    def test_workspace_tools_reject_escape_and_edit_once(self):
        context = AgentContext(self.root)
        denied = self.dispatcher.execute(ToolCall("1", "write_file", {"path": "../bad", "content": "x"}), context)
        self.assertEqual(denied.status, "error")
        self.assertEqual(self.dispatcher.execute(ToolCall("2", "write_file", {"path": "a.txt", "content": "one"}), context).status, "ok")
        edited = self.dispatcher.execute(ToolCall("3", "edit_file", {"path": "a.txt", "old_text": "one", "new_text": "two"}), context)
        self.assertEqual(edited.status, "ok")
        self.assertEqual((self.root / "a.txt").read_text(), "two")

    def test_loop_preserves_observations_and_memory(self):
        model = ScriptedModel([
            ModelResponse(tool_calls=[ToolCall("write", "write_file", {"path": "fix.py", "content": "answer = 42\n"})]),
            ModelResponse("fixed and verified"),
        ])
        memory = FileMemory(self.root)
        result = CodeAgent(model, self.dispatcher, memory).run("fix it", AgentContext(self.root))
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(result.tool_results), 1)
        self.assertTrue(memory.recall("default", "verified"))

    def test_mcp_is_namespaced_and_dispatched(self):
        install_mcp_tools(self.registry, FakeMCP())
        result = self.dispatcher.execute(ToolCall("m", "mcp__docs_server__lookup", {"topic": "api"}), AgentContext(self.root))
        self.assertEqual(result.content, "lookup:api")


if __name__ == "__main__":
    unittest.main()


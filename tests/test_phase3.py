import json
import unittest
import uuid
from pathlib import Path

from code_agent.agents.main_agent import MainAgent
from code_agent.agents.planner import JsonTaskPlanner, PlanningError
from code_agent.schemas import AgentResult, ModelResponse


class FixedPlannerModel:
    def __init__(self, content):
        self.content = content
        self.messages = None
    def generate(self, messages, tools):
        self.messages = messages
        self.assert_tools = tools
        return ModelResponse(self.content)


class RecordingSubagent:
    def __init__(self): self.calls = []
    def run(self, task, upstream):
        self.calls.append((task.task_id, sorted(upstream)))
        return AgentResult("completed", f"finished {task.task_id}", 0,
                           task_id=task.task_id, agent_id="fake", summary=f"finished {task.task_id}")


class PhaseThreeTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / ".test-workspace" / self._testMethodName
        self.root.mkdir(parents=True, exist_ok=True)

    def test_json_planner_validates_and_binds_workspace(self):
        model = FixedPlannerModel(json.dumps([
            {"task_id": "explore", "description": "Inspect tests", "dependencies": [], "write_access": False},
            {"task_id": "implement", "description": "Fix defect", "dependencies": ["explore"], "write_access": True},
            {"task_id": "test", "description": "Run tests", "dependencies": ["implement"], "write_access": False},
            {"task_id": "review", "description": "Review diff", "dependencies": ["test"], "write_access": False},
        ]))
        tasks = JsonTaskPlanner(model).plan("fix the failing test", self.root)
        self.assertEqual([task.task_id for task in tasks], ["explore", "implement", "test", "review"])
        self.assertTrue(tasks[1].write_access)
        self.assertTrue(all(task.workspace == str(self.root) for task in tasks))
        self.assertIn("Return only a JSON array", model.messages[0]["content"])

    def test_invalid_plans_are_rejected_before_execution(self):
        invalid = FixedPlannerModel('[{"task_id":"later","description":"x","dependencies":["missing"],"write_access":false}]')
        with self.assertRaises(PlanningError):
            JsonTaskPlanner(invalid).plan("do work", self.root)

    def test_natural_language_request_reaches_completed_workflow(self):
        plan = FixedPlannerModel(json.dumps([
            {"task_id": "explore", "description": "Explore repository", "dependencies": [], "write_access": False},
            {"task_id": "implement", "description": "Implement fix", "dependencies": ["explore"], "write_access": True},
            {"task_id": "verify", "description": "Run tests", "dependencies": ["implement"], "write_access": False},
        ]))
        subagent = RecordingSubagent()
        state = MainAgent(subagent).plan_and_execute(f"e2e-{uuid.uuid4().hex}", "fix the bug", self.root, JsonTaskPlanner(plan))
        self.assertTrue(all(status == "completed" for status in state["task_status"].values()))
        self.assertEqual(subagent.calls, [("explore", []), ("implement", ["explore"]), ("verify", ["implement"])])

    def test_checkpoint_rejects_a_different_plan(self):
        subagent = RecordingSubagent()
        agent = MainAgent(subagent)
        first = FixedPlannerModel('[{"task_id":"one","description":"one","dependencies":[],"write_access":false}]')
        workflow_id = f"same-{uuid.uuid4().hex}"
        agent.plan_and_execute(workflow_id, "first", self.root, JsonTaskPlanner(first))
        different = FixedPlannerModel('[{"task_id":"two","description":"two","dependencies":[],"write_access":false}]')
        with self.assertRaisesRegex(ValueError, "task set"):
            agent.plan_and_execute(workflow_id, "second", self.root, JsonTaskPlanner(different))


if __name__ == "__main__":
    unittest.main()


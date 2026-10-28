import time
import unittest
from pathlib import Path

from code_agent.runtime.checkpoint import WorkflowCheckpoint
from code_agent.runtime.scheduler import DagScheduler
from code_agent.agents.subagent import SubAgent
from code_agent.runtime.context import AgentContext
from code_agent.schemas import AgentResult, TaskSpec


class PhaseTwoTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / ".test-workspace" / self._testMethodName
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def worker(task, upstream):
        return AgentResult("completed", f"done {task.task_id}", 0,
                           task_id=task.task_id, agent_id="worker", summary=f"done {task.task_id}")

    def test_dag_order_and_checkpoint_resume(self):
        tasks = [TaskSpec("explore", "inspect", workspace=str(self.root)),
                 TaskSpec("fix", "change", dependencies=("explore",), workspace=str(self.root), write_access=True),
                 TaskSpec("test", "verify", dependencies=("fix",), workspace=str(self.root))]
        checkpoint = WorkflowCheckpoint(self.root, "fix-flow")
        state = DagScheduler().run("fix-flow", tasks, self.worker, checkpoint)
        self.assertEqual(state["task_status"], {"explore": "completed", "fix": "completed", "test": "completed"})
        restored = checkpoint.load()
        calls = []
        def should_not_run(task, upstream):
            calls.append(task.task_id)
            return self.worker(task, upstream)
        DagScheduler().run("fix-flow", tasks, should_not_run, checkpoint)
        self.assertEqual(calls, [])
        self.assertEqual(restored["task_results"]["fix"].agent_id, "worker")

    def test_failure_blocks_dependents(self):
        tasks = [TaskSpec("broken", "broken", workspace=str(self.root)),
                 TaskSpec("after", "after", dependencies=("broken",), workspace=str(self.root))]
        def worker(task, upstream):
            status = "failed" if task.task_id == "broken" else "completed"
            return AgentResult(status, status, 0, task_id=task.task_id)
        state = DagScheduler().run("blocked-flow", tasks, worker)
        self.assertEqual(state["task_status"], {"broken": "failed", "after": "blocked"})

    def test_read_only_tasks_can_run_in_parallel(self):
        tasks = [TaskSpec("one", "one", workspace=str(self.root)), TaskSpec("two", "two", workspace=str(self.root))]
        def slow_worker(task, upstream):
            time.sleep(0.05)
            return self.worker(task, upstream)
        started = time.monotonic()
        DagScheduler(max_read_concurrency=2).run("parallel-flow", tasks, slow_worker)
        self.assertLess(time.monotonic() - started, 0.095)

    def test_subagent_owns_a_fresh_context_and_only_gets_upstream_summary(self):
        received = []
        class FakeCodeAgent:
            def run(self, prompt, context):
                received.append((prompt, context))
                return AgentResult("completed", "analysis", 0)
        upstream = {"explore": AgentResult("completed", "secret history", 0,
                                             task_id="explore", summary="public summary")}
        task = TaskSpec("implement", "implement fix", dependencies=("explore",), workspace=str(self.root))
        result = SubAgent(FakeCodeAgent(), "implementer").run(task, upstream)
        self.assertEqual(result.task_id, "implement")
        self.assertEqual(result.agent_id, "implementer")
        self.assertIn("public summary", received[0][0])
        self.assertNotIn("secret history", received[0][0])
        self.assertEqual(received[0][1].messages, [])
        self.assertEqual(received[0][1].memory_scope, "task:implement")


if __name__ == "__main__":
    unittest.main()


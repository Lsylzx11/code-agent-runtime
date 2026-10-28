from __future__ import annotations

import argparse
from pathlib import Path

from .agents.main_agent import MainAgent
from .agents.planner import JsonTaskPlanner
from .agents.review_agent import ReviewAgent
from .agents.routing_subagent import RoutingSubAgent
from .agents.subagent import SubAgent
from .anthropic_model import AnthropicModel
from .defaults import build_code_registry
from .memory import FileMemory
from .runtime.agent_loop import CodeAgent
from .runtime.context import AgentContext
from .runtime.worktree import GitWorktreeManager
from .runtime.merge_gate import MergeGate
from .tools.dispatcher import ToolDispatcher
from .tools.permissions import PermissionPolicy


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Code Agent runtime.")
    parser.add_argument("task")
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--model")
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--allow-execute", action="store_true")
    parser.add_argument("--workflow", action="store_true",
                        help="Plan the request into a multi-agent DAG before executing it.")
    parser.add_argument("--workflow-id", default="default",
                        help="Checkpoint key used with --workflow; reuse it to resume the same plan.")
    parser.add_argument("--merge-reviewed", action="store_true",
                        help="Explicitly commit and merge reviews that returned verdict=approved.")
    args = parser.parse_args()
    workspace = Path(args.workspace).resolve()
    context = AgentContext(workspace=workspace, max_steps=args.max_steps)
    dispatcher = ToolDispatcher(build_code_registry(), PermissionPolicy(
        allow_execute=args.allow_execute,
    ))
    model = AnthropicModel(args.model)
    agent = CodeAgent(model, dispatcher, FileMemory(workspace))
    if args.workflow:
        manager = GitWorktreeManager(workspace, args.workflow_id)
        routed_worker = RoutingSubAgent(SubAgent(agent, "code-worker"), ReviewAgent(agent), manager)
        state = MainAgent(routed_worker).plan_and_execute(
            args.workflow_id, args.task, workspace, JsonTaskPlanner(model))
        failures = [task_id for task_id, status in state["task_status"].items()
                    if status != "completed"]
        if args.merge_reviewed and not failures:
            gate = MergeGate()
            reviews = [result for result in state["task_results"].values() if result.review]
            for review in reviews:
                if review.review.get("verdict") == "approved":
                    gate.merge(review, manager)
        print("workflow completed" if not failures else f"workflow incomplete: {', '.join(failures)}")
        return 0 if not failures else 1
    result = agent.run(args.task, context)
    print(result.output)
    return 0 if result.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())


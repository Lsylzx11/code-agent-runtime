from __future__ import annotations

from typing import Protocol

from ..memory import FileMemory
from ..schemas import AgentResult, ModelResponse
from ..tools.dispatcher import ToolDispatcher
from .context import AgentContext


class Model(Protocol):
    def generate(self, messages: list[dict], tools: list[dict]) -> ModelResponse: ...


class CodeAgent:
    def __init__(self, model: Model, dispatcher: ToolDispatcher, memory: FileMemory | None = None) -> None:
        self.model, self.dispatcher, self.memory = model, dispatcher, memory

    def run(self, task: str, context: AgentContext) -> AgentResult:
        recalled = self.memory.recall(context.memory_scope, task) if self.memory else []
        if recalled:
            context.messages.append({"role": "system", "content": "Relevant memory:\n" + "\n".join(x.text for x in recalled)})
        context.messages.append({"role": "user", "content": task})
        results = []
        try:
            for step in range(1, context.max_steps + 1):
                response = self.model.generate(context.messages, self.dispatcher.registry.schemas())
                assistant_content = ([{"type": "text", "text": response.content}]
                                     if response.content else [])
                assistant_content.extend({"type": "tool_use", "id": call.id,
                                          "name": call.name, "input": call.arguments}
                                         for call in response.tool_calls)
                context.messages.append({"role": "assistant", "content": assistant_content})
                if not response.tool_calls:
                    if self.memory and response.content:
                        self.memory.remember(context.memory_scope, response.content)
                    return AgentResult("completed", response.content, step - 1, results)
                round_results = [self.dispatcher.execute(call, context) for call in response.tool_calls]
                results.extend(round_results)
                context.messages.append({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": result.call_id,
                     "content": result.content, "is_error": result.status != "ok"}
                    for result in round_results
                ]})
            return AgentResult("max_steps", "maximum tool-call steps reached", context.max_steps, results)
        except KeyboardInterrupt:
            return AgentResult("cancelled", "agent cancelled", len(results), results)
        except Exception as exc:
            return AgentResult("failed", "agent runtime failed", len(results), results, [f"{type(exc).__name__}: {exc}"])


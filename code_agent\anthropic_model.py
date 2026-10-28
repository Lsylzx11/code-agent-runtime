from __future__ import annotations

import os

from .schemas import ModelResponse, ToolCall


class AnthropicModel:
    """Thin production adapter; importing the package does not require an API key."""

    def __init__(self, model: str | None = None, client=None) -> None:
        if client is None:
            from anthropic import Anthropic
            client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL") or None)
        self.client = client
        self.model = model or os.environ.get("MODEL_ID")
        if not self.model:
            raise ValueError("MODEL_ID is required, or pass model explicitly")

    def generate(self, messages: list[dict], tools: list[dict]) -> ModelResponse:
        response = self.client.messages.create(model=self.model, max_tokens=4096,
                                               messages=messages, tools=tools)
        text = "\n".join(block.text for block in response.content if block.type == "text")
        calls = [ToolCall(block.id, block.name, block.input)
                 for block in response.content if block.type == "tool_use"]
        return ModelResponse(text, calls)


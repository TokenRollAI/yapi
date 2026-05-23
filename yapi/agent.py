from __future__ import annotations

import os
import warnings

from pydantic_ai import Agent

from yapi.errors import YapiUsageWarning
from yapi.runner import AgentRunner, RunnerContext


class PydanticAIRunner:
    def __init__(self, model: str | None = None) -> None:
        self._model = model

    def run(self, ctx: RunnerContext) -> dict:
        if self._model is None:
            raise RuntimeError(
                "YAPI_MODEL is not set. "
                "Set YAPI_MODEL=test for an offline smoke test, "
                "or YAPI_MODEL=openai:gpt-4o etc. for real models."
            )
        agent = Agent(
            self._model,
            output_type=ctx.response_model,
            system_prompt=ctx.prompt,
        )
        user_prompt = f"request={ctx.request}\ninjected={ctx.injected}"
        result = agent.run_sync(user_prompt)
        output = getattr(result, "output", result)
        if hasattr(output, "model_dump"):
            return output.model_dump()
        return dict(output)


def build_default_runner(model: str | None = None) -> AgentRunner:
    resolved = model or os.getenv("YAPI_MODEL")
    if resolved is None:
        warnings.warn(
            "YAPI_MODEL not set; the first request to a prompt route will raise. "
            "Set YAPI_MODEL=test for an offline smoke test, "
            "or YAPI_MODEL=openai:gpt-4o etc. for real models.",
            YapiUsageWarning,
            stacklevel=2,
        )
    return PydanticAIRunner(model=resolved)


build_agent_runner = build_default_runner

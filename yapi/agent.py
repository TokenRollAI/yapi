from __future__ import annotations

import os
from collections.abc import Callable

from pydantic import BaseModel
from pydantic_ai import Agent


DEFAULT_SYSTEM_PREFIX = (
    "You are the execution engine behind a declarative HTTP endpoint. "
    "Return data that matches the required response model exactly."
)


def build_agent_runner(model: str | None = None) -> Callable[..., dict]:
    configured_model = model or os.getenv("YAPI_MODEL")

    def runner(
        *,
        prompt: str,
        request: dict,
        injected: dict,
        response_model: type[BaseModel],
    ) -> dict:
        if configured_model is None:
            raise NotImplementedError("Connect pydantic_ai.Agent by setting YAPI_MODEL")

        agent = Agent(
            configured_model,
            output_type=response_model,
            system_prompt=prompt,
        )

        user_prompt = f"request={request}\ninjected={injected}"
        result = agent.run_sync(user_prompt)
        output = getattr(result, "output", result)
        if hasattr(output, "model_dump"):
            return output.model_dump()
        return dict(output)

    return runner

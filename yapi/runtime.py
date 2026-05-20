from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel

from yapi.endpoint import PromptEndpoint
from yapi.errors import RuntimeExecutionError
from yapi.models import RuntimeContext

DEFAULT_SYSTEM_PREFIX = (
    "You are the execution engine behind a declarative HTTP endpoint. "
    "Return data that strictly matches the required response model."
)


def compose_prompt(endpoint: PromptEndpoint, dynamic_prompt: str | None) -> str:
    sections = [DEFAULT_SYSTEM_PREFIX]
    response_doc = endpoint.response_doc
    if response_doc:
        sections.append(response_doc)
    if endpoint.function_doc:
        sections.append(endpoint.function_doc)
    if dynamic_prompt:
        sections.append(dynamic_prompt)
    return "\n\n".join(sections)


class Runtime:
    def __init__(self, agent_runner: Callable[..., dict]) -> None:
        self._agent_runner = agent_runner

    def build_context(self, request_data: dict, injected: dict) -> RuntimeContext:
        return RuntimeContext(
            request=dict(request_data),
            injected=dict(injected),
        )

    def execute(
        self,
        endpoint: PromptEndpoint,
        request_model: BaseModel | None,
        injected: dict,
        dynamic_prompt: str | None,
    ) -> BaseModel:
        request_data = {} if request_model is None else request_model.model_dump()
        context = self.build_context(request_data=request_data, injected=injected)
        prompt = compose_prompt(endpoint, dynamic_prompt)

        try:
            payload = self._agent_runner(
                prompt=prompt,
                request=context.request,
                injected=context.injected,
                response_model=endpoint.response_model,
            )
        except Exception as exc:
            raise RuntimeExecutionError("Agent execution failed") from exc

        return endpoint.response_model.model_validate(payload)

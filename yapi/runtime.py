from __future__ import annotations

import logging
from collections.abc import Callable

from pydantic import BaseModel

from yapi.endpoint import PromptEndpoint
from yapi.errors import RuntimeExecutionError
from yapi.models import RuntimeContext
from yapi.runner import AgentRunner, RunnerContext, _coerce_runner

logger = logging.getLogger("yapi.runtime")

DEFAULT_SYSTEM_PREFIX = (
    "You are the execution engine behind a declarative HTTP endpoint. "
    "Return data that strictly matches the required response model."
)


PromptComposer = Callable[[PromptEndpoint, str | None], str]


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
    def __init__(
        self,
        agent_runner: AgentRunner | Callable[..., dict],
        prompt_composer: PromptComposer | None = None,
    ) -> None:
        self._agent_runner: AgentRunner = _coerce_runner(agent_runner)
        self._compose_prompt: PromptComposer = prompt_composer or compose_prompt

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
        prompt = self._compose_prompt(endpoint, dynamic_prompt)

        logger.debug(
            "execute path=%s method=%s has_request_model=%s injected_keys=%s",
            endpoint.path,
            endpoint.method,
            request_model is not None,
            list(context.injected.keys()),
        )
        logger.debug(
            "prompt composed prompt_length=%d sections=%d",
            len(prompt),
            prompt.count("\n\n") + 1,
        )

        ctx = RunnerContext(
            prompt=prompt,
            request=context.request,
            injected=context.injected,
            response_model=endpoint.response_model,
            path=endpoint.path,
            method=endpoint.method,
        )

        logger.debug("invoking runner=%s", type(self._agent_runner).__name__)
        try:
            payload = self._agent_runner.run(ctx)
        except Exception as exc:
            logger.warning("runner failed: %r", exc)
            raise RuntimeExecutionError(
                f"Agent execution failed: {type(exc).__name__}: {exc}"
            ) from exc

        if isinstance(payload, endpoint.response_model):
            return payload
        try:
            return endpoint.response_model.model_validate(payload)
        except Exception as exc:
            logger.warning("response model_validate failed: %r", exc)
            raise

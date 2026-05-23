from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


@dataclass(frozen=True)
class RunnerContext:
    prompt: str
    request: dict
    injected: dict
    response_model: type[BaseModel]
    path: str
    method: str


@runtime_checkable
class AgentRunner(Protocol):
    def run(self, ctx: RunnerContext) -> dict | BaseModel:
        ...


class _LegacyCallableRunner:
    def __init__(self, fn: Any) -> None:
        self._fn = fn

    def run(self, ctx: RunnerContext) -> dict | BaseModel:
        return self._fn(
            prompt=ctx.prompt,
            request=ctx.request,
            injected=ctx.injected,
            response_model=ctx.response_model,
        )


def _coerce_runner(runner: Any) -> AgentRunner:
    if runner is None:
        raise TypeError("agent_runner must not be None")
    if hasattr(runner, "run") and not isinstance(runner, type):
        return runner
    if callable(runner):
        return _LegacyCallableRunner(runner)
    raise TypeError(
        "agent_runner must be an AgentRunner or a "
        "(*, prompt, request, injected, response_model) callable, "
        f"got {type(runner).__name__}"
    )

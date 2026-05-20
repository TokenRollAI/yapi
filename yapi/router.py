from __future__ import annotations

import inspect
from collections.abc import Callable

from fastapi import APIRouter, params
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from yapi.agent import build_agent_runner
from yapi.endpoint import PromptEndpoint
from yapi.errors import RuntimeExecutionError, YapiDeclarationError
from yapi.runtime import Runtime

_HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")


def _introspect(func: Callable) -> tuple[type[BaseModel] | None, type[BaseModel], list[tuple[str, inspect.Parameter]]]:
    signature = inspect.signature(func)

    return_annotation = signature.return_annotation
    if return_annotation is inspect.Signature.empty:
        raise YapiDeclarationError(
            f"yapi route handler '{func.__name__}' must declare a return type annotation"
        )
    if not (isinstance(return_annotation, type) and issubclass(return_annotation, BaseModel)):
        raise YapiDeclarationError(
            f"yapi route handler '{func.__name__}' must return a Pydantic BaseModel subclass"
        )

    request_model: type[BaseModel] | None = None
    dependency_params: list[tuple[str, inspect.Parameter]] = []

    for name, param in signature.parameters.items():
        annotation = param.annotation
        default = param.default

        if isinstance(default, params.Depends):
            dependency_params.append((name, param))
            continue

        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            if request_model is not None:
                raise YapiDeclarationError(
                    f"yapi route handler '{func.__name__}' may declare at most one Pydantic request model parameter"
                )
            request_model = annotation
            continue

        raise YapiDeclarationError(
            f"yapi route handler '{func.__name__}' has parameter '{name}' that is neither a Pydantic model nor a Depends() dependency"
        )

    return request_model, return_annotation, dependency_params


class PromptRouter(APIRouter):
    def __init__(self, agent_runner: Callable[..., dict] | None = None) -> None:
        super().__init__()
        self._runtime = Runtime(agent_runner=agent_runner or build_agent_runner())

    def _register(self, method: str, path: str) -> Callable[[Callable], Callable]:
        upper = method.upper()
        if upper not in _HTTP_METHODS:
            raise YapiDeclarationError(f"Unsupported HTTP method: {method}")

        def decorator(func: Callable) -> Callable:
            request_model, response_model, dependency_params = _introspect(func)
            endpoint = PromptEndpoint(
                path=path,
                method=upper,
                request_model=request_model,
                response_model=response_model,
                function_doc=(func.__doc__ or "").strip(),
            )

            handler_params: list[inspect.Parameter] = []
            request_param_name: str | None = None
            for name, param in inspect.signature(func).parameters.items():
                handler_params.append(param)
                if isinstance(param.default, params.Depends):
                    continue
                if isinstance(param.annotation, type) and issubclass(param.annotation, BaseModel):
                    request_param_name = name

            async def handler(**kwargs):
                injected = {
                    name: kwargs[name] for name, _ in dependency_params if name in kwargs
                }
                request_instance = (
                    kwargs.get(request_param_name) if request_param_name is not None else None
                )

                dynamic_prompt = func(**kwargs)
                if dynamic_prompt is not None and not isinstance(dynamic_prompt, str):
                    raise RuntimeExecutionError(
                        f"yapi route handler '{func.__name__}' must return None or str, "
                        f"got {type(dynamic_prompt).__name__}"
                    )

                return await run_in_threadpool(
                    self._runtime.execute,
                    endpoint=endpoint,
                    request_model=request_instance,
                    injected=injected,
                    dynamic_prompt=dynamic_prompt,
                )

            handler.__signature__ = inspect.Signature(parameters=handler_params, return_annotation=response_model)
            handler.__annotations__ = {p.name: p.annotation for p in handler_params if p.annotation is not inspect.Parameter.empty}
            handler.__annotations__["return"] = response_model
            handler.__name__ = func.__name__

            self.add_api_route(
                path,
                handler,
                methods=[upper],
                response_model=response_model,
            )
            return func

        return decorator

    def get(self, path: str, **_unused):
        return self._register("GET", path)

    def post(self, path: str, **_unused):
        return self._register("POST", path)

    def put(self, path: str, **_unused):
        return self._register("PUT", path)

    def patch(self, path: str, **_unused):
        return self._register("PATCH", path)

    def delete(self, path: str, **_unused):
        return self._register("DELETE", path)

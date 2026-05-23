from __future__ import annotations

import inspect
import logging
import warnings
from collections.abc import Callable
from enum import Enum
from typing import Any

from fastapi import APIRouter, params
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from yapi.agent import build_default_runner
from yapi.endpoint import PromptEndpoint
from yapi.errors import RuntimeExecutionError, YapiDeclarationError, YapiUsageWarning
from yapi.runner import AgentRunner
from yapi.runtime import PromptComposer, Runtime

logger = logging.getLogger("yapi.router")

_HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")

_INJECTED_FIELD_TYPES: tuple[type[params.Param], ...] = (
    params.Query,
    params.Header,
    params.Cookie,
    params.Path,
    params.Form,
    params.File,
)

_PASSTHROUGH_KWARGS = frozenset(
    {
        "tags",
        "summary",
        "description",
        "status_code",
        "deprecated",
        "operation_id",
        "name",
        "include_in_schema",
        "responses",
        "openapi_extra",
    }
)

_REJECTED_KWARGS: dict[str, str] = {
    "response_model": (
        "response_model is inferred from the return annotation; do not pass it"
    ),
    "response_class": (
        "yapi controls the response class; do not pass response_class"
    ),
    "dependencies": (
        "declare dependencies on the function signature with Depends(...), "
        "not as a route-level dependencies= kwarg"
    ),
}


class ParamRole(Enum):
    REQUEST_MODEL = "request_model"
    DEPENDENCY = "dependency"
    INJECTED_FIELD = "injected_field"


def _unwrap_annotated(annotation: Any) -> tuple[Any, tuple[Any, ...]]:
    if hasattr(annotation, "__metadata__") and hasattr(annotation, "__origin__"):
        return annotation.__origin__, tuple(annotation.__metadata__)
    return annotation, ()


def _is_basemodel_type(tp: Any) -> bool:
    return isinstance(tp, type) and issubclass(tp, BaseModel)


def _classify_param(
    name: str,
    param: inspect.Parameter,
    func_name: str,
) -> ParamRole:
    if param.kind in (
        inspect.Parameter.VAR_POSITIONAL,
        inspect.Parameter.VAR_KEYWORD,
    ):
        raise YapiDeclarationError(
            f"yapi prompt route '{func_name}' does not support *args/**kwargs "
            f"(parameter '{name}')"
        )

    annotation = param.annotation
    default = param.default
    base_annotation, metadata = _unwrap_annotated(annotation)

    if isinstance(default, params.Depends):
        return ParamRole.DEPENDENCY

    if isinstance(default, _INJECTED_FIELD_TYPES):
        return ParamRole.INJECTED_FIELD

    if isinstance(default, params.Body):
        if _is_basemodel_type(base_annotation):
            return ParamRole.REQUEST_MODEL
        raise YapiDeclarationError(
            f"yapi prompt route '{func_name}' parameter '{name}': "
            "Body(...) may only be used with a Pydantic BaseModel-typed parameter; "
            "use Query/Header/Cookie/Path/Form/File for scalar fields"
        )

    for marker in metadata:
        if isinstance(marker, params.Depends):
            return ParamRole.DEPENDENCY
        if isinstance(marker, params.Body):
            if _is_basemodel_type(base_annotation):
                return ParamRole.REQUEST_MODEL
            raise YapiDeclarationError(
                f"yapi prompt route '{func_name}' parameter '{name}': "
                "Body() may only annotate a Pydantic BaseModel-typed parameter; "
                "use Query/Header/Cookie/Path/Form/File for scalar fields"
            )
        if isinstance(marker, _INJECTED_FIELD_TYPES):
            return ParamRole.INJECTED_FIELD

    if _is_basemodel_type(base_annotation):
        return ParamRole.REQUEST_MODEL

    raise YapiDeclarationError(
        f"yapi prompt route '{func_name}' has parameter '{name}' that is "
        "neither a Pydantic BaseModel, a Depends() dependency, nor a "
        "FastAPI Annotated marker (Query/Header/Cookie/Path/Form/File/Body)"
    )


def _introspect(
    func: Callable,
) -> tuple[type[BaseModel] | None, type[BaseModel], dict[str, ParamRole], str | None]:
    signature = inspect.signature(func)

    return_annotation = signature.return_annotation
    if return_annotation is inspect.Signature.empty:
        raise YapiDeclarationError(
            f"yapi prompt route '{func.__name__}' must declare a return type annotation"
        )
    if not _is_basemodel_type(return_annotation):
        raise YapiDeclarationError(
            f"yapi prompt route '{func.__name__}' must return a Pydantic BaseModel subclass"
        )

    if inspect.isgeneratorfunction(func) or inspect.isasyncgenfunction(func):
        raise YapiDeclarationError(
            f"yapi prompt route '{func.__name__}' must return None or a str, "
            "not a generator"
        )

    param_roles: dict[str, ParamRole] = {}
    request_model: type[BaseModel] | None = None
    request_param_name: str | None = None

    for name, param in signature.parameters.items():
        role = _classify_param(name, param, func.__name__)
        param_roles[name] = role
        if role is ParamRole.REQUEST_MODEL:
            if request_model is not None:
                raise YapiDeclarationError(
                    f"yapi prompt route '{func.__name__}' may declare at most one "
                    "Pydantic request model parameter"
                )
            base_annotation, _ = _unwrap_annotated(param.annotation)
            request_model = base_annotation
            request_param_name = name

    return request_model, return_annotation, param_roles, request_param_name


def _validate_prompt_kwargs(path: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    for rejected, reason in _REJECTED_KWARGS.items():
        if rejected in kwargs:
            raise YapiDeclarationError(
                f"yapi prompt route '{path}' rejects kwarg '{rejected}': {reason}"
            )

    unknown = sorted(k for k in kwargs if k not in _PASSTHROUGH_KWARGS)
    if unknown:
        warnings.warn(
            f"yapi: kwargs {unknown} are not recognized and will be ignored",
            YapiUsageWarning,
            stacklevel=4,
        )

    return {k: v for k, v in kwargs.items() if k in _PASSTHROUGH_KWARGS}


class _PromptDecorators:
    def __init__(self, router: "PromptRouter") -> None:
        self._router = router

    def get(self, path: str, **kwargs: Any) -> Callable[[Callable], Callable]:
        return self._router._register_prompt("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Callable[[Callable], Callable]:
        return self._router._register_prompt("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Callable[[Callable], Callable]:
        return self._router._register_prompt("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> Callable[[Callable], Callable]:
        return self._router._register_prompt("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Callable[[Callable], Callable]:
        return self._router._register_prompt("DELETE", path, **kwargs)


class PromptRouter(APIRouter):
    def __init__(
        self,
        agent_runner: AgentRunner | Callable[..., dict] | None = None,
        prompt_composer: PromptComposer | None = None,
        **apirouter_kwargs: Any,
    ) -> None:
        super().__init__(**apirouter_kwargs)
        self._runtime = Runtime(
            agent_runner=agent_runner if agent_runner is not None else build_default_runner(),
            prompt_composer=prompt_composer,
        )
        self.prompt = _PromptDecorators(self)

    def _register_prompt(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Callable[[Callable], Callable]:
        upper = method.upper()
        if upper not in _HTTP_METHODS:
            raise YapiDeclarationError(f"Unsupported HTTP method: {method}")

        passthrough = _validate_prompt_kwargs(path, kwargs)

        def decorator(func: Callable) -> Callable:
            request_model, response_model, param_roles, request_param_name = _introspect(func)

            endpoint = PromptEndpoint(
                path=path,
                method=upper,
                request_model=request_model,
                response_model=response_model,
                function_doc=(func.__doc__ or "").strip(),
            )

            is_async = inspect.iscoroutinefunction(func)
            original_signature = inspect.signature(func)
            original_params = list(original_signature.parameters.values())

            async def handler(**kwargs):
                injected: dict[str, Any] = {}
                request_instance: BaseModel | None = None
                for name, role in param_roles.items():
                    if name not in kwargs:
                        continue
                    if role is ParamRole.REQUEST_MODEL:
                        request_instance = kwargs[name]
                    else:
                        injected[name] = kwargs[name]

                if is_async:
                    dynamic_prompt = await func(**kwargs)
                else:
                    dynamic_prompt = func(**kwargs)

                if dynamic_prompt is not None and not isinstance(dynamic_prompt, str):
                    raise RuntimeExecutionError(
                        f"yapi prompt route '{func.__name__}' must return None or str, "
                        f"got {type(dynamic_prompt).__name__}"
                    )

                return await run_in_threadpool(
                    self._runtime.execute,
                    endpoint=endpoint,
                    request_model=request_instance,
                    injected=injected,
                    dynamic_prompt=dynamic_prompt,
                )

            handler.__signature__ = inspect.Signature(
                parameters=original_params,
                return_annotation=response_model,
            )
            handler.__annotations__ = {
                p.name: p.annotation
                for p in original_params
                if p.annotation is not inspect.Parameter.empty
            }
            handler.__annotations__["return"] = response_model
            handler.__name__ = func.__name__
            handler.__doc__ = func.__doc__

            logger.debug(
                "registering prompt route method=%s path=%s handler=%s async=%s",
                upper,
                path,
                func.__name__,
                is_async,
            )

            self.add_api_route(
                path,
                handler,
                methods=[upper],
                response_model=response_model,
                **passthrough,
            )
            return func

        return decorator

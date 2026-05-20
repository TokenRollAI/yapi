from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel


@dataclass(frozen=True)
class PromptEndpoint:
    path: str
    method: str
    request_model: type[BaseModel] | None
    response_model: type[BaseModel]
    function_doc: str = ""

    @property
    def response_doc(self) -> str:
        return (self.response_model.__doc__ or "").strip()

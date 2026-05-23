from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from yapi.errors import RuntimeExecutionError


def _format_value(value: Any) -> str:
    if value is None:
        raise RuntimeExecutionError(
            "PromptContext does not accept None; use an empty string if you want an empty segment."
        )
    if isinstance(value, str):
        return value
    if isinstance(value, BaseModel):
        return value.model_dump_json()
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


class PromptContext:
    def __init__(self) -> None:
        self._segments: list[str] = []

    def add(self, value: Any) -> None:
        self._segments.append(_format_value(value))

    def add_kv(self, key: str, value: Any) -> None:
        self._segments.append(f"{key}: {_format_value(value)}")

    def add_section(self, name: str, body: Any) -> None:
        self._segments.append(f"# {name}\n{_format_value(body)}")

    def segments(self) -> tuple[str, ...]:
        return tuple(self._segments)

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RuntimeContext:
    request: dict
    injected: dict

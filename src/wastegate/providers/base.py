"""One provider interface. Usage comes from provider JSON only; None when absent. Never estimated."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class Completion:
    text: str
    provider: str
    model_id: str
    usage: Optional[Usage]
    raw: Optional[dict] = None


class Provider(Protocol):
    name: str

    def complete(self, model_id: str, system: str, messages: list[dict], max_tokens: int) -> Completion: ...

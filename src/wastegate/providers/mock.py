"""Scripted replies from disk: <replies_dir>/<role>.md. No network; usage is None."""
from __future__ import annotations

from pathlib import Path

from .base import Completion


class MockProvider:
    name = "mock"

    def __init__(self, replies_dir: Path, role: str):
        self.path = Path(replies_dir) / f"{role}.md"
        if not self.path.exists():
            raise FileNotFoundError(f"no scripted reply: {self.path}")

    def complete(self, model_id: str, system: str, messages: list[dict], max_tokens: int) -> Completion:
        return Completion(self.path.read_text(encoding="utf-8"), self.name, model_id, usage=None)


def mock_providers(replies_dir: Path):
    return lambda role, model_id=None: MockProvider(replies_dir, role)

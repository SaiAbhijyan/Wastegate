"""Local Ollama via its OpenAI-compatible endpoint. Checked 2026-09-25 (docs.ollama.com/api/openai-compatibility):
base http://localhost:11434/v1/, /v1/chat/completions, API key "required but ignored".
We use 127.0.0.1 and send a placeholder bearer; no real key is ever sent.
UNVERIFIED: whether non-streaming responses include `usage` (docs mention stream_options include_usage)."""
from __future__ import annotations

import os
import urllib.request
from typing import Callable, Optional

from .base import LiveDisabled
from .http import OpenAICompatible, Transport

BASE = "http://127.0.0.1:11434"


def _default_probe() -> None:
    with urllib.request.urlopen(f"{BASE}/v1/models", timeout=2) as r:
        r.read(1)


class OllamaProvider(OpenAICompatible):
    name = "ollama"
    key_envs = ()
    url = f"{BASE}/v1/chat/completions"

    def __init__(self, allow_network: bool = False, transport: Optional[Transport] = None,
                 probe: Optional[Callable[[], None]] = None):
        super().__init__(allow_network=allow_network, transport=transport)
        self._probe = probe

    def check(self) -> str:
        if not self.allow_network:
            raise LiveDisabled("--live not set")
        if self._transport is None:
            if self._probe is None and "PYTEST_CURRENT_TEST" in os.environ:
                raise LiveDisabled("network disabled under pytest")
            try:
                (self._probe or _default_probe)()
            except Exception:
                raise LiveDisabled(f"ollama not reachable at {BASE} (start it with `ollama serve`)")
        return "ollama"  # placeholder bearer; Ollama ignores it

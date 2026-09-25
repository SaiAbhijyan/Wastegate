"""Shared gate + transport for live adapters. Dark by default.

HTTP runs only when: the adapter's key env var is set, allow_network=True (CLI --live), and we
are not under pytest (unless a fake transport is injected). Keys are never logged or repr'd.
Usage comes only from the provider JSON; missing -> None (docs/PROVIDERS.md).
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Callable, Optional

from .. import __version__
from .base import Completion, LiveDisabled, Usage

Transport = Callable[[str, dict, dict], dict]


def post_json(url: str, headers: dict, body: dict) -> dict:
    # Explicit User-Agent: Cloudflare-fronted APIs (api.groq.com) return 403 / error 1010 for Python-urllib.
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"content-type": "application/json",
                                          "user-agent": f"wastegate/{__version__}", **headers})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())


class LiveAdapter:
    name = ""
    key_envs: tuple[str, ...] = ()

    def __init__(self, allow_network: bool = False, transport: Optional[Transport] = None):
        self.allow_network = allow_network
        self._transport = transport

    def __repr__(self) -> str:
        return f"{type(self).__name__}(allow_network={self.allow_network}, key={'set' if self._key() else 'unset'})"

    def _key(self) -> Optional[str]:
        return next((os.environ[v] for v in self.key_envs if os.environ.get(v)), None)

    def check(self) -> str:
        key = self._key()
        if not key or not self.allow_network:
            raise LiveDisabled("no key or --live not set")
        if self._transport is None and "PYTEST_CURRENT_TEST" in os.environ:
            raise LiveDisabled("network disabled under pytest")
        return key

    def complete(self, model_id: str, system: str, messages: list[dict], max_tokens: int) -> Completion:
        key = self.check()
        url, headers, body = self.build(key, model_id, system, messages, max_tokens)
        raw = (self._transport or post_json)(url, headers, body)
        text, usage = self.parse(raw)
        return Completion(text, self.name, model_id, usage, raw)

    def build(self, key, model_id, system, messages, max_tokens) -> tuple[str, dict, dict]:
        raise NotImplementedError

    def parse(self, raw: dict) -> tuple[str, Optional[Usage]]:
        raise NotImplementedError


class OpenAICompatible(LiveAdapter):
    url = ""
    max_tokens_field = "max_tokens"

    def build(self, key, model_id, system, messages, max_tokens):
        body = {"model": model_id, "messages": [{"role": "system", "content": system}, *messages],
                self.max_tokens_field: max_tokens}
        return self.url, {"Authorization": f"Bearer {key}"}, body

    def parse(self, raw):
        text = raw["choices"][0]["message"].get("content") or ""
        u = raw.get("usage")
        if not u or u.get("prompt_tokens") is None or u.get("completion_tokens") is None:
            return text, None
        return text, Usage(int(u["prompt_tokens"]), int(u["completion_tokens"]))

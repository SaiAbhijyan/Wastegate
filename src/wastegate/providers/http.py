"""Shared gate + transport for live adapters. Dark by default.

HTTP runs only when: the adapter's key env var is set, allow_network=True (CLI --live), and we
are not under pytest (unless a fake transport is injected). Keys are never logged or repr'd.
Usage comes only from the provider JSON; missing -> None (docs/PROVIDERS.md).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Callable, Optional

from .. import __version__
from .base import Completion, LiveDisabled, Usage

Transport = Callable[[str, dict, dict], dict]


ERROR_BODY_CAP = 1000


class ProviderHTTPError(urllib.error.URLError):
    """Non-2xx from a provider, with the (redacted, capped) response body so users can see WHY."""

    def __init__(self, status: int, body: str):
        from ..log import redact
        self.status = status
        full = redact(body)
        self.body = full[:ERROR_BODY_CAP]
        try:  # uncapped parsed body, e.g. Groq's error.failed_generation for tool-call recovery
            self.data = json.loads(full)
        except ValueError:
            self.data = None
        super().__init__(f"HTTP {status}: {self.body}")

    def __str__(self) -> str:
        return f"HTTP {self.status}: {self.body}"


def post_json(url: str, headers: dict, body: dict) -> dict:
    # Explicit User-Agent: Cloudflare-fronted APIs (api.groq.com) return 403 / error 1010 for Python-urllib.
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"content-type": "application/json",
                                          "user-agent": f"wastegate/{__version__}", **headers})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8", errors="replace")
        except Exception:
            raw = ""
        raise ProviderHTTPError(e.code, raw or str(e.reason)) from None


class LiveAdapter:
    name = ""
    key_envs: tuple[str, ...] = ()
    max_tokens_cap: Optional[int] = None  # set by live_providers from the catalog tier
    supports_tools = False  # True: complete() accepts tools= (OpenAI function specs)

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

    def complete(self, model_id: str, system: str, messages: list[dict], max_tokens: int,
                 tools: Optional[list] = None) -> Completion:
        key = self.check()
        if self.max_tokens_cap:
            max_tokens = min(max_tokens, self.max_tokens_cap)
        url, headers, body = self.build(key, model_id, system, messages, max_tokens)
        if tools and self.supports_tools:
            body["tools"], body["tool_choice"] = tools, "auto"
        raw = (self._transport or post_json)(url, headers, body)
        text, usage = self.parse(raw)
        return Completion(text, self.name, model_id, usage, raw, self.parse_tool_calls(raw))

    def parse_tool_calls(self, raw: dict) -> tuple:
        return ()

    def build(self, key, model_id, system, messages, max_tokens) -> tuple[str, dict, dict]:
        raise NotImplementedError

    def parse(self, raw: dict) -> tuple[str, Optional[Usage]]:
        raise NotImplementedError


class OpenAICompatible(LiveAdapter):
    url = ""
    max_tokens_field = "max_tokens"
    supports_tools = True

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

    def parse_tool_calls(self, raw):
        calls = raw["choices"][0]["message"].get("tool_calls") or []
        return tuple({"id": c.get("id", ""), "name": (c.get("function") or {}).get("name", ""),
                      "arguments": (c.get("function") or {}).get("arguments") or ""} for c in calls)

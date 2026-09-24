"""Anthropic Messages API. Fields verified 2026-09-24 against platform.claude.com/docs/en/api/messages."""
from __future__ import annotations

from .base import Usage
from .http import LiveAdapter


class AnthropicProvider(LiveAdapter):
    name = "anthropic"
    key_envs = ("ANTHROPIC_API_KEY",)
    url = "https://api.anthropic.com/v1/messages"

    def build(self, key, model_id, system, messages, max_tokens):
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        body = {"model": model_id, "max_tokens": max_tokens, "system": system, "messages": messages}
        return self.url, headers, body

    def parse(self, raw):
        text = "".join(b.get("text", "") for b in raw.get("content", []) if b.get("type") == "text")
        u = raw.get("usage")
        if not u or u.get("input_tokens") is None or u.get("output_tokens") is None:
            return text, None
        # Docs: total input = input_tokens + cache_creation_input_tokens + cache_read_input_tokens.
        tin = u["input_tokens"] + (u.get("cache_creation_input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0)
        return text, Usage(int(tin), int(u["output_tokens"]))

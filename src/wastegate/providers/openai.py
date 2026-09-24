"""OpenAI Chat Completions. Fields verified 2026-09-24 against openai/openai-openapi openapi.yaml."""
from __future__ import annotations

from .http import OpenAICompatible


class OpenAIProvider(OpenAICompatible):
    name = "openai"
    key_envs = ("OPENAI_API_KEY",)
    url = "https://api.openai.com/v1/chat/completions"
    max_tokens_field = "max_completion_tokens"

"""Groq (OpenAI-compatible). Verified 2026-09-24: base https://api.groq.com/openai/v1 and GROQ_API_KEY
(console.groq.com/docs/openai); /chat/completions, usage prompt_tokens/completion_tokens,
max_completion_tokens (console.groq.com/docs/api-reference)."""
from __future__ import annotations

from .http import OpenAICompatible


class GroqProvider(OpenAICompatible):
    name = "groq"
    key_envs = ("GROQ_API_KEY",)
    url = "https://api.groq.com/openai/v1/chat/completions"
    max_tokens_field = "max_completion_tokens"

"""Gemini via its OpenAI-compatible endpoint. Verified 2026-09-24 (ai.google.dev/gemini-api/docs/openai):
base .../v1beta/openai/, chat/completions, Authorization: Bearer $GEMINI_API_KEY.
UNVERIFIED: usage field names and the max-tokens field (not on that page); GOOGLE_API_KEY is accepted
by user request, not seen on that page. GEMINI_API_KEY wins if both are set."""
from __future__ import annotations

from .http import OpenAICompatible


class GeminiProvider(OpenAICompatible):
    name = "gemini"
    key_envs = ("GEMINI_API_KEY", "GOOGLE_API_KEY")
    url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    max_tokens_field = "max_tokens"

"""OpenRouter (OpenAI-compatible). Endpoint/auth/usage verified 2026-09-24 against
openrouter.ai/docs/api-reference/overview. `usage.cost` is kept in Completion.raw only;
usd stays null until a catalog price is verified. `max_tokens` request field: UNVERIFIED."""
from __future__ import annotations

from .http import OpenAICompatible


class OpenRouterProvider(OpenAICompatible):
    name = "openrouter"
    key_env = "OPENROUTER_API_KEY"
    url = "https://openrouter.ai/api/v1/chat/completions"

from __future__ import annotations

from ..catalog import Catalog
from .anthropic import AnthropicProvider
from .base import LiveDisabled
from .openai import OpenAIProvider
from .openrouter import OpenRouterProvider

ADAPTERS = {"anthropic": AnthropicProvider, "openai": OpenAIProvider, "openrouter": OpenRouterProvider}


def live_providers(catalog: Catalog, allow_network: bool):
    """Factory(role, model_id) -> adapter, checked at resolve time (before any repo write)."""
    def get(role: str, model_id: str):
        m = next((m for m in catalog.models if m.id == model_id), None)
        if m is None or m.provider not in ADAPTERS:
            raise LiveDisabled(f"no live adapter for model {model_id!r}")
        a = ADAPTERS[m.provider](allow_network=allow_network)
        a.check()
        return a
    return get

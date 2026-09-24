from __future__ import annotations

import os

from ..catalog import Catalog
from .anthropic import AnthropicProvider
from .base import LiveDisabled
from .openai import OpenAIProvider
from .openrouter import OpenRouterProvider

ADAPTERS = {"anthropic": AnthropicProvider, "openai": OpenAIProvider, "openrouter": OpenRouterProvider}


def live_catalog(catalog: Catalog) -> Catalog:
    """Only rows whose provider key is set, so --live never silently uses another provider."""
    keyed = {name for name, cls in ADAPTERS.items() if os.environ.get(cls.key_env)}
    sub = catalog.for_providers(keyed)
    if not sub.models:
        raise LiveDisabled("no key or --live not set")
    return sub


def live_providers(catalog: Catalog, allow_network: bool, transport=None):
    """Factory(role, model_id) -> adapter, checked at resolve time (before any repo write).
    transport: test-only fake; None = real HTTP."""
    def get(role: str, model_id: str):
        m = next((m for m in catalog.models if m.id == model_id), None)
        if m is None or m.provider not in ADAPTERS:
            raise LiveDisabled(f"no live adapter for model {model_id!r}")
        a = ADAPTERS[m.provider](allow_network=allow_network, transport=transport)
        a.check()
        return a
    return get

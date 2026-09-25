from __future__ import annotations

import os

from ..catalog import Catalog, Model
from .anthropic import AnthropicProvider
from .base import LiveDisabled
from .gemini import GeminiProvider
from .groq import GroqProvider
from .ollama import OllamaProvider
from .openai import OpenAIProvider
from .openrouter import OpenRouterProvider

ADAPTERS = {"anthropic": AnthropicProvider, "openai": OpenAIProvider, "openrouter": OpenRouterProvider,
            "groq": GroqProvider, "gemini": GeminiProvider, "ollama": OllamaProvider}
PAID_PROVIDERS = {"anthropic", "openai"}


def is_paid(m: Model) -> bool:
    """Groq/Gemini are free-tier providers (not a $0 guarantee: see docs/KEYS.md)."""
    return m.provider in PAID_PROVIDERS or (m.provider == "openrouter" and not m.id.endswith(":free"))


def paid_allowed(flag: bool = False) -> bool:
    return flag or os.environ.get("ALLOW_PAID") == "1"


def live_catalog(catalog: Catalog, allow_paid: bool = False, local: bool = False) -> Catalog:
    """Rows whose provider key is set; paid rows dropped unless --allow-paid / ALLOW_PAID=1.
    local=True: only keyless local (Ollama) rows; cloud keys ignored.
    --live never silently falls back to another provider."""
    if local:
        sub = catalog.for_providers({"ollama"})
        if not sub.models:
            raise LiveDisabled("no local (ollama) model in catalog")
        return sub
    keyed = {name for name, cls in ADAPTERS.items() if any(os.environ.get(v) for v in cls.key_envs)}
    sub = catalog.for_providers(keyed)
    if not sub.models:
        raise LiveDisabled("no key or --live not set")
    if not paid_allowed(allow_paid):
        sub = type(sub)([m for m in sub.models if not is_paid(m)])
        if not sub.models:
            raise LiveDisabled("only paid keys/models available; set ALLOW_PAID=1 or pass --allow-paid")
    return sub


def live_providers(catalog: Catalog, allow_network: bool, transport=None, allow_paid: bool = False):
    """Factory(role, model_id) -> adapter, checked at resolve time (before any repo write or HTTP).
    Paid gate is enforced here too, so an unfiltered catalog cannot reach a paid model.
    transport: test-only fake; None = real HTTP."""
    def get(role: str, model_id: str):
        m = next((m for m in catalog.models if m.id == model_id), None)
        if m is None or m.provider not in ADAPTERS:
            raise LiveDisabled(f"no live adapter for model {model_id!r}")
        if is_paid(m) and not paid_allowed(allow_paid):
            raise LiveDisabled(f"paid model {model_id!r} refused; set ALLOW_PAID=1 or pass --allow-paid")
        a = ADAPTERS[m.provider](allow_network=allow_network, transport=transport)
        a.check()
        return a
    return get

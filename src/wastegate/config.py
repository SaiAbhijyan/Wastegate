from __future__ import annotations

import os
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

from .router import RouterConfig

DEFAULT_TOML = """# Wastegate config. API keys are read from env only; never put them here.
[systemone]
backend = "heuristic"      # heuristic | laya | jev (laya/jev live calls disabled in v0.1)

[router]
frontier_threshold = 0.7
tests_threshold = 0.5
yagni_threshold = 0.5
ambiguous_threshold = 0.6
reviewer_budget_tokens = 8192   # tester/skeptic max_tokens; reasoning models need headroom for the verdict line
"""


def home() -> Path:
    return Path(os.environ.get("WASTEGATE_HOME", Path.home() / ".wastegate"))


def load() -> dict:
    p = home() / "config.toml"
    return tomllib.loads(p.read_text() if p.exists() else DEFAULT_TOML)


def router_config(cfg: dict) -> RouterConfig:
    return RouterConfig(**cfg.get("router", {}))

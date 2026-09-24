from __future__ import annotations

import sys
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

TIERS = ("local", "cheap", "mid", "frontier")


@dataclass(frozen=True)
class Model:
    tier: str
    id: str
    provider: str
    name: str
    verified: bool
    source: str


@dataclass(frozen=True)
class Catalog:
    models: list[Model]

    def tiers(self) -> list[str]:
        return [t for t in TIERS if any(m.tier == t for m in self.models)]

    def first(self, tier: str) -> Model | None:
        return next((m for m in self.models if m.tier == tier), None)

    def resolve(self, want: str) -> str:
        """Nearest available tier: cheaper first, then dearer."""
        have = self.tiers()
        if not have:
            raise ValueError("catalog is empty")
        if want in have:
            return want
        i = TIERS.index(want)
        for t in reversed(TIERS[:i]):
            if t in have:
                return t
        return next(t for t in TIERS[i + 1:] if t in have)


def load_catalog(path: Path | None = None) -> Catalog:
    raw = Path(path).read_bytes() if path else resources.files("wastegate").joinpath("data/models.toml").read_bytes()
    data = tomllib.loads(raw.decode())
    return Catalog([Model(**m) for m in data.get("model", [])])

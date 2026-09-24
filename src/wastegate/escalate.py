"""Decide the frontier slice: only unresolved findings, only files they name. Pure; no key needed."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Sequence

from .catalog import Catalog
from .router import Route

PATH_RE = re.compile(r"^\s*([\w./-]+\.\w+|[\w.-]+/[\w./-]+)\s*:")


@dataclass(frozen=True)
class Slice:
    model_id: str
    findings: tuple[str, ...]
    files: tuple[str, ...]
    budget_tokens: int


def escalate_slice(unresolved: Sequence[str], route: Route, catalog: Catalog) -> tuple[Optional[Slice], str]:
    if not unresolved:
        return None, "nothing unresolved"
    fs = next((s for s in route.specialists if s.role == "frontier-slice"), None)
    frontier = catalog.first("frontier")
    if fs is None or frontier is None:
        return None, "no frontier available: report unresolved to user"
    files = tuple(dict.fromkeys(m.group(1) for f in unresolved if (m := PATH_RE.match(f))))
    return Slice(fs.model or frontier.id, tuple(unresolved), files, fs.budget_tokens), "escalate unresolved slice"

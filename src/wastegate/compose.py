"""Compose the system prefix from ONLY the route's skills, under a byte budget."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from .router import Route
from .skills.registry import Skill

DEFAULT_BUDGET = 12_000


@dataclass
class Composed:
    system: str
    user: str
    included: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)


def compose(route: Route, user: str, registry: Mapping[str, Skill],
            budget_bytes: int = DEFAULT_BUDGET) -> Composed:
    d = route.driver
    header = (f"Role: {d.role}. Tier: {d.tier}. Token budget: {d.budget_tokens} (hard cap).\n"
              + ("Ask one clarifying question before acting.\n" if route.clarify_first else ""))
    parts, included, dropped = [header], [], []
    used = len(header.encode())
    for sid in route.skills:
        s = registry.get(sid)
        if s is None or s.quarantined:
            dropped.append(sid)
            continue
        block = f"\n<skill id=\"{sid}\" sha256=\"{s.sha256[:12]}\">\n{s.body.strip()}\n</skill>\n"
        if used + len(block.encode()) > budget_bytes:
            dropped.append(sid)
            continue
        parts.append(block)
        used += len(block.encode())
        included.append(sid)
    return Composed("".join(parts), user, included, dropped)

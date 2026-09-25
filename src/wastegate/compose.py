"""Compose the system prefix from ONLY the route's skills, under a byte budget."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from .router import Route
from .skills.registry import Skill

DEFAULT_BUDGET = 12_000


@dataclass
class Composed:
    system: str
    user: str
    included: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    instincts: list[str] = field(default_factory=list)


def compose(route: Route, user: str, registry: Mapping[str, Skill],
            budget_bytes: int = DEFAULT_BUDGET, instincts: Sequence[str] = ()) -> Composed:
    d = route.driver
    header = (f"Role: {d.role}. Tier: {d.tier}. Token budget: {d.budget_tokens} (hard cap).\n"
              + ("Ask one clarifying question before acting.\n" if route.clarify_first else ""))
    parts, included, dropped, used_instincts = [header], [], [], []
    used = len(header.encode())
    if instincts:
        block = ("\n<instincts note=\"user preferences learned from reviews\">\n"
                 + "".join(f"- {i}\n" for i in instincts) + "</instincts>\n")
        if used + len(block.encode()) <= budget_bytes:
            parts.append(block)
            used += len(block.encode())
            used_instincts = list(instincts)
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
    return Composed("".join(parts), user, included, dropped, used_instincts)

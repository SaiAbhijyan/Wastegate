"""Agent-loop gate extras. Locked templates, same Question/Answer interface as GATE_QUESTIONS.

The heuristic answers live here (heuristic.py is frozen). Any other backend (Jev later) is asked the
same questions via decide(); it only routes, it never writes code.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from ..catalog import TIERS, Catalog
from ..providers.base import LiveDisabled
from ..router import RouterConfig
from .base import GATE_QUESTIONS, Answer, Question, noul_answer
from .heuristic import HeuristicSystemOne
from .shortlist import shortlist

AGENT_TOOLS = ("read", "grep", "edit", "shell", "pytest")
READONLY_TOOLS = ("read", "grep", "shell")
WRITE_KINDS = ("implement", "debug", "other")
LOOP_PROVIDERS = {"groq", "openrouter", "ollama", "mock"}
DEFAULT_MAX_STEPS = 8

TOOL_LOOP = Question("tool_loop", "noul",
                     "Does this task need several tool calls (read, search, edit, run tests) rather than one answer?")
MODEL_PICK_TEXT = "Which available model should do this task?"
HARNESS_WORDS = re.compile(r"\b(verify|test it|prove|harden|ship)\b", re.IGNORECASE)


def load_harness(kind: str, prompt: str) -> bool:
    """verification-harness loads for implement/debug, or when the prompt asks to verify/test it/prove/harden/ship."""
    return kind in ("implement", "debug") or bool(HARNESS_WORDS.search(prompt))


def agent_catalog(catalog: Catalog) -> Catalog:
    """Loop-eligible generation models: groq, openrouter :free, ollama (and mock in tests)."""
    rows = [m for m in catalog.models
            if m.provider in LOOP_PROVIDERS and (m.provider != "openrouter" or m.id.endswith(":free"))]
    if not rows:
        raise LiveDisabled("no loop-eligible model: the agent loop uses groq, openrouter :free, or ollama (--local)")
    return Catalog(rows)


def model_pick_question(ids: list[str], state: str) -> Optional[Question]:
    ids = list(dict.fromkeys(ids))[:255]
    if len(ids) < 2:
        return None
    return shortlist(Question("model_pick", "choice", MODEL_PICK_TEXT, tuple(ids)), state, k=20)


@dataclass
class AgentPlan:
    model_id: str
    tools: tuple[str, ...]
    max_steps: int
    harness: bool
    kind: str
    answers: dict = field(default_factory=dict)
    harness_mode: str = ""  # "full" | "code-only" | "off" (set by agent.build_system)


def _ans(a: Answer) -> dict:
    return {"value": a.value, "distribution": dict(a.distribution), "confidence": a.confidence}


def agent_plan(prompt: str, s1, catalog: Catalog, cfg: RouterConfig, max_steps: int = DEFAULT_MAX_STEPS,
               gate: Optional[dict] = None) -> AgentPlan:
    gate = gate or s1.decide(prompt, GATE_QUESTIONS)
    kind = str(gate["kind"].value)
    ids = [m.id for m in catalog.models]
    q = model_pick_question(ids, prompt)
    if isinstance(s1, HeuristicSystemOne):
        # Cheapest tier first (e.g. Groq gpt-oss-20b over -120b); Jev may override via model_pick later.
        cheapest = min(catalog.tiers(), key=TIERS.index)
        pick = catalog.first(cheapest).id
        opts = q.options if q else tuple(ids)
        if pick not in opts:
            pick = opts[0]
        n = len(opts)
        dist = {o: (0.9 if o == pick else 0.1 / (n - 1)) for o in opts} if n > 1 else {pick: 1.0}
        mp = Answer(pick, dist, dist[pick], s1.name)
        tl = noul_answer(0.85 if kind in ("implement", "debug") else 0.6 if kind in ("review", "other") else 0.3,
                         s1.name)
    else:  # Jev / Laya: same locked templates through decide()
        qs = {"tool_loop": TOOL_LOOP, **({"model_pick": q} if q else {})}
        got = s1.decide(prompt, qs)
        tl = got["tool_loop"]
        mp = got.get("model_pick") or Answer(ids[0], {ids[0]: 1.0}, 1.0, s1.name)
    return AgentPlan(model_id=str(mp.value), tools=AGENT_TOOLS if kind in WRITE_KINDS else READONLY_TOOLS,
                     max_steps=max_steps, harness=load_harness(kind, prompt), kind=kind,
                     answers={"tool_loop": _ans(tl), "model_pick": _ans(mp)})

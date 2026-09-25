"""Rules-first router: System One answers -> experts (role x skills x model tier x budget).

Invariants: driver is never frontier; frontier only as a slice specialist; skeptic runs on a
tier <= driver; works with any non-empty subset of tiers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping

from .catalog import TIERS, Catalog
from .systemone.base import Answer

LEVELS = ("trivial", "small", "feature", "deep", "ultracode")
DRIVER_TIER = {"trivial": "cheap", "small": "cheap", "feature": "mid", "deep": "mid", "ultracode": "mid"}
DRIVER_BUDGET = {"trivial": 2_000, "small": 4_000, "feature": 16_000, "deep": 32_000, "ultracode": 64_000}
KIND_SKILLS = {"ask": ("feynman",), "plan": ("superpowers",), "implement": ("karpathy",),
               "debug": ("karpathy",), "review": ("fable-mode",), "research": ("feynman",),
               "ship": ("brag",), "other": ()}


@dataclass(frozen=True)
class RouterConfig:
    frontier_threshold: float = 0.7
    tests_threshold: float = 0.5
    yagni_threshold: float = 0.5
    ambiguous_threshold: float = 0.6
    # Tester/skeptic max_tokens. Reasoning models spend completion tokens before the visible verdict,
    # so this must leave room for reasoning + the contract line (4000 truncated a Groq gpt-oss-20b skeptic).
    reviewer_budget_tokens: int = 8_192


@dataclass(frozen=True)
class Expert:
    role: str
    tier: str
    model: str | None
    skills: tuple[str, ...]
    budget_tokens: int


@dataclass(frozen=True)
class Route:
    driver: Expert
    specialists: tuple[Expert, ...]
    skills: tuple[str, ...]
    clarify_first: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def _p(a: Answer) -> float:
    return float(a.value)


def route(gate: Mapping[str, Answer], catalog: Catalog, cfg: RouterConfig) -> Route:
    kind = str(gate["kind"].value)
    domain = str(gate["domain"].value)
    cx = str(gate["complexity"].value)
    reasons: list[str] = []

    def expert(role: str, want: str, skills: tuple[str, ...], budget: int) -> Expert:
        tier = catalog.resolve(want)
        if tier != want:
            reasons.append(f"{role}: wanted {want}, using {tier} (not in catalog)")
        m = catalog.first(tier)
        return Expert(role, tier, m.id if m else None, skills, budget)

    # skills
    skills: list[str] = []
    primary = str(gate["skill_primary"].value)
    if primary != "none":
        skills.append(primary)
    skills += KIND_SKILLS[kind]
    if _p(gate["yagni"]) >= cfg.yagni_threshold:
        skills.append("ponytail")
        reasons.append(f"P(yagni)={_p(gate['yagni']):.2f} >= {cfg.yagni_threshold}: ponytail")
    deep = LEVELS.index(cx) >= LEVELS.index("deep")
    if deep:
        skills += ["ecc", "fable-mode"]
    skills.append("caveman")
    skills_t = tuple(dict.fromkeys(skills))

    # driver: never frontier by default
    drv_want = DRIVER_TIER[cx]
    reasons.append(f"complexity={cx}: driver wants {drv_want}")
    # resolve() prefers cheaper tiers, so frontier drives only if it is the sole tier
    driver = expert("driver", drv_want, skills_t, DRIVER_BUDGET[cx])

    specs: list[Expert] = []
    have = catalog.tiers()
    if LEVELS.index(cx) >= LEVELS.index("feature"):
        cheapest = min(have, key=TIERS.index)
        sk_tier = cheapest if TIERS.index(cheapest) <= TIERS.index(driver.tier) else driver.tier
        specs.append(expert("skeptic", sk_tier, ("fable-mode", "caveman"), cfg.reviewer_budget_tokens))
    if _p(gate["needs_tests"]) >= cfg.tests_threshold:
        specs.append(expert("tester", driver.tier, ("superpowers", "caveman"), cfg.reviewer_budget_tokens))
    if kind == "research" or domain == "research":
        specs.append(expert("researcher", driver.tier, ("feynman", "caveman"), 8_000))
    if kind == "ship":
        specs.append(expert("bragger", "cheap", ("brag",), 4_000))

    pf = _p(gate["needs_frontier"])
    if pf >= cfg.frontier_threshold or cx == "ultracode":
        if "frontier" in have:
            specs.append(expert("frontier-slice", "frontier", ("fable-mode", "caveman"), 8_000))
            reasons.append(f"P(needs_frontier)={pf:.2f}, complexity={cx}: frontier on unresolved slice only")
        else:
            reasons.append("frontier wanted but not in catalog: staying on mid")

    clarify = _p(gate["ambiguous"]) >= cfg.ambiguous_threshold
    if clarify:
        reasons.append("P(ambiguous) high: ask a clarifying question first")
    return Route(driver, tuple(specs), skills_t, clarify, tuple(reasons))

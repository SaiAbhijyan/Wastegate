from wastegate.catalog import Catalog, Model, load_catalog
from wastegate.router import RouterConfig, route
from wastegate.systemone.base import Answer, GATE_QUESTIONS
from wastegate.systemone.heuristic import HeuristicSystemOne

TIER_ORDER = ["local", "cheap", "mid", "frontier"]


def gate(complexity="small", kind="implement", frontier=0.1, yagni=0.1, tests=0.1,
         ambiguous=0.1, domain="code", skill="none"):
    def ch(q, v):
        opts = GATE_QUESTIONS[q].options
        return Answer(v, {o: (1.0 if o == v else 0.0) for o in opts}, 1.0, "test")

    def nl(p):
        return Answer(p, {"yes": p, "no": 1 - p}, max(p, 1 - p), "test")

    return {"kind": ch("kind", kind), "domain": ch("domain", domain),
            "complexity": ch("complexity", complexity), "needs_frontier": nl(frontier),
            "yagni": nl(yagni), "needs_tests": nl(tests), "ambiguous": nl(ambiguous),
            "skill_primary": ch("skill_primary", skill)}


def cat(*tiers):
    return Catalog([Model(t, f"{t}-model", "test", t, False, "test") for t in tiers])


CFG = RouterConfig()


def test_trivial_goes_cheap_and_no_skeptic():
    r = route(gate("trivial"), cat("cheap", "mid", "frontier"), CFG)
    assert r.driver.tier == "cheap"
    assert "skeptic" not in [s.role for s in r.specialists]


def test_feature_goes_mid_with_cheaper_skeptic():
    r = route(gate("feature"), cat("cheap", "mid", "frontier"), CFG)
    assert r.driver.tier == "mid"
    sk = [s for s in r.specialists if s.role == "skeptic"][0]
    assert TIER_ORDER.index(sk.tier) <= TIER_ORDER.index(r.driver.tier)
    assert sk.tier == "cheap"


def test_driver_never_frontier_even_at_ultracode():
    r = route(gate("ultracode", frontier=0.95), cat("cheap", "mid", "frontier"), CFG)
    assert r.driver.tier != "frontier"
    assert any(s.role == "frontier-slice" and s.tier == "frontier" for s in r.specialists)


def test_no_frontier_in_catalog_still_routes():
    r = route(gate("ultracode", frontier=0.95), cat("cheap", "mid"), CFG)
    assert r.driver.tier == "mid"
    assert all(s.tier in ("cheap", "mid") for s in r.specialists)
    assert not any(s.role == "frontier-slice" for s in r.specialists)
    assert any("frontier" in why for why in r.reasons)


def test_only_mid_present_falls_back():
    r = route(gate("trivial"), cat("mid"), CFG)
    assert r.driver.tier == "mid"


def test_frontier_slice_requires_threshold():
    r = route(gate("deep", frontier=0.2), cat("cheap", "mid", "frontier"), CFG)
    assert not any(s.role == "frontier-slice" for s in r.specialists)


def test_specialists_and_skills():
    r = route(gate("feature", kind="implement", tests=0.9, yagni=0.9), cat("cheap", "mid"), CFG)
    roles = [s.role for s in r.specialists]
    assert "tester" in roles
    assert "ponytail" in r.skills and "caveman" in r.skills
    r2 = route(gate("small", kind="research", domain="research"), cat("cheap", "mid"), CFG)
    assert "researcher" in [s.role for s in r2.specialists]
    r3 = route(gate("small", kind="ship"), cat("cheap", "mid"), CFG)
    assert "bragger" in [s.role for s in r3.specialists] and "brag" in r3.skills


def test_clarify_first_on_ambiguity():
    assert route(gate(ambiguous=0.9), cat("cheap"), CFG).clarify_first
    assert not route(gate(ambiguous=0.1), cat("cheap"), CFG).clarify_first


def test_end_to_end_deterministic_with_default_catalog():
    g = HeuristicSystemOne().decide("deadlock under load, find the invariant", GATE_QUESTIONS)
    a = route(g, load_catalog(), CFG)
    b = route(g, load_catalog(), CFG)
    assert a == b


def test_default_catalog_marks_unverified():
    c = load_catalog()
    assert {m.tier for m in c.models} >= {"cheap", "mid"}
    assert all(m.verified is False for m in c.models)

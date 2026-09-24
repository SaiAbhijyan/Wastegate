from wastegate.compose import compose
from wastegate.router import Expert, Route
from wastegate.skills.registry import load_builtin


def _route(skills):
    return Route(driver=Expert("driver", "cheap", "m", tuple(skills), 4000),
                 specialists=(), skills=tuple(skills), clarify_first=False, reasons=())


def _marker(skill):
    # first non-empty body line is unique per builtin skill
    return next(l for l in skill.body.splitlines() if l.strip())


def test_only_selected_bodies():
    reg = load_builtin()
    c = compose(_route(["karpathy", "caveman"]), "fix it", reg)
    assert _marker(reg["karpathy"]) in c.system and _marker(reg["caveman"]) in c.system
    for other in set(reg) - {"karpathy", "caveman"}:
        assert _marker(reg[other]) not in c.system, other
    assert c.user == "fix it"
    assert c.included == ["karpathy", "caveman"]


def test_budget_drops_and_reports():
    reg = load_builtin()
    c = compose(_route(list(reg)), "x", reg, budget_bytes=len(reg["ecc"].body.encode()) + 400)
    assert c.dropped and len(c.system.encode()) <= len(reg["ecc"].body.encode()) + 400


def test_quarantined_never_composed():
    import dataclasses
    reg = load_builtin()
    reg["karpathy"] = dataclasses.replace(reg["karpathy"], quarantined=True)
    c = compose(_route(["karpathy"]), "x", reg)
    assert _marker(reg["karpathy"]) not in c.system
    assert "karpathy" in c.dropped

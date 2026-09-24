from wastegate.catalog import Catalog, Model
from wastegate.escalate import escalate_slice
from wastegate.router import Expert, Route


def cat(*tiers):
    return Catalog([Model(t, f"{t}-model", "test", t, False, "test") for t in tiers])


def rt(frontier_slice: bool):
    specs = (Expert("frontier-slice", "frontier", "frontier-model", ("fable-mode",), 8000),) if frontier_slice else ()
    return Route(Expert("driver", "mid", "mid-model", (), 16000), specs, (), False, ())


FINDINGS = ["tiny_pkg/__init__.py: add() ignores floats", "general: style nit"]


def test_nothing_unresolved():
    s, why = escalate_slice([], rt(True), cat("cheap", "mid", "frontier"))
    assert s is None and "nothing unresolved" in why


def test_no_frontier_in_catalog():
    s, why = escalate_slice(FINDINGS, rt(True), cat("cheap", "mid"))
    assert s is None and "no frontier" in why


def test_route_without_frontier_slice():
    s, why = escalate_slice(FINDINGS, rt(False), cat("cheap", "mid", "frontier"))
    assert s is None and "no frontier" in why


def test_slice_contains_only_unresolved_and_named_files():
    s, why = escalate_slice(FINDINGS, rt(True), cat("cheap", "mid", "frontier"))
    assert s is not None
    assert s.model_id == "frontier-model"
    assert s.findings == tuple(FINDINGS)
    assert s.files == ("tiny_pkg/__init__.py",)
    assert s.budget_tokens == 8000

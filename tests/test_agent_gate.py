"""Agent gate extras: tool_loop (noul) + model_pick (choice over <=20 shortlisted live ids)."""
import pytest

from wastegate.catalog import Catalog, Model, load_catalog, mock_catalog
from wastegate.providers.live import live_catalog
from wastegate.router import RouterConfig
from wastegate.systemone import jev
from wastegate.systemone.agent_gate import AGENT_TOOLS, TOOL_LOOP, agent_catalog, agent_plan, model_pick_question
from wastegate.systemone.base import GATE_QUESTIONS
from wastegate.systemone.heuristic import HeuristicSystemOne

H = HeuristicSystemOne()


def plan(prompt, catalog, **kw):
    return agent_plan(prompt, H, catalog, RouterConfig(), **kw)


def test_locked_base_questions_unchanged():
    assert list(GATE_QUESTIONS) == ["kind", "domain", "complexity", "needs_frontier", "yagni", "needs_tests",
                                    "ambiguous", "skill_primary"]
    assert TOOL_LOOP.type == "noul"


def test_groq_only_picks_groq(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gk-1")
    cat = agent_catalog(live_catalog(load_catalog()))
    p = plan("fix the off-by-one in sliding_windows", cat)
    groq_ids = {m.id for m in load_catalog().models if m.provider == "groq"}
    assert p.model_id in groq_ids
    assert set(p.answers["model_pick"]["distribution"]) <= groq_ids
    assert 0.0 <= p.answers["tool_loop"]["value"] <= 1.0


def test_openrouter_only_free_ids_and_no_gemini(monkeypatch):
    for v in ("OPENROUTER_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.setenv(v, "k")
    cat = agent_catalog(live_catalog(load_catalog()))
    assert {m.provider for m in cat.models} == {"openrouter"}
    assert all(m.id.endswith(":free") for m in cat.models)


def test_model_pick_shortlisted_to_20():
    many = Catalog([Model("mid", f"groq-m{i}", "groq", f"m{i}", False, "t") for i in range(40)])
    q = model_pick_question([m.id for m in many.models], "use groq-m33 please")
    assert len(q.options) == 20 and "groq-m33" in q.options


def test_tools_and_steps_by_kind():
    p = plan("fix the off-by-one in sliding_windows", mock_catalog())
    assert p.tools == AGENT_TOOLS and p.max_steps == 8 and p.harness is True
    q = plan("explain how git rebase works", mock_catalog())
    assert "edit" not in q.tools and "pytest" not in q.tools and q.harness is False
    assert plan("fix it", mock_catalog(), max_steps=3).max_steps == 3


def test_jev_request_shape_for_agent_questions():
    qs = {"tool_loop": TOOL_LOOP, "model_pick": model_pick_question(["a", "b", "c"], "x")}
    req = jev.build_request("fix the bug", qs)
    assert req["questions"]["tool_loop"]["type"] == "noul"
    assert set(req["questions"]["model_pick"]["criteria"]) == {"a", "b", "c"}


def test_empty_agent_catalog_raises(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    from wastegate.providers.base import LiveDisabled
    with pytest.raises(LiveDisabled, match="loop-eligible"):
        agent_catalog(live_catalog(load_catalog()))

"""Live agent loop must fit Groq: visible HTTP errors, capped tokens, no full-harness stuffing. No sockets."""
import io
import json
import shutil
import urllib.error

import pytest
from typer.testing import CliRunner

from wastegate.agent import build_system, run_agent
from wastegate.catalog import Catalog, Model, load_catalog
from wastegate.cli import app
from wastegate.pipeline import plan_turn
from wastegate.providers import http
from wastegate.providers.http import ProviderHTTPError
from wastegate.providers.live import live_catalog, live_providers
from wastegate.router import RouterConfig
from wastegate.skills.registry import load_builtin
from wastegate.systemone.agent_gate import agent_catalog, agent_plan
from wastegate.systemone.heuristic import HeuristicSystemOne

from conftest import FIXTURES

PROMPT = "fix the off-by-one in sliding_windows"
PLANTED = "gsk_" + "Q1w2E3r4T5y6U7i8O9p0A1s2D3f4G5h6"
BODY400 = json.dumps({"error": {"message": "max_tokens too large", "echo": PLANTED}})
FIX = ("<<<REPLACE windows/__init__.py\n    return [xs[i:i + k] for i in range(len(xs) - k)]\n<<<WITH\n"
       "    return [xs[i:i + k] for i in range(len(xs) - k + 1)]\n<<<END\n")


@pytest.fixture
def obo(tmp_path):
    dst = tmp_path / "off_by_one"
    shutil.copytree(FIXTURES / "off_by_one", dst)
    return dst


def test_post_json_surfaces_status_and_redacted_body(monkeypatch):
    def boom(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, io.BytesIO(BODY400.encode() + b"x" * 3000))
    monkeypatch.setattr(http.urllib.request, "urlopen", boom)
    with pytest.raises(ProviderHTTPError) as ei:
        http.post_json("https://api.groq.com/openai/v1/chat/completions", {"Authorization": "Bearer k"}, {})
    e = ei.value
    assert e.status == 400 and "max_tokens too large" in e.body and PLANTED not in e.body
    assert len(e.body) <= 1000 and str(e).startswith("HTTP 400: ")
    assert isinstance(e, urllib.error.URLError)


def test_cli_live_loop_400_is_printed_and_logged(obo, tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gk-fake-key-000111")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)  # let the adapter reach (fake) post_json

    def fake_post(url, headers, body):
        raise ProviderHTTPError(400, BODY400)
    monkeypatch.setattr(http, "post_json", fake_post)
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(app, ["ask", "--live", "--repo", str(obo), PROMPT])
    assert r.exit_code == 1, r.output
    assert "HTTP 400" in r.output and "max_tokens too large" in r.output
    assert PLANTED not in r.output and "gk-fake-key-000111" not in r.output
    rec = json.loads((tmp_path / ".wastegate/logs/turns.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert rec["provider_error"]["status"] == 400 and "max_tokens too large" in rec["provider_error"]["body"]
    assert "len(xs) - k)" in (obo / "windows/__init__.py").read_text(encoding="utf-8")  # unedited
    reports = list((tmp_path / "results").glob("*-live-agent*.md"))
    assert len(reports) == 1
    text = reports[0].read_text(encoding="utf-8")
    assert "max_tokens too large" in text and PLANTED not in text and "wiring check only, not a benchmark" in text


def _groq_setup(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gk-fake-key-000111")
    return agent_catalog(live_catalog(load_catalog()))


def test_first_pick_is_cheapest_groq(monkeypatch):
    cat = _groq_setup(monkeypatch)
    ap = agent_plan("implement a deep multi-tenant billing refactor across services", HeuristicSystemOne(), cat,
                    RouterConfig())
    assert ap.model_id == "openai/gpt-oss-20b"


def test_live_loop_caps_tokens_strips_harness_and_passes(obo, monkeypatch):
    cat = _groq_setup(monkeypatch)
    sent = []
    replies = ["TOOL grep range\\(len\n", FIX, "TOOL pytest\n", "<<<DONE\nfixed\n>>>\n"]

    def transport(url, headers, body):
        sent.append(body)
        return {"choices": [{"message": {"content": replies[len(sent) - 1]}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5}}

    s1 = HeuristicSystemOne()
    plan = plan_turn(PROMPT, s1, cat, RouterConfig(), load_builtin())
    ap = agent_plan(PROMPT, s1, cat, RouterConfig(), gate=plan.gate)
    system = build_system(plan.composed.system, ap, obo)
    assert ap.harness_mode == "code-only" and "The 6 laws" not in system and "VERIFICATION" in system
    res = run_agent(PROMPT, obo, ap, live_providers(cat, True, transport=transport), system, budget=32_000,
                    tier="cheap")
    assert res.verification["status"] == "PASS"
    assert all(b["max_completion_tokens"] <= 4096 for b in sent) and len(sent) == 4
    assert all("The 6 laws" not in b["messages"][0]["content"] for b in sent)


def test_mid_cap_8192(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gk-fake-key-000111")
    cat = live_catalog(load_catalog())
    sent = []
    get = live_providers(cat, True, transport=lambda u, h, b: sent.append(b) or {"choices": [{"message": {"content": "ok"}}]})
    get("driver", "openai/gpt-oss-120b").complete("openai/gpt-oss-120b", "s", [{"role": "user", "content": "x"}], 32_000)
    assert sent[0]["max_completion_tokens"] == 8192


def test_verified_catalog_cap_can_be_smaller(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gk-fake-key-000111")
    cat = Catalog([Model("cheap", "openai/gpt-oss-20b", "groq", "x", True, "t", max_output_tokens=1000),
                   Model("mid", "openai/gpt-oss-120b", "groq", "y", False, "t", max_output_tokens=10)])
    sent = []
    get = live_providers(cat, True, transport=lambda u, h, b: sent.append(b) or {"choices": [{"message": {"content": "ok"}}]})
    get("a", "openai/gpt-oss-20b").complete("openai/gpt-oss-20b", "s", [], 4000)
    get("a", "openai/gpt-oss-120b").complete("openai/gpt-oss-120b", "s", [], 9000)
    assert sent[0]["max_completion_tokens"] == 1000  # verified row: honored
    assert sent[1]["max_completion_tokens"] == 8192  # unverified row: tier cap only


def test_full_harness_when_budget_allows(obo, monkeypatch):
    s1 = HeuristicSystemOne()
    from wastegate.catalog import mock_catalog
    plan = plan_turn(PROMPT, s1, mock_catalog(), RouterConfig(), load_builtin())
    ap = agent_plan(PROMPT, s1, mock_catalog(), RouterConfig(), gate=plan.gate)
    assert "The 6 laws" in build_system(plan.composed.system, ap, obo, max_system_bytes=100_000)
    assert ap.harness_mode == "full"

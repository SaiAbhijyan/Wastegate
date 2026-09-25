"""Phase 2b free-provider hardening. No socket (conftest guard); keys + ALLOW_PAID cleared by conftest."""
import hashlib
import json
import shutil

import pytest
from typer.testing import CliRunner

from wastegate.catalog import load_catalog
from wastegate.cli import app
from wastegate.log import TurnLogger
from wastegate.pipeline import run_ask
from wastegate.providers.base import LiveDisabled
from wastegate.providers.live import live_catalog, live_providers
from wastegate.providers.mock import MockProvider
from wastegate.router import RouterConfig, route
from wastegate.skills.registry import load_builtin
from wastegate.smoke import write_smoke_report
from wastegate.systemone.base import GATE_QUESTIONS
from wastegate.systemone.heuristic import HeuristicSystemOne

from conftest import FIXTURES

PROMPT = "fix the bug in tiny_pkg and add a regression test"
FREE_KEYS = ["GROQ_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY"]
runner = CliRunner()


@pytest.fixture
def repo(tmp_path):
    dst = tmp_path / "tiny_pkg"
    shutil.copytree(FIXTURES / "tiny_pkg", dst)
    return dst


def snapshot(d):
    return {str(p.relative_to(d)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(d.rglob("*")) if p.is_file()}


# B1: paid gate enforced where adapters are created, not only in live_catalog
def test_paid_openrouter_id_refused_before_http_even_with_unfiltered_catalog(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key-123456")
    calls = []
    get = live_providers(load_catalog(), True, transport=lambda *a: calls.append(a) or {})
    with pytest.raises(LiveDisabled, match="paid model"):
        get("driver", "openai/gpt-5.2")
    assert calls == []
    assert get("driver", "qwen/qwen3.8-27b:free") is not None


@pytest.mark.parametrize("how", ["arg", "env"])
def test_paid_openrouter_id_allowed_when_opted_in(monkeypatch, how):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key-123456")
    if how == "env":
        monkeypatch.setenv("ALLOW_PAID", "1")
    get = live_providers(load_catalog(), True, transport=lambda *a: {}, allow_paid=(how == "arg"))
    assert get("driver", "openai/gpt-5.2") is not None


# B2: stdout transcript redacted
def test_cli_transcript_redacts_planted_key(repo, tmp_path, monkeypatch):
    secret = "gsk-planted-secret-987654"
    monkeypatch.setenv("GROQ_API_KEY", secret)
    replies = tmp_path / "replies"
    shutil.copytree(FIXTURES / "replies" / "fix_add", replies)
    (replies / "skeptic.md").write_text(f"VERDICT: reject\n- tiny_pkg/__init__.py: leaked {secret}\n")
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["ask", "--oneshot", "--mock", "--replies", str(replies), "--repo", str(repo), PROMPT])
    assert r.exit_code == 0, r.output
    assert "[REDACTED]" in r.output and secret not in r.output
    assert secret not in (tmp_path / ".wastegate/logs/turns.jsonl").read_text()


# C1: driver resolves, tester LiveDisabled -> nothing written, driver never called
def test_tester_live_disabled_aborts_before_any_write(repo):
    before = snapshot(repo)
    driver_calls = []

    class Driver:
        name = "fake"

        def complete(self, *a):
            driver_calls.append(a)
            raise AssertionError("driver must not be called")

    def providers(role, model_id=None):
        if role == "tester":
            raise LiveDisabled("no key or --live not set")
        if role == "driver":
            return Driver()
        return MockProvider(FIXTURES / "replies" / "fix_add", role)

    with pytest.raises(LiveDisabled):
        run_ask(PROMPT, repo, HeuristicSystemOne(), load_catalog(), RouterConfig(), load_builtin(),
                mode="live", providers=providers)
    assert driver_calls == [] and snapshot(repo) == before


# C2: Groq key only -> every routed model is a groq id (also with ALLOW_PAID=1)
@pytest.mark.parametrize("allow_paid_env", [False, True])
def test_groq_only_routes_only_groq_ids(monkeypatch, allow_paid_env):
    monkeypatch.setenv("GROQ_API_KEY", "gk-123456")
    if allow_paid_env:
        monkeypatch.setenv("ALLOW_PAID", "1")
    full = load_catalog()
    groq_ids = {m.id for m in full.models if m.provider == "groq"}
    cat = live_catalog(full)
    assert {m.id for m in cat.models} == groq_ids
    for p in ("rename foo to bar in one file", PROMPT, "deadlock under load, find the invariant"):
        r = route(HeuristicSystemOne().decide(p, GATE_QUESTIONS), cat, RouterConfig())
        assert {e.model for e in (r.driver, *r.specialists)} <= groq_ids


# C4: each free key absent from JSONL and smoke markdown when planted in prompt and usage_raw
@pytest.mark.parametrize("var", FREE_KEYS)
def test_free_keys_redacted_in_jsonl_and_smoke(tmp_path, monkeypatch, var):
    secret = f"planted-{var.lower()}-value"
    monkeypatch.setenv(var, secret)
    rec = {"prompt": f"please use {secret}", "tests": {"before": 1, "after": 0},
           "calls": [{"role": "driver", "tier": "mid", "provider": "groq", "model_id": "m",
                      "tokens_in": 1, "tokens_out": 1, "usd": None, "usage_raw": {"echo": secret}}]}
    TurnLogger(tmp_path / "logs").write(rec)
    md = write_smoke_report(rec, tmp_path / "results", "20260924")
    for text in ((tmp_path / "logs/turns.jsonl").read_text(), md.read_text()):
        assert secret not in text and "[REDACTED]" in text


# C5: --live, no keys, cwd = repo: exit 2, every file unchanged, nothing created
def test_live_no_keys_cwd_repo_unchanged(repo, monkeypatch):
    monkeypatch.chdir(repo)
    before = snapshot(repo)
    r = runner.invoke(app, ["ask", "--oneshot", "--live", PROMPT])
    assert r.exit_code == 2 and "no key or --live not set" in r.output
    assert snapshot(repo) == before
    assert not (repo / ".wastegate").exists() and not (repo / "results").exists()


# C6: all three modes together
def test_three_modes_together_exit_2():
    r = runner.invoke(app, ["ask", "--oneshot", "--dry-run", "--mock", "--live", "--replies", "x", PROMPT])
    assert r.exit_code == 2 and "choose one" in r.output

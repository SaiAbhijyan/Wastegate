"""Free-tier providers behind the one OpenAI-compatible client; paid keys ignored by default.
No socket: conftest guard. Keys and ALLOW_PAID cleared by conftest."""
import shutil

import pytest
from typer.testing import CliRunner

from wastegate.catalog import load_catalog, tomllib
from wastegate.cli import app
from wastegate.log import redact
from wastegate.pipeline import run_ask
from wastegate.providers.base import LiveDisabled
from wastegate.providers.gemini import GeminiProvider
from wastegate.providers.groq import GroqProvider
from wastegate.providers.live import is_paid, live_catalog, live_providers
from wastegate.router import RouterConfig
from wastegate.skills.registry import load_builtin
from wastegate.systemone.heuristic import HeuristicSystemOne

from conftest import FIXTURES, ROOT

PROMPT = "fix the bug in tiny_pkg and add a regression test"
MSGS = [{"role": "user", "content": "hi"}]
OK = {"choices": [{"message": {"content": "ok"}}], "usage": {"prompt_tokens": 5, "completion_tokens": 1}}


def capture():
    seen = {}

    def transport(url, headers, body):
        seen.update(url=url, headers=headers, body=body)
        return OK
    return seen, transport


def only(provider):
    return {m.provider for m in live_catalog(load_catalog()).models} == {provider}


def test_groq_key_selects_groq_host(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gk-1")
    assert only("groq")
    cat = live_catalog(load_catalog())
    seen, t = capture()
    a = live_providers(cat, True, transport=t)("driver", cat.first("mid").id)
    assert isinstance(a, GroqProvider)
    c = a.complete(cat.first("mid").id, "sys", MSGS, 16)
    assert seen["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer gk-1"
    assert seen["body"]["max_completion_tokens"] == 16
    assert (c.usage.input_tokens, c.usage.output_tokens) == (5, 1)


@pytest.mark.parametrize("var", ["GEMINI_API_KEY", "GOOGLE_API_KEY"])
def test_gemini_key_selects_gemini_host(monkeypatch, var):
    monkeypatch.setenv(var, "gm-1")
    assert only("gemini")
    cat = live_catalog(load_catalog())
    seen, t = capture()
    a = live_providers(cat, True, transport=t)("driver", cat.first("cheap").id)
    assert isinstance(a, GeminiProvider)
    a.complete(cat.first("cheap").id, "sys", MSGS, 16)
    assert seen["url"] == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer gm-1"


def test_gemini_key_precedence(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gm-first")
    monkeypatch.setenv("GOOGLE_API_KEY", "gg-second")
    seen, t = capture()
    GeminiProvider(allow_network=True, transport=t).complete("gemini-3.8-flash", "s", MSGS, 8)
    assert seen["headers"]["Authorization"] == "Bearer gm-first"


def test_openrouter_key_only_free_ids(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-1")
    cat = live_catalog(load_catalog())
    assert cat.models and all(m.provider == "openrouter" and m.id.endswith(":free") for m in cat.models)


@pytest.mark.parametrize("how", ["flag", "env"])
def test_openrouter_paid_ids_need_allow_paid(monkeypatch, how):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-1")
    if how == "env":
        monkeypatch.setenv("ALLOW_PAID", "1")
    cat = live_catalog(load_catalog(), allow_paid=(how == "flag"))
    ids = {m.id for m in cat.models}
    assert any(not i.endswith(":free") for i in ids) and any(i.endswith(":free") for i in ids)


@pytest.mark.parametrize("var", ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"])
def test_paid_key_alone_is_ignored(monkeypatch, var):
    monkeypatch.setenv(var, "paid-1")
    with pytest.raises(LiveDisabled, match="only paid"):
        live_catalog(load_catalog())


def test_allow_paid_other_values_do_not_count(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "paid-1")
    monkeypatch.setenv("ALLOW_PAID", "true")
    with pytest.raises(LiveDisabled, match="only paid"):
        live_catalog(load_catalog())


def test_all_keys_no_allow_paid_uses_no_paid_rows(monkeypatch):
    for v in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.setenv(v, "k")
    cat = live_catalog(load_catalog())
    assert not any(is_paid(m) for m in cat.models)
    assert {m.provider for m in cat.models} == {"groq", "gemini", "openrouter"}


def test_cli_paid_key_only_exits_2_no_writes(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "paid-1")
    repo = tmp_path / "tiny_pkg"
    shutil.copytree(FIXTURES / "tiny_pkg", repo)
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(app, ["ask", "--live", "--repo", str(repo), PROMPT])
    assert r.exit_code == 2 and "only paid" in r.output
    assert (repo / "tiny_pkg/__init__.py").read_text().strip().endswith("a - b")
    assert not (tmp_path / ".wastegate").exists()


def test_cli_allow_paid_flag_reaches_pytest_guard(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "paid-1")
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(app, ["ask", "--live", "--allow-paid", PROMPT])
    assert r.exit_code == 2 and "network disabled under pytest" in r.output


def test_groq_pipeline_fake_transport(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gk-1")
    repo = tmp_path / "tiny_pkg"
    shutil.copytree(FIXTURES / "tiny_pkg", repo)
    driver_text = (FIXTURES / "replies/fix_add/driver.md").read_text()
    hosts = []

    def transport(url, headers, body):
        hosts.append(url.split("/")[2])
        sys = body["messages"][0]["content"]
        text = driver_text if sys.startswith("Role: driver") else (
            "TESTER: pass" if "tester" in sys else "VERDICT: approve")
        return {"choices": [{"message": {"content": text}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3}}

    cat = live_catalog(load_catalog())
    rec = run_ask(PROMPT, repo, HeuristicSystemOne(), cat, RouterConfig(), load_builtin(),
                  mode="live", providers=live_providers(cat, True, transport=transport)).record
    assert set(hosts) == {"api.groq.com"}
    assert {c["provider"] for c in rec["calls"]} == {"groq"}
    n = len(rec["calls"])
    assert rec["tokens_in"] == 7 * n and rec["tokens_out"] == 3 * n and rec["usd"] is None
    assert rec["tests"] == {"before": 1, "after": 0}


def test_catalog_free_rows_and_no_prices():
    c = load_catalog()
    provs = {m.provider for m in c.models}
    assert {"groq", "gemini", "openrouter"} <= provs
    assert any(m.provider == "openrouter" and m.id.endswith(":free") for m in c.models)
    assert all(m.verified is False for m in c.models)
    rows = tomllib.loads((ROOT / "src/wastegate/data/models.toml").read_text())["model"]
    assert not [k for r in rows for k in r if "price" in k.lower() or "usd" in k.lower()]


@pytest.mark.parametrize("var", ["GROQ_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "GITHUB_TOKEN"])
def test_new_key_values_redacted(monkeypatch, var):
    monkeypatch.setenv(var, "plain-free-key-42")
    assert "plain-free-key-42" not in redact("x plain-free-key-42 y")

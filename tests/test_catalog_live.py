"""Catalog rows per provider; --live picks the provider whose key is set. No socket (conftest guard)."""
import shutil

import pytest
from typer.testing import CliRunner

from wastegate.catalog import load_catalog
from wastegate.cli import app
from wastegate.pipeline import run_ask
from wastegate.providers.base import LiveDisabled
from wastegate.providers.live import live_catalog, live_providers
from wastegate.providers.openai import OpenAIProvider
from wastegate.router import RouterConfig
from wastegate.skills.registry import load_builtin
from wastegate.systemone.heuristic import HeuristicSystemOne

from conftest import FIXTURES, ROOT

PROMPT = "fix the bug in tiny_pkg and add a regression test"


def test_catalog_has_openai_and_openrouter_unverified_no_prices():
    c = load_catalog()
    provs = {m.provider for m in c.models}
    assert {"anthropic", "openai", "openrouter"} <= provs
    assert all(m.verified is False for m in c.models)
    from wastegate.catalog import tomllib
    rows = tomllib.loads((ROOT / "src/wastegate/data/models.toml").read_text())["model"]
    assert not [k for r in rows for k in r if "price" in k.lower() or "usd" in k.lower()]


def test_no_keys_means_no_live_catalog():
    with pytest.raises(LiveDisabled, match="no key or --live not set"):
        live_catalog(load_catalog())


def test_openai_key_only_selects_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k-openai-only")
    monkeypatch.setenv("ALLOW_PAID", "1")  # openai is paid: ignored unless allowed
    cat = live_catalog(load_catalog(), allow_paid=True)
    assert {m.provider for m in cat.models} == {"openai"}
    get = live_providers(cat, allow_network=True, transport=lambda *a: {})
    model = cat.first("mid")
    assert isinstance(get("driver", model.id), OpenAIProvider)


def test_live_pipeline_with_fake_transport_uses_openai(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k-openai-only")
    monkeypatch.setenv("ALLOW_PAID", "1")  # openai is paid: ignored unless allowed
    repo = tmp_path / "tiny_pkg"
    shutil.copytree(FIXTURES / "tiny_pkg", repo)
    driver_text = (FIXTURES / "replies/fix_add/driver.md").read_text()
    seen = []

    def transport(url, headers, body):
        seen.append(url)
        role = body["messages"][0]["content"]
        text = driver_text if role.startswith("Role: driver") else (
            "TESTER: pass" if "tester" in role else "VERDICT: approve")
        return {"choices": [{"message": {"content": text}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 2, "total_tokens": 13}}

    cat = live_catalog(load_catalog(), allow_paid=True)
    res = run_ask(PROMPT, repo, HeuristicSystemOne(), cat, RouterConfig(), load_builtin(),
                  mode="live", providers=live_providers(cat, True, transport=transport))
    rec = res.record
    assert seen and all(u == "https://api.openai.com/v1/chat/completions" for u in seen)
    assert {c["provider"] for c in rec["calls"]} == {"openai"}
    assert all(c["usage_raw"] == {"prompt_tokens": 11, "completion_tokens": 2, "total_tokens": 13}
               for c in rec["calls"])
    n = len(rec["calls"])
    assert rec["tokens_in"] == 11 * n and rec["tokens_out"] == 2 * n and rec["usd"] is None
    assert rec["tests"] == {"before": 1, "after": 0}


def test_cli_live_openai_key_under_pytest_exits_2_without_writes(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k-openai-only")
    monkeypatch.setenv("ALLOW_PAID", "1")  # openai is paid: ignored unless allowed
    repo = tmp_path / "tiny_pkg"
    shutil.copytree(FIXTURES / "tiny_pkg", repo)
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(app, ["ask", "--live", "--repo", str(repo), PROMPT])
    assert r.exit_code == 2 and "network disabled under pytest" in r.output
    assert (repo / "tiny_pkg/__init__.py").read_text().strip().endswith("a - b")
    assert not (tmp_path / ".wastegate").exists() and not (tmp_path / "results").exists()

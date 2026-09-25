import pytest
from typer.testing import CliRunner

from wastegate.catalog import load_catalog
from wastegate.cli import app
from wastegate.providers.base import LiveDisabled
from wastegate.providers.live import is_paid, live_catalog, live_providers
from wastegate.providers.ollama import OllamaProvider

MSGS = [{"role": "user", "content": "hi"}]


def test_local_catalog_is_only_ollama():
    cat = live_catalog(load_catalog(), local=True)
    assert cat.models and {m.provider for m in cat.models} == {"ollama"}
    assert not any(is_paid(m) for m in cat.models)


def test_ollama_excluded_without_local(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gk-1")
    assert "ollama" not in {m.provider for m in live_catalog(load_catalog()).models}


def test_local_ignores_cloud_keys(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gk-1")
    assert {m.provider for m in live_catalog(load_catalog(), local=True).models} == {"ollama"}


def test_fake_transport_hits_localhost_without_real_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gk-real-should-not-leak")
    seen = {}

    def t(url, headers, body):
        seen.update(url=url, headers=headers, body=body)
        return {"choices": [{"message": {"content": "ok"}}]}

    cat = live_catalog(load_catalog(), local=True)
    mid = cat.first("local").id
    a = live_providers(cat, True, transport=t)("driver", mid)
    c = a.complete(mid, "sys", MSGS, 32)
    assert seen["url"] == "http://127.0.0.1:11434/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer ollama"
    assert "gk-real-should-not-leak" not in str(seen)
    assert c.text == "ok" and c.usage is None  # no usage in reply -> null, never estimated


def test_probe_failure_is_live_disabled():
    def down():
        raise OSError("connection refused")
    with pytest.raises(LiveDisabled, match="ollama not reachable"):
        OllamaProvider(allow_network=True, probe=down).check()


def test_probe_ok_passes():
    assert OllamaProvider(allow_network=True, probe=lambda: None).check()


def test_without_live_disabled():
    with pytest.raises(LiveDisabled):
        OllamaProvider(allow_network=False, probe=lambda: None).check()


def test_under_pytest_without_fakes_is_dark():
    with pytest.raises(LiveDisabled, match="pytest"):
        OllamaProvider(allow_network=True).check()


def test_cli_local_exits_2_before_writes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(app, ["ask", "--live", "--local", "fix the bug in tiny_pkg"])
    assert r.exit_code == 2
    assert not (tmp_path / ".wastegate").exists()


def test_local_requires_live():
    r = CliRunner().invoke(app, ["ask", "--dry-run", "--local", "x"])
    assert r.exit_code == 2 and "--local" in r.output


def test_default_views_exclude_local_rows(tmp_path, monkeypatch):
    import json
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(app, ["route", "--json", "--no-log", "fix the bug in tiny_pkg and add a regression test"])
    route = json.loads(r.output)["route"]
    tiers = [route["driver"]["tier"]] + [s["tier"] for s in route["specialists"]]
    assert "local" not in tiers

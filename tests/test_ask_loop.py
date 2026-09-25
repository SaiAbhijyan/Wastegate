"""wg ask --repo uses the agent loop by default; --oneshot keeps the old path."""
import json
import shutil

import pytest
from typer.testing import CliRunner

from wastegate.cli import app

from conftest import FIXTURES

runner = CliRunner()
PROMPT = "fix the off-by-one in sliding_windows"
FINAL = "Fixed the off-by-one: range now goes to len(xs) - k + 1. Tests pass after the edit."


@pytest.fixture
def obo(tmp_path):
    dst = tmp_path / "off_by_one"
    shutil.copytree(FIXTURES / "off_by_one", dst)
    return dst


def last(tmp_path):
    return json.loads((tmp_path / ".wastegate/logs/turns.jsonl").read_text(encoding="utf-8").splitlines()[-1])


@pytest.mark.parametrize("cmd", ["ask", "run"])
def test_ask_repo_defaults_to_loop(obo, tmp_path, monkeypatch, cmd):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, [cmd, "--mock", "--replies", str(FIXTURES / "replies/agent_obo"), "--repo", str(obo), PROMPT])
    assert r.exit_code == 0, r.output
    out = r.output
    assert "[step 2] edit windows/__init__.py" in out and "VERIFICATION: PASS" in out
    assert "Checks: python -m pytest -q → exit 0" in out
    assert out.index("[step 3] pytest") < out.index("--- driver reply ---") < out.index(FINAL) \
        < out.index("gate:") < out.index("VERIFICATION: PASS")
    rec = last(tmp_path)
    assert rec["mode"] == "ask-agent-mock" and rec["driver_text"].strip() == FINAL
    assert rec["verification"]["status"] == "PASS"


def test_ask_oneshot_keeps_old_path(obo, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["ask", "--mock", "--replies", str(FIXTURES / "replies/off_by_one"), "--repo", str(obo),
                            "--oneshot", PROMPT])
    assert r.exit_code == 0 and "tests: before=1 after=0" in r.output and "VERIFICATION" not in r.output


def test_ask_without_repo_is_old_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["ask", "--dry-run", PROMPT])
    assert r.exit_code == 0 and "agent:" not in r.output and "no generation" in r.output


def test_ask_loop_dry_run(obo, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["ask", "--dry-run", "--repo", str(obo), PROMPT])
    assert r.exit_code == 0 and "agent: model=" in r.output and "no generation" in r.output


def test_ask_loop_max_steps(obo, tmp_path, monkeypatch):
    d = tmp_path / "rep"
    d.mkdir()
    for i in range(1, 6):
        (d / f"agent_{i}.md").write_text("TOOL read windows/__init__.py\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["ask", "--mock", "--replies", str(d), "--repo", str(obo), "--max-steps", "2", PROMPT])
    rec = last(tmp_path)
    assert len(rec["tool_calls"]) == 2 and rec["stop_reason"] == "max_steps"


def test_ask_loop_live_without_key_exits_2(obo, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["ask", "--live", "--repo", str(obo), PROMPT])
    assert r.exit_code == 2 and not (tmp_path / ".wastegate").exists()

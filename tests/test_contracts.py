"""Tester/skeptic output contracts on reasoning-style replies; budgets; driver test instruction."""
import json
import shutil

import pytest
from typer.testing import CliRunner

from wastegate.catalog import mock_catalog
from wastegate.cli import app
from wastegate.pipeline import (SKEPTIC_SYSTEM, TESTER_SYSTEM, driver_request, parse_skeptic, parse_tester,
                                plan_turn, wants_test)
from wastegate.router import RouterConfig, route
from wastegate.skills.registry import load_builtin
from wastegate.systemone.base import GATE_QUESTIONS
from wastegate.systemone.heuristic import HeuristicSystemOne

from conftest import FIXTURES

PROMPT = "fix the bug in tiny_pkg and add a regression test"
runner = CliRunner()


@pytest.mark.parametrize("text,want", [
    ("VERDICT: approve", ("approve", [])),
    ("**VERDICT: approve**", ("approve", [])),
    ("VERDICT: **reject**\n- a", ("reject", ["a"])),
    ("`VERDICT: reject`\n- a\n- b", ("reject", ["a", "b"])),
    ("thinking\n- stray\nVERDICT: reject\n- real", ("reject", ["real"])),
    ("VERDICT: approve\nVERDICT: reject\n- x", ("approve", ["x"])),  # first matching line wins
    ("verdict: Approve.", ("approve", [])),
])
def test_parse_skeptic_tolerant(text, want):
    assert parse_skeptic(text) == want


@pytest.mark.parametrize("text,want", [
    ("TESTER: pass", ("pass", [])),
    ("TESTER: **fail**\n- t", ("fail", ["t"])),
    ("hmm\n- stray\n**TESTER: pass**\n- ok", ("pass", ["ok"])),
    ("no contract here\n- x", ("invalid", [])),
])
def test_parse_tester_tolerant(text, want):
    assert parse_tester(text) == want


def test_system_contracts_state_first_line_rule():
    assert "TESTER: pass" in TESTER_SYSTEM and "TESTER: fail" in TESTER_SYSTEM and "first line" in TESTER_SYSTEM
    assert "VERDICT: approve" in SKEPTIC_SYSTEM and "VERDICT: reject" in SKEPTIC_SYSTEM and "first line" in SKEPTIC_SYSTEM
    for s in (TESTER_SYSTEM, SKEPTIC_SYSTEM):
        assert "- " in s and "no preamble" in s.lower()


def test_reviewer_budget_from_config():
    g = HeuristicSystemOne().decide(PROMPT, GATE_QUESTIONS)
    r = route(g, mock_catalog(), RouterConfig(reviewer_budget_tokens=12_345))
    budgets = {s.role: s.budget_tokens for s in r.specialists}
    assert budgets["skeptic"] == 12_345 and budgets["tester"] == 12_345
    assert RouterConfig().reviewer_budget_tokens >= 8_000


@pytest.mark.parametrize("p,want", [
    (PROMPT, True), ("add session auth with tests", True), ("write a unit test for parse()", True),
    ("explain how git rebase works", False), ("fix the race in worker.py", False),
])
def test_wants_test(p, want):
    assert wants_test(p) is want


def test_driver_instruction_for_regression_test(tmp_path):
    repo = tmp_path / "tiny_pkg"
    shutil.copytree(FIXTURES / "tiny_pkg", repo)
    plan = plan_turn(PROMPT, HeuristicSystemOne(), mock_catalog(), RouterConfig(), load_builtin())
    system, _ = driver_request(plan, PROMPT, repo)
    assert "add or update a test file" in system and "do not only patch the implementation" in system
    plain = plan_turn("fix the race in worker.py", HeuristicSystemOne(), mock_catalog(), RouterConfig(), load_builtin())
    assert "add or update a test file" not in driver_request(plain, "fix the race in worker.py", repo)[0]


@pytest.fixture
def repo(tmp_path):
    dst = tmp_path / "tiny_pkg"
    shutil.copytree(FIXTURES / "tiny_pkg", dst)
    return dst


def run(replies, repo, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["ask", "--mock", "--replies", str(FIXTURES / "replies" / replies), "--repo", str(repo), PROMPT])
    assert r.exit_code == 0, r.output
    return r, json.loads((tmp_path / ".wastegate/logs/turns.jsonl").read_text().splitlines()[-1])


def test_reasoning_preamble_replies_parse(repo, tmp_path, monkeypatch):
    r, rec = run("reasoning", repo, tmp_path, monkeypatch)
    assert rec["tester"]["status"] == "pass" and rec["tester"]["findings"] == ["tests/test_add.py covers add(2, 3)"]
    assert rec["skeptic"]["verdict"] == "reject" and rec["skeptic"]["findings"] == ["no new regression test was added"]
    assert rec["unresolved"] == ["no new regression test was added"]
    assert rec["tester"]["parse_error"] is None and rec["skeptic"]["parse_error"] is None
    assert rec["test_file_changed"] is False


def test_missing_lines_skip_tester_reject_skeptic(repo, tmp_path, monkeypatch):
    r, rec = run("no_verdict", repo, tmp_path, monkeypatch)
    assert rec["tester"]["status"] == "skipped" and "no TESTER" in rec["tester"]["parse_error"]
    assert rec["skeptic"]["verdict"] == "reject" and "no VERDICT" in rec["skeptic"]["parse_error"]
    assert any("skeptic reply unparseable" in u for u in rec["unresolved"])
    assert not any("tester" in u for u in rec["unresolved"])
    assert rec["tests"] == {"before": 1, "after": 0}


def test_test_file_changed_detected(repo, tmp_path, monkeypatch):
    d = tmp_path / "replies"
    d.mkdir()
    (d / "driver.md").write_text(
        "<<<REPLACE tiny_pkg/__init__.py\n    return a - b\n<<<WITH\n    return a + b\n<<<END\n"
        "<<<FILE tests/test_regression.py\nfrom tiny_pkg import add\n\n\ndef test_neg():\n    assert add(-1, 1) == 0\n>>>\n")
    (d / "skeptic.md").write_text("VERDICT: approve\n")
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["ask", "--mock", "--replies", str(d), "--repo", str(repo), PROMPT])
    rec = json.loads((tmp_path / ".wastegate/logs/turns.jsonl").read_text().splitlines()[-1])
    assert rec["test_file_changed"] is True and rec["tests"]["after"] == 0

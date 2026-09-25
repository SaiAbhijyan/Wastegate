"""Coding loop: driver follow-up for tests, skeptic scope guard, escalation on mid (no frontier/paid)."""
import json
import shutil

import pytest
from typer.testing import CliRunner

from wastegate.cli import app
from wastegate.pipeline import FOLLOWUP_TEXT, SKEPTIC_SYSTEM, scope_filter

from conftest import FIXTURES

PROMPT = "fix the bug in tiny_pkg and add a regression test"
runner = CliRunner()


@pytest.fixture
def repo(tmp_path):
    dst = tmp_path / "tiny_pkg"
    shutil.copytree(FIXTURES / "tiny_pkg", dst)
    return dst


def ask(replies, repo, tmp_path, monkeypatch, prompt=PROMPT):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["ask", "--oneshot", "--mock", "--replies", str(FIXTURES / "replies" / replies), "--repo", str(repo), prompt])
    assert r.exit_code == 0, r.output
    return r, json.loads((tmp_path / ".wastegate/logs/turns.jsonl").read_text().splitlines()[-1])


# 1) driver follow-up
def test_followup_adds_test_file(repo, tmp_path, monkeypatch):
    r, rec = ask("followup", repo, tmp_path, monkeypatch)
    assert rec["followup"]["ran"] is True
    assert rec["edits"] == ["tiny_pkg/__init__.py", "tests/test_regression.py"]
    assert rec["test_file_changed"] is True and rec["tests"]["after"] == 0
    assert [c["role"] for c in rec["calls"]][:2] == ["driver", "driver_followup"]
    assert (repo / "tests/test_regression.py").exists()
    assert "follow-up" in r.output


def test_followup_text():
    assert FOLLOWUP_TEXT.startswith("add or update a test file only; do not re-litigate the implementation unless tests still fail")


def test_no_followup_when_no_test_asked(repo, tmp_path, monkeypatch):
    _, rec = ask("followup", repo, tmp_path, monkeypatch, prompt="fix the bug in tiny_pkg")
    assert rec["followup"]["ran"] is False and "no test requested" in rec["followup"]["reason"]


def test_no_followup_when_tests_passed_from_start(repo, tmp_path, monkeypatch):
    (repo / "tiny_pkg/__init__.py").write_text("def add(a, b):\n    return a + b\n")
    (FIXTURES / "replies")  # driver REPLACE target missing -> use a FILE-only reply dir
    d = tmp_path / "r"
    d.mkdir()
    (d / "driver.md").write_text("<<<FILE tiny_pkg/__init__.py\ndef add(a, b):\n    return a + b\n>>>\n")
    shutil.copy(FIXTURES / "replies/followup/driver_followup.md", d / "driver_followup.md")
    (d / "skeptic.md").write_text("VERDICT: approve\n")
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["ask", "--oneshot", "--mock", "--replies", str(d), "--repo", str(repo), PROMPT])
    rec = json.loads((tmp_path / ".wastegate/logs/turns.jsonl").read_text().splitlines()[-1])
    assert rec["tests"]["before"] == 0
    assert rec["followup"]["ran"] is False and "passing from the start" in rec["followup"]["reason"]


def test_no_followup_when_driver_already_added_test(repo, tmp_path, monkeypatch):
    d = tmp_path / "r"
    d.mkdir()
    (d / "driver.md").write_text((FIXTURES / "replies/fix_add/driver.md").read_text()
                                 + (FIXTURES / "replies/followup/driver_followup.md").read_text())
    (d / "driver_followup.md").write_text("should not be used\n")
    (d / "skeptic.md").write_text("VERDICT: approve\n")
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["ask", "--oneshot", "--mock", "--replies", str(d), "--repo", str(repo), PROMPT])
    rec = json.loads((tmp_path / ".wastegate/logs/turns.jsonl").read_text().splitlines()[-1])
    assert rec["followup"]["ran"] is False and "already" in rec["followup"]["reason"]
    assert "driver_followup" not in [c["role"] for c in rec["calls"]]


def test_followup_missing_reply_is_skip_not_crash(repo, tmp_path, monkeypatch):
    _, rec = ask("fix_add", repo, tmp_path, monkeypatch)
    assert rec["followup"]["ran"] is False and "driver_followup.md" in rec["followup"]["reason"]


# 2) skeptic scope guard
def test_skeptic_system_scope_rules():
    s = SKEPTIC_SYSTEM.lower()
    assert "only the diff" in s and "test results" in s
    assert "do not invent" in s and "validation" in s and "error handling" in s
    assert "must start with a file path" in s


def test_scope_filter_drops_pathless_and_speculative():
    kept, dropped = scope_filter(
        ["tiny_pkg/__init__.py: add() lacks input validation for non-numeric types",
         "add() should raise a clear error message",
         "tests/test_add.py: no regression test covers the bug"],
        prompt=PROMPT, originals={"tiny_pkg/__init__.py": "def add(a, b):\n    return a - b\n"})
    assert kept == ["tests/test_add.py: no regression test covers the bug"]
    assert len(dropped) == 2


def test_scope_filter_keeps_requested_topic():
    kept, _ = scope_filter(["api.py: missing input validation"], prompt="add input validation to api.py",
                           originals={})
    assert kept == ["api.py: missing input validation"]


def test_hallucinated_validation_reject_is_dismissed(repo, tmp_path, monkeypatch):
    r, rec = ask("scope", repo, tmp_path, monkeypatch)
    sk = rec["skeptic"]
    assert sk["verdict"] == "reject" and sk["effective"] == "dismissed"
    assert sk["kept"] == [] and len(sk["dropped"]) == 3
    assert not any("validation" in u or "docstring" in u for u in rec["unresolved"])


# 3) escalation on mid
def test_reject_escalates_to_mid_and_adds_test(repo, tmp_path, monkeypatch):
    r, rec = ask("escalate_mid", repo, tmp_path, monkeypatch)
    m = rec["mid_escalation"]
    assert m["ran"] is True and m["model_id"] == "mock-mid"
    assert m["edits"] == ["tests/test_add.py"] and m["tests_after"] == 0
    assert rec["escalation"]["slice"] is None  # frontier path unchanged
    assert rec["test_file_changed"] is True and rec["tests"]["after"] == 0
    assert rec["unresolved"] == []
    assert "escalate" in [c["role"] for c in rec["calls"]]
    assert "def test_add_regression_not_subtraction" in (repo / "tests/test_add.py").read_text()


def test_no_mid_means_report_unresolved(repo, tmp_path, monkeypatch):
    # escalate.md missing -> escalation skipped with reason, unresolved reported
    _, rec = ask("reject", repo, tmp_path, monkeypatch)
    assert rec["mid_escalation"]["ran"] is False
    assert rec["unresolved"]


def test_mid_escalation_never_uses_frontier_or_paid(repo, tmp_path, monkeypatch):
    _, rec = ask("escalate_mid", repo, tmp_path, monkeypatch)
    assert all(c["tier"] != "frontier" for c in rec["calls"])

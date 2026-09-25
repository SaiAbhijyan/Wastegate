"""wg run alias, second fixture (off-by-one), chat test-file follow-up."""
import json
import shutil

import pytest
from typer.testing import CliRunner

from wastegate.cli import app

from conftest import FIXTURES

runner = CliRunner()


def last(tmp_path):
    return json.loads((tmp_path / ".wastegate/logs/turns.jsonl").read_text().splitlines()[-1])


# 1) wg run
def test_run_help_mentions_ask():
    r = runner.invoke(app, ["run", "--help"])
    assert r.exit_code == 0 and "ask" in r.output
    for flag in ("--dry-run", "--mock", "--live", "--local", "--allow-paid", "--replies", "--repo"):
        assert flag in r.output, flag


def test_run_behaves_like_ask(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["run", "--dry-run", "fix the race in worker.py"])
    assert r.exit_code == 0 and "generation: (empty, dry-run)" in r.output
    assert runner.invoke(app, ["run", "x"]).exit_code == 2  # same mode rules as ask


# 3) second fixture: real off-by-one, fixed by REPLACE
@pytest.fixture
def obo(tmp_path):
    dst = tmp_path / "off_by_one"
    shutil.copytree(FIXTURES / "off_by_one", dst)
    return dst


def test_off_by_one_fixture_really_fails(obo):
    from wastegate.pipeline import run_tests
    assert run_tests(obo) != 0


def test_mock_ask_fixes_off_by_one(obo, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["ask", "--mock", "--replies", str(FIXTURES / "replies/off_by_one"), "--repo", str(obo),
                            "fix the off-by-one in sliding_windows"])
    assert r.exit_code == 0, r.output
    rec = last(tmp_path)
    assert rec["tests"] == {"before": 1, "after": 0} and rec["edits"] == ["windows/__init__.py"]
    assert "len(xs) - k + 1" in (obo / "windows/__init__.py").read_text()


# 4) chat follow-up (same one-shot rule as ask)
@pytest.fixture
def tiny(tmp_path):
    dst = tmp_path / "tiny_pkg"
    shutil.copytree(FIXTURES / "tiny_pkg", dst)
    return dst


def chat(tmp_path, monkeypatch, repo, line, replies="followup"):
    monkeypatch.chdir(tmp_path)
    return runner.invoke(app, ["chat", "--mock", "--replies", str(FIXTURES / "replies" / replies), "--repo", str(repo), "--oneshot"],
                         input=f"{line}\n/exit\n")


def test_chat_followup_adds_test_file(tiny, tmp_path, monkeypatch):
    r = chat(tmp_path, monkeypatch, tiny, "fix the bug in tiny_pkg and add a regression test")
    assert r.exit_code == 0, r.output
    assert "follow-up (test file)" in r.output
    rec = last(tmp_path)
    assert rec["followup"]["ran"] is True
    assert rec["edits"] == ["tiny_pkg/__init__.py", "tests/test_regression.py"]
    assert rec["tests"]["after"] == 0 and (tiny / "tests/test_regression.py").exists()
    assert [c["role"] for c in rec["calls"]] == ["driver", "driver_followup"]


def test_chat_no_followup_without_test_request(tiny, tmp_path, monkeypatch):
    chat(tmp_path, monkeypatch, tiny, "fix the bug in tiny_pkg")
    rec = last(tmp_path)
    assert rec["followup"]["ran"] is False and "no test requested" in rec["followup"]["reason"]
    assert not (tiny / "tests/test_regression.py").exists()


def test_chat_followup_missing_reply_is_skip(tiny, tmp_path, monkeypatch):
    r = chat(tmp_path, monkeypatch, tiny, "fix the bug in tiny_pkg and add a regression test", replies="fix_add")
    assert r.exit_code == 0
    rec = last(tmp_path)
    assert rec["followup"]["ran"] is False and "driver_followup.md" in rec["followup"]["reason"]
    assert rec["tests"]["after"] == 0

import json
import shutil

import pytest
from typer.testing import CliRunner

from wastegate.cli import app
from wastegate.pipeline import parse_tester

from conftest import FIXTURES

runner = CliRunner()
PROMPT = "fix the bug in tiny_pkg and add a regression test"  # routes with a tester (see test_ask)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    dst = tmp_path / "tiny_pkg"
    shutil.copytree(FIXTURES / "tiny_pkg", dst)
    monkeypatch.chdir(tmp_path)
    return dst


def run(replies, repo):
    return runner.invoke(app, ["ask", "--mock", "--replies", str(FIXTURES / "replies" / replies),
                               "--repo", str(repo), PROMPT])


def last(tmp_path):
    return json.loads((tmp_path / ".wastegate/logs/turns.jsonl").read_text().splitlines()[-1])


def test_parse_tester():
    assert parse_tester("TESTER: pass\n") == ("pass", [])
    assert parse_tester("TESTER: FAIL\n- a.py: x\n- b\n") == ("fail", ["a.py: x", "b"])
    assert parse_tester("looks fine")[0] == "invalid"


def test_tester_missing_is_skip_not_crash(repo, tmp_path):
    r = run("fix_add", repo)
    assert r.exit_code == 0, r.output
    rec = last(tmp_path)
    assert rec["tester"]["status"] == "skipped" and "tester.md" in rec["tester"]["reason"]
    assert rec["unresolved"] == []
    assert "tester" not in {c["role"] for c in rec["calls"]}


def test_tester_fail_goes_to_unresolved(repo, tmp_path):
    r = run("tester_fail", repo)
    assert r.exit_code == 0, r.output
    rec = last(tmp_path)
    assert rec["tester"]["status"] == "fail"
    assert rec["unresolved"] == ["tests/test_add.py: no case for negative numbers"]
    assert rec["skeptic"]["verdict"] == "approve"
    assert rec["escalation"]["slice"] is None and "no frontier" in rec["escalation"]["reason"]
    roles = [c["role"] for c in rec["calls"]]
    assert roles == ["driver", "tester", "skeptic"]  # tester after edits, before skeptic


def test_reject_with_tester_fail(repo, tmp_path):
    r = run("reject", repo)
    assert r.exit_code == 0, r.output
    rec = last(tmp_path)
    assert len(rec["unresolved"]) == 3  # 1 tester + 2 skeptic
    assert rec["escalation"]["slice"] is None

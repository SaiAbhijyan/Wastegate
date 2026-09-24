import json
import shutil

import pytest
from typer.testing import CliRunner

from wastegate.cli import app
from wastegate.catalog import TIERS, load_catalog

from conftest import FIXTURES

runner = CliRunner()
PROMPT = "fix the bug in tiny_pkg and add a regression test"
NULL_FIELDS = ("provider", "model_id", "tokens_in", "tokens_out", "usd")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    dst = tmp_path / "tiny_pkg"
    shutil.copytree(FIXTURES / "tiny_pkg", dst)
    monkeypatch.chdir(tmp_path)
    return dst


def last_log(tmp_path):
    return json.loads((tmp_path / ".wastegate" / "logs" / "turns.jsonl").read_text().splitlines()[-1])


def test_dry_run_no_generation(repo, tmp_path):
    r = runner.invoke(app, ["ask", "--dry-run", "--repo", str(repo), PROMPT])
    assert r.exit_code == 0, r.output
    assert "generation: (empty, dry-run)" in r.output and "karpathy" in r.output
    rec = last_log(tmp_path)
    assert rec["mode"] == "dry-run" and rec["calls"] == []
    for f in NULL_FIELDS:
        assert rec[f] is None, f
    assert (repo / "tiny_pkg" / "__init__.py").read_text().strip().endswith("a - b")


def test_mock_fixes_fixture(repo, tmp_path):
    r = runner.invoke(app, ["ask", "--mock", "--replies", str(FIXTURES / "replies" / "fix_add"),
                            "--repo", str(repo), PROMPT])
    assert r.exit_code == 0, r.output
    rec = last_log(tmp_path)
    assert rec["tests"]["before"] != 0 and rec["tests"]["after"] == 0
    assert rec["edits"] == ["tiny_pkg/__init__.py"]
    roles = {c["role"]: c for c in rec["calls"]}
    assert set(roles) == {"driver", "skeptic"}
    assert TIERS.index(roles["skeptic"]["tier"]) < TIERS.index(roles["driver"]["tier"])
    real_ids = {m.id for m in load_catalog().models}
    for c in rec["calls"]:
        assert c["provider"] == "mock" and c["model_id"].startswith("mock-")
        assert c["model_id"] not in real_ids
        assert c["tokens_in"] is None and c["tokens_out"] is None and c["usd"] is None
    assert rec["provider"] == "mock" and rec["model_id"] == roles["driver"]["model_id"]
    assert rec["tokens_in"] is None and rec["tokens_out"] is None and rec["usd"] is None
    assert rec["skeptic"]["verdict"] == "approve" and rec["escalation"]["slice"] is None


def test_mock_reject_reports_unresolved_without_frontier(repo, tmp_path):
    r = runner.invoke(app, ["ask", "--mock", "--replies", str(FIXTURES / "replies" / "reject"),
                            "--repo", str(repo), PROMPT])
    assert r.exit_code == 0, r.output
    rec = last_log(tmp_path)
    assert rec["skeptic"]["verdict"] == "reject" and len(rec["skeptic"]["findings"]) == 2
    assert rec["escalation"]["slice"] is None and "no frontier" in rec["escalation"]["reason"]
    assert "unresolved" in r.output


def test_path_traversal_rejected(repo, tmp_path):
    r = runner.invoke(app, ["ask", "--mock", "--replies", str(FIXTURES / "replies" / "traversal"),
                            "--repo", str(repo), PROMPT])
    assert r.exit_code != 0
    assert not (tmp_path / "evil.py").exists()
    assert (repo / "tiny_pkg" / "__init__.py").read_text().strip().endswith("a - b")


def test_mode_required(repo):
    r = runner.invoke(app, ["ask", PROMPT])
    assert r.exit_code == 2 and "not implemented" in r.output
    r = runner.invoke(app, ["ask", "--dry-run", "--mock", "--replies", "x", PROMPT])
    assert r.exit_code == 2


def test_mock_requires_replies(repo):
    assert runner.invoke(app, ["ask", "--mock", PROMPT]).exit_code == 2


def test_missing_reply_aborts_before_any_write(repo, tmp_path):
    r = runner.invoke(app, ["ask", "--mock", "--replies", str(FIXTURES / "replies" / "no_skeptic"),
                            "--repo", str(repo), PROMPT])
    assert r.exit_code == 1 and "no edits written" in r.output
    assert (repo / "tiny_pkg" / "__init__.py").read_text().strip().endswith("a - b")

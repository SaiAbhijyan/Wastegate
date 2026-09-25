import json
import shutil

import pytest
from typer.testing import CliRunner

from wastegate.chat import ChatSession
from wastegate.catalog import mock_catalog
from wastegate.cli import app
from wastegate.providers.base import Completion
from wastegate.router import RouterConfig
from wastegate.skills.registry import load_builtin
from wastegate.systemone.heuristic import HeuristicSystemOne

from conftest import FIXTURES

runner = CliRunner()
INIT = "tiny_pkg/__init__.py"
FIX = f"<<<REPLACE {INIT}\n    return a - b\n<<<WITH\n    return a + b\n<<<END\n"


@pytest.fixture
def repo(tmp_path):
    dst = tmp_path / "tiny_pkg"
    shutil.copytree(FIXTURES / "tiny_pkg", dst)
    return dst


def replies(tmp_path, text):
    d = tmp_path / "replies"
    d.mkdir(exist_ok=True)
    (d / "driver.md").write_text(text)
    return d


def log_lines(tmp_path):
    p = tmp_path / ".wastegate" / "logs" / "turns.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


def test_dry_run_slash_commands(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["chat", "--dry-run"], input="fix the race in worker.py\n/route\n/skills\n/nope\n/exit\n")
    assert r.exit_code == 0, r.output
    assert "generation: (empty, dry-run)" in r.output
    assert "driver:" in r.output and "skills:" in r.output and "/route /skills /exit" in r.output
    recs = log_lines(tmp_path)
    assert len(recs) == 1 and recs[0]["mode"] == "chat-dry-run" and recs[0]["turn"] == 1


def test_route_before_any_turn(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["chat", "--dry-run"], input="/route\n/exit\n")
    assert "no turn yet" in r.output


def test_eof_exits_cleanly(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["chat", "--dry-run"], input="hello\n").exit_code == 0


def test_mock_two_turns_logged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = replies(tmp_path, "sure, here is the answer")
    r = runner.invoke(app, ["chat", "--mock", "--replies", str(d)], input="explain git rebase\nand merge?\n/exit\n")
    assert r.exit_code == 0, r.output
    assert r.output.count("sure, here is the answer") == 2
    recs = log_lines(tmp_path)
    assert [x["turn"] for x in recs] == [1, 2]
    assert all(x["tokens_in"] is None and x["usd"] is None and x["calls"][0]["provider"] == "mock" for x in recs)


def test_history_grows_and_is_capped():
    seen = []

    class P:
        name = "rec"

        def complete(self, model_id, system, messages, max_tokens):
            seen.append(list(messages))
            return Completion("ok", "rec", model_id, None)

    s = ChatSession(HeuristicSystemOne(), mock_catalog(), RouterConfig(), load_builtin(),
                    providers=lambda role, model_id=None: P(), repo=None, state_dir=None, mode="mock")
    for i in range(8):
        s.turn(f"question {i}")
    assert len(seen[0]) == 1 and len(seen[1]) == 3
    assert len(seen[-1]) == 11  # last 10 history messages + current user


def test_mock_with_repo_applies_replace_fail_to_pass(repo, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = replies(tmp_path, "Fix:\n" + FIX)
    r = runner.invoke(app, ["chat", "--mock", "--replies", str(d), "--repo", str(repo)],
                      input="fix the bug in tiny_pkg\n/exit\n")
    assert r.exit_code == 0, r.output
    assert "tests: before=1 after=0" in r.output
    assert (repo / INIT).read_text().endswith("a + b\n")
    rec = log_lines(tmp_path)[0]
    assert rec["edits"] == [INIT] and rec["tests"] == {"before": 1, "after": 0}


def test_mock_without_repo_does_not_write(repo, tmp_path, monkeypatch):
    monkeypatch.chdir(repo)  # even with cwd = repo, no --repo means no writes
    d = replies(tmp_path, "Fix:\n" + FIX)
    r = runner.invoke(app, ["chat", "--mock", "--replies", str(d)], input="fix it\n/exit\n")
    assert "edits not applied (no --repo)" in r.output
    assert (repo / INIT).read_text().endswith("a - b\n")


def test_bad_edit_rejected_session_continues(repo, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = replies(tmp_path, f"<<<REPLACE {INIT}\nnot there\n<<<WITH\nx\n<<<END\n")
    r = runner.invoke(app, ["chat", "--mock", "--replies", str(d), "--repo", str(repo)],
                      input="one\ntwo\n/exit\n")
    assert r.exit_code == 0 and r.output.count("edits rejected, nothing written") == 2
    assert (repo / INIT).read_text().endswith("a - b\n")


def test_reply_redacted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GROQ_API_KEY", "gsk-echoed-by-model-5555")
    d = replies(tmp_path, "your key is gsk-echoed-by-model-5555")
    r = runner.invoke(app, ["chat", "--mock", "--replies", str(d)], input="hi\n/exit\n")
    assert "gsk-echoed-by-model-5555" not in r.output


def test_live_no_key_exit_2(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["chat", "--live"], input="hi\n/exit\n")
    assert r.exit_code == 2 and "no key or --live not set" in r.output


@pytest.mark.parametrize("args", [[], ["--dry-run", "--mock", "--replies", "x"], ["--mock"], ["--dry-run", "--local"]])
def test_bad_mode_combos_exit_2(args):
    assert runner.invoke(app, ["chat", *args], input="/exit\n").exit_code == 2

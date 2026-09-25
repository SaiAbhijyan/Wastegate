"""Tool loop + verification harness, mock only."""
import json
import shutil

import pytest
from typer.testing import CliRunner

from wastegate.cli import app

from conftest import FIXTURES

runner = CliRunner()
PROMPT = "fix the off-by-one in sliding_windows"
REPL = ("<<<REPLACE windows/__init__.py\n    return [xs[i:i + k] for i in range(len(xs) - k)]\n<<<WITH\n"
        "    return [xs[i:i + k] for i in range(len(xs) - k + 1)]\n<<<END\n")
BAD = ("<<<REPLACE windows/__init__.py\n    return [xs[i:i + k] for i in range(len(xs) - k)]\n<<<WITH\n"
       "    return [xs[i:i + k] for i in range(len(xs) - k - 1)]\n<<<END\n")


@pytest.fixture
def obo(tmp_path):
    dst = tmp_path / "off_by_one"
    shutil.copytree(FIXTURES / "off_by_one", dst)
    return dst


def script(tmp_path, *steps):
    d = tmp_path / "agent_script"
    d.mkdir(exist_ok=True)
    for i, s in enumerate(steps, 1):
        (d / f"agent_{i}.md").write_text(s)
    return d


def chat(tmp_path, monkeypatch, repo, replies, line=PROMPT, extra=()):
    monkeypatch.chdir(tmp_path)
    return runner.invoke(app, ["chat", "--mock", "--replies", str(replies), "--repo", str(repo), *extra],
                         input=f"{line}\n/exit\n")


def last(tmp_path):
    return json.loads((tmp_path / ".wastegate/logs/turns.jsonl").read_text().splitlines()[-1])


def test_three_step_loop_fail_to_pass(obo, tmp_path, monkeypatch):
    r = chat(tmp_path, monkeypatch, obo, FIXTURES / "replies/agent_obo")
    assert r.exit_code == 0, r.output
    out = r.output
    assert "[step 1] grep" in out and "[step 2] edit windows/__init__.py" in out and "[step 3] pytest" in out
    assert "VERIFICATION: PASS" in out and "Checks: python -m pytest -q → exit 0" in out
    rec = last(tmp_path)
    assert rec["mode"] == "chat-agent-mock"
    assert rec["verification"]["status"] == "PASS" and rec["verification"]["baseline"]["exit"] == 1
    assert [c["tool"] for c in rec["tool_calls"]] == ["grep", "edit", "pytest", "done"]
    assert rec["tool_calls"][1]["arg"] == "windows/__init__.py"
    assert "len(xs) - k + 1" in (obo / "windows/__init__.py").read_text()
    # order: tool calls, then model text, then gate, then verification
    assert out.index("[step 3] pytest") < out.index("Fixed the off-by-one") < out.index("gate:") \
        < out.index("VERIFICATION: PASS")


def test_driver_text_in_output_and_jsonl(obo, tmp_path, monkeypatch):
    r = chat(tmp_path, monkeypatch, obo, FIXTURES / "replies/agent_obo")
    final = "Fixed the off-by-one: range now goes to len(xs) - k + 1. Tests pass after the edit."
    assert final in r.output
    assert last(tmp_path)["driver_text"].strip() == final


def test_not_verified_when_tests_not_rerun_after_edit(obo, tmp_path, monkeypatch):
    d = script(tmp_path, REPL, "<<<DONE\nall fixed, trust me\n>>>\n")  # nudge -> script ends
    r = chat(tmp_path, monkeypatch, obo, d)
    assert r.exit_code == 0, r.output
    assert "VERIFICATION: NOT VERIFIED" in r.output and "tests not run after last edit" in r.output
    rec = last(tmp_path)
    assert rec["verification"]["status"] == "NOT VERIFIED" and rec["verification"]["nudged"] is True


def test_stale_test_run_does_not_count(obo, tmp_path, monkeypatch):
    d = script(tmp_path, "<<<TOOL pytest\n>>>\n", REPL, "<<<DONE\ndone\n>>>\n")
    r = chat(tmp_path, monkeypatch, obo, d)
    assert "VERIFICATION: NOT VERIFIED" in r.output and "tests not run after last edit" in r.output


def test_skip_marker_tamper_is_not_verified(obo, tmp_path, monkeypatch):
    tamper = ("<<<REPLACE tests/test_windows.py\ndef test_includes_last_window():\n<<<WITH\n"
              "import pytest\n\n\n@pytest.mark.skip\ndef test_includes_last_window():\n<<<END\n")
    d = script(tmp_path, tamper, REPL, "<<<TOOL pytest\n>>>\n", "<<<DONE\nok\n>>>\n")
    r = chat(tmp_path, monkeypatch, obo, d)
    assert "VERIFICATION: NOT VERIFIED" in r.output and "tamper" in r.output
    rec = last(tmp_path)
    assert rec["verification"]["checks"][0]["exit"] == 0 and rec["verification"]["tamper"]


def test_changed_expected_value_is_tamper(obo, tmp_path, monkeypatch):
    weaken = ("<<<REPLACE tests/test_windows.py\n    assert sliding_windows([1, 2, 3], 2) == [[1, 2], [2, 3]]\n<<<WITH\n"
              "    assert sliding_windows([1, 2, 3], 2) == [[1, 2]]\n<<<END\n")
    d = script(tmp_path, weaken, "<<<TOOL pytest\n>>>\n", "<<<DONE\nok\n>>>\n")
    r = chat(tmp_path, monkeypatch, obo, d)
    assert "VERIFICATION: NOT VERIFIED" in r.output and "tamper" in r.output


def test_repair_cap_five(obo, tmp_path, monkeypatch):
    steps = []
    for i in range(8):  # alternate a no-op-ish failing edit and a failing test run
        steps += [f"<<<FILE notes_{i}.txt\nattempt {i}\n>>>\n", "<<<TOOL pytest\n>>>\n"]
    d = script(tmp_path, *steps)
    monkeypatch.setenv("WASTEGATE_AGENT_MAX_STEPS", "30")
    r = chat(tmp_path, monkeypatch, obo, d, extra=("--max-steps", "30"))
    assert "VERIFICATION: NOT VERIFIED" in r.output and "repair cap" in r.output
    rec = last(tmp_path)
    fails = [c for c in rec["tool_calls"] if c["tool"] == "pytest"]
    assert len(fails) == 6  # first failure + 5 repair attempts, then stop


def test_max_steps_respected(obo, tmp_path, monkeypatch):
    d = script(tmp_path, *["<<<TOOL read\nwindows/__init__.py\n>>>\n"] * 10)
    r = chat(tmp_path, monkeypatch, obo, d, extra=("--max-steps", "3"))
    rec = last(tmp_path)
    assert len(rec["tool_calls"]) == 3 and rec["stop_reason"] == "max_steps"


def test_path_escape_in_loop_is_error_not_crash(obo, tmp_path, monkeypatch):
    d = script(tmp_path, "<<<TOOL read\n../../etc/passwd\n>>>\n", "<<<TOOL shell\nrm -rf .\n>>>\n",
               "<<<FILE ../evil.py\nx\n>>>\n", "<<<DONE\nstopped\n>>>\n")
    r = chat(tmp_path, monkeypatch, obo, d)
    assert r.exit_code == 0, r.output
    rec = last(tmp_path)
    assert [c["ok"] for c in rec["tool_calls"][:3]] == [False, False, False]
    assert not (tmp_path / "evil.py").exists() and (obo / "windows/__init__.py").exists()


def test_tool_not_allowed_for_kind(obo, tmp_path, monkeypatch):
    d = script(tmp_path, REPL, "<<<DONE\nx\n>>>\n")
    r = chat(tmp_path, monkeypatch, obo, d, line="explain how sliding_windows works")
    rec = last(tmp_path)
    assert rec["tool_calls"][0]["ok"] is False and "not allowed" in rec["tool_calls"][0]["error"]
    assert "len(xs) - k)" in (obo / "windows/__init__.py").read_text()  # unchanged
    assert "VERIFICATION: n/a (no edits)" in r.output


def test_no_harness_body_for_explain(obo, tmp_path, monkeypatch):
    from wastegate.agent import build_system
    from wastegate.catalog import mock_catalog
    from wastegate.pipeline import plan_turn
    from wastegate.router import RouterConfig
    from wastegate.skills.registry import load_builtin
    from wastegate.systemone.agent_gate import agent_plan
    from wastegate.systemone.heuristic import HeuristicSystemOne
    for prompt, want in (("explain how git rebase works", False), (PROMPT, True)):
        p = plan_turn(prompt, HeuristicSystemOne(), mock_catalog(), RouterConfig(), load_builtin())
        ap = agent_plan(prompt, HeuristicSystemOne(), mock_catalog(), RouterConfig())
        system = build_system(p.composed.system, ap, obo, max_system_bytes=100_000)  # room for the full skill
        assert ("No evidence = not done" in system) is want
        assert ap.harness_mode == ("full" if want else "off")


def test_dry_run_repo_shows_plan(obo, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["chat", "--dry-run", "--repo", str(obo)], input=f"{PROMPT}\n/exit\n")
    assert r.exit_code == 0 and "no generation" in r.output and "agent: model=" in r.output
    assert "harness=code-only" in r.output and "max_steps=8" in r.output  # default 12 KB budget strips the skill


def test_oneshot_flag_keeps_old_path(obo, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["chat", "--mock", "--oneshot", "--replies", str(FIXTURES / "replies/off_by_one"),
                            "--repo", str(obo)], input=f"{PROMPT}\n/exit\n")
    assert "tests: before=1 after=0" in r.output and "VERIFICATION" not in r.output

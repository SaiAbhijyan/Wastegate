"""Driver reply text is printed before the gate/stats block and logged (redacted, capped) as driver_text."""
import json
import shutil

import pytest
from typer.testing import CliRunner

from wastegate.cli import app

from conftest import FIXTURES

runner = CliRunner()
PROMPT = "fix the off-by-one in sliding_windows"
BODY = (FIXTURES / "replies/off_by_one/driver.md").read_text().strip()


@pytest.fixture
def obo(tmp_path):
    dst = tmp_path / "off_by_one"
    shutil.copytree(FIXTURES / "off_by_one", dst)
    return dst


def last(tmp_path):
    return json.loads((tmp_path / ".wastegate/logs/turns.jsonl").read_text().splitlines()[-1])


def replies(tmp_path, text):
    d = tmp_path / "replies"
    d.mkdir(exist_ok=True)
    (d / "driver.md").write_text(text)
    (d / "skeptic.md").write_text("VERDICT: approve\n")
    return d


def test_mock_ask_prints_driver_body_before_gate(obo, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["ask", "--mock", "--replies", str(FIXTURES / "replies/off_by_one"), "--repo", str(obo), PROMPT])
    assert r.exit_code == 0, r.output
    assert BODY in r.output
    assert r.output.index(BODY) < r.output.index("gate:")
    assert last(tmp_path)["driver_text"] == BODY + "\n" or last(tmp_path)["driver_text"].strip() == BODY


def test_dry_run_says_no_generation_before_gate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["ask", "--dry-run", PROMPT])
    assert r.exit_code == 0
    assert "no generation" in r.output and r.output.index("no generation") < r.output.index("gate:")
    assert last(tmp_path)["driver_text"] is None


def test_driver_text_redacted_in_output_and_log(obo, tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-driver-echo-31337")
    d = replies(tmp_path, "Here is your key gsk-driver-echo-31337, no edits.\n")
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["ask", "--mock", "--replies", str(d), "--repo", str(obo), PROMPT])
    assert r.exit_code == 0, r.output
    raw = (tmp_path / ".wastegate/logs/turns.jsonl").read_text()
    assert "gsk-driver-echo-31337" not in r.output and "gsk-driver-echo-31337" not in raw
    assert "[REDACTED]" in last(tmp_path)["driver_text"]


def test_driver_text_capped_at_4k(obo, tmp_path, monkeypatch):
    d = replies(tmp_path, "x" * 10_000 + "\n")
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["ask", "--mock", "--replies", str(d), "--repo", str(obo), PROMPT])
    assert len(last(tmp_path)["driver_text"]) <= 4000


def test_chat_mock_prints_reply_before_gate_and_logs(tmp_path, monkeypatch):
    d = replies(tmp_path, "sure, here is the answer\n")
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["chat", "--mock", "--replies", str(d)], input="explain git rebase\n/exit\n")
    assert r.exit_code == 0, r.output
    assert r.output.index("sure, here is the answer") < r.output.index("gate:")
    assert last(tmp_path)["driver_text"].strip() == "sure, here is the answer"


def test_chat_dry_run_no_generation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["chat", "--dry-run"], input="explain git rebase\n/exit\n")
    assert r.output.index("no generation") < r.output.index("gate:")
    assert last(tmp_path)["driver_text"] is None


def test_terminal_shows_full_reply_log_is_capped(obo, tmp_path, monkeypatch):
    d = replies(tmp_path, "y" * 6_000 + "END_MARK\n")
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["ask", "--mock", "--replies", str(d), "--repo", str(obo), PROMPT])
    assert "END_MARK" in r.output
    assert len(last(tmp_path)["driver_text"]) == 4000 and "END_MARK" not in last(tmp_path)["driver_text"]

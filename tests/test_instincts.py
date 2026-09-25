import json

from typer.testing import CliRunner

from wastegate.cli import app
from wastegate.instincts import add_instinct, load_instincts, select_instincts
from wastegate.log import TurnLogger

runner = CliRunner()


def store(tmp_path):
    return tmp_path / ".wastegate" / "instincts.jsonl"


def seed_turn(tmp_path, kind="implement"):
    TurnLogger(tmp_path / ".wastegate" / "logs").write(
        {"prompt": "p", "turn_id": "t1", "gate": {"kind": {"value": kind, "confidence": 0.5}}})


def test_review_minus_one_with_note_creates_one_instinct(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    seed_turn(tmp_path)
    r = runner.invoke(app, ["review", "-1", "--note", "prefer stdlib over new deps"])
    assert r.exit_code == 0, r.output
    rows = [json.loads(l) for l in store(tmp_path).read_text().splitlines()]
    assert len(rows) == 1
    row = rows[0]
    assert row["text"] == "prefer stdlib over new deps" and row["kind"] == "implement"
    assert row["confidence"] == 0.5 and row["support"] == 1 and row["source_turn"]


def test_verdict_option_form_also_creates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    seed_turn(tmp_path)
    assert runner.invoke(app, ["review", "--verdict", "-1", "--note", "no new frameworks"]).exit_code == 0
    assert len(load_instincts(tmp_path / ".wastegate")) == 1


def test_plus_one_or_no_note_creates_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    seed_turn(tmp_path)
    runner.invoke(app, ["review", "+1", "--note", "nice"])
    runner.invoke(app, ["review", "-1"])
    assert not store(tmp_path).exists()


def test_next_prompt_injects_instinct(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    seed_turn(tmp_path, kind="debug")
    runner.invoke(app, ["review", "-1", "--note", "always reproduce the bug first"])
    r = runner.invoke(app, ["prompt", "fix the race in worker.py"])
    assert r.exit_code == 0
    assert "<instincts" in r.output and "always reproduce the bug first" in r.output


def test_select_at_most_three_same_kind_first_newest_first(tmp_path):
    d = tmp_path / ".wastegate"
    for i in range(3):
        add_instinct(d, f"other-{i}", "plan", f"t{i}")
    for i in range(3):
        add_instinct(d, f"debug-{i}", "debug", f"d{i}")
    add_instinct(d, "debug-newest", "debug", "d9")
    got = select_instincts(load_instincts(d), "debug")
    assert got == ["debug-newest", "debug-2", "debug-1"]
    assert select_instincts(load_instincts(d), "ship", k=3) == ["debug-newest", "debug-2", "debug-1"]


def test_note_is_redacted_and_capped(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-in-a-note-7777")
    d = tmp_path / ".wastegate"
    add_instinct(d, "use key gsk-in-a-note-7777 " + "x" * 400, "debug", "t")
    raw = (d / "instincts.jsonl").read_text()
    assert "gsk-in-a-note-7777" not in raw
    assert len(load_instincts(d)[0]["text"]) <= 200


def test_no_store_means_no_instincts_block(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["prompt", "fix the race in worker.py"])
    assert "<instincts" not in r.output

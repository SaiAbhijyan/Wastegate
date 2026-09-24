import json

import pytest
from typer.testing import CliRunner

from wastegate.cli import app
from wastegate.log import TurnLogger

runner = CliRunner()


@pytest.fixture
def logged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    lg = TurnLogger(tmp_path / ".wastegate" / "logs")
    lg.write({"prompt": "first"})
    lg.write({"prompt": "second"})
    return lg.path


def lines(p):
    return [json.loads(l) for l in p.read_text().splitlines()]


@pytest.mark.parametrize("args,verdict", [
    (["--verdict", "-1"], "-1"), (["--verdict", "+1"], "+1"), (["-1"], "-1"), (["+1"], "+1"),
])
def test_review_writes_last_line_only(logged, args, verdict):
    r = runner.invoke(app, ["review", *args, "--note", "too much abstraction"])
    assert r.exit_code == 0, r.output
    recs = lines(logged)
    assert recs[0]["review"] is None
    assert recs[1]["review"]["verdict"] == verdict
    assert recs[1]["review"]["note"] == "too much abstraction"
    assert recs[1]["prompt"] == "second"


@pytest.mark.parametrize("args", [["0"], ["--verdict", "meh"], [], ["-1", "--verdict", "+1"]])
def test_review_bad_input(logged, args):
    r = runner.invoke(app, ["review", *args])
    assert r.exit_code == 2, (args, r.output)
    assert all(rec["review"] is None for rec in lines(logged))


def test_review_no_log(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["review", "-1"]).exit_code == 1

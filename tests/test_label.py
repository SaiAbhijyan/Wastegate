import json

from typer.testing import CliRunner

from wastegate.cli import app
from wastegate.labels import load_labels, load_pool

from conftest import LABELS, ROOT

POOL = ROOT / "evals/route_quality/pool.md"
runner = CliRunner()


def norm(s):
    return " ".join(s.lower().split())


def test_pool_is_30_unique_and_disjoint_from_frozen_labels():
    pool = load_pool(POOL)
    assert len(pool) == 30 and len({p.id for p in pool}) == 30
    frozen = {norm(r.prompt) for r in load_labels(LABELS)}
    assert not frozen & {norm(p.prompt) for p in pool}


def invoke(out, inp):
    return runner.invoke(app, ["label", "new", "--out", str(out), "--pool", str(POOL),
                               "--labeler", "tester-human"], input=inp)


def rows(out):
    return [json.loads(l) for l in out.read_text().splitlines()] if out.exists() else []


def test_one_prompt_at_a_time_skip_and_quit(tmp_path):
    out = tmp_path / "human.jsonl"
    r = invoke(out, "n\nimplement\ns\nq\n")
    assert r.exit_code == 0, r.output
    assert "P01" in r.output and "P02" in r.output and "P03" in r.output
    got = rows(out)
    assert len(got) == 1
    row = got[0]
    assert row["id"] == "P01" and row["kind"] == "implement" and row["labeler"] == "tester-human"
    assert row["read_heuristic"] is False and len(row["pool_sha256"]) == 64
    # resume: P01 done, skipped P02 is offered again
    r = invoke(out, "n\nq\n")
    assert "P02" in r.output and "P01 " not in r.output


def test_invalid_kind_reprompts(tmp_path):
    out = tmp_path / "human.jsonl"
    r = invoke(out, "y\ndance\nask\nq\n")
    assert r.exit_code == 0
    assert rows(out)[0]["kind"] == "ask" and rows(out)[0]["read_heuristic"] is True


def test_never_shows_gate_prediction(tmp_path):
    r = invoke(tmp_path / "h.jsonl", "n\nq\n")
    assert "heuristic predicts" not in r.output.lower() and "confidence" not in r.output.lower()

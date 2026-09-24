import json

from typer.testing import CliRunner

from wastegate.cli import app

runner = CliRunner()


def test_route_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["route", "--json", "fix the race in worker.py"])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out["gate"]["kind"]["value"] == "debug"
    assert out["route"]["driver"]["tier"] in ("cheap", "mid")
    assert (tmp_path / ".wastegate" / "logs" / "turns.jsonl").exists()


def test_route_human_output(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["route", "survey papers on LLM routers"])
    assert r.exit_code == 0 and "research" in r.output


def test_prompt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["prompt", "let's brag about this CLI"])
    assert r.exit_code == 0 and "brag" in r.output.lower()


def test_skills_and_models():
    r = runner.invoke(app, ["skills", "ls"])
    assert r.exit_code == 0 and "fable-mode" in r.output
    r = runner.invoke(app, ["skills", "show", "karpathy"])
    assert r.exit_code == 0 and "provenance" in r.output.lower()
    assert runner.invoke(app, ["skills", "show", "nope"]).exit_code != 0
    r = runner.invoke(app, ["models"])
    assert r.exit_code == 0 and "unverified" in r.output


def test_init_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("WASTEGATE_HOME", str(tmp_path / "h"))
    assert runner.invoke(app, ["init"]).exit_code == 0
    cfg = tmp_path / "h" / "config.toml"
    assert 'backend = "heuristic"' in cfg.read_text()
    cfg.write_text(cfg.read_text() + "# mine\n")
    assert runner.invoke(app, ["init"]).exit_code == 0
    assert "# mine" in cfg.read_text()


def test_stubs_exit_2():
    for cmd in (["chat"], ["evolve"], ["report"]):
        r = runner.invoke(app, cmd)
        assert r.exit_code == 2, cmd
        assert "not implemented" in r.output


def test_eval_dry_print_only():
    r = runner.invoke(app, ["eval", "run", "--suite", "route_quality", "--dry-run"])
    assert r.exit_code == 0 and "sha256" in r.output and "G01" in r.output
    assert runner.invoke(app, ["eval", "run", "--suite", "route_quality"]).exit_code == 2


def test_jev_backend_refuses_live(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["route", "--backend", "jev", "x"])
    assert r.exit_code == 2 and "disabled" in r.output

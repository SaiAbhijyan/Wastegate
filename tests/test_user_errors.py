"""v0.1 user-facing errors: bad --repo, missing pytest, init without keys. No tracebacks."""
import shutil
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest
from typer.testing import CliRunner

from wastegate import cli as cli_mod
from wastegate.cli import app
from wastegate.pipeline import RepoError, validate_repo

from conftest import FIXTURES

runner = CliRunner()
PROMPT = "fix the off-by-one in sliding_windows"


# 1) --repo validation
@pytest.mark.parametrize("raw", [
    str(PureWindowsPath(r"C:\Users\nobody\no_such_repo")),
    str(PurePosixPath("/definitely/not/here/repo")),
    "relative/missing/dir",
])
def test_validate_repo_rejects_missing(raw):
    with pytest.raises(RepoError, match="repo not a directory"):
        validate_repo(Path(raw))


def test_validate_repo_rejects_file(tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("x")
    with pytest.raises(RepoError, match="repo not a directory"):
        validate_repo(f)


def test_validate_repo_accepts_dir(tmp_path):
    assert validate_repo(tmp_path) == tmp_path


@pytest.mark.parametrize("cmd", [["ask", "--mock", "--replies", "x"], ["ask", "--dry-run"], ["run", "--dry-run"],
                                 ["ask", "--live"]])
@pytest.mark.parametrize("raw", [r"C:\Users\nobody\no_such_repo", "/definitely/not/here/repo"])
def test_cli_bad_repo_exit_2_no_traceback(tmp_path, monkeypatch, cmd, raw):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, [*cmd, "--repo", raw, PROMPT])
    assert r.exit_code == 2, r.output
    assert "repo not a directory:" in r.output and "Traceback" not in r.output
    assert r.exception is None or isinstance(r.exception, SystemExit)
    assert not (tmp_path / ".wastegate").exists()


def test_chat_bad_repo_exit_2(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["chat", "--dry-run", "--repo", "/definitely/not/here"], input="/exit\n")
    assert r.exit_code == 2 and "repo not a directory:" in r.output


# 2) pytest missing in the environment
@pytest.fixture
def obo(tmp_path):
    dst = tmp_path / "off_by_one"
    shutil.copytree(FIXTURES / "off_by_one", dst)
    return dst


def test_missing_pytest_exit_2_before_any_call_or_write(obo, tmp_path, monkeypatch):
    monkeypatch.setattr(cli_mod, "pytest_available", lambda: False)
    monkeypatch.chdir(tmp_path)
    before = (obo / "windows/__init__.py").read_text()
    r = runner.invoke(app, ["ask", "--mock", "--replies", str(FIXTURES / "replies/off_by_one"), "--repo", str(obo), PROMPT])
    assert r.exit_code == 2 and "pip install pytest" in r.output and "Traceback" not in r.output
    assert 'pip install -e ".[dev]"' in r.output  # not eaten by rich markup
    assert (obo / "windows/__init__.py").read_text() == before
    assert not (tmp_path / ".wastegate").exists()


def test_missing_pytest_chat_with_repo_exit_2(obo, tmp_path, monkeypatch):
    monkeypatch.setattr(cli_mod, "pytest_available", lambda: False)
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["chat", "--mock", "--replies", str(FIXTURES / "replies/off_by_one"), "--repo", str(obo)],
                      input="/exit\n")
    assert r.exit_code == 2 and "pip install pytest" in r.output


def test_missing_pytest_irrelevant_for_dry_run(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_mod, "pytest_available", lambda: False)
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["ask", "--dry-run", PROMPT]).exit_code == 0


def test_pytest_available_is_true_here():
    assert cli_mod.pytest_available() is True


def test_failing_repo_tests_are_not_an_error(obo, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["ask", "--mock", "--replies", str(FIXTURES / "replies/off_by_one"), "--repo", str(obo), PROMPT])
    assert r.exit_code == 0 and "tests: before=1 after=0" in r.output


# 4) init needs no key; --help works
def test_init_without_any_key(tmp_path, monkeypatch):
    monkeypatch.setenv("WASTEGATE_HOME", str(tmp_path / "h"))
    r = runner.invoke(app, ["init"])
    assert r.exit_code == 0
    cfg = (tmp_path / "h" / "config.toml").read_text()
    assert 'backend = "heuristic"' in cfg
    settings = [l.split("=")[0].strip().lower() for l in cfg.splitlines() if "=" in l and not l.lstrip().startswith("#")]
    assert settings and not any("key" in k for k in settings)
    assert "no API key needed" in r.output


def test_top_level_help():
    r = runner.invoke(app, ["--help"])
    assert r.exit_code == 0
    for c in ("ask", "run", "chat", "route", "prompt", "review", "init", "models", "skills"):
        assert c in r.output

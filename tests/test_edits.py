import shutil

import pytest
from typer.testing import CliRunner

from wastegate.cli import app
from wastegate.pipeline import EditError, UnsafeEdit, apply_edits, parse_edits, repo_context

from conftest import FIXTURES

PROMPT = "fix the bug in tiny_pkg and add a regression test"


@pytest.fixture
def repo(tmp_path):
    dst = tmp_path / "tiny_pkg"
    shutil.copytree(FIXTURES / "tiny_pkg", dst)
    return dst


INIT = "tiny_pkg/__init__.py"


def rep(path, old, new):
    return f"<<<REPLACE {path}\n{old}\n<<<WITH\n{new}\n<<<END\n"


def test_single_replace(repo):
    edits = parse_edits(rep(INIT, "    return a - b", "    return a + b"), repo)
    assert edits == [(INIT, "def add(a, b):\n    return a + b\n")]
    assert (repo / INIT).read_text().endswith("a - b\n")  # parse never writes
    apply_edits(repo, edits)
    assert (repo / INIT).read_text() == "def add(a, b):\n    return a + b\n"


def test_two_replaces_same_file_in_order(repo):
    text = rep(INIT, "a - b", "a * b") + rep(INIT, "a * b", "a + b")
    assert parse_edits(text, repo) == [(INIT, "def add(a, b):\n    return a + b\n")]


def test_file_then_replace_mixed(repo):
    text = "<<<FILE notes.txt\nhello\n>>>\n" + rep("notes.txt", "hello", "bye") + rep(INIT, "a - b", "a + b")
    assert dict(parse_edits(text, repo)) == {"notes.txt": "bye\n", INIT: "def add(a, b):\n    return a + b\n"}


def test_replace_with_empty(repo):
    (repo / "x.txt").write_text("keep\ndrop\n")
    assert parse_edits(rep("x.txt", "drop\n", ""), repo) == [("x.txt", "keep\n")]


@pytest.mark.parametrize("text,exc,msg", [
    (rep(INIT, "not here", "x"), EditError, "not found"),
    (rep(INIT, "a", "x"), EditError, r"\d+ times"),
    (rep("missing.py", "x", "y"), EditError, "does not exist"),
    (rep("../evil.py", "x", "y"), UnsafeEdit, "escapes"),
    ("<<<FILE ../evil.py\nx\n>>>\n", UnsafeEdit, "escapes"),
])
def test_bad_edits_raise_and_write_nothing(repo, text, exc, msg):
    before = (repo / INIT).read_text()
    with pytest.raises(exc, match=msg):
        parse_edits(rep(INIT, "a - b", "a + b") + text, repo)
    assert (repo / INIT).read_text() == before
    assert not (repo.parent / "evil.py").exists()


def test_edit_error_is_unsafe_edit():
    assert issubclass(EditError, UnsafeEdit)


def test_ask_mock_with_replace_reply_fixes_fixture(repo, tmp_path, monkeypatch):
    replies = tmp_path / "replies"
    replies.mkdir()
    (replies / "driver.md").write_text("Fix:\n" + rep(INIT, "    return a - b", "    return a + b"))
    (replies / "skeptic.md").write_text("VERDICT: approve\n")
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(app, ["ask", "--mock", "--replies", str(replies), "--repo", str(repo), PROMPT])
    assert r.exit_code == 0, r.output
    assert "tests: before=1 after=0" in r.output


def test_repo_context_includes_code_skips_secrets_and_caps(repo, monkeypatch):
    (repo / ".env").write_text("SECRET=1\n")
    (repo / "id_rsa").write_text("private\n")
    (repo / ".wastegate").mkdir()
    (repo / ".wastegate" / "x.jsonl").write_text("log\n")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-planted-in-file-1234")
    (repo / "cfg.py").write_text("KEY = 'gsk-planted-in-file-1234'\n")
    ctx = repo_context(repo)
    assert "def add(a, b):" in ctx and "tiny_pkg/__init__.py" in ctx
    assert ".env" not in ctx and "id_rsa" not in ctx and ".wastegate" not in ctx
    assert "gsk-planted-in-file-1234" not in ctx
    assert len(repo_context(repo, budget=200).encode()) <= 400

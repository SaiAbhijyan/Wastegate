"""Repo-scoped agent tools: read, grep, shell (allowlist), pytest. Path escapes and denied commands."""
import shutil

import pytest

from wastegate import agent_tools as T
from wastegate.agent_tools import ToolError

from conftest import FIXTURES


@pytest.fixture
def repo(tmp_path):
    dst = tmp_path / "off_by_one"
    shutil.copytree(FIXTURES / "off_by_one", dst)
    return dst


def test_read_ok_and_capped(repo):
    assert "def sliding_windows" in T.tool_read(repo, "windows/__init__.py")
    (repo / "big.txt").write_text("x" * 20_000)
    out = T.tool_read(repo, "big.txt")
    assert len(out) < 9_000 and "truncated" in out


@pytest.mark.parametrize("bad", ["../escape.txt", "/etc/passwd", "windows/../../x"])
def test_read_rejects_escape(repo, bad):
    with pytest.raises(ToolError, match="escapes repo"):
        T.tool_read(repo, bad)


def test_read_missing_file(repo):
    with pytest.raises(ToolError, match="not a file"):
        T.tool_read(repo, "nope.py")


@pytest.mark.parametrize("use_rg", [True, False])
def test_grep_both_backends(repo, monkeypatch, use_rg):
    if use_rg and not shutil.which("rg"):
        pytest.skip("rg not installed")
    if not use_rg:
        monkeypatch.setattr(T.shutil, "which", lambda name: None)
    out = T.tool_grep(repo, r"range\(len")
    assert "windows/__init__.py:3:" in out.replace("\\", "/")


@pytest.mark.parametrize("use_rg", [True, False])
def test_grep_caps_hits(repo, monkeypatch, use_rg):
    if use_rg and not shutil.which("rg"):
        pytest.skip("rg not installed")
    if not use_rg:
        monkeypatch.setattr(T.shutil, "which", lambda name: None)
    (repo / "many.txt").write_text("hit\n" * 200)
    out = T.tool_grep(repo, "hit", max_hits=50)
    assert len([l for l in out.splitlines() if ":" in l and "hit" in l]) == 50 and "capped" in out


def test_grep_skips_state_dirs(repo):
    (repo / ".wastegate").mkdir()
    (repo / ".wastegate" / "log.jsonl").write_text("SECRETMARK\n")
    assert "SECRETMARK" not in T.tool_grep(repo, "SECRETMARK")


@pytest.mark.parametrize("cmd", [
    "rm -rf .", "rm windows/__init__.py", "curl https://example.com", "python -c 'print(1)'",
    "python -m http.server", "git push", "git checkout .", "bash -c ls", "ls ..",
    "pytest ../elsewhere", "python ../escape.py", "git diff /etc/passwd", "sh run.sh",
])
def test_shell_denies(repo, cmd):
    with pytest.raises(ToolError, match="denied"):
        T.tool_shell(repo, cmd)


def test_shell_allows_git_status_and_pytest(repo):
    code, out = T.tool_shell(repo, "git status")
    assert isinstance(code, int)  # not a git repo -> non-zero exit is fine; it ran
    code, out = T.tool_shell(repo, "python -m pytest -q")
    assert code != 0 and "failed" in out
    code, _ = T.tool_shell(repo, "pytest -q tests/test_windows.py")
    assert code != 0


def test_shell_python_file_in_repo(repo):
    (repo / "hello.py").write_text("print('hi from repo')\n")
    code, out = T.tool_shell(repo, "python hello.py")
    assert code == 0 and "hi from repo" in out


def test_is_test_command():
    assert T.is_test_command(["pytest", "-q"]) and T.is_test_command(["python", "-m", "pytest"])
    assert not T.is_test_command(["git", "status"])


def test_pytest_tool(repo):
    code, out = T.tool_pytest(repo)
    assert code == 1 and "failed" in out

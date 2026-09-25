"""Repo-scoped tools for the agent loop: read, grep, shell (allowlist), pytest. Edit reuses pipeline.parse_edits.

Nothing here is a sandbox: `python <file>.py` inside the repo can run arbitrary code (docs/AGENT.md).
"""
from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from .pipeline import CONTEXT_SKIP_DIRS, UnsafeEdit, _guard

READ_CAP = 8_000
OUT_CAP = 4_000
MAX_HITS = 50
TIMEOUT = 120
PYTEST_CMD = "python -m pytest -q"


class ToolError(Exception):
    pass


def _path(repo: Path, rel: str) -> Path:
    try:
        return _guard(rel.strip(), repo.resolve())
    except UnsafeEdit:
        raise ToolError(f"path escapes repo: {rel.strip()}")


def _tail(text: str, cap: int = OUT_CAP) -> str:
    return text if len(text) <= cap else "… (output truncated)\n" + text[-cap:]


def tool_read(repo: Path, rel: str) -> str:
    p = _path(repo, rel)
    if not p.is_file():
        raise ToolError(f"not a file: {rel.strip()}")
    try:
        text = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise ToolError(f"not a text file: {rel.strip()}")
    if len(text) > READ_CAP:
        return text[:READ_CAP] + f"\n… (truncated at {READ_CAP} chars)"
    return text


def tool_grep(repo: Path, arg: str, max_hits: int = MAX_HITS) -> str:
    """arg = 'pattern' or 'pattern\\npath' (second line scopes the search; path-guarded)."""
    parts = arg.strip().split("\n", 1)
    pattern = parts[0].strip()
    scope = _path(repo, parts[1]) if len(parts) > 1 and parts[1].strip() else repo.resolve()
    try:
        rx = re.compile(pattern)
    except re.error as e:
        raise ToolError(f"bad regex: {e}")
    hits: list[str] = []
    if shutil.which("rg"):
        r = subprocess.run(["rg", "-n", "--no-heading", "--color=never", "--glob", "!.git", "--glob", "!.wastegate",
                            "-e", pattern, "--", scope.relative_to(repo.resolve()).as_posix() or "."], cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT)
        if r.returncode > 1:
            raise ToolError(f"grep failed: {r.stderr.strip()[:200]}")
        hits = [l[2:] if l.startswith("./") else l for l in r.stdout.splitlines()]
    else:
        root = repo.resolve()
        walk = [(str(scope.parent), [], [scope.name])] if scope.is_file() else os.walk(scope)
        for dirpath, dirnames, filenames in walk:
            dirnames[:] = sorted(d for d in dirnames if d not in CONTEXT_SKIP_DIRS and not d.startswith("."))
            for name in sorted(filenames):
                p = Path(dirpath) / name
                try:
                    lines = p.read_text(encoding="utf-8").splitlines()
                except (UnicodeDecodeError, OSError):
                    continue
                rel = p.relative_to(root).as_posix()
                hits += [f"{rel}:{i}:{line}" for i, line in enumerate(lines, 1) if rx.search(line)]
                if len(hits) > max_hits:
                    break
    if not hits:
        return "no matches"
    capped = len(hits) > max_hits
    return "\n".join(hits[:max_hits]) + (f"\n… (capped at {max_hits} hits)" if capped else "")


def is_test_command(argv: list[str]) -> bool:
    return bool(argv) and (argv[0] == "pytest" or argv[:3] == ["python", "-m", "pytest"])


def _check_args(repo: Path, args: list[str]) -> None:
    root = repo.resolve()
    for a in args:
        if a.startswith("-"):
            continue
        cand = Path(a.split("::")[0])
        if cand.is_absolute() or not (root / cand).resolve().is_relative_to(root):
            raise ToolError(f"denied: argument escapes repo: {a}")


def _allowed(repo: Path, argv: list[str]) -> list[str]:
    """Map an allowlisted command to the argv we actually run. Raises ToolError('denied: …') otherwise."""
    head = argv[0] if argv else ""
    if head == "git" and len(argv) > 1 and argv[1] in ("status", "diff"):
        _check_args(repo, argv[2:])
        return argv
    if head == "pytest":
        _check_args(repo, argv[1:])
        return [sys.executable, "-m", "pytest", *argv[1:]]
    if head == "python":
        if argv[1:3] == ["-m", "pytest"]:
            _check_args(repo, argv[3:])
            return [sys.executable, *argv[1:]]
        if len(argv) > 1 and argv[1].endswith(".py") and not argv[1].startswith("-"):
            _check_args(repo, argv[1:])
            return [sys.executable, *argv[1:]]
    raise ToolError("denied: allowed commands are git status|diff, pytest, python -m pytest, python <file>.py")


def _run(repo: Path, argv: list[str]) -> tuple[int, str]:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        r = subprocess.run(argv, cwd=repo, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return 124, f"timeout after {TIMEOUT}s"
    return r.returncode, _tail(r.stdout + r.stderr)


def tool_shell(repo: Path, cmd: str) -> tuple[int, str]:
    try:
        argv = shlex.split(cmd.strip())
    except ValueError as e:
        raise ToolError(f"denied: unparseable command: {e}")
    return _run(repo, _allowed(repo, argv))


def tool_pytest(repo: Path) -> tuple[int, str]:
    return _run(repo, [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"])

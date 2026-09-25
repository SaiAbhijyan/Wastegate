"""Security guarantees that must stay green (Layer A)."""
import json
import shutil

import pytest
from typer.testing import CliRunner

from wastegate import agent_tools as T
from wastegate.agent_tools import ToolError
from wastegate.cli import app
from wastegate.log import redact
from wastegate.pipeline import UnsafeEdit, parse_edits

from conftest import FIXTURES

runner = CliRunner()
PROMPT = "fix the off-by-one in sliding_windows"
GSK = "gsk_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6"
SKK = "sk-" + "proj-Zz9Yy8Xx7Ww6Vv5Uu4Tt3Ss2"


@pytest.fixture
def obo(tmp_path):
    dst = tmp_path / "off_by_one"
    shutil.copytree(FIXTURES / "off_by_one", dst)
    return dst


@pytest.mark.parametrize("bad", ["../x.py", "/etc/passwd", "windows/../../x"])
def test_read_denies_escape(obo, bad):
    with pytest.raises(ToolError, match="escapes repo"):
        T.tool_read(obo, bad)


@pytest.mark.parametrize("bad", ["../x", "/etc"])
def test_grep_scope_denies_escape(obo, bad):
    with pytest.raises(ToolError, match="escapes repo"):
        T.tool_grep(obo, f"root\n{bad}")


def test_grep_scope_inside_repo(obo):
    assert "windows/__init__.py" in T.tool_grep(obo, "range\nwindows").replace("\\", "/")
    assert "no matches" in T.tool_grep(obo, "range\ntests")


@pytest.mark.parametrize("block", ["<<<FILE ../evil.py\nx\n>>>\n", "<<<FILE /tmp/evil.py\nx\n>>>\n",
                                   "<<<REPLACE ../x.py\na\n<<<WITH\nb\n<<<END\n"])
def test_edit_denies_escape(obo, block):
    with pytest.raises(UnsafeEdit, match="escapes"):
        parse_edits(block, obo)


@pytest.mark.parametrize("cmd", ["pytest ../elsewhere", "git diff /etc/passwd", "python ../x.py",
                                 "rm -rf .", "curl https://example.com", "python -c 'import os'", "git push"])
def test_shell_denies(obo, cmd):
    with pytest.raises(ToolError, match="denied"):
        T.tool_shell(obo, cmd)


def test_redact_patterns_without_env():
    out = redact(f"a {GSK} b {SKK} c")
    assert GSK not in out and SKK not in out and out.count("[REDACTED]") == 2


def _script(tmp_path, steps):
    d = tmp_path / "rep"
    d.mkdir(exist_ok=True)
    for name, text in steps.items():
        (d / name).write_text(text, encoding="utf-8")
    return d


@pytest.mark.parametrize("path", ["ask-oneshot", "ask-loop", "chat-loop"])
def test_planted_keys_never_printed_or_logged(obo, tmp_path, monkeypatch, path):
    planted = f"here: {GSK} and {SKK}\n"
    if path == "ask-oneshot":
        d = _script(tmp_path, {"driver.md": planted, "skeptic.md": "VERDICT: approve\n"})
        args = ["ask", "--mock", "--replies", str(d), "--repo", str(obo), "--oneshot", PROMPT]
        inp = None
    else:
        d = _script(tmp_path, {"agent_1.md": f"<<<DONE\n{planted}>>>\n"})
        cmd = "ask" if path == "ask-loop" else "chat"
        args = [cmd, "--mock", "--replies", str(d), "--repo", str(obo)] + ([PROMPT] if cmd == "ask" else [])
        inp = None if cmd == "ask" else f"{PROMPT}\n/exit\n"
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, args, input=inp)
    assert r.exit_code == 0, r.output
    raw = (tmp_path / ".wastegate/logs/turns.jsonl").read_text(encoding="utf-8")
    for secret in (GSK, SKK):
        assert secret not in r.output and secret not in raw
    assert "[REDACTED]" in r.output


@pytest.mark.parametrize("marker", ["@pytest.mark.skip", "@pytest.mark.xfail"])
def test_tamper_skip_xfail_not_verified(obo, tmp_path, monkeypatch, marker):
    fix = ("<<<REPLACE windows/__init__.py\n    return [xs[i:i + k] for i in range(len(xs) - k)]\n<<<WITH\n"
           "    return [xs[i:i + k] for i in range(len(xs) - k + 1)]\n<<<END\n")
    tamper = ("<<<REPLACE tests/test_windows.py\ndef test_includes_last_window():\n<<<WITH\n"
              f"import pytest\n\n\n{marker}\ndef test_includes_last_window():\n<<<END\n")
    d = _script(tmp_path, {"agent_1.md": tamper, "agent_2.md": fix, "agent_3.md": "<<<TOOL pytest\n>>>\n",
                           "agent_4.md": "<<<DONE\nok\n>>>\n"})
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["ask", "--mock", "--replies", str(d), "--repo", str(obo), PROMPT])
    assert "VERIFICATION: NOT VERIFIED" in r.output and "tamper" in r.output
    rec = json.loads((tmp_path / ".wastegate/logs/turns.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert rec["verification"]["checks"][0]["exit"] == 0


def test_no_test_uses_fixture_dir_as_repo():
    import re
    from conftest import ROOT
    bad = []
    for p in sorted((ROOT / "tests").glob("*.py")):
        text = p.read_text(encoding="utf-8")
        for m in re.finditer(r'"--repo",\s*([^\]\),]+)', text):
            arg = m.group(1)
            if "FIXTURES" in arg or "tests/fixtures" in arg:
                bad.append(f"{p.name}: {arg}")
    assert bad == []

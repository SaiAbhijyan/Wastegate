"""verification-harness skill: exact user text on disk, provenance, conditional loading."""
import hashlib

import pytest
from typer.testing import CliRunner

from wastegate.agent import harness_body, load_harness
from wastegate.cli import app
from wastegate.skills.registry import builtin_root, load_builtin
from wastegate.skills.scan import scan_skill_dir

SKILL = builtin_root() / "verification-harness" / "SKILL.md"
LAWS = [
    "1. **No evidence = not done.**",
    "2. **Never bend the tests.**",
    "3. **Evidence must be fresh.**",
    "4. **Independent tests.**",
    "5. **Small, real changes.**",
    "6. **Stopping honestly is allowed.**",
]


def test_exact_user_text_on_disk():
    raw = SKILL.read_bytes()
    assert hashlib.sha256(raw).hexdigest().startswith("2e1cb93b61f1b7b4")  # committed in c1a5724
    text = raw.decode()
    assert text.startswith("---\nname: verification-harness\n")
    assert "license: MIT" in text and "arXiv:2312.13010" in text
    assert "## The 6 laws (read first, never break)" in text
    for law in LAWS:
        assert law in text


def test_registry_provenance_sidecar():
    s = load_builtin()["verification-harness"]
    assert s.provenance["text"] == "user-supplied" and "2312.13010" in s.provenance["credits"]
    assert "MIT" in s.provenance["license"] and not s.quarantined


def test_scan_only_size_exempted():
    rep = scan_skill_dir(SKILL.parent)
    assert rep.high == []
    assert any(f.rule == "size" and "exempt" in f.detail for f in rep.findings)


def test_imported_dir_cannot_self_exempt(tmp_path):
    d = tmp_path / "imp"
    d.mkdir()
    (d / "SKILL.md").write_text(SKILL.read_text())
    (d / "provenance.toml").write_text('text = "user-supplied"\n')
    assert any(f.rule == "size" for f in scan_skill_dir(d).high)


@pytest.mark.parametrize("kind,prompt,want", [
    ("implement", "add a CSV export", True),
    ("debug", "segfault on empty input", True),
    ("ask", "please verify the parser", True),
    ("ask", "can you test it end to end", True),
    ("review", "prove the cache is safe", True),
    ("plan", "harden the auth flow", True),
    ("ship", "ship it", True),
    ("ask", "explain how git rebase works", False),
    ("research", "survey papers on routers", False),
])
def test_load_harness(kind, prompt, want):
    assert load_harness(kind, prompt) is want


def test_harness_body_is_below_frontmatter():
    body = harness_body()
    assert body.lstrip().startswith("# Verification Harness") and "name: verification-harness" not in body


def test_default_compose_for_explain_has_no_laws(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(app, ["prompt", "explain how git rebase works"])
    assert r.exit_code == 0 and "The 6 laws" not in r.output and "No evidence = not done" not in r.output

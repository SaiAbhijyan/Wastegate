"""UTF-8 everywhere: skills with non-ASCII load, and no encoding-less text I/O in src (Windows cp1252 guard)."""
import ast

from wastegate.skills.registry import load_builtin, load_skill_dir

from conftest import ROOT


def test_skill_with_checkmark_loads(tmp_path):
    d = tmp_path / "uni"
    d.mkdir()
    (d / "SKILL.md").write_bytes("---\nname: uni\ndescription: d\n---\nPass ✅ → done — “quotes”\n".encode("utf-8"))
    s = load_skill_dir(d, imported=True)
    assert "✅" in s.body and "→" in s.body


def test_builtin_harness_body_has_checkmark():
    assert "✅" in load_builtin()["verification-harness"].body


def test_no_text_io_without_encoding():
    bad = []
    for p in sorted((ROOT / "src" / "wastegate").rglob("*.py")):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""
            kws = {k.arg for k in node.keywords}
            if name in ("read_text", "write_text") and "encoding" not in kws:
                bad.append(f"{p.name}:{node.lineno} {name}")
            if name == "open" and "encoding" not in kws:
                mode = node.args[0].value if node.args and isinstance(node.args[0], ast.Constant) else "r"
                if isinstance(mode, str) and "b" not in mode:
                    bad.append(f"{p.name}:{node.lineno} open")
            if name == "run" and any(k.arg == "text" for k in node.keywords) and "encoding" not in kws:
                bad.append(f"{p.name}:{node.lineno} subprocess.run(text=True) without encoding")
    assert bad == [], bad

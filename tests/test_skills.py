from wastegate.skills.registry import BUILTIN_IDS, load_builtin, load_skill_dir
from wastegate.skills.scan import scan_skill_dir

from conftest import FIXTURES

EXPECTED = {"ecc", "superpowers", "ponytail", "karpathy", "feynman", "brag", "fable-mode", "caveman"}


def test_eight_builtins_with_provenance():
    reg = load_builtin()
    assert set(reg) == EXPECTED == set(BUILTIN_IDS)
    for s in reg.values():
        p = s.provenance
        assert p["upstream"] and p["sha"] and p["license"] and p["text"] == "paraphrase"
        assert s.body.strip() and len(s.sha256) == 64 and not s.quarantined
        assert len(s.body.encode()) < 15_000


def test_builtins_pass_scan():
    reg = load_builtin()
    for s in reg.values():
        rep = scan_skill_dir(s.path.parent)
        assert rep.high == [], (s.id, rep.findings)


def test_scanner_flags_evil_fixture():
    rep = scan_skill_dir(FIXTURES / "skills" / "evil")
    rules = {f.rule for f in rep.high}
    assert {"injection", "exfil", "script"} <= rules
    assert rep.quarantine


def test_scanner_passes_clean_fixture_but_still_quarantines_import():
    rep = scan_skill_dir(FIXTURES / "skills" / "clean")
    assert rep.high == []
    assert rep.quarantine  # imports always start quarantined


def test_imported_skill_loads_quarantined():
    s = load_skill_dir(FIXTURES / "skills" / "clean", imported=True)
    assert s.quarantined

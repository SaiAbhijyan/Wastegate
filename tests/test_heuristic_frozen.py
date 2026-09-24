"""heuristic.py must stay byte-identical (apart from the FROZEN header) to the code that ran
on the holdout. Editing cues fails this test until results/20260924-dev-selflabel.md is
explicitly replaced by a new run on a new, human-written label set."""
import hashlib
import re

from conftest import ROOT

HEURISTIC = ROOT / "src" / "wastegate" / "systemone" / "heuristic.py"
RESULTS = ROOT / "results" / "20260924-dev-selflabel.md"
HEADER = b"# FROZEN after session 1. Cue edits need a new labels set from a human who has not read this file.\n"


def recorded_hash() -> str:
    m = re.search(r"heuristic\.py sha256: `([0-9a-f]{64})`", RESULTS.read_text())
    assert m, "results file lost its heuristic hash"
    return m.group(1)


def body_hash(raw: bytes) -> str:
    assert raw.startswith(HEADER), "FROZEN header missing or altered"
    return hashlib.sha256(raw[len(HEADER):]).hexdigest()


def test_heuristic_matches_recorded_run():
    assert body_hash(HEURISTIC.read_bytes()) == recorded_hash()


def test_cue_edit_would_be_detected():
    mutated = HEURISTIC.read_bytes().replace(b'"debug": [', b'"debug": [ ', 1)
    assert body_hash(mutated) != recorded_hash()

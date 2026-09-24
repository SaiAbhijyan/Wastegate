"""Phase-1 gate: golden 15 kinds. Regression fixture only -- the author saw these
prompts while writing the heuristic, so passing says nothing about generalization.
Holdout rows are deliberately NOT exercised here."""
import pytest

from wastegate.labels import load_labels
from wastegate.systemone.base import GATE_QUESTIONS
from wastegate.systemone.heuristic import HeuristicSystemOne

from conftest import LABELS

GOLDEN = [r for r in load_labels(LABELS) if r.split == "golden"]


@pytest.mark.parametrize("row", GOLDEN, ids=[r.id for r in GOLDEN])
def test_golden_kind(row):
    ans = HeuristicSystemOne().decide(row.prompt, GATE_QUESTIONS)
    assert ans["kind"].value == row.kind, ans["kind"].distribution

from wastegate.labels import load_labels
from wastegate.systemone.base import GATE_QUESTIONS

from conftest import LABELS


def test_label_file_shape():
    rows = load_labels(LABELS)
    golden = [r for r in rows if r.split == "golden"]
    holdout = [r for r in rows if r.split == "holdout"]
    assert len(golden) == 15 and len(holdout) == 20
    kinds = set(GATE_QUESTIONS["kind"].options)
    assert all(r.kind in kinds for r in rows)
    assert len({r.id for r in rows}) == 35

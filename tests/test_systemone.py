import math

import pytest

from wastegate.systemone.base import GATE_QUESTIONS, Question
from wastegate.systemone.heuristic import HeuristicSystemOne
from wastegate.systemone.shortlist import shortlist

PROMPTS = ["fix the race in worker.py", "hello", "", "survey papers on LLM routers"]


@pytest.mark.parametrize("p", PROMPTS)
def test_answers_are_well_formed(p):
    ans = HeuristicSystemOne().decide(p, GATE_QUESTIONS)
    assert set(ans) == set(GATE_QUESTIONS)
    for qid, a in ans.items():
        q = GATE_QUESTIONS[qid]
        assert math.isclose(sum(a.distribution.values()), 1.0, abs_tol=1e-9)
        assert 0.0 <= a.confidence <= 1.0
        if q.type == "noul":
            assert set(a.distribution) == {"yes", "no"}
            assert a.value == pytest.approx(a.distribution["yes"])
        else:
            assert set(a.distribution) == set(q.options)
            assert a.value == max(q.options, key=lambda o: (a.distribution[o], -q.options.index(o)))


def test_deterministic():
    s1 = HeuristicSystemOne()
    a = s1.decide("deadlock under load, find the invariant", GATE_QUESTIONS)
    b = HeuristicSystemOne().decide("deadlock under load, find the invariant", GATE_QUESTIONS)
    assert a == b


def test_question_validation():
    with pytest.raises(ValueError):
        Question("x", "choice", "pick", ("only",))
    with pytest.raises(ValueError):
        Question("x", "score", "rate", tuple(str(i) for i in range(11)))
    with pytest.raises(ValueError):
        Question("x", "noul", "yes?", ("a", "b"))
    with pytest.raises(ValueError):
        Question("x", "choice", "pick", tuple(str(i) for i in range(256)))


def test_shortlist_caps_and_keeps_mentioned():
    opts = tuple(f"opt{i}" for i in range(60))
    q = Question("big", "choice", "pick", opts)
    s = shortlist(q, "please use opt55 and opt42", k=20)
    assert len(s.options) == 20
    assert "opt55" in s.options and "opt42" in s.options
    small = Question("s", "choice", "pick", ("a", "b"))
    assert shortlist(small, "x") is small

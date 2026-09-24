"""Jev/Laya: wire shapes only. Live calls must be disabled."""
import pytest

from wastegate.systemone.base import GATE_QUESTIONS
from wastegate.systemone import jev, laya

QS = {k: GATE_QUESTIONS[k] for k in ("kind", "complexity", "needs_tests")}


def test_request_shape_matches_laya_documented_format():
    req = jev.build_request("fix it", QS)
    assert req["state"] == {"body": "fix it"}
    kind = req["questions"]["kind"]
    assert kind["type"] == "choice" and set(kind["criteria"]) == set(QS["kind"].options)
    cx = req["questions"]["complexity"]
    assert cx["type"] == "score" and cx["criteria"] == list(QS["complexity"].options)
    nt = req["questions"]["needs_tests"]
    assert nt["type"] == "noul" and "criteria" not in nt


def test_request_shortlists_high_cardinality():
    from wastegate.systemone.base import Question
    q = Question("big", "choice", "pick", tuple(f"o{i}" for i in range(40)))
    req = jev.build_request("o3", {"big": q})
    assert len(req["questions"]["big"]["criteria"]) == 20


def test_parse_response():
    resp = {
        "answers": {
            "kind": {"choice": "debug", "confidence": 0.7,
                     "probabilities": {"debug": 0.7, "implement": 0.3}},
            "complexity": {"score": 2.6, "confidence": 0.5},
            "needs_tests": {"noul": 0.8, "confidence": 0.6},
        },
        "usage": {"input_tokens": 120, "output_tokens": 0},
    }
    ans, usage = jev.parse_response(resp, QS, backend="jev")
    assert ans["kind"].value == "debug"
    assert ans["kind"].distribution["debug"] == pytest.approx(0.7)
    assert ans["kind"].distribution["plan"] == 0.0
    assert ans["complexity"].value == "deep"  # round(2.6)=3 -> index 3, 0-based (unverified scale)
    assert ans["needs_tests"].value == pytest.approx(0.8)
    assert ans["needs_tests"].distribution == pytest.approx({"yes": 0.8, "no": 0.2})
    assert usage == {"input_tokens": 120, "output_tokens": 0}


def test_parse_rejects_unknown_choice():
    with pytest.raises(ValueError):
        jev.parse_response({"answers": {"kind": {"choice": "dance"}}}, {"kind": QS["kind"]}, "jev")


def test_live_calls_disabled(monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "jev-live-key")
    with pytest.raises(NotImplementedError):
        jev.JevSystemOne().decide("x", QS)
    with pytest.raises(NotImplementedError):
        laya.LayaSystemOne().decide("x", QS)


@pytest.mark.parametrize("var", ["TYPESAFE_API_KEY", "JEV_API_KEY"])
def test_key_from_env_and_repr_hides_it(monkeypatch, var):
    monkeypatch.setenv(var, "sekrit-value-9")
    s1 = jev.JevSystemOne()
    assert jev.api_key() == "sekrit-value-9"
    assert "sekrit" not in repr(s1)
    assert jev.auth_headers()["Authorization"] == "Bearer sekrit-value-9"


def test_laya_predict_args_same_shape():
    state, questions = laya.build_predict_args("fix it", QS)
    assert state == "fix it"
    assert questions == jev.build_request("fix it", QS)["questions"]

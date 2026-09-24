"""TypeSafe Jev adapter: wire shapes only. Live HTTP is DISABLED in session 1.

UNVERIFIED: Jev's public pages (fetched 2026-09-24) do not document the request/response
JSON or the auth header. We use the body documented by Laya for its "Jev-compatible"
`POST /v1/systemone` server. Confirm against Jev's API guide before enabling live calls.
Keys: TYPESAFE_API_KEY or JEV_API_KEY, env only, never logged.
"""
from __future__ import annotations

import os
from typing import Any, Mapping

from .base import Answer, Question, argmax, noul_answer
from .shortlist import shortlist

ENDPOINT_PATH = "/v1/systemone"
KEY_VARS = ("TYPESAFE_API_KEY", "JEV_API_KEY")


def api_key() -> str | None:
    for v in KEY_VARS:
        if os.environ.get(v):
            return os.environ[v]
    return None


def auth_headers() -> dict[str, str]:
    key = api_key()
    if not key:
        raise RuntimeError(f"set one of {', '.join(KEY_VARS)}")
    return {"Authorization": f"Bearer {key}"}  # header scheme UNVERIFIED for Jev


def question_spec(q: Question) -> dict[str, Any]:
    spec: dict[str, Any] = {"type": q.type, "instructions": q.instructions}
    if q.type == "choice":
        spec["criteria"] = {o: o for o in q.options}   # label -> description
    elif q.type == "score":
        spec["criteria"] = list(q.options)             # ordered low -> high
    # noul: criteria shape not documented; omitted (UNVERIFIED)
    return spec


def build_request(state: str, questions: Mapping[str, Question]) -> dict[str, Any]:
    qs = {qid: question_spec(shortlist(q, state)) for qid, q in questions.items()}
    return {"state": {"body": state}, "questions": qs}


def parse_response(resp: Mapping[str, Any], questions: Mapping[str, Question],
                   backend: str) -> tuple[dict[str, Answer], dict | None]:
    out: dict[str, Answer] = {}
    for qid, raw in resp["answers"].items():
        q = questions[qid]
        conf = float(raw.get("confidence", 0.0))
        probs = raw.get("probabilities") or raw.get("distribution") or {}
        if q.type == "noul":
            a = noul_answer(raw["noul"], backend)
            out[qid] = Answer(a.value, a.distribution, conf, backend)
        elif q.type == "choice":
            if raw["choice"] not in q.options:
                raise ValueError(f"{qid}: backend returned unknown option {raw['choice']!r}")
            dist = {o: float(probs.get(o, 0.0)) for o in q.options} if probs else \
                {o: float(o == raw["choice"]) for o in q.options}
            out[qid] = Answer(raw["choice"], dist, conf, backend)
        else:
            # UNVERIFIED: treat `score` as 0-based expected level index.
            idx = min(len(q.options) - 1, max(0, round(float(raw["score"]))))
            dist = {o: float(probs.get(o, 0.0)) for o in q.options} if probs else \
                {o: float(i == idx) for i, o in enumerate(q.options)}
            out[qid] = Answer(q.options[idx], dist, conf, backend)
    return out, resp.get("usage")


class JevSystemOne:
    name = "jev"

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url

    def __repr__(self) -> str:
        return f"JevSystemOne(base_url={self.base_url!r}, key={'set' if api_key() else 'unset'})"

    def decide(self, state: str, questions: Mapping[str, Question]) -> dict[str, Answer]:
        raise NotImplementedError("live Jev calls disabled until the wire format is verified")

# FROZEN after session 1. Cue edits need a new labels set from a human who has not read this file.
"""Keyword-rule System One. DEV / OFFLINE CI ONLY.

Cues come from the rubric in evals/route_quality/labels.md, not from a fitted model.
Probabilities are a softmax over rule scores: well-formed, NOT calibrated.
Never cite this backend's accuracy or confidence as product evidence.
"""
from __future__ import annotations

import math
import re
from typing import Mapping

from .base import Answer, Question, argmax, noul_answer

Rules = list[tuple[str, float]]

KIND_RULES: dict[str, Rules] = {
    "debug": [
        (r"\b(fix|bug|race|deadlock|hangs?|hanging|crash\w*|segfault|leak(s|ing)?|flaky|intermittent\w*"
         r"|fails?|failing|broken|regression|contend\w*|contention|not working|root cause|invariant"
         r"|figure out why|stack overflow|oom|timeout|times out)\b", 2.0),
    ],
    "ask": [
        (r"\b(explain|what is|what's|what does|what are|how does|how do|difference between|differs?"
         r"|meaning|mean)\b", 1.5),
        (r"\bwhy\b", 1.0),
    ],
    "implement": [
        (r"\b(add|implement|build|create|refactor|rename|simplify|convert|port|extract|replace|remove"
         r"|support|endpoint|feature|wire up|integrate)\b", 1.5),
        (r"\b(write|make)\b", 0.75),
    ],
    "plan": [
        (r"\b(plan|design|outline|roadmap|architecture|strategy|proposal|rfc|steps to|migration)\b", 2.0),
    ],
    "review": [
        (r"\b(review|audit|look over|check|risky|risks?|vulnerab\w*|reachable|exploitable|injection"
         r"|correct|safe|secure|sound)\b", 1.75),
        (r"^\s*(is|are|does) (this|these|my|the)\b", 0.75),
    ],
    "research": [
        (r"\b(survey|papers?|literature|prior art|state of the art|sota|find (recent )?work|sources|cite"
         r"|citations?|compare .+ with sources|benchmarks? of)\b", 2.5),
    ],
    "ship": [
        (r"\b(brag|launch|release notes|announc\w*|tweets?|changelog|blog post|shot list|press|marketing"
         r"|landing page|share copy|demo video)\b", 3.0),
    ],
    "other": [],
}
OTHER_PRIOR = 0.5  # "other" wins only when nothing work-shaped fires

DOMAIN_RULES: dict[str, Rules] = {
    "code": [(r"(\.py|\.js|\.ts|\.go|\.rs)\b|\b(code|function|module|class|bug|tests?|api|endpoint|sql|flask"
              r"|django|git|refactor|compile\w*|traceback|mutex|thread|race|deadlock|regex|async|callback"
              r"|utils|cli|repo|pr|diff|middleware|http|parser|parsing)\b", 1.5)],
    "research": [(r"\b(papers?|literature|survey|research|sources|arxiv|state of the art)\b", 2.0)],
    "writing": [(r"\b(tweets?|blog|release notes|copy|essay|paragraph|announc\w*|shot list|docs?)\b", 1.5)],
    "data": [(r"\b(csv|dataset|dataframe|pandas|etl|database|postgres|warehouse|query|analytics)\b", 1.25)],
    "ops": [(r"\b(deploy\w*|ci|docker|kubernetes|k8s|nightly|cron|server|infra|terraform|on-?call|outage)\b", 1.25)],
    "unknown": [],
}
UNKNOWN_PRIOR = 0.5

COMPLEXITY_RULES: dict[str, Rules] = {
    "trivial": [(r"\b(rename|typo|one[- ]line|one file|bump|whitespace)\b", 2.5)],
    "small": [(r"\b(explain|what|how|why|regex|translate|small|quick)\b", 1.0)],
    "feature": [(r"\b(add|endpoint|auth\w*|feature|export|retry|with tests|integrate|convert|refactor)\b", 1.5)],
    "deep": [(r"\b(deadlock|race|invariant|concurren\w*|contend\w*|migration|multi-tenant|architecture"
              r"|security|injection|intermittent\w*|under load|split the monolith|distributed)\b", 2.0)],
    "ultracode": [(r"\b(entire (codebase|repo)|whole (codebase|repo)|from scratch|rewrite everything"
                   r"|across (all|every) (services|repos))\b", 3.0)],
}
COMPLEXITY_PRIOR = {"trivial": 0.0, "small": 0.75, "feature": 0.25, "deep": 0.0, "ultracode": -1.0}

YAGNI_RE = r"\b(framework|plugin|abstraction|generic|extensible|microservices?|future-proof|configurable|platform)\b"
TESTS_RE = r"\b(tests?|tdd|coverage|regression)\b"
KIND_TO_SKILL = {"debug": "karpathy", "implement": "superpowers", "plan": "superpowers",
                 "review": "fable-mode", "research": "feynman", "ask": "feynman", "ship": "brag",
                 "other": "none"}


def _score(text: str, rules: Rules) -> float:
    return sum(w * len(re.findall(p, text)) for p, w in rules)


def _softmax(scores: Mapping[str, float]) -> dict[str, float]:
    m = max(scores.values())
    e = {k: math.exp(v - m) for k, v in scores.items()}
    z = sum(e.values())
    return {k: v / z for k, v in e.items()}


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _choice(q: Question, scores: Mapping[str, float]) -> Answer:
    dist = _softmax({o: scores.get(o, 0.0) for o in q.options})
    v = argmax(q.options, dist)
    return Answer(v, dist, dist[v], HeuristicSystemOne.name)


class HeuristicSystemOne:
    name = "heuristic"

    def decide(self, state: str, questions: Mapping[str, Question]) -> dict[str, Answer]:
        t = state.lower()
        kind_s = {k: _score(t, r) for k, r in KIND_RULES.items()}
        kind_s["other"] = OTHER_PRIOR
        dom_s = {k: _score(t, r) for k, r in DOMAIN_RULES.items()}
        dom_s["unknown"] = UNKNOWN_PRIOR
        cx_s = {k: _score(t, r) + COMPLEXITY_PRIOR[k] for k, r in COMPLEXITY_RULES.items()}

        kind = argmax(tuple(KIND_RULES), _softmax(kind_s))
        cx_dist = _softmax(cx_s)
        levels = tuple(COMPLEXITY_RULES)
        expected_level = sum(i * cx_dist[l] for i, l in enumerate(levels))  # 0..4
        yagni_hits = len(re.findall(YAGNI_RE, t))
        wants_tests = bool(re.search(TESTS_RE, t))
        words = len(t.split())

        nouls = {
            "needs_frontier": _sigmoid(2.0 * (expected_level - 3.0)),
            "yagni": 0.85 if yagni_hits else 0.15,
            "needs_tests": 0.9 if wants_tests else (0.6 if kind in ("implement", "debug") else 0.1),
            "ambiguous": 0.6 if words < 3 else 0.2,
        }
        skill = "ponytail" if yagni_hits else KIND_TO_SKILL[kind]

        out: dict[str, Answer] = {}
        for qid, q in questions.items():
            if qid == "kind":
                out[qid] = _choice(q, kind_s)
            elif qid == "domain":
                out[qid] = _choice(q, dom_s)
            elif qid == "complexity":
                out[qid] = _choice(q, cx_s)
            elif qid == "skill_primary":
                out[qid] = _choice(q, {skill: 2.0})
            elif qid in nouls:
                out[qid] = noul_answer(nouls[qid], self.name)
            else:
                raise KeyError(f"heuristic backend has no rule for question {qid!r}")
        return out

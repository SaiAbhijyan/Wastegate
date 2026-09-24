"""System One contract: typed decisions (choice / score / noul), no text generation."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping, Protocol, Union

QType = Literal["choice", "score", "noul"]


@dataclass(frozen=True)
class Question:
    id: str
    type: QType
    instructions: str
    options: tuple[str, ...] = ()

    def __post_init__(self):
        n = len(self.options)
        if self.type == "choice" and not 2 <= n <= 255:
            raise ValueError(f"{self.id}: choice needs 2..255 options, got {n}")
        if self.type == "score" and not 2 <= n <= 10:
            raise ValueError(f"{self.id}: score needs 2..10 levels, got {n}")
        if self.type == "noul" and n:
            raise ValueError(f"{self.id}: noul takes no options")
        if self.type not in ("choice", "score", "noul"):
            raise ValueError(f"{self.id}: unknown type {self.type}")


@dataclass(frozen=True)
class Answer:
    value: Union[str, float]          # option label, or P(yes) for noul
    distribution: Mapping[str, float] = field(hash=False)  # sums to 1; noul -> {"yes", "no"}
    confidence: float                  # backend-defined; NOT comparable across backends
    backend: str


class SystemOne(Protocol):
    name: str

    def decide(self, state: str, questions: Mapping[str, Question]) -> dict[str, Answer]: ...


# Locked templates. Changing wording invalidates any calibration fitted on them.
SKILL_IDS = ("ecc", "superpowers", "ponytail", "karpathy", "feynman", "brag", "fable-mode", "caveman")

GATE_QUESTIONS: dict[str, Question] = {q.id: q for q in (
    Question("kind", "choice", "What is the primary deliverable the user wants back?",
             ("ask", "plan", "implement", "debug", "review", "research", "ship", "other")),
    Question("domain", "choice", "Which domain is this task in?",
             ("code", "research", "writing", "data", "ops", "unknown")),
    Question("complexity", "score", "How much engineering effort does this task need?",
             ("trivial", "small", "feature", "deep", "ultracode")),
    Question("needs_frontier", "noul",
             "Will a mid-tier model likely fail this task without a frontier model's help?"),
    Question("yagni", "noul", "Does this task invite adding more code or abstraction than needed?"),
    Question("needs_tests", "noul", "Should the answer include or run tests?"),
    Question("ambiguous", "noul", "Is the request too ambiguous to act on without a clarifying question?"),
    Question("skill_primary", "choice", "Which single working-style skill fits this task best?",
             SKILL_IDS + ("none",)),
)}


def noul_answer(p: float, backend: str) -> Answer:
    p = min(1.0, max(0.0, float(p)))
    return Answer(p, {"yes": p, "no": 1.0 - p}, max(p, 1.0 - p), backend)


def argmax(options: tuple[str, ...], dist: Mapping[str, float]) -> str:
    """Highest probability; ties go to the earlier option."""
    return max(options, key=lambda o: (dist.get(o, 0.0), -options.index(o)))

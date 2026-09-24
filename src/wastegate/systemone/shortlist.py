"""Cap choice cardinality before a backend call (Laya's head budget overflows past ~20)."""
from __future__ import annotations

import dataclasses
import re

from .base import Question


def shortlist(q: Question, state: str, k: int = 20) -> Question:
    if q.type != "choice" or len(q.options) <= k:
        return q
    low = state.lower()
    mentioned = [o for o in q.options if re.search(rf"\b{re.escape(o.lower())}\b", low)]
    rest = [o for o in q.options if o not in mentioned]
    keep = set((mentioned + rest)[:k])
    return dataclasses.replace(q, options=tuple(o for o in q.options if o in keep))

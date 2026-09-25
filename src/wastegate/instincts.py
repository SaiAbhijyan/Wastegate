"""Instincts v0: one atomic preference per thumbs-down note (ECC-style), injected into later composes.
No clustering, decay, or pinning yet."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from .log import redact

MAX_CHARS = 200
FILE = "instincts.jsonl"


def add_instinct(state_dir: Path, text: str, kind: Optional[str], source_turn: Optional[str]) -> dict:
    row = {"id": uuid.uuid4().hex, "text": redact(" ".join(text.split()))[:MAX_CHARS], "kind": kind,
           "confidence": 0.5, "support": 1, "source_turn": source_turn,
           "ts": datetime.now(timezone.utc).isoformat()}
    p = Path(state_dir) / FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(row) + "\n")
    return row


def load_instincts(state_dir: Path) -> list[dict]:
    p = Path(state_dir) / FILE
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def select_instincts(rows: Sequence[dict], kind: Optional[str], k: int = 3) -> list[str]:
    """Same-kind first, then the rest; newest first within each group; at most k."""
    newest = list(reversed(rows))
    ordered = [r for r in newest if r.get("kind") == kind] + [r for r in newest if r.get("kind") != kind]
    return [r["text"] for r in ordered[:k]]

"""Layer-0 turn log (JSONL). Redaction runs on every serialized line."""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

SECRET_ENV = ("TYPESAFE_API_KEY", "JEV_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
              "OPENROUTER_API_KEY", "LAYA_API_KEY")
PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
]
MASK = "[REDACTED]"


def redact(text: str) -> str:
    for var in SECRET_ENV:
        v = os.environ.get(var)
        if v and len(v) >= 6:
            text = text.replace(v, MASK)
    for p in PATTERNS:
        text = p.sub(MASK, text)
    return text


class TurnLogger:
    def __init__(self, directory: Path):
        self.path = Path(directory) / "turns.jsonl"

    def write(self, record: dict) -> dict:
        rec = {"ts": datetime.now(timezone.utc).isoformat(), "turn_id": uuid.uuid4().hex,
               "tokens": None, "usd": None, **record}
        line = redact(json.dumps(rec, default=str, sort_keys=True))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(line + "\n")
        return json.loads(line)

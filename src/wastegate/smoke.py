"""Live smoke report: raw provider usage exactly as returned, keys redacted, usd null. Not a benchmark."""
from __future__ import annotations

import json
from pathlib import Path

from .log import redact


def write_smoke_report(record: dict, out_dir: Path, date: str) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    p, n = out_dir / f"{date}-live-smoke.md", 2
    while p.exists():
        p, n = out_dir / f"{date}-live-smoke-{n}.md", n + 1
    lines = [f"# {date} live smoke", "",
             "**Wiring check only: one `wg ask --live` invocation. This is not a benchmark and not a quality claim.**", "",
             f"- prompt: {record.get('prompt')}",
             f"- tests: {json.dumps(record.get('tests'))}",
             "- usd: null (no verified price in catalog)", ""]
    for c in record.get("calls", []):
        lines += [f"## {c['role']}: {c['provider']} `{c['model_id']}` (tier {c.get('tier')})", "",
                  f"tokens_in={c['tokens_in']} tokens_out={c['tokens_out']} usd: null", "",
                  "raw usage JSON as returned:", "", "```json",
                  json.dumps(c.get("usage_raw"), indent=2, sort_keys=True), "```", ""]
    p.write_text(redact("\n".join(lines)))
    return p

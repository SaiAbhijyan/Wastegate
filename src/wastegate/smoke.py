"""Live smoke report: raw provider usage exactly as returned, keys redacted, usd null. Not a benchmark."""
from __future__ import annotations

import json
import os
from pathlib import Path

from urllib.parse import urlparse

from .log import SECRET_ENV, redact


def _host(provider: str) -> str:
    from .providers.live import ADAPTERS
    cls = ADAPTERS.get(provider)
    return urlparse(cls.url).netloc if cls is not None and getattr(cls, "url", "") else "n/a"


def write_smoke_report(record: dict, out_dir: Path, date: str) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    p, n = out_dir / f"{date}-live-smoke.md", 2
    while p.exists():
        p, n = out_dir / f"{date}-live-smoke-{n}.md", n + 1
    lines = [f"# {date} live smoke", "",
             "**wiring check only, not a benchmark.** One `wg ask --live` invocation; not a quality claim.", "",
             f"- prompt: {record.get('prompt')}",
             f"- tests: {json.dumps(record.get('tests'))}",
             "- usd: null (no verified price in catalog)", ""]
    for c in record.get("calls", []):
        lines += [f"## {c['role']}: {c['provider']} `{c['model_id']}` (tier {c.get('tier')})", "",
                  f"host: {_host(c['provider'])}", "",
                  f"tokens_in={c['tokens_in']} tokens_out={c['tokens_out']} usd: null", "",
                  "raw usage JSON as returned:", "", "```json",
                  json.dumps(c.get("usage_raw"), indent=2, sort_keys=True), "```", ""]
    body = redact("\n".join(lines))
    leaked = any(os.environ.get(v) and len(os.environ[v]) >= 6 and os.environ[v] in body for v in SECRET_ENV)
    body += f"\nredaction check: no configured key value present: {'no' if leaked else 'yes'}\n"
    p.write_text(body)
    return p

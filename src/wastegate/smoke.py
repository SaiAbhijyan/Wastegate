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


def _yn(v) -> str:
    return "n/a" if v is None else ("yes" if v else "no")


def _parsed(d, key: str) -> str:
    if not d or d.get(key) in (None, "not routed"):
        return "n/a (not routed)"
    if d.get("parse_error"):
        return f"no ({d.get(key)}: {d['parse_error']})"
    extra = ""
    if d.get("effective") and d.get("effective") != d.get(key):
        extra += f" -> {d['effective']}"
    if d.get("dropped"):
        extra += f"; {len(d['dropped'])} finding(s) dropped"
    return f"yes ({d.get(key)}{extra})"


def _ran(d) -> str:
    if not d:
        return "n/a"
    if d.get("ran"):
        return f"yes (edits: {', '.join(d.get('edits') or []) or 'none'})"
    return f"no ({d.get('reason', '')})"


def write_smoke_report(record: dict, out_dir: Path, date: str, name: str = "live-smoke") -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    p, n = out_dir / f"{date}-{name}.md", 2
    while p.exists():
        p, n = out_dir / f"{date}-{name}-{n}.md", n + 1
    lines = [f"# {date} live smoke", "",
             "**wiring + contract check, not a benchmark.** One `wg ask --live` invocation; not a quality claim.", "",
             f"- prompt: {record.get('prompt')}",
             f"- tests: {json.dumps(record.get('tests'))}",
             f"- test file changed: {_yn(record.get('test_file_changed'))}",
             f"- tester parsed: {_parsed(record.get('tester'), 'status')}",
             f"- skeptic parsed: {_parsed(record.get('skeptic'), 'verdict')}",
             f"- follow-up ran: {_ran(record.get('followup'))}",
             f"- mid escalation ran: {_ran(record.get('mid_escalation'))}",
             "- usd: null (no verified price in catalog)", ""]
    if record.get("agent"):
        a, v = record["agent"], record.get("verification") or {}
        lines += ["## agent loop", "",
                  "**wiring check only, not a benchmark.**", "",
                  f"- model: `{a.get('model_id')}` · harness: {a.get('harness')} · system prompt: {a.get('system_bytes')} B"
                  f" · max_steps: {a.get('max_steps')}",
                  f"- stop reason: {record.get('stop_reason')}",
                  f"- tool steps: " + (", ".join(f"{c['step']}:{c['tool']}" + ("" if c.get("ok", True) else "(error)")
                                               for c in record.get("tool_calls") or []) or "none"),
                  f"- VERIFICATION: {v.get('status')}" + (f" ({v.get('reason')})" if v.get("reason") else ""),
                  f"- checks: " + ("; ".join(f"{c['cmd']} → exit {c['exit']}" for c in v.get("checks") or []) or "none"),
                  ""]
    if record.get("provider_error"):
        e = record["provider_error"]
        lines += ["## provider error", "", f"HTTP {e.get('status')} (redacted body, ≤1000 chars):", "", "```text",
                  str(e.get("body")), "```", ""]
    for c in record.get("calls", []):
        lines += [f"## {c['role']}: {c['provider']} `{c['model_id']}` (tier {c.get('tier')})", "",
                  f"host: {_host(c['provider'])}", "",
                  f"tokens_in={c['tokens_in']} tokens_out={c['tokens_out']} usd: null", "",
                  "raw usage JSON as returned:", "", "```json",
                  json.dumps(c.get("usage_raw"), indent=2, sort_keys=True), "```", ""]
    body = redact("\n".join(lines))
    leaked = any(os.environ.get(v) and len(os.environ[v]) >= 6 and os.environ[v] in body for v in SECRET_ENV)
    body += f"\nredaction check: no configured key value present: {'no' if leaked else 'yes'}\n"
    p.write_text(body, encoding="utf-8")
    return p

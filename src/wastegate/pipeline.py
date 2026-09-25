"""wg ask: gate -> route -> compose -> driver -> apply edits -> tests -> skeptic -> escalate slice."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence

from .catalog import Catalog
from .compose import Composed, compose
from .escalate import escalate_slice
from .providers.base import Completion, Provider
from .router import Route, RouterConfig, route
from .skills.registry import Skill
from .systemone.base import GATE_QUESTIONS, SystemOne

FILE_BLOCK = re.compile(r"^<<<FILE (\S+)\n(.*?)\n>>>$", re.DOTALL | re.MULTILINE)
REPLACE_BLOCK = re.compile(r"^<<<REPLACE (\S+)\n(.*?)\n<<<WITH\n(.*?)<<<END$", re.DOTALL | re.MULTILINE)
ANY_EDIT = re.compile(r"^<<<(FILE|REPLACE) ", re.MULTILINE)
EDIT_FORMAT = """Edit format (the only way your changes reach the repo; paths relative to the repo root):
<<<REPLACE path/to/file.py
exact existing text (must occur exactly once)
<<<WITH
new text
<<<END
To create or fully rewrite a file:
<<<FILE path/to/file.py
full file contents
>>>
"""
CONTEXT_SKIP_DIRS = {".git", ".wastegate", "__pycache__", ".venv", "venv", "node_modules", ".pytest_cache", "results"}
CONTEXT_SKIP_NAMES = re.compile(r"^(\..*|id_rsa.*|id_ed25519.*|.*\.(pem|key|p12|pfx)|credentials.*|secrets?\..*)$")
TESTER = re.compile(r"^\s*TESTER:\s*(pass|fail)\s*$", re.IGNORECASE | re.MULTILINE)
VERDICT = re.compile(r"^\s*VERDICT:\s*(approve|reject)\s*$", re.IGNORECASE | re.MULTILINE)


class UnsafeEdit(Exception):
    pass


class EditError(UnsafeEdit):
    """Edit cannot be applied exactly (missing file, old text absent or ambiguous). Nothing written."""


@dataclass
class TurnResult:
    record: dict
    transcript: list[str] = field(default_factory=list)


def _guard(rel: str, root: Path) -> Path:
    p = Path(rel)
    if p.is_absolute() or not (root / p).resolve().is_relative_to(root):
        raise UnsafeEdit(f"edit path escapes repo: {rel}")
    return root / p


def parse_edits(text: str, repo: Path) -> list[tuple[str, str]]:
    """Resolve every FILE / REPLACE block, in document order, entirely in memory.
    Returns (rel, final_content) per touched file. Raises before anything is written."""
    root = repo.resolve()
    blocks = sorted([(m.start(), "file", m) for m in FILE_BLOCK.finditer(text)]
                    + [(m.start(), "replace", m) for m in REPLACE_BLOCK.finditer(text)], key=lambda b: b[0])
    content: dict[str, str] = {}
    for _, kind, m in blocks:
        rel = m.group(1)
        path = _guard(rel, root)
        if kind == "file":
            content[rel] = m.group(2) + "\n"
            continue
        old, new = m.group(2), m.group(3)
        new = new[:-1] if new.endswith("\n") else new
        if rel not in content:
            if not path.is_file():
                raise EditError(f"REPLACE target does not exist: {rel}")
            content[rel] = path.read_text()
        n = content[rel].count(old)
        if n != 1:
            raise EditError(f"REPLACE old text in {rel} " + ("not found" if n == 0 else f"found {n} times"))
        content[rel] = content[rel].replace(old, new, 1)
    return list(content.items())


def apply_edits(repo: Path, edits: list[tuple[str, str]]) -> None:
    for rel, body in edits:
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(body)


def repo_context(repo: Path, budget: int = 24_000, max_file: int = 8_000) -> str:
    """File list + small text files for the driver. Skips dotfiles, key-like files, logs; redacted; capped."""
    from .log import redact
    root = repo.resolve()
    files = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if any(part in CONTEXT_SKIP_DIRS or CONTEXT_SKIP_NAMES.match(part) for part in rel.parts):
            continue
        if p.is_file():
            files.append(p)
    parts = ["<repo files>\n" + "\n".join(str(p.relative_to(root)) for p in files) + "\n</repo files>\n"]
    used = len(parts[0].encode())
    for p in files:
        if p.stat().st_size > max_file:
            continue
        try:
            body = p.read_text()
        except UnicodeDecodeError:
            continue
        block = f"<file path=\"{p.relative_to(root)}\">\n{body}</file>\n"
        if used + len(block.encode()) > budget:
            break
        parts.append(block)
        used += len(block.encode())
    return redact("".join(parts))[:budget]


def _findings(text: str) -> list[str]:
    return [l.strip()[2:] for l in text.splitlines() if l.strip().startswith("- ")]


def parse_skeptic(text: str) -> tuple[str, list[str]]:
    m = VERDICT.search(text)
    return (m.group(1).lower() if m else "invalid"), _findings(text)


def parse_tester(text: str) -> tuple[str, list[str]]:
    m = TESTER.search(text)
    return (m.group(1).lower() if m else "invalid"), _findings(text)


def run_tests(repo: Path) -> int:
    # No .pyc writes: a same-size, same-second edit could otherwise reuse stale bytecode.
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                              cwd=repo, env=env, capture_output=True, timeout=300).returncode
    except subprocess.TimeoutExpired:
        return 124


def _call(role: str, tier: str, c: Completion) -> dict:
    u = c.usage
    # usd stays None: no catalog price is verified (docs/PHASE2.md).
    return {"role": role, "tier": tier, "provider": c.provider, "model_id": c.model_id,
            "tokens_in": u.input_tokens if u else None, "tokens_out": u.output_tokens if u else None,
            "usd": None, "usage_raw": (c.raw or {}).get("usage")}


def _total(calls: list[dict], key: str):
    vals = [c[key] for c in calls]
    return sum(vals) if vals and all(v is not None for v in vals) else None


@dataclass
class Plan:
    gate: dict
    route: Route
    composed: Composed
    record: dict
    transcript: list[str]


def plan_turn(prompt: str, s1: SystemOne, catalog: Catalog, cfg: RouterConfig,
              registry: Mapping[str, Skill], instincts: Sequence[str] = ()) -> Plan:
    """gate -> route -> compose. Shared by wg ask and wg chat. No provider calls."""
    gate = s1.decide(prompt, GATE_QUESTIONS)
    r = route(gate, catalog, cfg)
    c = compose(r, prompt, registry, instincts=instincts)
    record = {"prompt": prompt, "backend": s1.name, "route": r.to_dict(),
              "gate": {k: {"value": a.value, "confidence": a.confidence} for k, a in gate.items()},
              "skills": [{"id": s, "sha": registry[s].sha256} for s in c.included],
              "instincts": list(c.instincts), "calls": []}
    t = [f"gate: kind={gate['kind'].value} complexity={gate['complexity'].value} (backend={s1.name}, uncalibrated)",
         f"driver: {r.driver.tier} {r.driver.model} budget={r.driver.budget_tokens}"]
    t += [f"  + {s.role}: {s.tier} {s.model}" for s in r.specialists]
    t.append(f"skills composed: {', '.join(c.included)} ({len(c.system.encode())} bytes)"
             + (f"; dropped: {', '.join(c.dropped)}" if c.dropped else ""))
    if c.instincts:
        t.append(f"instincts injected: {len(c.instincts)}")
    return Plan(gate, r, c, record, t)


def driver_request(plan: Plan, prompt: str, repo: Optional[Path]) -> tuple[str, str]:
    """(system, user) for the driver. With a repo: edit format + repo context."""
    if repo is None:
        return plan.composed.system, prompt
    return plan.composed.system + "\n" + EDIT_FORMAT, prompt + "\n\n" + repo_context(repo)


def run_ask(prompt: str, repo: Path, s1: SystemOne, catalog: Catalog, cfg: RouterConfig,
            registry: Mapping[str, Skill], mode: str = "dry-run",
            providers: Optional[Callable[[str, Optional[str]], Provider]] = None,
            instincts: Sequence[str] = ()) -> TurnResult:
    """providers=None means dry-run: no generation."""
    plan = plan_turn(prompt, s1, catalog, cfg, registry, instincts)
    r, c = plan.route, plan.composed
    out = TurnResult(plan.record, plan.transcript)
    t = out.transcript
    if providers is None:
        out.record.update(mode="dry-run", generation="")
        t.append("generation: (empty, dry-run)")
        return out

    out.record["mode"] = mode
    sk = next((s for s in r.specialists if s.role == "skeptic"), None)
    ts = next((s for s in r.specialists if s.role == "tester"), None)
    # resolve every provider before any write
    drv_p = providers("driver", r.driver.model)
    sk_p = providers("skeptic", sk.model) if sk is not None else None
    ts_p, tester = None, {"status": "not routed", "findings": [], "reason": ""}
    if ts is not None:
        try:
            ts_p = providers("tester", ts.model)
        except FileNotFoundError as e:  # missing tester reply = skip, not abort
            tester = {"status": "skipped", "findings": [], "reason": str(e)}
    system, user = driver_request(plan, prompt, repo)
    drv = drv_p.complete(r.driver.model, system, [{"role": "user", "content": user}], r.driver.budget_tokens)
    calls = [_call("driver", r.driver.tier, drv)]
    edits = parse_edits(drv.text, repo)  # raises before any write
    before = run_tests(repo)
    apply_edits(repo, edits)
    after = run_tests(repo)
    t.append(f"edits: {', '.join(e for e, _ in edits) or '(none)'}")
    t.append(f"tests: before={before} after={after}")

    unresolved: list[str] = []
    if ts_p is not None:
        tmsg = [{"role": "user", "content": f"Task: {prompt}\nEdits: {[e for e, _ in edits]}\n"
                                            f"Tests before={before} after={after}\nReply TESTER: pass|fail."}]
        tc = ts_p.complete(ts.model, "Role: tester.", tmsg, ts.budget_tokens)
        calls.append(_call("tester", ts.tier, tc))
        status, tf = parse_tester(tc.text)
        tester = {"status": status, "findings": tf, "reason": ""}
        if status != "pass":
            unresolved += tf or [f"tester reply {status}"]
        t.append(f"tester ({ts.tier} {ts.model}): {status}" + "".join(f"\n  - {f}" for f in tf))
    elif ts is not None:
        t.append(f"tester: {tester['status']} ({tester['reason']})")

    verdict, findings = None, []
    if sk is not None:
        review_msg = [{"role": "user", "content": f"Task: {prompt}\nEdits: {[e for e, _ in edits]}\n"
                                                  f"Tests before={before} after={after}\nRefute or approve."}]
        skc = sk_p.complete(sk.model, "Role: skeptic.", review_msg, sk.budget_tokens)
        calls.append(_call("skeptic", sk.tier, skc))
        verdict, findings = parse_skeptic(skc.text)
        if verdict != "approve":
            unresolved += findings or ["skeptic reply unparseable"]
        t.append(f"skeptic ({sk.tier} {sk.model}): {verdict}" + "".join(f"\n  - {f}" for f in findings))
    if after != 0:
        unresolved.append(f"tests still failing (exit {after})")

    sl, why = escalate_slice(unresolved, r, catalog)
    t.append(f"escalation: {why}" + (f" -> {sl.model_id}" if sl else ""))
    if unresolved and sl is None:
        t.append("unresolved (reported to user):" + "".join(f"\n  - {u}" for u in unresolved))

    out.record.update(
        calls=calls, provider=drv.provider, model_id=drv.model_id,
        tokens_in=_total(calls, "tokens_in"), tokens_out=_total(calls, "tokens_out"), usd=_total(calls, "usd"),
        edits=[e for e, _ in edits], tests={"before": before, "after": after},
        tester=tester, skeptic={"verdict": verdict, "findings": findings}, unresolved=unresolved,
        escalation={"slice": asdict(sl) if sl else None, "reason": why})
    t.append(f"tokens in/out: {out.record['tokens_in']}/{out.record['tokens_out']} (provider-reported; null if any call lacked usage); usd: null (no verified price)")
    return out

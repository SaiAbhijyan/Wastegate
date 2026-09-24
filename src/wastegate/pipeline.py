"""wg ask: gate -> route -> compose -> driver -> apply edits -> tests -> skeptic -> escalate slice."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Optional

from .catalog import Catalog
from .compose import compose
from .escalate import escalate_slice
from .providers.base import Completion, Provider
from .router import RouterConfig, route
from .skills.registry import Skill
from .systemone.base import GATE_QUESTIONS, SystemOne

FILE_BLOCK = re.compile(r"^<<<FILE (\S+)\n(.*?)\n>>>$", re.DOTALL | re.MULTILINE)
VERDICT = re.compile(r"^\s*VERDICT:\s*(approve|reject)\s*$", re.IGNORECASE | re.MULTILINE)


class UnsafeEdit(Exception):
    pass


@dataclass
class TurnResult:
    record: dict
    transcript: list[str] = field(default_factory=list)


def parse_edits(text: str, repo: Path) -> list[tuple[str, str]]:
    """All-or-nothing: every path must be relative and resolve inside repo."""
    root = repo.resolve()
    edits = []
    for rel, body in FILE_BLOCK.findall(text):
        p = Path(rel)
        if p.is_absolute() or not (root / p).resolve().is_relative_to(root):
            raise UnsafeEdit(f"edit path escapes repo: {rel}")
        edits.append((rel, body + "\n"))
    return edits


def parse_skeptic(text: str) -> tuple[str, list[str]]:
    m = VERDICT.search(text)
    findings = [l.strip()[2:] for l in text.splitlines() if l.strip().startswith("- ")]
    return (m.group(1).lower() if m else "invalid"), findings


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
            "usd": None}


def _total(calls: list[dict], key: str):
    vals = [c[key] for c in calls]
    return sum(vals) if vals and all(v is not None for v in vals) else None


def run_ask(prompt: str, repo: Path, s1: SystemOne, catalog: Catalog, cfg: RouterConfig,
            registry: Mapping[str, Skill], providers: Optional[Callable[[str], Provider]] = None) -> TurnResult:
    """providers=None means dry-run: no generation."""
    gate = s1.decide(prompt, GATE_QUESTIONS)
    r = route(gate, catalog, cfg)
    c = compose(r, prompt, registry)
    out = TurnResult({"prompt": prompt, "backend": s1.name, "route": r.to_dict(),
                      "gate": {k: {"value": a.value, "confidence": a.confidence} for k, a in gate.items()},
                      "skills": [{"id": s, "sha": registry[s].sha256} for s in c.included],
                      "calls": []})
    t = out.transcript
    t.append(f"gate: kind={gate['kind'].value} complexity={gate['complexity'].value} (backend={s1.name}, uncalibrated)")
    t.append(f"driver: {r.driver.tier} {r.driver.model} budget={r.driver.budget_tokens}")
    t += [f"  + {s.role}: {s.tier} {s.model}" for s in r.specialists]
    t.append(f"skills composed: {', '.join(c.included)} ({len(c.system.encode())} bytes)"
             + (f"; dropped: {', '.join(c.dropped)}" if c.dropped else ""))
    if providers is None:
        out.record.update(mode="dry-run", generation="")
        t.append("generation: (empty, dry-run)")
        return out

    out.record["mode"] = "mock"
    sk = next((s for s in r.specialists if s.role == "skeptic"), None)
    drv_p = providers("driver")                      # resolve every provider before any write
    sk_p = providers("skeptic") if sk is not None else None
    msgs = [{"role": "user", "content": prompt}]
    drv = drv_p.complete(r.driver.model, c.system, msgs, r.driver.budget_tokens)
    calls = [_call("driver", r.driver.tier, drv)]
    edits = parse_edits(drv.text, repo)  # raises before any write
    before = run_tests(repo)
    for rel, body in edits:
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(body)
    after = run_tests(repo)
    t.append(f"edits: {', '.join(e for e, _ in edits) or '(none)'}")
    t.append(f"tests: before={before} after={after}")

    unresolved: list[str] = []
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
        skeptic={"verdict": verdict, "findings": findings},
        escalation={"slice": asdict(sl) if sl else None, "reason": why})
    t.append("tokens/usd: null (mock provider reports no usage)")
    return out

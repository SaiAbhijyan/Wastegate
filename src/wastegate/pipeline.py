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
from .instincts import select_instincts
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
def _contract(word: str, choices: str) -> re.Pattern:
    # Tolerates markdown decoration (**, `, _) and a trailing period; first matching line wins.
    return re.compile(rf"^[ \t]*[*`_]*[ \t]*{word}:[ \t]*[*`_]*[ \t]*({choices})\b[*`_. \t]*$",
                      re.IGNORECASE | re.MULTILINE)


TESTER = _contract("TESTER", "pass|fail")
VERDICT = _contract("VERDICT", "approve|reject")
TESTER_SYSTEM = ("Role: tester.\n"
                 "Output contract: the first line of your reply must be exactly `TESTER: pass` or `TESTER: fail`.\n"
                 "After it, only lines starting with `- ` (one finding each). No preamble, no markdown, no other text.")
SKEPTIC_SYSTEM = ("Role: skeptic. Judge ONLY the diff (original vs edited files) and the test results against "
                  "the user's request.\n"
                  "Do not invent requirements: no new error handling, validation, type hints, docstrings, logging "
                  "or features unless the user asked for them or the original files already had them.\n"
                  "Output contract: the first line of your reply must be exactly `VERDICT: approve` or `VERDICT: reject`.\n"
                  "After it, only lines starting with `- `; each finding must start with a file path, "
                  "e.g. `- tests/test_x.py: ...`. No preamble, no markdown, no other text.")
FOLLOWUP_TEXT = ("add or update a test file only; do not re-litigate the implementation unless tests still fail. "
                 "Use the same edit format.")
ESCALATE_SYSTEM = ("Role: escalation. Resolve ONLY the unresolved items listed by the user, with the smallest edits. "
                   "Do not change anything else.\n")
FINDING_PATH = re.compile(r"^\s*`?([\w./-]+\.\w+|[\w.-]+/[\w./-]+)`?\s*:")
SPECULATIVE = re.compile(r"\b(validat\w*|type[- ]?check\w*|type hints?|docstrings?|error handling|error messages?"
                         r"|raises?|exceptions?|backward[- ]compat\w*|non[- ]numeric|edge[- ]cases?|logging"
                         r"|sanitiz\w*)\b", re.IGNORECASE)
TEST_INSTRUCTION = ("The user asked for a test: add or update a test file (e.g. under tests/) that fails before "
                    "your fix and passes after; do not only patch the implementation.\n")
WANTS_TEST = re.compile(r"\bregression tests?\b|\b(add|write|with|include|create)\b[^.\n]{0,40}\btests?\b",
                        re.IGNORECASE)
TEST_PATH = re.compile(r"(^|/)(tests?/|test_[^/]*\.py$|[^/]*_test\.py$)")


class UnsafeEdit(Exception):
    pass


class RepoError(Exception):
    """--repo is not a usable directory."""


def validate_repo(path: Path) -> Path:
    if not Path(path).is_dir():
        raise RepoError(f"repo not a directory: {path}")
    return Path(path)


class EditError(UnsafeEdit):
    """Edit cannot be applied exactly (missing file, old text absent or ambiguous). Nothing written."""


@dataclass
class TurnResult:
    record: dict
    transcript: list[str] = field(default_factory=list)
    driver_text: Optional[str] = None  # redacted + capped; None = no generation (dry-run)


DRIVER_TEXT_CAP = 4_000


def cap_text(text: str, limit: Optional[int] = DRIVER_TEXT_CAP) -> str:
    """Redact first, then truncate, so a cut can never leave an unredacted key fragment. limit=None: no cap."""
    from .log import redact
    return redact(text)[:limit]


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
            content[rel] = path.read_text(encoding="utf-8")
        n = content[rel].count(old)
        if n != 1:
            raise EditError(f"REPLACE old text in {rel} " + ("not found" if n == 0 else f"found {n} times"))
        content[rel] = content[rel].replace(old, new, 1)
    return list(content.items())


def apply_edits(repo: Path, edits: list[tuple[str, str]]) -> None:
    for rel, body in edits:
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(body, encoding="utf-8")


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
    parts = ["<repo files>\n" + "\n".join(p.relative_to(root).as_posix() for p in files) + "\n</repo files>\n"]
    used = len(parts[0].encode())
    for p in files:
        if p.stat().st_size > max_file:
            continue
        try:
            body = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        block = f"<file path=\"{p.relative_to(root).as_posix()}\">\n{body}</file>\n"
        if used + len(block.encode()) > budget:
            break
        parts.append(block)
        used += len(block.encode())
    return redact("".join(parts))[:budget]


def _findings(text: str) -> list[str]:
    return [l.strip()[2:] for l in text.splitlines() if l.strip().startswith("- ")]


def _parse_contract(pat: re.Pattern, text: str) -> tuple[str, list[str]]:
    """First contract line anywhere in the reply; findings are the `- ` lines after it only."""
    m = pat.search(text)
    if not m:
        return "invalid", []
    return m.group(1).lower(), _findings(text[m.end():])


def parse_skeptic(text: str) -> tuple[str, list[str]]:
    return _parse_contract(VERDICT, text)


def parse_tester(text: str) -> tuple[str, list[str]]:
    return _parse_contract(TESTER, text)


def scope_filter(findings: list[str], prompt: str, originals: Mapping[str, str]) -> tuple[list[str], list[dict]]:
    """Keep findings that cite a path and do not demand unrequested extras (validation, error handling, ...)
    absent from both the user's request and the original files."""
    allowed = (prompt + "\n" + "\n".join(originals.values())).lower()
    kept, dropped = [], []
    for f in findings:
        if not FINDING_PATH.match(f):
            dropped.append({"finding": f, "reason": "no file path"})
            continue
        extra = [m.group(0).lower() for m in SPECULATIVE.finditer(f) if m.group(0).lower()[:6] not in allowed]
        if extra:
            dropped.append({"finding": f, "reason": f"unrequested scope: {', '.join(extra)}"})
            continue
        kept.append(f)
    return kept, dropped


def wants_test(prompt: str) -> bool:
    return bool(WANTS_TEST.search(prompt))


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
    raw_usage = (c.raw or {}).get("usage")
    reasoning = ((raw_usage or {}).get("completion_tokens_details") or {}).get("reasoning_tokens")
    # usd stays None: no catalog price is verified (docs/PHASE2.md).
    return {"role": role, "tier": tier, "provider": c.provider, "model_id": c.model_id,
            "tokens_in": u.input_tokens if u else None, "tokens_out": u.output_tokens if u else None,
            "reasoning_tokens": reasoning, "usd": None, "usage_raw": raw_usage}


def _parse_error(label: str, call: dict, budget: int) -> str:
    msg = f"no {label}: line in reply"
    if call["tokens_out"] is not None and call["tokens_out"] >= budget:
        msg += f" (hit max_tokens={budget}; reasoning_tokens={call['reasoning_tokens']})"
    return msg


def _review_brief(prompt: str, originals: Mapping[str, Optional[str]], repo: Path, before: int, after: int,
                  cap: int = 6_000) -> str:
    from .log import redact
    orig = "".join(f"<original path=\"{rel}\">\n{text if text is not None else '(new file)'}</original>\n"
                   for rel, text in originals.items())
    new = "".join(f"<edited path=\"{rel}\">\n{(repo / rel).read_text(encoding='utf-8')}</edited>\n" for rel in originals)
    return redact(f"User request: {prompt}\nOriginal files:\n{orig[:cap]}\nEdited files:\n{new[:cap]}\n"
                  f"Repo tests exit code: before={before} after={after} (0 = pass)\n")


def _snapshot(repo: Path, edits: list[tuple[str, str]], originals: dict) -> None:
    for rel, _ in edits:
        if rel not in originals:
            p = repo / rel
            originals[rel] = p.read_text(encoding="utf-8") if p.is_file() else None


def run_followup(prompt: str, touched: list[str], before: int, after: int, fu_p, why_fu: str, model: str,
                 tier: str, budget: int, system: str, msgs: list[dict], repo: Path,
                 originals: dict) -> tuple[dict, Optional[dict], int]:
    """One-shot driver follow-up for a missing test file (shared by ask and chat).
    msgs must end with the driver's assistant reply. Mutates `touched`/`originals`; returns (followup, call, after)."""
    followup = {"ran": False, "reason": "", "edits": [], "error": None}
    if not wants_test(prompt):
        followup["reason"] = "no test requested"
    elif any(TEST_PATH.search(e) for e in touched):
        followup["reason"] = "driver already changed a test file"
    elif before == 0:
        followup["reason"] = "repo tests were passing from the start"
    elif fu_p is None:
        followup["reason"] = f"follow-up provider unavailable: {why_fu}"
    else:
        fmsgs = msgs + [{"role": "user", "content": FOLLOWUP_TEXT + f"\nRepo tests after your change: exit {after}."}]
        fc = fu_p.complete(model, system, fmsgs, budget)
        followup["ran"] = True
        followup["text"] = cap_text(fc.text)
        try:
            fedits = parse_edits(fc.text, repo)
        except UnsafeEdit as e:
            followup["error"] = str(e)
            fedits = []
        _snapshot(repo, fedits, originals)
        apply_edits(repo, fedits)
        touched += [e for e, _ in fedits if e not in touched]
        followup["edits"] = [e for e, _ in fedits]
        if fedits:
            after = run_tests(repo)
        return followup, _call("driver_followup", tier, fc), after
    return followup, None, after


def followup_line(followup: dict, after: int) -> str:
    return (f"follow-up (test file): edits {', '.join(followup['edits']) or '(none)'}"
            + (f" [rejected: {followup['error']}]" if followup["error"] else "") + f"; tests after={after}")


def _try_provider(providers, role: str, model_id: str):
    """Optional role (mock reply file may be absent): None + reason instead of an error."""
    try:
        return providers(role, model_id), ""
    except FileNotFoundError as e:
        return None, str(e)


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
              registry: Mapping[str, Skill], instincts: Sequence[dict] = ()) -> Plan:
    """gate -> route -> compose. Shared by wg ask and wg chat. No provider calls.
    instincts: stored rows; up to 3 relevant to the gated kind are injected."""
    gate = s1.decide(prompt, GATE_QUESTIONS)
    r = route(gate, catalog, cfg)
    c = compose(r, prompt, registry, instincts=select_instincts(instincts, str(gate["kind"].value)))
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
    system = plan.composed.system + "\n" + EDIT_FORMAT + (TEST_INSTRUCTION if wants_test(prompt) else "")
    return system, prompt + "\n\n" + repo_context(repo)


def run_ask(prompt: str, repo: Path, s1: SystemOne, catalog: Catalog, cfg: RouterConfig,
            registry: Mapping[str, Skill], mode: str = "dry-run",
            providers: Optional[Callable[[str, Optional[str]], Provider]] = None,
            instincts: Sequence[dict] = ()) -> TurnResult:
    """providers=None means dry-run: no generation."""
    plan = plan_turn(prompt, s1, catalog, cfg, registry, instincts)
    r, c = plan.route, plan.composed
    out = TurnResult(plan.record, plan.transcript)
    t = out.transcript
    if providers is None:
        out.record.update(mode="dry-run", generation="", driver_text=None)
        t.append("generation: (empty, dry-run)")
        return out

    out.record["mode"] = mode
    sk = next((s for s in r.specialists if s.role == "skeptic"), None)
    ts = next((s for s in r.specialists if s.role == "tester"), None)
    mid = catalog.first("mid")
    # resolve every provider before any write
    drv_p = providers("driver", r.driver.model)
    sk_p = providers("skeptic", sk.model) if sk is not None else None
    ts_p, tester = None, {"status": "not routed", "findings": [], "reason": "", "parse_error": None}
    if ts is not None:
        ts_p, why_ts = _try_provider(providers, "tester", ts.model)
        if ts_p is None:  # missing tester reply = skip, not abort
            tester = {"status": "skipped", "findings": [], "reason": why_ts, "parse_error": None}
    fu_p, why_fu = _try_provider(providers, "driver_followup", r.driver.model)
    esc_p, why_esc = (_try_provider(providers, "escalate", mid.id) if mid is not None
                      else (None, "no mid model in catalog"))

    system, user = driver_request(plan, prompt, repo)
    msgs = [{"role": "user", "content": user}]
    drv = drv_p.complete(r.driver.model, system, msgs, r.driver.budget_tokens)
    calls = [_call("driver", r.driver.tier, drv)]
    out.driver_text = cap_text(drv.text, limit=None)       # full, redacted: for the terminal
    out.record["driver_text"] = cap_text(drv.text)          # capped, redacted: for the log
    edits = parse_edits(drv.text, repo)  # raises before any write
    originals: dict[str, Optional[str]] = {}
    touched: list[str] = []
    before = run_tests(repo)
    _snapshot(repo, edits, originals)
    apply_edits(repo, edits)
    touched += [e for e, _ in edits if e not in touched]
    after = run_tests(repo)
    t.append(f"edits: {', '.join(e for e, _ in edits) or '(none)'}")
    t.append(f"tests: before={before} after={after}")

    # 1) one follow-up when a test was requested but none was written
    followup, fcall, after = run_followup(prompt, touched, before, after, fu_p, why_fu, r.driver.model,
                                          r.driver.tier, r.driver.budget_tokens, system,
                                          msgs + [{"role": "assistant", "content": drv.text}], repo, originals)
    if fcall is not None:
        calls.append(fcall)
    if followup["ran"]:
        t.append(followup_line(followup, after))

    unresolved: list[str] = []
    brief = _review_brief(prompt, originals, repo, before, after)
    if ts_p is not None:
        tc = ts_p.complete(ts.model, TESTER_SYSTEM, [{"role": "user", "content": brief + "Reply per the contract."}],
                           ts.budget_tokens)
        tcall = _call("tester", ts.tier, tc)
        calls.append(tcall)
        status, tf = parse_tester(tc.text)
        if status == "invalid":  # contract missed: skip, do not guess
            tester = {"status": "skipped", "findings": [], "reason": "",
                      "parse_error": _parse_error("TESTER", tcall, ts.budget_tokens)}
        else:
            tester = {"status": status, "findings": tf, "reason": "", "parse_error": None}
            if status == "fail":
                unresolved += tf or ["tester reported fail without findings"]
        t.append(f"tester ({ts.tier} {ts.model}): {tester['status']}"
                 + (f" [{tester['parse_error']}]" if tester["parse_error"] else "")
                 + "".join(f"\n  - {f}" for f in tester["findings"]))
    elif ts is not None:
        t.append(f"tester: {tester['status']} ({tester['reason']})")

    # 2) skeptic, scope-guarded
    skeptic = {"verdict": None, "effective": None, "findings": [], "kept": [], "dropped": [], "parse_error": None}
    if sk is not None:
        skc = sk_p.complete(sk.model, SKEPTIC_SYSTEM, [{"role": "user", "content": brief + "Reply per the contract."}],
                            sk.budget_tokens)
        scall = _call("skeptic", sk.tier, skc)
        calls.append(scall)
        verdict, findings = parse_skeptic(skc.text)
        skeptic["findings"] = findings
        if verdict == "invalid":  # contract missed: fail closed
            err = _parse_error("VERDICT", scall, sk.budget_tokens)
            skeptic.update(verdict="reject", effective="reject", parse_error=err)
            unresolved.append(f"skeptic reply unparseable ({err})")
        elif verdict == "reject":
            kept, dropped = scope_filter(findings, prompt, {k: v for k, v in originals.items() if v})
            skeptic.update(verdict="reject", kept=kept, dropped=dropped)
            if kept:
                skeptic["effective"] = "reject"
                unresolved += kept
            elif findings:
                skeptic["effective"] = "dismissed"  # every finding was pathless or out of scope
            else:
                skeptic["effective"] = "reject"
                unresolved.append("skeptic rejected without findings")
        else:
            skeptic.update(verdict=verdict, effective=verdict)
        t.append(f"skeptic ({sk.tier} {sk.model}): {skeptic['verdict']}"
                 + (f" -> {skeptic['effective']}" if skeptic["effective"] != skeptic["verdict"] else "")
                 + (f" [{skeptic['parse_error']}]" if skeptic["parse_error"] else "")
                 + "".join(f"\n  - {f}" for f in (skeptic["kept"] or findings))
                 + "".join(f"\n  x dropped ({d['reason']}): {d['finding']}" for d in skeptic["dropped"]))
    if after != 0:
        unresolved.append(f"tests still failing (exit {after})")

    sl, why = escalate_slice(unresolved, r, catalog)
    t.append(f"escalation: {why}" + (f" -> {sl.model_id}" if sl else ""))

    # 3) no frontier slice: one pass on the mid model already in this (key/paid-filtered) catalog
    mid_esc = {"ran": False, "model_id": None, "reason": "", "edits": [], "tests_after": None,
               "addressed_unverified": [], "error": None}
    if not unresolved:
        mid_esc["reason"] = "nothing unresolved"
    elif sl is not None:
        mid_esc["reason"] = "frontier slice selected"
    elif esc_p is None:
        mid_esc["reason"] = why_esc
    else:
        items = "".join(f"- {u}\n" for u in unresolved)
        euser = (f"User request: {prompt}\nUnresolved items to fix:\n{items}\n" + repo_context(repo))
        ec = esc_p.complete(mid.id, ESCALATE_SYSTEM + EDIT_FORMAT, [{"role": "user", "content": euser}],
                            r.driver.budget_tokens)
        calls.append(_call("escalate", mid.tier, ec))
        mid_esc.update(ran=True, model_id=mid.id)
        try:
            eedits = parse_edits(ec.text, repo)
        except UnsafeEdit as e:
            mid_esc["error"] = str(e)
            eedits = []
        _snapshot(repo, eedits, originals)
        apply_edits(repo, eedits)
        touched += [e for e, _ in eedits if e not in touched]
        mid_esc["edits"] = [e for e, _ in eedits]
        after = run_tests(repo) if eedits else after
        mid_esc["tests_after"] = after
        if eedits and after == 0:
            mid_esc["addressed_unverified"] = unresolved  # not re-reviewed (one pass cap)
            unresolved = []
        elif after != 0 and not any(u.startswith("tests still failing") for u in unresolved):
            unresolved.append(f"tests still failing (exit {after})")
        t.append(f"mid escalation ({mid.tier} {mid.id}): edits {', '.join(mid_esc['edits']) or '(none)'}"
                 + (f" [rejected: {mid_esc['error']}]" if mid_esc["error"] else "")
                 + f"; tests after={after}" + ("; items addressed, not re-reviewed" if not unresolved else ""))
    if unresolved:
        t.append("unresolved (reported to user):" + "".join(f"\n  - {u}" for u in unresolved))

    out.record.update(
        calls=calls, provider=drv.provider, model_id=drv.model_id,
        tokens_in=_total(calls, "tokens_in"), tokens_out=_total(calls, "tokens_out"), usd=_total(calls, "usd"),
        edits=touched, tests={"before": before, "after": after},
        test_file_changed=any(TEST_PATH.search(e) for e in touched),
        followup=followup, tester=tester, skeptic=skeptic, unresolved=unresolved,
        escalation={"slice": asdict(sl) if sl else None, "reason": why}, mid_escalation=mid_esc)
    t.append(f"tokens in/out: {out.record['tokens_in']}/{out.record['tokens_out']} (provider-reported; null if any call lacked usage); usd: null (no verified price)")
    return out

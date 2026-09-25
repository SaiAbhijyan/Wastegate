"""Agent tool loop (one action per model reply) + verification gate enforced in code.

The model never gets to declare success: VERIFICATION is computed here from a test run that happened
after the last edit (docs/AGENT.md).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .agent_tools import PYTEST_CMD, ToolError, is_test_command, tool_grep, tool_pytest, tool_read, tool_shell
from .log import redact
from .pipeline import (CONTEXT_SKIP_DIRS, CONTEXT_SKIP_NAMES, EDIT_FORMAT, FILE_BLOCK, REPLACE_BLOCK, TEST_PATH,
                       UnsafeEdit, _call, _snapshot, apply_edits, parse_edits)
from .skills.registry import builtin_root
from .systemone.agent_gate import AgentPlan, load_harness  # noqa: F401  (re-exported)

REPAIR_CAP = 5
RESULT_CAP = 4_000
TOOL_BLOCK = re.compile(r"^<<<TOOL (\w+)[ \t]*\n(.*?)^>>>[ \t]*$", re.DOTALL | re.MULTILINE)
DONE_BLOCK = re.compile(r"^<<<DONE[ \t]*\n(.*?)^>>>[ \t]*$", re.DOTALL | re.MULTILINE)
NUDGE = ("VERIFICATION GATE: you edited files but did not run the tests after your last edit. "
         "Reply with <<<TOOL pytest\n>>> now. Do not claim success without a fresh passing run.")
SKIP_MARKERS = re.compile(r"pytest\.mark\.(skip|xfail)|@unittest\.skip|\bxfail\b|\.only\(")
SUPPRESSIONS = re.compile(r"#\s*type:\s*ignore|#\s*noqa|except[^:\n]*:\s*pass\b")
TEST_LINE = re.compile(r"^\s*(def test_|async def test_|assert\b)")


def harness_body() -> str:
    """verification-harness SKILL.md below its frontmatter (the skill says to paste exactly that part)."""
    text = (builtin_root() / "verification-harness" / "SKILL.md").read_text()
    return text.split("---\n", 2)[2] if text.startswith("---\n") else text


def repo_file_list(repo: Path, cap: int = 300) -> list[str]:
    root = repo.resolve()
    out = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if any(part in CONTEXT_SKIP_DIRS or CONTEXT_SKIP_NAMES.match(part) for part in rel.parts):
            continue
        if p.is_file():
            out.append(rel.as_posix())
        if len(out) >= cap:
            break
    return out


def protocol(tools: tuple[str, ...]) -> str:
    lines = ["Agent protocol: reply with exactly ONE action per message, then stop and wait for the result.",
             "Available tools (anything else is refused):"]
    if "read" in tools:
        lines.append("<<<TOOL read\nrelative/path.py\n>>>")
    if "grep" in tools:
        lines.append("<<<TOOL grep\nregex\n>>>")
    if "shell" in tools:
        lines.append("<<<TOOL shell\ngit diff\n>>>   (only: git status|diff, pytest, python -m pytest, python <file>.py)")
    if "pytest" in tools:
        lines.append("<<<TOOL pytest\n>>>   (runs `python -m pytest -q` in the repo)")
    if "edit" in tools:
        lines.append("Edits (the edit tool):\n" + EDIT_FORMAT)
        lines.append("After your last edit you MUST run the tests before finishing.")
    lines.append("When finished:\n<<<DONE\none-paragraph summary of what you did and the evidence\n>>>")
    return "\n".join(lines) + "\n"


def build_system(composed_system: str, plan: AgentPlan, repo: Path) -> str:
    parts = [composed_system, protocol(plan.tools),
             "<repo files>\n" + "\n".join(repo_file_list(repo)) + "\n</repo files>\n"]
    if plan.harness:
        parts.append("<skill id=\"verification-harness\" source=\"user-supplied, MIT\">\n" + harness_body()
                     + "\n</skill>\n")
    return "\n".join(parts)


def parse_action(text: str) -> tuple[str, str]:
    """-> (kind, arg): kind is a tool name, 'edit', 'done', or 'final' (no action)."""
    found = []
    for m in TOOL_BLOCK.finditer(text):
        found.append((m.start(), m.group(1), m.group(2).strip()))
    for rx in (REPLACE_BLOCK, FILE_BLOCK):
        m = rx.search(text)
        if m:
            found.append((m.start(), "edit", ""))
    m = DONE_BLOCK.search(text)
    if m:
        found.append((m.start(), "done", m.group(1).strip()))
    if not found:
        return "final", text.strip()
    _, kind, arg = min(found, key=lambda f: f[0])
    return kind, arg


def tamper_flags(repo: Path, originals: dict) -> list[str]:
    """Line-level guard against bending the tests or silencing checks (docs/AGENT.md, gate rule 4)."""
    flags = []
    for rel, orig in originals.items():
        p = repo / rel
        new = p.read_text() if p.is_file() else None
        is_test = bool(TEST_PATH.search(rel))
        if is_test and orig is not None and new is None:
            flags.append(f"{rel}: test file deleted")
            continue
        if new is None:
            continue
        if is_test and orig is not None:
            new_lines = {l.strip() for l in new.splitlines()}
            gone = [l.strip() for l in orig.splitlines() if TEST_LINE.match(l) and l.strip() not in new_lines]
            if gone:
                flags.append(f"{rel}: changed or removed test line: {gone[0][:80]}")
        before = orig or ""
        if is_test and len(SKIP_MARKERS.findall(new)) > len(SKIP_MARKERS.findall(before)):
            flags.append(f"{rel}: added skip/xfail/.only")
        if len(SUPPRESSIONS.findall(new)) > len(SUPPRESSIONS.findall(before)):
            flags.append(f"{rel}: added a check suppression (type: ignore / noqa / except: pass)")
    return flags


def _passed(output: str) -> int:
    m = re.search(r"(\d+) passed", output)
    return int(m.group(1)) if m else 0


@dataclass
class LoopResult:
    tool_calls: list = field(default_factory=list)
    calls: list = field(default_factory=list)
    step_lines: list = field(default_factory=list)
    final_text: str = ""
    stop_reason: str = ""
    verification: dict = field(default_factory=dict)


def run_agent(prompt: str, repo: Path, plan: AgentPlan, providers: Callable, system: str, budget: int,
              history: Optional[list] = None, tier: str = "") -> LoopResult:
    res = LoopResult()
    baseline = None
    if plan.harness:
        code, _ = tool_pytest(repo)
        baseline = {"cmd": PYTEST_CMD, "exit": code}
    messages = list(history or []) + [{"role": "user", "content": prompt}]
    originals: dict = {}
    last_edit = None
    tests: list[dict] = []
    failing_after_edit = 0
    nudged = False
    last_text = ""
    step = 0
    while step < plan.max_steps:
        step += 1
        try:
            prov = providers(f"agent_{step}", plan.model_id)
        except FileNotFoundError:
            res.stop_reason = "script ended"
            break
        c = prov.complete(plan.model_id, system, messages, budget)
        res.calls.append(_call(f"agent_{step}", tier, c))
        last_text = c.text
        messages.append({"role": "assistant", "content": c.text})
        kind, arg = parse_action(c.text)
        entry = {"step": step, "tool": kind, "arg": arg if kind not in ("done", "final") else "", "ok": True}
        result = ""
        if kind in ("done", "final"):
            res.tool_calls.append(entry)
            res.step_lines.append(f"[step {step}] {kind}")
            post_edit_test = last_edit is not None and any(t["step"] > last_edit for t in tests)
            if last_edit is not None and not post_edit_test and not nudged and step < plan.max_steps:
                nudged = True
                messages.append({"role": "user", "content": NUDGE})
                res.step_lines.append("  verification gate: no test run after last edit -> nudge")
                continue
            res.final_text = arg
            res.stop_reason = "done"
            break
        if kind != "edit" and kind not in plan.tools or kind == "edit" and "edit" not in plan.tools:
            entry.update(ok=False, error=f"tool not allowed for this task: {kind}")
            result = f"TOOL ERROR ({kind}): not allowed for this task; allowed: {', '.join(plan.tools)}"
        else:
            try:
                if kind == "read":
                    result = f"TOOL RESULT (read {arg}):\n" + tool_read(repo, arg)
                elif kind == "grep":
                    result = f"TOOL RESULT (grep {arg}):\n" + tool_grep(repo, arg)
                elif kind == "edit":
                    edits = parse_edits(c.text, repo)
                    _snapshot(repo, edits, originals)
                    apply_edits(repo, edits)
                    last_edit = step
                    entry["arg"] = ", ".join(e for e, _ in edits)
                    result = f"TOOL RESULT (edit): wrote {entry['arg'] or 'nothing'}"
                else:  # shell / pytest
                    if kind == "pytest":
                        cmd, (code, out) = PYTEST_CMD, tool_pytest(repo)
                        entry["arg"] = cmd
                    else:
                        import shlex
                        cmd = arg
                        code, out = tool_shell(repo, arg)
                        if not is_test_command(shlex.split(arg)):
                            cmd = None
                    entry["exit"] = code
                    result = f"TOOL RESULT ({kind}): exit {code}\n{out}"
                    if cmd is not None:
                        tests.append({"step": step, "cmd": cmd, "exit": code, "passed": _passed(out)})
                        if last_edit is not None and code != 0:
                            failing_after_edit += 1
            except (ToolError, UnsafeEdit) as e:
                entry.update(ok=False, error=str(e))
                result = f"TOOL ERROR ({kind}): {e}"
        res.tool_calls.append(entry)
        status = (f"ERROR: {entry['error']}" if not entry["ok"]
                  else f"exit {entry['exit']}" if "exit" in entry else "ok")
        res.step_lines.append(f"[step {step}] {kind} {entry['arg']} -> {status}".replace("  ", " "))
        messages.append({"role": "user", "content": redact(result)[:RESULT_CAP]})
        if failing_after_edit > REPAIR_CAP:
            res.stop_reason = f"repair cap ({REPAIR_CAP}) exceeded"
            break
    else:
        res.stop_reason = "max_steps"
    if not res.final_text:
        res.final_text = re.sub(r"<<<.*?(>>>|<<<END)", "", last_text, flags=re.DOTALL).strip() or "(no final text)"
    res.verification = verify(repo, originals, last_edit, tests, plan.harness, baseline, res.stop_reason, nudged)
    return res


def verify(repo: Path, originals: dict, last_edit: Optional[int], tests: list, harness: bool,
           baseline: Optional[dict], stop_reason: str, nudged: bool) -> dict:
    after = [t for t in tests if last_edit is None or t["step"] > last_edit]
    latest = after[-1] if after else None
    flags = tamper_flags(repo, originals)
    v = {"status": "PASS", "checks": [{"cmd": latest["cmd"], "exit": latest["exit"]}] if latest else [],
         "reason": "", "tamper": flags, "baseline": baseline, "nudged": nudged, "stop_reason": stop_reason}
    if last_edit is None and not harness:
        v["status"], v["reason"] = "n/a (no edits)", ""
    elif flags:
        v["status"], v["reason"] = "NOT VERIFIED", "test tampering: " + "; ".join(flags)
    elif latest is None:
        v["status"] = "NOT VERIFIED"
        v["reason"] = "tests not run after last edit" if last_edit is not None else "no tests run"
    elif latest["exit"] != 0 or latest["passed"] == 0:
        v["status"] = "NOT VERIFIED"
        v["reason"] = (f"tests failing (exit {latest['exit']})" if latest["exit"] != 0 else "0 tests passed")
    if stop_reason.startswith("repair cap") and v["status"] != "PASS":
        v["reason"] = f"{stop_reason}; {v['reason']}"
    return v


def verification_lines(v: dict) -> list[str]:
    if v["status"].startswith("n/a"):
        return [f"VERIFICATION: {v['status']}"]
    lines = [f"VERIFICATION: {v['status']}"]
    if v["checks"]:
        lines += [f"Checks: {c['cmd']} → exit {c['exit']}" for c in v["checks"]]
    else:
        lines.append("Checks: none run after last edit")
    if v.get("baseline"):
        lines.append(f"Baseline (before loop): {v['baseline']['cmd']} → exit {v['baseline']['exit']}")
    if v["status"] != "PASS":
        lines.append(f"Reason: {v['reason']}")
    return lines

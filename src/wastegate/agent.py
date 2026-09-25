"""Agent tool loop (one action per model reply) + verification gate enforced in code.

The model never gets to declare success: VERIFICATION is computed here from a test run that happened
after the last edit (docs/AGENT.md).
"""
from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .agent_tools import PYTEST_CMD, ToolError, is_test_command, tool_grep, tool_pytest, tool_read, tool_shell
from .log import redact
from .providers.http import ProviderHTTPError
from .pipeline import (CONTEXT_SKIP_DIRS, CONTEXT_SKIP_NAMES, EDIT_FORMAT, FILE_BLOCK, REPLACE_BLOCK, TEST_PATH,
                       UnsafeEdit, _call, _snapshot, apply_edits, parse_edits)
from .skills.registry import builtin_root
from .systemone.agent_gate import AgentPlan, load_harness  # noqa: F401  (re-exported)

REPAIR_CAP = 5
MAX_RECOVERIES = 2  # Groq tool_use_failed 400s turned back into actions per loop
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
    text = (builtin_root() / "verification-harness" / "SKILL.md").read_text(encoding="utf-8")
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


MAX_SYSTEM_BYTES = 12_000
CODE_GATE_NOTE = ("Verification gate (enforced by the harness, not by you):\n"
                  "- After your last edit, run the tests (<<<TOOL pytest>>>) before finishing.\n"
                  "- Never delete, skip, xfail or weaken a test, or change an expected value; never add noqa/type: ignore.\n"
                  "- The harness prints VERIFICATION: PASS | NOT VERIFIED from its own test runs.\n")


def build_system(composed_system: str, plan: AgentPlan, repo: Path, max_system_bytes: int = MAX_SYSTEM_BYTES) -> str:
    """Full harness skill only if the whole system prompt fits max_system_bytes; else a short code-gate note.
    The code gate (verify()) is identical either way. Sets plan.harness_mode = full | code-only | off."""
    parts = [composed_system, protocol(plan.tools),
             "<repo files>\n" + "\n".join(repo_file_list(repo)) + "\n</repo files>\n"]
    base = "\n".join(parts)
    if not plan.harness:
        plan.harness_mode = "off"
        return base
    full = base + "\n<skill id=\"verification-harness\" source=\"user-supplied, MIT\">\n" + harness_body() + "\n</skill>\n"
    if len(full.encode("utf-8")) <= max_system_bytes:
        plan.harness_mode = "full"
        return full
    plan.harness_mode = "code-only"
    return base + "\n" + CODE_GATE_NOTE


TOOL_LINE = re.compile(r"^[ \t]*TOOL[ \t]+(read|grep|edit|pytest|shell)\b[ \t]*(.*)$", re.MULTILINE)
FENCE_LINE = re.compile(r"^[ \t]*```[\w+-]*[ \t]*$\n?", re.MULTILINE)


def parse_action(text: str) -> tuple[str, str]:
    """-> (kind, arg): kind is a tool name, 'edit', 'done', or 'final' (no action).
    Accepts <<<TOOL name\\narg\\n>>> and single-line `TOOL name arg`; retries with markdown fences removed."""
    kind, arg = _parse_action(text)
    if kind == "final" and "```" in text:
        k2, a2 = _parse_action(FENCE_LINE.sub("", text))
        if k2 != "final":
            return k2, a2
    return kind, arg


def _parse_action(text: str) -> tuple[str, str]:
    found = []
    for m in TOOL_BLOCK.finditer(text):
        found.append((m.start(), m.group(1), m.group(2).strip()))
    for m in TOOL_LINE.finditer(text):
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
        new = p.read_text(encoding="utf-8") if p.is_file() else None
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


def _fn(name: str, desc: str, props: dict, required: list) -> dict:
    return {"type": "function", "function": {"name": name, "description": desc, "parameters":
            {"type": "object", "properties": props, "required": required}}}


_S = {"type": "string"}
TOOL_SCHEMAS = {
    "read": _fn("read", "Read a text file in the repo (8 KB cap).", {"path": {**_S, "description": "relative path"}},
                ["path"]),
    "grep": _fn("grep", "Regex search over the repo (50 hits max).",
                {"pattern": {**_S, "description": "Python regex"},
                 "path": {**_S, "description": "optional relative file or directory to scope the search"}},
                ["pattern"]),
    "edit": _fn("edit", "Apply one <<<REPLACE path/<<<WITH/<<<END or <<<FILE path/>>> block (format in the system prompt).",
                {"text": {**_S, "description": "the full REPLACE or FILE block"}}, ["text"]),
    "pytest": _fn("pytest", "Run `python -m pytest -q` in the repo.", {}, []),
    "shell": _fn("shell", "Allowlisted command only: git status|diff, pytest, python -m pytest, python <file>.py.",
                 {"cmd": _S}, ["cmd"]),
}
GREP_ALIASES = {"search", "find", "rg", "ripgrep", "grep_search", "search_files", "code_search", "search_code"}


def openai_tools(tools: tuple[str, ...]) -> list[dict]:
    """OpenAI/Groq `tools=` specs for the plan's tools, in fixed order. Only our five names; nothing invented."""
    return [TOOL_SCHEMAS[t] for t in TOOL_SCHEMAS if t in tools]


def native_action(name: str, arguments) -> tuple[str, str, Optional[str]]:
    """Native tool call -> (kind, arg, error). Strips namespaces (repo_browser.grep -> grep), maps grep-like names
    to grep; anything else -> error 'unknown tool'. For edit, arg is the REPLACE/FILE block text."""
    base = re.split(r"[./]", (name or "").strip().lower())[-1]
    kind = "grep" if base in GREP_ALIASES else base
    if kind not in TOOL_SCHEMAS:
        return name, "", f"unknown tool: {name}; use one of {', '.join(TOOL_SCHEMAS)}"
    try:
        a = arguments if isinstance(arguments, dict) else json.loads(arguments) if str(arguments).strip() else {}
        if not isinstance(a, dict):
            raise ValueError("arguments must be a JSON object")
    except ValueError as e:
        return kind, "", f"bad arguments for {kind}: {e}"
    if kind == "grep":
        pat, path = str(a.get("pattern") or a.get("query") or a.get("regex") or ""), str(a.get("path") or "")
        return kind, pat + (f"\n{path}" if path else ""), None
    if kind == "read":
        return kind, str(a.get("path") or a.get("file") or ""), None
    if kind == "shell":
        return kind, str(a.get("cmd") or a.get("command") or ""), None
    if kind == "edit":
        return kind, str(a.get("text") or ""), None
    return kind, "", None


def recover_failed_generation(e: ProviderHTTPError) -> Optional[tuple[str, object]]:
    """Groq 400 tool_use_failed carries the model's attempted call in error.failed_generation -> (name, args)."""
    err = (e.data or {}).get("error") if isinstance(e.data, dict) else None
    if not isinstance(err, dict) or err.get("code") != "tool_use_failed":
        return None
    try:
        g = json.loads(err.get("failed_generation") or "")
    except ValueError:
        return None
    if isinstance(g, list) and g:
        g = g[0]
    if not isinstance(g, dict) or not g.get("name"):
        return None
    return g["name"], g.get("arguments") or g.get("parameters") or {}


@dataclass
class LoopResult:
    tool_calls: list = field(default_factory=list)
    provider_error: Optional[dict] = None
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
    st = {"originals": {}, "last_edit": None, "tests": [], "failing_after_edit": 0}
    fn_tools = openai_tools(plan.tools)
    nudged = False
    last_text = ""
    recoveries = 0
    step = 0
    while step < plan.max_steps:
        step += 1
        try:
            prov = providers(f"agent_{step}", plan.model_id)
        except FileNotFoundError:
            res.stop_reason = "script ended"
            break
        native = bool(fn_tools) and getattr(prov, "supports_tools", False)
        try:
            c = (prov.complete(plan.model_id, system, messages, budget, tools=fn_tools) if native
                 else prov.complete(plan.model_id, system, messages, budget))
        except ProviderHTTPError as e:
            rec = recover_failed_generation(e) if recoveries < MAX_RECOVERIES else None
            if rec is None:
                res.provider_error = {"step": step, "status": e.status, "body": e.body}
                res.step_lines.append(f"[step {step}] provider error: HTTP {e.status}: {e.body}")
                res.stop_reason = "provider error"
                break
            # The model emitted a call the API rejected (e.g. invented repo_browser.grep). Run it via our
            # mapping and continue in the text protocol (no tool_call_id exists for a rejected generation).
            recoveries += 1
            kind, arg, err = native_action(*rec)
            messages.append({"role": "assistant", "content": f"TOOL {kind} {arg}".strip()})
            result = _execute(repo, plan, step, kind, arg, arg, err, "recovered", st, res)
            messages.append({"role": "user", "content": redact(result)[:RESULT_CAP]})
            if st["failing_after_edit"] > REPAIR_CAP:
                res.stop_reason = f"repair cap ({REPAIR_CAP}) exceeded"
                break
            continue
        res.calls.append(_call(f"agent_{step}", tier, c))
        last_text = c.text
        if c.tool_calls:  # native function call(s): execute the first, answer every tool_call_id
            first = c.tool_calls[0]
            messages.append({"role": "assistant", "content": c.text or None, "tool_calls": [
                {"id": t["id"], "type": "function", "function": {"name": t["name"], "arguments": t["arguments"]}}
                for t in c.tool_calls]})
            kind, arg, err = native_action(first["name"], first["arguments"])
            result = _execute(repo, plan, step, kind, arg, arg, err, "native", st, res)
            messages.append({"role": "tool", "tool_call_id": first["id"], "content": redact(result)[:RESULT_CAP]})
            for t in c.tool_calls[1:]:
                messages.append({"role": "tool", "tool_call_id": t["id"],
                                 "content": "TOOL ERROR: one action per message; not executed"})
        else:
            messages.append({"role": "assistant", "content": c.text})
            kind, arg = parse_action(c.text)
            if kind in ("done", "final"):
                res.tool_calls.append({"step": step, "tool": kind, "arg": "", "ok": True, "via": "text"})
                res.step_lines.append(f"[step {step}] {kind}")
                post_edit_test = st["last_edit"] is not None and any(t["step"] > st["last_edit"] for t in st["tests"])
                if st["last_edit"] is not None and not post_edit_test and not nudged and step < plan.max_steps:
                    nudged = True
                    messages.append({"role": "user", "content": NUDGE})
                    res.step_lines.append("  verification gate: no test run after last edit -> nudge")
                    continue
                res.final_text = arg
                res.stop_reason = "done"
                break
            result = _execute(repo, plan, step, kind, arg, c.text, None, "text", st, res)
            messages.append({"role": "user", "content": redact(result)[:RESULT_CAP]})
        if st["failing_after_edit"] > REPAIR_CAP:
            res.stop_reason = f"repair cap ({REPAIR_CAP}) exceeded"
            break
    else:
        res.stop_reason = "max_steps"
    if not res.final_text:
        res.final_text = re.sub(r"<<<.*?(>>>|<<<END)", "", last_text, flags=re.DOTALL).strip() or "(no final text)"
    res.verification = verify(repo, st["originals"], st["last_edit"], st["tests"], plan.harness, baseline,
                              res.stop_reason, nudged)
    return res


def _execute(repo: Path, plan: AgentPlan, step: int, kind: str, arg: str, edit_text: str, err: Optional[str],
             via: str, st: dict, res: LoopResult) -> str:
    """Run one action (text, native or recovered) through the same tools and bookkeeping. Returns the tool result."""
    entry = {"step": step, "tool": kind, "arg": arg, "ok": True, "via": via}
    result = ""
    if err:
        entry.update(ok=False, error=err)
        result = f"TOOL ERROR ({kind}): {err}"
    elif kind not in plan.tools:
        entry.update(ok=False, error=f"tool not allowed for this task: {kind}")
        result = f"TOOL ERROR ({kind}): not allowed for this task; allowed: {', '.join(plan.tools)}"
    else:
        try:
            if kind == "read":
                result = f"TOOL RESULT (read {arg}):\n" + tool_read(repo, arg)
            elif kind == "grep":
                result = f"TOOL RESULT (grep {arg}):\n" + tool_grep(repo, arg)
            elif kind == "edit":
                edits = parse_edits(edit_text, repo)
                _snapshot(repo, edits, st["originals"])
                apply_edits(repo, edits)
                st["last_edit"] = step
                entry["arg"] = ", ".join(e for e, _ in edits)
                result = f"TOOL RESULT (edit): wrote {entry['arg'] or 'nothing'}"
            else:  # shell / pytest
                if kind == "pytest":
                    cmd, (code, out) = PYTEST_CMD, tool_pytest(repo)
                    entry["arg"] = cmd
                else:
                    cmd = arg
                    code, out = tool_shell(repo, arg)
                    if not is_test_command(shlex.split(arg)):
                        cmd = None
                entry["exit"] = code
                result = f"TOOL RESULT ({kind}): exit {code}\n{out}"
                if cmd is not None:
                    st["tests"].append({"step": step, "cmd": cmd, "exit": code, "passed": _passed(out)})
                    if st["last_edit"] is not None and code != 0:
                        st["failing_after_edit"] += 1
        except (ToolError, UnsafeEdit, ValueError) as e:
            entry.update(ok=False, error=str(e))
            result = f"TOOL ERROR ({kind}): {e}"
    res.tool_calls.append(entry)
    status = (f"ERROR: {entry['error']}" if not entry["ok"]
              else f"exit {entry['exit']}" if "exit" in entry else "ok")
    tag = "" if via == "text" else f" ({via})"
    res.step_lines.append(f"[step {step}] {kind}{tag} {entry['arg']} -> {status}".replace("  ", " "))
    return result


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

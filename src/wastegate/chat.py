"""wg chat: one gate -> route -> compose -> driver pass per user line.
Edits in replies are applied only when a repo is given (same parser, guard, all-or-nothing)."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Mapping, Optional

from .catalog import Catalog
from .instincts import load_instincts
from .agent import build_system, run_agent, verification_lines
from .log import TurnLogger
from .systemone.agent_gate import agent_plan
from .pipeline import (ANY_EDIT, Plan, UnsafeEdit, _call, cap_text, _snapshot, _try_provider, apply_edits, driver_request,
                       followup_line, parse_edits, plan_turn, run_followup, run_tests, wants_test)
from .providers.base import Provider
from .router import RouterConfig
from .skills.registry import Skill
from .systemone.base import SystemOne

HISTORY = 10


def reply_lines(driver_text):
    """Driver reply first, before any gate/stats lines."""
    if driver_text is None:
        return ["driver reply: (no generation, dry-run)"]
    return ["--- driver reply ---", driver_text.rstrip("\n"), "--- end driver reply ---"]


class ChatSession:
    def __init__(self, s1: SystemOne, catalog: Catalog, cfg: RouterConfig, registry: Mapping[str, Skill],
                 providers: Optional[Callable[[str, Optional[str]], Provider]], repo: Optional[Path],
                 state_dir: Optional[Path], mode: str, agent: bool = False, max_steps: int = 8):
        self.s1, self.catalog, self.cfg, self.registry = s1, catalog, cfg, registry
        self.providers, self.repo, self.state_dir, self.mode = providers, repo, state_dir, mode
        self.agent, self.max_steps = agent and repo is not None, max_steps
        self.history: list[dict] = []
        self.last: Optional[Plan] = None
        self.n = 0

    def turn(self, text: str) -> list[str]:
        self.n += 1
        rows = load_instincts(self.state_dir) if self.state_dir else []
        plan = plan_turn(text, self.s1, self.catalog, self.cfg, self.registry, rows)
        self.last = plan
        if self.agent:
            return self._agent_turn(text, plan)
        lines = list(plan.transcript)
        rec = {**plan.record, "mode": f"chat-{self.mode}", "turn": self.n, "driver_text": None}
        if self.providers is None:
            lines = reply_lines(None) + lines + ["generation: (empty, dry-run)"]
        else:
            r = plan.route
            drv_p = self.providers("driver", r.driver.model)  # resolve before any write
            fu_p, why_fu = (_try_provider(self.providers, "driver_followup", r.driver.model) if self.repo
                            else (None, "no --repo"))
            system, user = driver_request(plan, text, self.repo)
            msgs = self.history[-HISTORY:] + [{"role": "user", "content": user}]
            c = drv_p.complete(r.driver.model, system, msgs, r.driver.budget_tokens)
            calls = [_call("driver", r.driver.tier, c)]
            rec["driver_text"] = cap_text(c.text)
            lines = reply_lines(cap_text(c.text, limit=None)) + lines
            self.history += [{"role": "user", "content": text}, {"role": "assistant", "content": c.text}]
            if ANY_EDIT.search(c.text) or (self.repo is not None and wants_test(text)):
                lines += self._edits(c.text, rec, text, calls, fu_p, why_fu, r, system,
                                     msgs + [{"role": "assistant", "content": c.text}])
            rec.update(calls=calls, provider=c.provider, model_id=c.model_id,
                       tokens_in=_sum(calls, "tokens_in"), tokens_out=_sum(calls, "tokens_out"), usd=None)
        if self.state_dir:
            TurnLogger(self.state_dir / "logs").write(rec)
        return lines

    def _agent_turn(self, text: str, plan: Plan) -> list[str]:
        ap = agent_plan(text, self.s1, self.catalog, self.cfg, max_steps=self.max_steps, gate=plan.gate)
        picks = (f"agent: model={ap.model_id} tools={','.join(ap.tools)} max_steps={ap.max_steps} "
                 f"harness={'on' if ap.harness else 'off'} tool_loop={ap.answers['tool_loop']['value']:.2f}")
        rec = {**plan.record, "mode": f"chat-agent-{self.mode}", "turn": self.n, "driver_text": None,
               "agent": {"model_id": ap.model_id, "tools": list(ap.tools), "max_steps": ap.max_steps,
                         "harness": ap.harness, "answers": ap.answers}}
        if self.providers is None:
            lines = reply_lines(None) + list(plan.transcript) + [picks, "generation: (empty, dry-run)"]
        else:
            system = build_system(plan.composed.system, ap, self.repo)
            res = run_agent(text, self.repo, ap, self.providers, system, plan.route.driver.budget_tokens,
                            history=self.history[-HISTORY:], tier=plan.route.driver.tier)
            lines = (res.step_lines + reply_lines(cap_text(res.final_text, limit=None)) + list(plan.transcript)
                     + [picks] + verification_lines(res.verification))
            rec.update(tool_calls=res.tool_calls, calls=res.calls, verification=res.verification,
                       stop_reason=res.stop_reason, driver_text=cap_text(res.final_text),
                       provider=res.calls[0]["provider"] if res.calls else None, model_id=ap.model_id,
                       tokens_in=_sum(res.calls, "tokens_in"), tokens_out=_sum(res.calls, "tokens_out"), usd=None)
            self.history += [{"role": "user", "content": text}, {"role": "assistant", "content": res.final_text}]
        if self.state_dir:
            TurnLogger(self.state_dir / "logs").write(rec)
        return lines

    def _edits(self, text: str, rec: dict, prompt: str, calls: list, fu_p, why_fu: str, r, system: str,
               msgs: list[dict]) -> list[str]:
        if self.repo is None:
            rec["edits"] = []
            return ["edits not applied (no --repo)"]
        try:
            edits = parse_edits(text, self.repo)
        except UnsafeEdit as e:
            rec["edits_error"] = str(e)
            return [f"edits rejected, nothing written: {e}"]
        originals: dict = {}
        before = run_tests(self.repo)
        _snapshot(self.repo, edits, originals)
        apply_edits(self.repo, edits)
        touched = [e for e, _ in edits]
        after = run_tests(self.repo)
        out = [f"edits: {', '.join(touched) or '(none)'}", f"tests: before={before} after={after}"]
        followup, fcall, after = run_followup(prompt, touched, before, after, fu_p, why_fu, r.driver.model,
                                              r.driver.tier, r.driver.budget_tokens, system, msgs, self.repo,
                                              originals)
        if fcall is not None:
            calls.append(fcall)
            self.history += [{"role": "user", "content": "(follow-up) add or update a test file"},
                             {"role": "assistant", "content": f"(applied edits: {', '.join(followup['edits']) or 'none'})"}]
        if followup["ran"]:
            out.append(followup_line(followup, after))
        rec.update(edits=touched, tests={"before": before, "after": after}, followup=followup)
        return out


def _sum(calls: list[dict], key: str):
    vals = [c[key] for c in calls]
    return sum(vals) if vals and all(v is not None for v in vals) else None

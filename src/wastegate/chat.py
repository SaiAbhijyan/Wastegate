"""wg chat: one gate -> route -> compose -> driver pass per user line.
Edits in replies are applied only when a repo is given (same parser, guard, all-or-nothing)."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Mapping, Optional

from .catalog import Catalog
from .instincts import load_instincts
from .log import TurnLogger
from .pipeline import (ANY_EDIT, Plan, UnsafeEdit, _call, apply_edits, driver_request, parse_edits,
                       plan_turn, run_tests)
from .providers.base import Provider
from .router import RouterConfig
from .skills.registry import Skill
from .systemone.base import SystemOne

HISTORY = 10


class ChatSession:
    def __init__(self, s1: SystemOne, catalog: Catalog, cfg: RouterConfig, registry: Mapping[str, Skill],
                 providers: Optional[Callable[[str, Optional[str]], Provider]], repo: Optional[Path],
                 state_dir: Optional[Path], mode: str):
        self.s1, self.catalog, self.cfg, self.registry = s1, catalog, cfg, registry
        self.providers, self.repo, self.state_dir, self.mode = providers, repo, state_dir, mode
        self.history: list[dict] = []
        self.last: Optional[Plan] = None
        self.n = 0

    def turn(self, text: str) -> list[str]:
        self.n += 1
        rows = load_instincts(self.state_dir) if self.state_dir else []
        plan = plan_turn(text, self.s1, self.catalog, self.cfg, self.registry, rows)
        self.last = plan
        lines = list(plan.transcript)
        rec = {**plan.record, "mode": f"chat-{self.mode}", "turn": self.n}
        if self.providers is None:
            lines.append("generation: (empty, dry-run)")
        else:
            r = plan.route
            drv_p = self.providers("driver", r.driver.model)  # resolve before any write
            system, user = driver_request(plan, text, self.repo)
            c = drv_p.complete(r.driver.model, system, self.history[-HISTORY:] + [{"role": "user", "content": user}],
                               r.driver.budget_tokens)
            call = _call("driver", r.driver.tier, c)
            rec.update(calls=[call], provider=c.provider, model_id=c.model_id,
                       tokens_in=call["tokens_in"], tokens_out=call["tokens_out"], usd=None)
            lines.append(c.text)
            if ANY_EDIT.search(c.text):
                lines += self._edits(c.text, rec)
            self.history += [{"role": "user", "content": text}, {"role": "assistant", "content": c.text}]
        if self.state_dir:
            TurnLogger(self.state_dir / "logs").write(rec)
        return lines

    def _edits(self, text: str, rec: dict) -> list[str]:
        if self.repo is None:
            rec["edits"] = []
            return ["edits not applied (no --repo)"]
        try:
            edits = parse_edits(text, self.repo)
        except UnsafeEdit as e:
            rec["edits_error"] = str(e)
            return [f"edits rejected, nothing written: {e}"]
        before = run_tests(self.repo)
        apply_edits(self.repo, edits)
        after = run_tests(self.repo)
        rec.update(edits=[e for e, _ in edits], tests={"before": before, "after": after})
        return [f"edits: {', '.join(e for e, _ in edits)}", f"tests: before={before} after={after}"]

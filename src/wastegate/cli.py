"""wastegate / wg CLI."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import config as cfgmod
from .catalog import load_catalog
from .compose import compose
from .log import TurnLogger
from .router import route as do_route
from .skills.registry import load_builtin
from .systemone.base import GATE_QUESTIONS
from .systemone.heuristic import HeuristicSystemOne
from .systemone.jev import JevSystemOne
from .systemone.laya import LayaSystemOne

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Cheap-first, System-One gated CLI.")
skills_app = typer.Typer(no_args_is_help=True, help="Built-in and imported skills.")
eval_app = typer.Typer(no_args_is_help=True, help="Frozen eval suites.")
app.add_typer(skills_app, name="skills")
app.add_typer(eval_app, name="eval")
out = Console(highlight=False, soft_wrap=True)

LABELS = Path("evals/route_quality/labels.md")
BACKENDS = {"heuristic": HeuristicSystemOne, "laya": LayaSystemOne, "jev": JevSystemOne}


def _gate_and_route(prompt: str, backend: Optional[str]):
    cfg = cfgmod.load()
    name = backend or cfg.get("systemone", {}).get("backend", "heuristic")
    if name not in BACKENDS:
        out.print(f"unknown backend {name!r}")
        raise typer.Exit(2)
    t0 = time.perf_counter()
    try:
        gate = BACKENDS[name]().decide(prompt, GATE_QUESTIONS)
    except NotImplementedError as e:
        out.print(f"{name}: {e}")
        raise typer.Exit(2)
    ms = round((time.perf_counter() - t0) * 1000, 2)
    return name, gate, do_route(gate, load_catalog(), cfgmod.router_config(cfg)), ms


def _gate_dict(gate) -> dict:
    return {k: {"value": a.value, "distribution": dict(a.distribution), "confidence": a.confidence}
            for k, a in gate.items()}


@app.command()
def route(prompt: str, backend: Optional[str] = typer.Option(None, help="heuristic|laya|jev"),
          as_json: bool = typer.Option(False, "--json"), log: bool = typer.Option(True, "--log/--no-log")):
    """Show System One answers + expert mix. No LLM call."""
    name, gate, r, ms = _gate_and_route(prompt, backend)
    payload = {"backend": name, "gate": _gate_dict(gate), "route": r.to_dict()}
    if log:
        TurnLogger(Path(".wastegate/logs")).write({"prompt": prompt, "latency_ms_gate": ms, **payload})
    if as_json:
        out.print_json(json.dumps(payload))
        return
    t = Table(title=f"gate ({name}; confidences uncalibrated)")
    for c in ("question", "value", "conf", "top-3"):
        t.add_column(c)
    for k, a in gate.items():
        top = sorted(a.distribution.items(), key=lambda kv: -kv[1])[:3]
        v = f"{a.value:.2f}" if isinstance(a.value, float) else a.value
        t.add_row(k, v, f"{a.confidence:.2f}", "  ".join(f"{o}={p:.2f}" for o, p in top))
    out.print(t)
    out.print(f"driver: {r.driver.tier} {r.driver.model} budget={r.driver.budget_tokens}")
    for s in r.specialists:
        out.print(f"  + {s.role}: {s.tier} {s.model}")
    out.print(f"skills: {', '.join(r.skills)}")
    if r.clarify_first:
        out.print("clarify first: yes")
    for why in r.reasons:
        out.print(f"  - {why}")


@app.command()
def prompt(text: str, backend: Optional[str] = typer.Option(None)):
    """Print the composed system prefix + user turn."""
    _, _, r, _ = _gate_and_route(text, backend)
    c = compose(r, text, load_builtin())
    out.print("=== system ===")
    out.print(c.system, markup=False)
    out.print("=== user ===")
    out.print(c.user, markup=False)
    if c.dropped:
        out.print(f"(dropped: {', '.join(c.dropped)})")


@app.command()
def init():
    """Write ~/.wastegate/config.toml if absent."""
    p = cfgmod.home() / "config.toml"
    if p.exists():
        out.print(f"exists: {p}")
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(cfgmod.DEFAULT_TOML)
    out.print(f"wrote {p}")


@app.command()
def models():
    """Model catalog by tier."""
    t = Table()
    for c in ("tier", "id", "provider", "status", "source"):
        t.add_column(c)
    for m in load_catalog().models:
        t.add_row(m.tier, m.id, m.provider, "verified" if m.verified else "unverified", m.source)
    out.print(t)


@skills_app.command("ls")
def skills_ls():
    t = Table()
    for c in ("id", "text", "license", "quarantined", "description"):
        t.add_column(c)
    for s in load_builtin().values():
        t.add_row(s.id, s.provenance.get("text", "?"), str(s.provenance.get("license")),
                  str(s.quarantined), s.description)
    out.print(t)


@skills_app.command("show")
def skills_show(skill_id: str):
    reg = load_builtin()
    if skill_id not in reg:
        out.print(f"unknown skill {skill_id!r}")
        raise typer.Exit(1)
    s = reg[skill_id]
    out.print(f"id: {s.id}\nsha256: {s.sha256}\nprovenance: {s.provenance}\nquarantined: {s.quarantined}\n")
    out.print(s.body, markup=False)


@eval_app.command("run")
def eval_run(suite: str = typer.Option(..., "--suite"), dry_run: bool = typer.Option(False, "--dry-run")):
    """Session 1: dry-print the frozen label file only. Scoring is Phase 3."""
    if suite != "route_quality":
        out.print(f"suite {suite!r}: not implemented (Phase 3)")
        raise typer.Exit(2)
    if not dry_run:
        out.print("scoring not implemented (Phase 3); use --dry-run to print frozen labels")
        raise typer.Exit(2)
    raw = LABELS.read_bytes() if LABELS.exists() else (Path(__file__).parents[2] / LABELS).read_bytes()
    out.print(f"sha256: {hashlib.sha256(raw).hexdigest()}")
    out.print(raw.decode(), markup=False)


def _stub(phase: str):
    out.print(f"not implemented ({phase})")
    raise typer.Exit(2)


@app.command()
def ask(text: str):
    """One-shot routed task (Phase 2)."""
    _stub("Phase 2")


@app.command()
def chat():
    """Multi-turn (Phase 2)."""
    _stub("Phase 2")


@app.command()
def review(verdict: str, note: Optional[str] = typer.Option(None)):
    """Human review of last turn (Phase 4)."""
    _stub("Phase 4")


@app.command()
def evolve(dry_run: bool = typer.Option(False, "--dry-run"), apply: bool = typer.Option(False, "--apply")):
    """Guided skill/router evolution (Phase 5)."""
    _stub("Phase 5")


@app.command()
def report():
    """Tokens, $, win-rate, ECE (Phase 3)."""
    _stub("Phase 3")

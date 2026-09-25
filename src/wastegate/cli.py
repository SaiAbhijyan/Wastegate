"""wastegate / wg CLI."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import time
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import config as cfgmod
from .catalog import load_catalog, mock_catalog
from .compose import compose
from .instincts import add_instinct, load_instincts, select_instincts
from .chat import ChatSession
from .log import TurnLogger, redact
from .pipeline import RepoError, UnsafeEdit, run_ask, validate_repo
from .providers.base import LiveDisabled
from .providers.live import live_catalog, live_providers
from .smoke import write_smoke_report
from .labels import load_pool
from .systemone.base import GATE_QUESTIONS as _GQ
from .providers.mock import mock_providers
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
label_app = typer.Typer(no_args_is_help=True, help="Human labeling (no model predictions shown).")
app.add_typer(eval_app, name="eval")
app.add_typer(label_app, name="label")
out = Console(highlight=False, soft_wrap=True)

LABELS = Path("evals/route_quality/labels.md")
STATE = Path(".wastegate")
BACKENDS = {"heuristic": HeuristicSystemOne, "laya": LayaSystemOne, "jev": JevSystemOne}


def cloud_catalog():
    """Catalog for non-live views (route/prompt/dry-run): local Ollama rows only appear with --live --local."""
    c = load_catalog()
    return c.for_providers({m.provider for m in c.models} - {"ollama"})


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
        out.print(f"{name}: {e}", markup=False)
        raise typer.Exit(2)
    ms = round((time.perf_counter() - t0) * 1000, 2)
    return name, gate, do_route(gate, cloud_catalog(), cfgmod.router_config(cfg)), ms


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
    _, gate, r, _ = _gate_and_route(text, backend)
    c = compose(r, text, load_builtin(),
                instincts=select_instincts(load_instincts(STATE), str(gate["kind"].value)))
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
        out.print(f"exists: {p} (no API key needed)")
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(cfgmod.DEFAULT_TOML)
    out.print(f"wrote {p} (no API key needed; keys are read from env vars only, see docs/KEYS.md)")


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


def pytest_available() -> bool:
    """Repo tests run as `python -m pytest` with this interpreter; it must be importable here."""
    return importlib.util.find_spec("pytest") is not None


def _check_repo(repo: Optional[Path]) -> None:
    if repo is None:
        return
    try:
        validate_repo(repo)
    except RepoError as e:
        out.print(str(e), markup=False)
        raise typer.Exit(2)


def _check_pytest(mode: str) -> None:
    if mode in ("mock", "live") and not pytest_available():
        out.print("pytest is not installed in this Python environment (wg runs your repo's tests with it).\n"
                  "Install it with: pip install pytest   (or: pip install -e \".[dev]\" in the Wastegate checkout)",
                  markup=False)
        raise typer.Exit(2)


def _resolve_mode(dry_run: bool, mock: bool, live: bool, local: bool, allow_paid: bool,
                  replies: Optional[Path]):
    """-> (mode, catalog, providers). Exits 2 on bad combos or when live has nothing usable."""
    modes = [m for m, on in (("dry-run", dry_run), ("mock", mock), ("live", live)) if on]
    if len(modes) > 1:
        out.print("choose one of --dry-run / --mock / --live")
        raise typer.Exit(2)
    if not modes:
        out.print("live not enabled (no-flag generation not implemented); use --dry-run, --mock or --live")
        raise typer.Exit(2)
    mode = modes[0]
    if local and mode != "live":
        out.print("--local needs --live")
        raise typer.Exit(2)
    if mode == "mock" and replies is None:
        out.print("--mock needs --replies DIR")
        raise typer.Exit(2)
    try:
        catalog = {"mock": mock_catalog, "dry-run": cloud_catalog,
                   "live": lambda: live_catalog(load_catalog(), allow_paid=allow_paid, local=local)}[mode]()
    except LiveDisabled as e:
        out.print(f"live: {e}", markup=False)
        raise typer.Exit(2)
    providers = {"dry-run": None, "mock": mock_providers(replies) if replies else None,
                 "live": live_providers(catalog, allow_network=True, allow_paid=allow_paid)}[mode]
    return mode, catalog, providers


@app.command()
def ask(text: str,
        dry_run: bool = typer.Option(False, "--dry-run", help="route + compose, no generation"),
        mock: bool = typer.Option(False, "--mock", help="scripted replies, no network"),
        live: bool = typer.Option(False, "--live", help="allow network; needs the provider key in env"),
        allow_paid: bool = typer.Option(False, "--allow-paid", help="with --live: allow paid keys/models (or ALLOW_PAID=1)"),
        local: bool = typer.Option(False, "--local", help="with --live: use local Ollama only (no key)"),
        replies: Optional[Path] = typer.Option(None, help="dir with <role>.md replies (with --mock)"),
        repo: Path = typer.Option(Path("."), help="repo the driver edits and tests run in")):
    """One-shot routed task: --dry-run, --mock, or --live (exactly one)."""
    _check_repo(repo)
    mode, catalog, providers = _resolve_mode(dry_run, mock, live, local, allow_paid, replies)
    _check_pytest(mode)
    cfg = cfgmod.load()
    name = cfg.get("systemone", {}).get("backend", "heuristic")
    try:
        res = run_ask(text, repo, BACKENDS[name](), catalog, cfgmod.router_config(cfg), load_builtin(),
                      mode=mode, providers=providers, instincts=load_instincts(STATE))
    except (NotImplementedError, LiveDisabled) as e:
        out.print(f"{mode}: {e}", markup=False)
        raise typer.Exit(2)
    except (UnsafeEdit, FileNotFoundError) as e:
        out.print(f"aborted, no edits written: {e}", markup=False)
        raise typer.Exit(1)
    except urllib.error.URLError as e:  # live only; may fire after edits were applied
        out.print(f"provider error (edits may already be applied in {repo}): {redact(str(e))}", markup=False)
        raise typer.Exit(1)
    TurnLogger(Path(".wastegate/logs")).write(res.record)
    for line in res.transcript:
        out.print(redact(line), markup=False)  # model-written findings may echo secrets
    if mode == "live":
        p = write_smoke_report(res.record, Path("results"), datetime.now(timezone.utc).strftime("%Y%m%d"))
        out.print(f"smoke report: {p}")


app.command("run", help="Alias of `wg ask` (same flags): one-shot routed task. "
                         "--dry-run, --mock or --live, exactly one.")(ask)


@app.command()
def chat(dry_run: bool = typer.Option(False, "--dry-run", help="route + compose each turn, no generation"),
         mock: bool = typer.Option(False, "--mock", help="scripted driver reply each turn, no network"),
         live: bool = typer.Option(False, "--live", help="allow network; needs the provider key in env"),
         allow_paid: bool = typer.Option(False, "--allow-paid", help="with --live: allow paid keys/models"),
         local: bool = typer.Option(False, "--local", help="with --live: use local Ollama only"),
         replies: Optional[Path] = typer.Option(None, help="dir with driver.md (with --mock)"),
         repo: Optional[Path] = typer.Option(None, help="apply edits here (without it, edits are shown, not written)")):
    """Multi-turn REPL. Each line: gate -> route -> compose -> driver. /route /skills /exit."""
    _check_repo(repo)
    mode, catalog, providers = _resolve_mode(dry_run, mock, live, local, allow_paid, replies)
    if repo is not None:
        _check_pytest(mode)
    cfg = cfgmod.load()
    name = cfg.get("systemone", {}).get("backend", "heuristic")
    sess = ChatSession(BACKENDS[name](), catalog, cfgmod.router_config(cfg), load_builtin(),
                       providers, repo, STATE, mode)
    out.print(f"wastegate chat ({mode}{', repo ' + str(repo) if repo else ', no repo: edits not applied'}). "
              "Commands: /route /skills /exit")
    while True:
        try:
            line = input("wg> ").strip()
        except EOFError:
            break
        if not line:
            continue
        if line in ("/exit", "/quit"):
            break
        if line == "/route":
            if sess.last is None:
                out.print("no turn yet")
            else:
                r = sess.last.route
                out.print(f"driver: {r.driver.tier} {r.driver.model}", markup=False)
                for s in r.specialists:
                    out.print(f"  + {s.role}: {s.tier} {s.model}", markup=False)
            continue
        if line == "/skills":
            if sess.last is None:
                out.print("no turn yet")
            else:
                c = sess.last.composed
                out.print(f"skills: {', '.join(c.included)}; instincts: {len(c.instincts)}", markup=False)
            continue
        if line.startswith("/"):
            out.print("commands: /route /skills /exit")
            continue
        try:
            lines = sess.turn(line)
        except (LiveDisabled, NotImplementedError, FileNotFoundError) as e:
            out.print(f"{mode}: {redact(str(e))}", markup=False)
            continue
        except urllib.error.URLError as e:
            out.print(f"provider error: {redact(str(e))}", markup=False)
            continue
        for l in lines:
            out.print(redact(l), markup=False)


@app.command(context_settings={"ignore_unknown_options": True})
def review(verdict_arg: Optional[str] = typer.Argument(None, metavar="VERDICT", help="+1 or -1"),
           verdict: Optional[str] = typer.Option(None, "--verdict", help="+1 or -1"),
           note: Optional[str] = typer.Option(None, "--note")):
    """Attach +1/-1 (and a note) to the last logged turn. -1 with --note saves an instinct."""
    given = [v for v in (verdict_arg, verdict) if v is not None]
    if len(given) != 1 or given[0] not in ("+1", "-1"):
        out.print("give exactly one verdict: +1 or -1 (positional or --verdict)")
        raise typer.Exit(2)
    try:
        rec = TurnLogger(Path(".wastegate/logs")).set_last_review(
            {"verdict": given[0], "note": note, "ts": datetime.now(timezone.utc).isoformat()})
    except FileNotFoundError as e:
        out.print(str(e))
        raise typer.Exit(1)
    out.print(f"review {given[0]} attached to last turn")
    if given[0] == "-1" and note:
        kind = ((rec.get("gate") or {}).get("kind") or {}).get("value")
        add_instinct(STATE, note, kind, rec.get("turn_id"))
        out.print(f"instinct saved ({kind or 'any'} tasks): injected into up to 3 relevant future turns")


@app.command()
def evolve(dry_run: bool = typer.Option(False, "--dry-run"), apply: bool = typer.Option(False, "--apply")):
    """Guided skill/router evolution (Phase 5)."""
    _stub("Phase 5")


@app.command()
def report():
    """Tokens, $, win-rate, ECE (Phase 3)."""
    _stub("Phase 3")


@label_app.command("new")
def label_new(out_path: Path = typer.Option(..., "--out", help="append-only JSONL, e.g. evals/route_quality/human.jsonl"),
              pool: Path = typer.Option(Path("evals/route_quality/pool.md"), "--pool"),
              labeler: str = typer.Option(..., "--labeler", help="who is labeling")):
    """Show one unlabeled pool prompt at a time; record the human's `kind`. Never shows a prediction."""
    rows = load_pool(pool)
    pool_sha = hashlib.sha256(pool.read_bytes()).hexdigest()
    done = set()
    if out_path.exists():
        done = {json.loads(l)["id"] for l in out_path.read_text().splitlines() if l.strip()}
    todo = [r for r in rows if r.id not in done]
    kinds = _GQ["kind"].options
    out.print(f"{len(todo)} unlabeled of {len(rows)}. Rubric: evals/route_quality/labels.md (kind). "
              f"Answer one of: {', '.join(kinds)}; s=skip, q=quit.")
    read = typer.confirm("Have you read src/wastegate/systemone/heuristic.py?", default=False)
    for i, r in enumerate(todo):
        out.print(f"\n{r.id} ({len(todo) - i} left): {r.prompt}", markup=False)
        while True:
            ans = typer.prompt("kind").strip().lower()
            if ans in kinds or ans in ("s", "q"):
                break
            out.print(f"not a kind: {ans!r}")
        if ans == "q":
            break
        if ans == "s":
            continue
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("a") as f:
            f.write(json.dumps({"id": r.id, "prompt": r.prompt, "kind": ans, "labeler": labeler,
                                "read_heuristic": read, "pool_sha256": pool_sha,
                                "rubric": "labels.md kind v1",
                                "ts": datetime.now(timezone.utc).isoformat()}) + "\n")

# CLAUDE.md — Wastegate

Wastegate: cheap-first coding/research CLI (`wastegate` / `wg`). System One gate (Jev / Laya;
heuristic only for offline CI) picks model tier + skills + roles. Full spec: **docs/MISSION.md**
(read the "Session-1 scope amendments" at its end). Contract: docs/SPEC.md, docs/RESEARCH.md,
docs/EVAL_PROTOCOL.md.

## Truth rules (non-negotiable)
- Vendor numbers are hypotheses. Never present Jev/Laya/OpenAI/Anthropic benches as ours.
- No quality claim without a pre-registered eval in `evals/` + raw results in `results/`.
- Tokens and $ come from provider responses only. Never estimate from word count.
- Never invent model IDs, prices, papers, star counts. Unverified → say "unverified".
- Never edit frozen labels after seeing scores. If a label changes, say so in the commit message.
- No calibration claim without reliability diagram + ECE on our labels.

## Working style
- Tests/evals first, then code. Surgical diffs. YAGNI. Terse narration; exact identifiers.
- Respect phase gates in MISSION.md. Stubs exit non-zero; never print fake output.
- Secrets (`TYPESAFE_API_KEY`, `JEV_API_KEY`, provider keys) never reach logs or stdout.
- Imported SKILL.md = untrusted prose: provenance + scan + quarantine by default.
- The evolver must never modify `evals/`, `results/`, or the rollback path.

## Commands
```bash
pip install -e '.[dev]'
pytest -q
wg route "fix the race in worker.py"
wg prompt "fix the race in worker.py"
wg skills ls
```

## Layout
`src/wastegate/` (systemone/, router.py, catalog.py, skills/, compose.py, log.py, cli.py),
`tests/`, `evals/`, `results/`, `docs/`.

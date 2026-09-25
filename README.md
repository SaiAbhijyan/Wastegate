# Wastegate

Cheap until it isn't. A System-One gated coding CLI: cheap models first, Fable/Astra only when the gate opens. Skills, MoE-style routing (role × skill × model tier), measured token spend.

## Quickstart (no keys needed)

```bash
pip install -e '.[dev]'
wg route "fix the deadlock in worker.py"          # gate + expert mix, no LLM
wg prompt "fix the deadlock in worker.py"         # composed system prompt (skills + instincts)
wg ask --dry-run "fix the bug in tiny_pkg"        # route + compose, no generation
wg ask --mock --replies tests/fixtures/replies/fix_add --repo <copy of tests/fixtures/tiny_pkg> "fix the bug"
wg chat --dry-run                                 # REPL: /route /skills /exit
wg review -1 --note "prefer stdlib"               # saves an instinct, injected into later turns
wg skills ls; wg models
```

With a free key in env (`GROQ_API_KEY`, `GEMINI_API_KEY` or `OPENROUTER_API_KEY`, see docs/KEYS.md):
`wg ask --live --repo <dir> "…"` and `wg chat --live --repo <dir>`. For local Ollama (no key): `--live --local`.
Paid providers are ignored unless you pass `--allow-paid`.

Edits from the model use `<<<REPLACE path / <<<WITH / <<<END` or `<<<FILE path … >>>`. They are applied only inside `--repo`, and nothing is written unless every edit resolves.

Status: Phase 2 (routing, skills, instincts v0, ask/chat with dry-run, mock and live). See docs/MISSION.md and docs/PHASE2.md.

## Honest limits

Copied from docs/EVAL_PROTOCOL.md.

- No quality comparison to Fable 5.1 or Astra exists.
- No token or $ savings have been measured. Provider adapters are wired. Two live wiring and contract checks were run (Groq, N=1 each, `results/20260925-live-smoke*.md`). Neither added the requested regression test. They are not quality or cost results.
- The offline heuristic gate is a keyword scorer for CI. Its confidences are not calibrated.
- Laya and Jev adapters are request/response shapes only. Live calls are disabled. The Jev wire format is unverified against Jev.
- Built-in skills are our paraphrases of upstream packs. Upstream licenses and SHAs are not yet verified.
- The route labels so far were written by the model, not a human.
